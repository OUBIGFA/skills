#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proxy-service-probe 命令行入口:
对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登、过盾、流媒体、打标命名及配置渲染）。
支持基于 curl 的 RateMeter 本地持续下载测速与 Key 优质前置跳板遴选（作为非主动技能，仅在显式指定时触发）。
具备端口黑名单避让与活跃物理网卡自动绑定机制，绝不破坏本地已有网络连接（完美适配 Karing / Sing-box / Mihomo / Xray）。
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from core.parsers import load_proxies
from core.mihomo_runner import find_mihomo_bin, node_listeners
from core.egress_geo import probe_egress, probe_geolocation, country_name_zh, flag_emoji
from core.ai_probe import probe_all_ai
from core.media_probe import probe_all_media
from core.shield_probe import probe_sites_http, probe_sites_browser, shield_passed
from core.youtube_probe import probe_youtube
from core.speed_probe import (
    DEFAULT_SUSTAINED_TARGETS,
    precheck_target,
    measure_download_sustained,
    speed_qualified,
    measure_speed_and_stall
)
from core.key_evaluator import select_key_nodes, is_landing_role
from core.tagger import tag_and_rename_nodes
from core.renderer import export_clash_yaml

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="代理节点服务能力测试与配置渲染工具 (proxy-service-probe)")
    parser.add_argument("--input", "-i", required=True, help="输入节点源: 本地文件路径(.yaml/.json/.txt)或远程订阅URL")
    parser.add_argument("--output", "-o", help="输出渲染后的 Clash/Mihomo YAML 配置文件路径")
    parser.add_argument("--report", "-r", help="保存测试详情的 JSON 报告文件路径")
    parser.add_argument("--template", "-t", help="自定义 Clash 母版模版路径 (默认使用内置 template.yaml)")
    parser.add_argument("--tests", default="all", help="指定测试维度: all, 或组合逗号分隔 ip,ai,youtube,shield,media,speed")
    parser.add_argument("--no-browser", action="store_true", help="轻量模式: 跳过 Playwright 浏览器实测 (跳过 YouTube 与浏览器免盾)")
    parser.add_argument("--iface", help="绑定物理网卡名称 (如 WLAN, 以太网)，防止被本地 TUN (如 Karing) 接管，不指定则自动探测")
    parser.add_argument("--direct-proxy", help="跑机自身基线出口探测的直连监听代理 (如 http://127.0.0.1:24999)")
    parser.add_argument("--mihomo", help="显式指定 Mihomo 可执行文件路径")
    parser.add_argument("--batch-size", type=int, default=10, help="单批次启动的临时监听节点数量 (默认: 10)")
    parser.add_argument("--workers", type=int, default=4, help="并发测试线程数 (默认: 4)")
    parser.add_argument("--dry-run", action="store_true", help="干跑测试: 仅解析节点与模版，不发起真实网络连接")
    parser.add_argument("--start-index", type=int, default=0, help="从指定节点序号 (0-based) 开始测试批次")
    parser.add_argument("--checkpoint", help="断点续测状态 JSON 文件路径")

    # 本地持续下载测速与 Key 遴选选项 (非主动技能: 默认不开启，仅在用户显式指定时触发)
    parser.add_argument("--speed-test", action="store_true", help="主动开启本地完整下载测速 (非主动技能，仅在显式要求时执行)")
    parser.add_argument("--rate-limit-mbps", type=float, default=10.0, help="测速带宽上限 (Mbps)，防止跑满本地网络导致卡顿 (默认: 10.0)")
    parser.add_argument("--speed-duration", type=float, default=5.0, help="单节点持续下载测速时长 (秒，默认: 5.0)")
    parser.add_argument("--min-speed-mbps", type=float, default=5.0, help="测速合格中位数速率门槛 (Mbps，默认: 5.0)")
    parser.add_argument("--speed-target", default=DEFAULT_SUSTAINED_TARGETS[0], help="持续测速目标 URL (默认: proof.ovh.us 100Mb)")

    return parser.parse_args(argv)


