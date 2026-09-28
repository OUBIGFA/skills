#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Gist 订阅搜索与节点提取命令行工具 (gist_search.py)
用于主动按需从 GitHub Gist 检索最新有效代理订阅源并提取节点。
采用方案 B (GitHub Fastly CDN Raw 直链免控拉取)，零风控、免 Token 频率限制，
默认抓取 20 条最新有效目标，并严格过滤单源超过 200 节点的公开垃圾源。

使用示例:
  # 1. 默认使用推荐主力语法搜索并提取节点保存至 gist_proxies.yaml (默认抓取 20 条最新有效 Gist)
  python scripts/gist_search.py --output gist_proxies.yaml

  # 2. 使用订阅直链金矿预设 (subs / singbox / hy2 / base64 / comprehensive)
  python scripts/gist_search.py --preset subs --output subs_nodes.yaml
  python scripts/gist_search.py --preset hy2 --output hy2_nodes.yaml

  # 3. 使用自定义 Gist 搜索语法
  python scripts/gist_search.py --query 'filename:yaml "vless" proxies' -o custom.yaml

  # 4. 仅测试检索目标 Gist (不下载解析节点)
  python scripts/gist_search.py --dry-run-targets

  # 5. 指定代理客户端与自定义配置文件
  python scripts/gist_search.py --proxy http://127.0.0.1:3067 --config gist_config.json

  # 6. 抓取后直接交由 probe_services.py 执行全套服务能力检测与测速
  python scripts/gist_search.py --probe --output final_nodes.yaml

  # 7. 抓取、测试并直接合流并入现有目标底库配置
  python scripts/gist_search.py --probe --merge-into base_template.yaml
