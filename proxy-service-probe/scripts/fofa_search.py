#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FoFa 订阅搜索与节点提取命令行工具 (fofa_search.py)
用于主动按需通过 FoFa 空间测绘引擎检索网络上高活性代理订阅源并提取节点。

使用示例:
  # 1. 默认使用推荐主力语法搜索并提取节点保存至 fofa_proxies.yaml
  python scripts/fofa_search.py --output fofa_proxies.yaml

  # 2. 使用特定预设语法 (vless / hy2 / billing / comprehensive)
  python scripts/fofa_search.py --preset hy2 --output hy2_nodes.yaml

  # 3. 使用自定义 FoFa 查询语法
  python scripts/fofa_search.py --query 'body="type: hysteria2" && status_code="200" && body!="<html"' -o custom.yaml

  # 4. 仅测试检索订阅源目标地址 (不下载解析节点)
  python scripts/fofa_search.py --dry-run-targets

  # 5. 指定代理客户端与自定义配置文件
  python scripts/fofa_search.py --proxy http://127.0.0.1:3067 --config fofa_config.json

  # 6. 抓取后直接交由 probe_services.py 执行全套服务能力检测与测速
  python scripts/fofa_search.py --probe --output final_nodes.yaml
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

from core.fofa import (
    DEFAULT_PRESET,
    PRESET_QUERIES,
    fetch_subscription_nodes,
    get_default_config_path,
    load_fofa_config,
    resolve_query,
    search_all_targets,
    search_fofa_targets,
)

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="FoFa / 360 Quake 订阅搜索与节点提取工具 (主动按需执行)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", "-o", default="fofa_proxies.yaml",
                        help="输出节点文件路径 (默认: fofa_proxies.yaml)")
    parser.add_argument("--engine", "-e", choices=["all", "fofa", "quake"], default="all",
                        help="测绘引擎: all (FoFa + 360 Quake 双引擎协同检索), fofa, quake (默认: all)")
    parser.add_argument("--preset", "-p", choices=list(PRESET_QUERIES.keys()), default=DEFAULT_PRESET,
                        help="预设查询语法: recommended (推荐主力), billing (动态计费), vless, hy2, sub_userinfo, comprehensive")
    parser.add_argument("--query", "-q", default=None,
                        help="自定义 FoFa 查询语法 (若指定将覆盖 --preset)")
    parser.add_argument("--quake-query", default=None,
                        help="自定义 360 Quake 查询语法 (若未指定则自动按 preset 匹配对应语法)")
    parser.add_argument("--config", "-c", default=None,
                        help=f"配置文件路径 (默认引用技能主目录下: {os.path.basename(get_default_config_path())})")
    parser.add_argument("--page", type=int, default=1, help="搜索页码 (默认: 1)")
    parser.add_argument("--page-size", "--size", type=int, default=80, help="单页结果条数 (默认: 80)")
    parser.add_argument("--max-targets", type=int, default=None, help="最多抓取的订阅源数量 (默认全量抓取)")
    parser.add_argument("--max-nodes-per-sub", type=int, default=None,
                        help="单订阅源节点数量上限 (默认: 200)，超过此上限的聚合源将被丢弃以防垃圾节点干扰")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP 超时秒数 (默认使用配置文件中的值)")
    parser.add_argument("--proxy", default=None, help="本地 HTTP/SOCKS 代理地址 (如 http://127.0.0.1:3067)")
    parser.add_argument("--dry-run-targets", action="store_true",
                        help="仅搜索并展示目标订阅地址，不下载与解析节点")
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
    print("   FoFa & 360 Quake 空间测绘订阅主动搜索与提取流水线 ")
    print("==================================================")

    cfg = load_fofa_config(args.config)
    cfg_src = cfg.get("_config_source") or "默认设置/环境变量"
    print(f"[*] 配置文件引用: {cfg_src}")
    print(f"[*] 选用检索引擎: {args.engine.upper()} (容错协同，自动去重)")

    has_fofa = bool(cfg.get("token") or cfg.get("key"))
    has_quake = bool(cfg.get("quake_key"))

    if not has_fofa and not has_quake:
        print("[!] 错误: 未检测到有效的 FoFa Token/Key 或 Quake Key 配置。")
        print(f"    请检查 {get_default_config_path()} 中的 key / token 或 quake_key。")
        return 1

    if args.proxy:
        cfg["proxy"] = args.proxy
    if args.timeout:
        cfg["timeout"] = args.timeout

    actual_query = resolve_query(args.query or args.preset, cfg.get("default_query"))
    print(f"[*] 选用搜索预设/语法: {args.preset} -> {actual_query}")
    if cfg.get("proxy"):
        print(f"[*] 请求代理: {cfg['proxy']}")

    print(f"\n[1/3] 正在通过空间测绘引擎检索目标订阅源 (第 {args.page} 页, 最多 {args.page_size} 条)...")
    start_time = time.time()
    targets, stats = search_all_targets(
        query_or_preset=args.query or args.preset,
        config=cfg,
        engine=args.engine,
        page=args.page,
        page_size=args.page_size,
        quake_query=args.quake_query
    )
    elapsed = time.time() - start_time
    print(f"      检索完成 (耗时 {elapsed:.2f}s)，发现 {len(targets)} 个独立候选目标地址")

    if not targets:
        print("[!] 未检索到有效目标。建议检查查询语法或 Token 授权状态。")
        return 1

    if args.dry_run_targets:
        print("\n[+] 发现的目标订阅源地址列表:")
        for idx, t in enumerate(targets, 1):
            print(f"  [{idx:2d}] {t}")
        return 0

    print(f"\n[2/3] 正在遍历抓取并解析订阅源中的节点 (并发/串行超时: {cfg.get('timeout', 12)}s)...")
    proxies = fetch_subscription_nodes(
        targets,
        config=cfg,
        max_targets=args.max_targets,
        timeout=int(cfg.get("timeout") or 8),
        max_nodes_per_sub=args.max_nodes_per_sub
    )
    print(f"      抓取完成，共提取到 {len(proxies)} 个独立有效代理节点 (已去重)")

    if not proxies:
        print("[!] 未能从目标订阅源提取到可用节点 (可能由于临时不可达或需要特殊凭据)。")
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