def print_summary_table(results, speed_tested=False):
    print("\n" + "=" * 115)
    speed_col_name = "带宽/中位数" if speed_tested else "带宽"
    print(f"{'序号':<4} | {'最终命名':<32} | {'出口IP':<15} | {'信誉':<5} | {'AI':<4} | {'免盾':<4} | {'YT':<4} | {'流媒体':<6} | {speed_col_name:<12} | {'角色'}")
    print("-" * 115)
    for idx, r in enumerate(results, 1):
        name = r.get("final_name", r["proxy"].get("name", "unk"))
        if len(name) > 30:
            name = name[:28] + ".."
        ip = r.get("exit_ip") or "未知"
        score = str((r.get("ip_info") or {}).get("score") or "-")
        ai = "✓" if r.get("ai_supported") else "✗"
        shield = "✓" if r.get("shield_passed") else "✗"
        yt = "✓" if r.get("youtube_passed") else "✗"

        media_str = []
        md = r.get("media_details") or {}
        if md.get("nf"):
            media_str.append("NF")
        if md.get("dp"):
            media_str.append("D+")
        media = "+".join(media_str) if media_str else "-"

        if speed_tested and r.get("speed_mbps") is not None:
            speed_text = f"{r['speed_mbps']:.1f} Mbps"
        elif r.get("speed_kbs"):
            speed_text = f"{r.get('speed_kbs')} KB/s"
        else:
            speed_text = "-"

        role = "Key跳板" if r.get("is_key") else ("Fast" if r.get("is_fast") else ("落地" if r.get("is_landing") else "直连"))
        print(f"{idx:<4} | {name:<32} | {ip:<15} | {score:<5} | {ai:<4} | {shield:<4} | {yt:<4} | {media:<6} | {speed_text:<12} | {role}")
    print("=" * 115 + "\n")