"""
import argparse
from collections import Counter
import io
import json
import os
import subprocess
import sys
import time

import yaml

# 确保脚本所在目录及父目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.gist import (
    DEFAULT_GIST_PRESET,
    DEFAULT_TARGETS,
    DEFAULT_MAX_AGE_HOURS,
    DEFAULT_MAX_NODES_PER_SUB,
    PRESET_GIST_QUERIES,
    extract_raw_urls_from_gist,
    fetch_gist_nodes,
    get_default_gist_config_path,
    load_gist_config,
    resolve_gist_query,
    search_gist_targets,
)

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="GitHub Gist 代理订阅搜索与节点提取工具 (主动按需执行，方案B Fastly CDN 免控拉取)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", "-o", default="gist_proxies.yaml",
                        help="输出节点文件路径 (默认: gist_proxies.yaml)")
    parser.add_argument("--preset", "-p", choices=list(PRESET_GIST_QUERIES.keys()), default=DEFAULT_GIST_PRESET,
                        help="预设查询语法: residential (官方优先主力: 家宽/双ISP/优质过盾), recommended (双源Clash+直链), subs (商用机场直连直链), clash, singbox, hy2, base64, comprehensive")
    parser.add_argument("--query", "-q", default=None,
                        help="自定义 Gist 查询语法 (若指定将覆盖 --preset)")
    parser.add_argument("--config", "-c", default=None,
                        help=f"配置文件路径 (默认引用技能主目录下: {os.path.basename(get_default_gist_config_path())})")
    parser.add_argument("--max-targets", "--limit", type=int, default=DEFAULT_TARGETS,
                        help=f"最多抓取的有效 Gist 数量 (默认: {DEFAULT_TARGETS} 条最新有效目标)")
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS,
                        help=f"时效过滤上限小时数 (默认: {DEFAULT_MAX_AGE_HOURS} 小时内更新的目标)")
    parser.add_argument("--max-nodes-per-sub", type=int, default=DEFAULT_MAX_NODES_PER_SUB,
                        help=f"单订阅源节点数量上限 (默认: {DEFAULT_MAX_NODES_PER_SUB})，超过此上限的聚合源将被丢弃以防垃圾节点干扰")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP 超时秒数 (默认使用配置文件中的值)")
    parser.add_argument("--proxy", default=None, help="本地 HTTP/SOCKS 代理地址 (如 http://127.0.0.1:3067)")
    parser.add_argument("--dry-run-targets", action="store_true",
                        help="仅搜索并展示目标 Gist 地址与发现的文件，不下载与解析节点")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出节点 (默认 YAML)")
    parser.add_argument("--probe", action="store_true",
                        help="抓取完成后直接调用 probe_services.py 对节点进行全量服务能力测试与渲染")
    parser.add_argument("--merge-into", default=None,
                        help="合流目标配置路径 (Clash YAML / sing-box JSON): 搜索/测试完成后直接并入目标订阅底库")
    parser.add_argument("--insert", dest="insert_mode", action="store_true",
                        help="合流时的中间插入模式: 打破原有编号完全重排序并从 1 重新编号 (默认优先保留目标底库原节点及原有编号)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    print("==================================================")
    print("   GitHub Gist 订阅搜索与节点提取引擎 (方案B 免控)")
    print("==================================================")

    cfg = load_gist_config(args.config)
    if args.proxy:
        cfg["proxy"] = args.proxy
    if args.timeout:
        cfg["timeout"] = args.timeout

    actual_query = resolve_gist_query(args.query or args.preset, cfg.get("default_query"))
    query_str = " + ".join(str(q) for q in actual_query) if isinstance(actual_query, list) else str(actual_query)
    print(f"[*] 选用搜索预设/语法: {args.preset} -> {query_str}")
    print(f"[*] 时效性窗口限制: 最近 {args.max_age_hours} 小时内更新")
    print(f"[*] 目标抓取配额: 最多 {args.max_targets} 条最新有效 Gist")
    print(f"[*] 单源节点熔断上限: {args.max_nodes_per_sub} 个节点")
    if cfg.get("proxy"):
        print(f"[*] 请求代理: {cfg['proxy']}")

    print(f"\n[1/3] 正在通过 GitHub Gist Web 端检索最新有效代码片段...")
    start_time = time.time()
    targets, stats = search_gist_targets(
        query=actual_query,
        config=cfg,
        max_targets=args.max_targets,
        max_age_hours=args.max_age_hours
    )
    elapsed = time.time() - start_time
    print(f"      检索完成 (耗时 {elapsed:.2f}s)，检索 {stats['pages_searched']} 页，发现 {len(targets)} 个时效达标的独立 Gist")

    if not targets:
        print("[!] 未检索到有效 Gist 目标。建议检查查询语法或放宽时效窗口。")
        return 1

    if args.dry_run_targets:
        print("\n[+] 发现的目标 Gist 列表:")
        for idx, t in enumerate(targets, 1):
            time_str = t.get("updated_at") or "未知"
            files_hint = ", ".join(t.get("snippet_files", [])) or "检测中"
            print(f"  [{idx:2d}] {t['gist_url']} (更新于: {time_str}, 文件: {files_hint})")
        return 0

    print(f"\n[2/3] 正在通过方案 B (Fastly CDN Raw 直链) 并发免控抓取与解析节点...")
    proxies = fetch_gist_nodes(
        targets,
        config=cfg,
        max_nodes_per_sub=args.max_nodes_per_sub
    )
    print(f"      抓取完成，共提取到 {len(proxies)} 个独立有效代理节点 (已去重与按协议排序)")

    if not proxies:
        print("[!] 未能从目标 Gist 提取到可用节点 (可能由于订阅过期或包含超量公开源被丢弃)。")
        return 1

    # 统计协议类型构成
    counts = Counter(p.get("type", "unknown") for p in proxies)
    print("\n[+] 协议构成统计:")
    for proto, cnt in counts.most_common():
        print(f"    - {proto.upper():12s}: {cnt} 个")

    print(f"\n[3/3] 正在保存节点数据至: {args.output}")
    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if args.json or args.output.endswith(".json"):
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"proxies": proxies}, f, ensure_ascii=False, indent=2)
    else:
        # 兼容 Clash YAML 规范
        yaml_content = yaml.safe_dump({"proxies": proxies}, allow_unicode=True, sort_keys=False)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(yaml_content)

    print(f"[✓] 成功导出 {len(proxies)} 个节点到: {args.output}")

    # 若指定了 --probe，自动调用 probe_services.py 进行全套能力测试
    if args.probe:
        print("\n[*] 自动触发服务能力测试流水线 (probe_services.py)...")
        probe_script = os.path.join(CURRENT_DIR, "probe_services.py")
        probe_cmd = [sys.executable, probe_script, "--input", args.output]
        if args.merge_into:
            probe_cmd += ["--merge-into", args.merge_into]
        if args.insert_mode:
            probe_cmd += ["--insert"]
        print(f"    执行命令: {' '.join(probe_cmd)}")
        return subprocess.call(probe_cmd)

    # 未开启 --probe 但指定了 --merge-into 时，将原始提取去重节点直接并入目标配置
    if args.merge_into:
        from core.merger import merge_into_target_file
        print(f"\n[*] 正在将抓取提取的 {len(proxies)} 个节点直接合流并入目标底库: {args.merge_into}...")
        try:
            dest, m_stats = merge_into_target_file(
                target_path=args.merge_into,
                new_nodes_or_file=proxies,
                insert_mode=args.insert_mode
            )
            mode_str = "【中间插入模式 (完全重排重编号)】" if args.insert_mode else "【默认合流模式 (优先保留底库原节点及编号，新节点补空号)】"
            print(f"      合流模式: {mode_str}")
            print(f"      底库原节点: {m_stats['base_count']} 个，新增: {m_stats['added_count']} 个，去重跳过: {m_stats['skipped_count']} 个，合并后总节点数: {m_stats['total_count']} 个")
            backup_msg = f" (原文件已备份: {os.path.basename(m_stats['backup_path'])})" if m_stats.get('backup_path') else ""
            print(f"      [✓] 目标底库已成功更新: {dest}{backup_msg}")
        except Exception as err:
            print(f"      [!] 合流并入底库失败: {err}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
