#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proxy-service-probe 命令行入口:
对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登、过盾、流媒体、断流测速、打标命名及配置渲染）。
"""
import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from core.parsers import load_proxies
from core.mihomo_runner import find_mihomo_bin, node_listeners
from core.egress_geo import probe_egress, probe_google_region, query_ip_info, country_name_zh, flag_emoji
from core.ai_probe import probe_all_ai
from core.media_probe import probe_all_media
from core.shield_probe import probe_sites_http, probe_sites_browser, shield_passed
from core.youtube_probe import probe_youtube
from core.speed_probe import measure_speed_and_stall
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
    parser.add_argument("--iface", help="绑定物理网卡名称 (如 WLAN, 以太网)，防止被本地 TUN (如 Karing) 接管")
    parser.add_argument("--direct-proxy", help="跑机自身基线出口探测的直连监听代理 (如 http://127.0.0.1:24999)")
    parser.add_argument("--mihomo", help="显式指定 Mihomo 可执行文件路径")
    parser.add_argument("--batch-size", type=int, default=10, help="单批次启动的临时监听节点数量 (默认: 10)")
    parser.add_argument("--workers", type=int, default=4, help="并发测试线程数 (默认: 4)")
    parser.add_argument("--dry-run", action="store_true", help="干跑测试: 仅解析节点与模版，不发起真实网络连接")
    return parser.parse_args(argv)


def is_landing_node(proxy):
    name = (proxy.get("name") or "").lower()
    p_type = (proxy.get("type") or "").lower()
    return bool(proxy.get("_is_landing") or "_lnd" in name or "_usai" in name
                or p_type in ("http", "socks", "socks5") or proxy.get("dialer-proxy"))


def print_summary_table(results):
    print("\n" + "=" * 110)
    print(f"{'序号':<4} | {'最终命名':<30} | {'真实出口IP':<15} | {'信誉分':<6} | {'AI全通':<6} | {'免盾':<6} | {'YT免登':<6} | {'流媒体':<8} | {'带宽':<10}")
    print("-" * 110)
    for idx, r in enumerate(results, 1):
        name = r.get("final_name", r["proxy"].get("name", "unk"))
        if len(name) > 28:
            name = name[:26] + ".."
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

        speed = f"{r.get('speed_kbs', 0)}KB/s"
        print(f"{idx:<4} | {name:<30} | {ip:<15} | {score:<6} | {ai:<6} | {shield:<6} | {yt:<6} | {media:<8} | {speed:<10}")
    print("=" * 110 + "\n")


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
        print("[Dry-run] 干跑模式: 跳过网络检测，直接执行命名与模版渲染...")
        mock_results = []
        for p in proxies:
            mock_results.append({
                "proxy": p,
                "cc": "US",
                "is_landing": is_landing_node(p),
                "ai_supported": True,
                "youtube_passed": False,
                "shield_passed": False,
                "is_key": False,
                "is_fast": False,
                "media_details": {"nf": True, "dp": True}
            })
        tag_and_rename_nodes(mock_results)
        print_summary_table(mock_results)
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
    test_speed = do_all or "speed" in req_tests
    browser_shield = test_shield and not args.no_browser

    print(f"[2/5] 确定测试维度:")
    print(f"      IP属地: {'✓' if test_ip else '✗'} | AI解锁: {'✓' if test_ai else '✗'} | 流媒体: {'✓' if test_media else '✗'}")
    print(f"      断流测速: {'✓' if test_speed else '✗'} | 免盾复核: {'✓' if test_shield else '✗'} (浏览器:{'✓' if browser_shield else '✗'}) | YT免登实播: {'✓' if test_yt else '✗'}")

    # 跑机自身出口基线探测 (防 TUN 污染)
    baseline_proxies = {"http": args.direct_proxy, "https": args.direct_proxy} if args.direct_proxy else None
    print(f"[3/5] 探测本地跑机公网基线出口...")
    baseline = probe_egress(baseline_proxies)
    runner_ips = set(baseline["observed_ips"])
    print(f"      跑机基线出口 IP: {list(runner_ips) or '未检测到(建议提供 --direct-proxy)'}")

    # 分批启动监听与测试
    results = []
    eliminated = []
    total = len(proxies)
    batch_size = max(1, args.batch_size)

    print(f"[4/5] 启动分批服务测试 (共 {total} 个节点，每批 {batch_size} 个)...")

    for batch_idx in range(0, total, batch_size):
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
                        "is_landing": is_landing_node(proxy),
                        "eliminated_reason": None
                    }

                    # 1. 真实出口探测
                    egress = probe_egress(node_proxies)
                    exit_ip = egress["ipv4"]["ip"] or egress["ipv6"]["ip"]
                    row["exit_ip"] = exit_ip
                    row["egress"] = egress

                    # 出口重合/代理失效判定
                    if exit_ip and exit_ip in runner_ips:
                        row["eliminated_reason"] = "出口与本机直连重合(代理失效或TUN未避让)"
                        return row

                    # 2. 3 秒流式下载带宽与断流检测
                    if test_speed:
                        sp_res = measure_speed_and_stall(node_proxies)
                        row.update(sp_res)
                        if sp_res.get("eliminated_reason"):
                            row["eliminated_reason"] = sp_res["eliminated_reason"]
                            return row
                    else:
                        row["speed_kbs"] = 0

                    # 3. Google 自身地区判定 (最高优先级)
                    g_region = probe_google_region(node_proxies)
                    row["google_region"] = g_region

                    # 4. 多源 GeoIP 与信誉查询
                    info = query_ip_info(exit_ip)
                    row["ip_info"] = info

                    # 归属国家判定: Google 优先，多源 GeoIP 为辅
                    cc = g_region.get("country_code") or info.get("country_code") or "UNK"
                    row["cc"] = cc

                    # 5. AI 解锁测试
                    if test_ai:
                        ai_res = probe_all_ai(node_proxies, google_region_info=g_region)
                        row["ai_supported"] = ai_res["ai_supported"]
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

                    # 判断角色
                    row["is_key"] = bool(not row["is_landing"] and row.get("speed_kbs", 0) >= 128 and not g_region.get("is_sent_to_china"))
                    row["is_fast"] = bool(row.get("speed_kbs", 0) >= 500)

                    return row

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for tested in pool.map(test_node, targets):
                        if tested.get("eliminated_reason"):
                            eliminated.append(tested)
                            print(f"      [淘汰] {tested['proxy'].get('name')}: {tested['eliminated_reason']}")
                        else:
                            results.append(tested)
                            print(f"      [合格] {flag_emoji(tested.get('cc'))} {country_name_zh(tested.get('cc'))} | IP: {tested.get('exit_ip')} | AI: {'✓' if tested.get('ai_supported') else '✗'} | YT: {'✓' if tested.get('youtube_passed') else '✗'} | 盾: {'✓' if tested.get('shield_passed') else '✗'}")

        except Exception as e:
            print(f"      批次运行异常: {e}")

    # 规范打标与排序
    print("\n[5/5] 执行规范化打标、命名与配置渲染...")
    if not results:
        print("警告: 本轮所有节点均未通过服务测试或已被淘汰。")
        sys.exit(1)

    tag_and_rename_nodes(results)
    print_summary_table(results)

    # 导出报告
    if args.report:
        report_data = {
            "timestamp": time.time(),
            "total_candidates": total,
            "qualified_count": len(results),
            "eliminated_count": len(eliminated),
            "results": [
                {
                    "final_name": r.get("final_name"),
                    "cc": r.get("cc"),
                    "exit_ip": r.get("exit_ip"),
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

    # 导出 Clash 配置
    if args.output:
        out_file = export_clash_yaml([r["proxy"] for r in results], args.output, template_path=args.template)
        print(f"      已成功导出 Clash 配置文件: {out_file}")

    elapsed = round(time.time() - start_time, 1)
    print(f"\n全部处理完毕，耗时 {elapsed} 秒，合格节点: {len(results)}/{total}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