def main(argv=None):
    args = parse_args(argv)
    start_time = time.time()

    print("[1/5] 加载并解析输入节点...")
    proxies = load_proxies(args.input)
    if not proxies:
        print("错误: 未从输入源解析到有效代理节点。")
        sys.exit(1)
    print(f"      成功解析到 {len(proxies)} 个候选节点")

    if args.dry_run:
        print("[Dry-run] 干跑模式: 跳过真实网络连接，直接执行命名与模版渲染...")
        mock_results = []
        has_key = False
        for idx, p in enumerate(proxies):
            is_lnd = is_landing_role(p)
            is_key_node = bool(args.speed_test and not is_lnd and not has_key)
            if is_key_node:
                has_key = True
            is_fast_node = bool(args.speed_test and not is_key_node and idx < 3)
            mock_results.append({
                "proxy": p,
                "cc": "US" if idx % 2 == 0 else "JP",
                "is_landing": is_lnd,
                "ai_supported": True,
                "youtube_passed": not args.no_browser,
                "shield_passed": not args.no_browser,
                "is_key": is_key_node,
                "is_fast": is_fast_node,
                "key_score": 38.5 if is_key_node else 0.0,
                "speed_mbps": 12.5 if (is_key_node or is_fast_node) else 2.1,
                "media_details": {"nf": True, "dp": True}
            })
        tag_and_rename_nodes(mock_results)
        print_summary_table(mock_results, speed_tested=args.speed_test)
        if args.output:
            out_file = export_clash_yaml([r["proxy"] for r in mock_results], args.output, template_path=args.template)
            print(f"[完成] 已导出 Clash 配置文件: {out_file}")
        return 0

    # 检查内核
    mihomo_bin = find_mihomo_bin(args.mihomo)
    if not mihomo_bin:
        print("错误: 未检测到 Mihomo 内核。请确认系统 PATH 或 _temp/mihomo.exe 存在，或通过 --mihomo 指定。")
        sys.exit(1)
    print(f"      使用 Mihomo 内核: {mihomo_bin}")

    # 解析测试维度
    req_tests = set(t.strip().lower() for t in args.tests.split(","))
    do_all = "all" in req_tests
    test_ip = do_all or "ip" in req_tests
    test_ai = do_all or "ai" in req_tests
    test_yt = (do_all or "youtube" in req_tests) and not args.no_browser
    test_shield = (do_all or "shield" in req_tests)
    test_media = do_all or "media" in req_tests
    test_speed = do_all or "speed" in req_tests or args.speed_test
    browser_shield = test_shield and not args.no_browser

    print(f"[2/5] 确定测试维度:")
    print(f"      IP属地: {'✓' if test_ip else '✗'} | AI解锁: {'✓' if test_ai else '✗'} | 流媒体: {'✓' if test_media else '✗'}")
    print(f"      免盾复核: {'✓' if test_shield else '✗'} (浏览器:{'✓' if browser_shield else '✗'}) | YT免登实播: {'✓' if test_yt else '✗'}")
    if args.speed_test:
        print(f"      【测速模式】已主动激活完整下载测速 (限速: {args.rate_limit_mbps}Mbps, 窗口: {args.speed_duration}s, 阈值: {args.min_speed_mbps}Mbps, 激活Key筛选)")
    else:
        print(f"      【测速模式】未激活 (默认非主动: 执行 3秒/<16KB 防断流轻量快检)")

    # 跑机自身出口基线探测 (防 TUN 污染)
    baseline_proxies = {"http": args.direct_proxy, "https": args.direct_proxy} if args.direct_proxy else None
    print(f"[3/5] 探测本地跑机公网基线出口...")
    baseline = probe_egress(baseline_proxies)
    runner_ips = set(baseline["observed_ips"])
    print(f"      跑机基线出口 IP: {list(runner_ips) or '未检测到(建议提供 --direct-proxy 或由物理网卡直连)'}")

    # 分批启动监听与测试
    results = []
    eliminated = []
    total = len(proxies)
    batch_size = max(1, args.batch_size)

    if args.checkpoint and os.path.isfile(args.checkpoint):
        try:
            with open(args.checkpoint, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
                results = ckpt.get("results", [])
                eliminated = ckpt.get("eliminated", [])
                print(f"      [断点] 已从检查点载入历史结果: 合格 {len(results)} 个，淘汰 {len(eliminated)} 个")
        except Exception as e:
            print(f"      [警告] 读取检查点失败: {e}")

    print(f"[4/5] 启动分批服务测试 (共 {total} 个节点，每批 {batch_size} 个，起始序号: {args.start_index + 1})...")

    for batch_idx in range(args.start_index, total, batch_size):
        chunk = proxies[batch_idx:batch_idx + batch_size]
        print(f"      正在启动批次 {batch_idx + 1}~{min(batch_idx + batch_size, total)} 临时监听...")

        try:
            with node_listeners(chunk, iface=args.iface, mihomo_bin=mihomo_bin) as targets:
                def test_node(item):
                    port, proxy = item[0], item[1]
                    proxy_url = f"http://127.0.0.1:{port}"
                    node_proxies = {"http": proxy_url, "https": proxy_url}

                    row = {
                        "proxy": proxy,
                        "orig_name": proxy.get("name"),
                        "is_landing": is_landing_role(proxy),
                        "eliminated_reason": None,
                        "delay": 0.0
                    }

                    # 1. 真实出口探测
                    t0_conn = time.monotonic()
                    egress = probe_egress(node_proxies)
                    row["delay"] = round((time.monotonic() - t0_conn) * 1000, 1)
                    exit_ip = egress["ipv4"]["ip"] or egress["ipv6"]["ip"]
                    row["exit_ip"] = exit_ip
                    row["egress"] = egress

                    # 出口重合/代理失效判定
                    if not exit_ip:
                        row["eliminated_reason"] = "未验证到公网出口"
                        return row
                    if exit_ip and exit_ip in runner_ips:
                        row["eliminated_reason"] = "出口与本机直连重合(代理失效或TUN未避让)"
                        return row

                    # 2. 带宽测速与防断流
                    if args.speed_test:
                        # 2.1 主动完整测速模式: 目标快速轻量预检 (Range: 0-1023)
                        pre_err = precheck_target(args.speed_target, proxy_url, timeout=3.0)
                        if pre_err:
                            row["eliminated_reason"] = f"测速预检失败({pre_err.get('error')})"
                            return row

                        # 2.2 执行受限流的持续流式下载测速
                        shard_dir = tempfile.mkdtemp(prefix="speed_probe_shard_")
                        try:
                            measured = measure_download_sustained(
                                url=args.speed_target,
                                proxy_url=proxy_url,
                                work_dir=shard_dir,
                                duration_seconds=args.speed_duration,
                                warmup_seconds=1.0,
                                rate_limit_mbps=args.rate_limit_mbps
                            )
                            row["speed_result"] = measured
                            row["speed_mbps"] = measured.get("median_mbps") or 0.0
                            row["speed_kbs"] = round(row["speed_mbps"] * 1024 / 8, 1)
                            is_qualified = speed_qualified(measured, min_median_mbps=args.min_speed_mbps)
                            row["is_fast"] = is_qualified
                            if not measured.get("complete"):
                                row["eliminated_reason"] = f"测速未完成({measured.get('status')})"
                                return row
                        finally:
                            shutil.rmtree(shard_dir, ignore_errors=True)
                    elif test_speed:
                        # 2.3 默认轻量防断流快检 (3秒/<16KB)
                        sp_res = measure_speed_and_stall(node_proxies)
                        row.update(sp_res)
                        if sp_res.get("eliminated_reason"):
                            row["eliminated_reason"] = sp_res["eliminated_reason"]
                            return row
                        row["is_fast"] = bool(row.get("speed_kbs", 0) >= 500)
                    else:
                        row["speed_kbs"] = 0
                        row["is_fast"] = False

                    # 3/4. 共享属地证据链：显式 Google 地区、绑定出口的 GeoIP、前后出口复核
                    row.update(probe_geolocation(node_proxies, egress=egress))
                    g_region = row["google_region"]

                    # 5. AI 解锁测试
                    if test_ai:
                        ai_res = probe_all_ai(node_proxies, google_region_info=g_region)
                        row["ai_supported"] = bool(ai_res["ai_supported"] and row["geo_decision"]["egress_stable"]
                                                   and not row["geo_decision"]["is_pool"])
                        row["ai_details"] = ai_res["details"]
                        row["ai_observations"] = ai_res["observations"]
                    else:
                        row["ai_supported"] = False
                        row["ai_details"] = {}

                    # 6. 流媒体测试
                    if test_media:
                        media_res = probe_all_media(node_proxies)
                        row["media_supported"] = media_res["media_supported"]
                        row["media_details"] = media_res["details"]
                    else:
                        row["media_supported"] = False
                        row["media_details"] = {}

                    # 7. 免盾测试
                    if test_shield:
                        http_shield = probe_sites_http(node_proxies)
                        browser_res = probe_sites_browser(proxy_url) if browser_shield else {}
                        combined_shield = {k: browser_res.get(k) or v for k, v in http_shield.items()}
                        row["shield_passed"] = shield_passed(combined_shield)
                        row["shield_details"] = combined_shield
                    else:
                        row["shield_passed"] = False
                        row["shield_details"] = {}

                    # 8. YouTube 免登实播测试
                    if test_yt:
                        yt_res = probe_youtube(proxy_url, expected_ip=exit_ip)
                        row["youtube_passed"] = yt_res.get("status") == "passed"
                        row["youtube_details"] = yt_res
                    else:
                        row["youtube_passed"] = False
                        row["youtube_details"] = {}

                    return row

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for tested in pool.map(test_node, targets):
                        if tested.get("eliminated_reason"):
                            eliminated.append(tested)
                            print(f"      [淘汰] {tested['proxy'].get('name')}: {tested['eliminated_reason']}")
                        else:
                            results.append(tested)
                            speed_disp = f"{tested['speed_mbps']:.1f}Mbps" if args.speed_test else f"{tested.get('speed_kbs', 0)}KB/s"
                            print(f"      [合格] {flag_emoji(tested.get('cc'))} {country_name_zh(tested.get('cc'))} | IP: {tested.get('exit_ip')} | 带宽: {speed_disp} | AI: {'✓' if tested.get('ai_supported') else '✗'} | YT: {'✓' if tested.get('youtube_passed') else '✗'} | 盾: {'✓' if tested.get('shield_passed') else '✗'}")

        except Exception as e:
            print(f"      批次运行异常: {e}")

        if args.checkpoint:
            try:
                with open(args.checkpoint, "w", encoding="utf-8") as f:
                    json.dump({"batch_idx": batch_idx, "results": results, "eliminated": eliminated}, f, ensure_ascii=False)
            except Exception:
                pass

    # Key 优质前置节点评选 (仅在主动测速模式下激活)
    if args.speed_test and results:
        print("\n[4.5] 执行 Key 优质前置跳板节点评选与配额分配...")
        chosen_keys = select_key_nodes(results, max_keys=10, per_country_cap=3)
        print(f"      成功评选出 {len(chosen_keys)} 个 Key 优质前置跳板节点")

    # 规范打标与排序
    print("\n[5/5] 执行规范化打标、命名与配置渲染...")
    if not results:
        print("警告: 本轮所有节点均未通过服务测试或已被淘汰。")
        sys.exit(1)

    tag_and_rename_nodes(results)
    print_summary_table(results, speed_tested=args.speed_test)

    # 导出报告
    if args.report:
        report_data = {
            "timestamp": time.time(),
            "speed_test_enabled": args.speed_test,
            "total_candidates": total,
            "qualified_count": len(results),
            "eliminated_count": len(eliminated),
            "key_count": sum(1 for r in results if r.get("is_key")),
            "results": [
                {
                    "orig_name": r.get("orig_name"),
                    "final_name": r.get("final_name"),
                    "cc": r.get("cc"),
                    "google_region": r.get("google_region"),
                    "geo_decision": r.get("geo_decision"),
                    "egress": r.get("egress"),
                    "egress_after": r.get("egress_after"),
                    "ip_info_by_ip": r.get("ip_info_by_ip"),
                    "exit_ip": r.get("exit_ip"),
                    "is_key": r.get("is_key", False),
                    "is_fast": r.get("is_fast", False),
                    "key_score": r.get("key_score"),
                    "speed_mbps": r.get("speed_mbps"),
                    "speed_kbs": r.get("speed_kbs"),
                    "ai_supported": r.get("ai_supported"),
                    "ai_details": r.get("ai_details"),
                    "youtube_passed": r.get("youtube_passed"),
                    "shield_passed": r.get("shield_passed"),
                    "media_details": r.get("media_details"),
                    "ip_info": r.get("ip_info")
                } for r in results
            ],
            "eliminated": [
                {
                    "name": e["proxy"].get("name"),
                    "reason": e.get("eliminated_reason")
                } for e in eliminated
            ]
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"      已保存详细测试报告: {args.report}")

    # 导出 Clash 配置 (自动处理 Key 前置策略组与落地链式绑定)
    if args.output:
        out_file = export_clash_yaml([r["proxy"] for r in results], args.output, template_path=args.template)
        print(f"      已成功导出 Clash 配置文件: {out_file}")

    elapsed = round(time.time() - start_time, 1)
    print(f"\n全部处理完毕，耗时 {elapsed} 秒，合格节点: {len(results)}/{total} (其中 Key: {sum(1 for r in results if r.get('is_key'))} 个)。")
    return 0


if __name__ == "__main__":
    ret = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(ret if isinstance(ret, int) else 0)
