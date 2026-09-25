#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sing-box 订阅节点服务能力测试、智能打标与配置导出命令行工具 (probe_singbox.py，备用流水线)。
主流水线为 probe_services.py (mihomo 内核)；本流水线以 sing-box 内核测试，用于 sing-box 兼容性验证与导出 sing-box JSON。
直连测试后，直连不可达的节点经前置 (Key -> 备用前置 -> 本机客户端端口) 重测以区分落地节点。
"""
import sys
import os
import io
import json
import time
import re
import socket
import argparse
from contextlib import ExitStack
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

# 直连初筛整批兜底上限：仅防线程卡死；属地多源复核经慢链路可达 20 秒左右，各探测自身均有超时
BATCH_HARD_TIMEOUT = 120.0

# 全局底层套接字保护 (>=6.0s 杜绝多跳 TLS Reality 握手被掐断)
socket.setdefaulttimeout(6.0)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.singbox_runner import find_singbox_bin, clean_node_for_singbox, singbox_dual_listeners, singbox_active_listeners, export_singbox_json
from core.egress_geo import probe_egress, probe_geolocation, country_name_zh, flag_emoji
from core.mihomo_runner import direct_listener
from core.ai_probe import probe_all_ai
from core.media_probe import probe_all_media
from core.speed_probe import (DEFAULT_STALL_MIN_BYTES, DEFAULT_SUSTAINED_TARGETS, FRONT_FALLBACK_TIER, describe_speed,
                              measure_rows_speed, speed_options, speed_verdict_text)
from core.run_profile import add_speed_arguments, apply_profile, validate_speed_options
from core.key_evaluator import pick_front_nodes, select_key_nodes
from core.youtube_probe import probe_youtube
from core.shield_probe import probe_sites_http, probe_sites_browser, shield_passed
from core.parsers import parse_singbox_outbound
from core.renderer import check_template, export_clash_yaml
# 命名与编号规则与 Mihomo 流水线共用 core.tagger，此处导出 format_node_name 保持脚本接口不变
from core.tagger import format_node_name, tag_and_rename_nodes


def parse_existing_slot(name):
    if not isinstance(name, str):
        return None
    m = re.search(r'_(?:[A-Za-z\u4e00-\u9fa5]+_)?(\d+)(?:_|$)', name)
    if not m:
        m = re.search(r'_(\d+)', name)
    return int(m.group(1)) if m else None


def parse_city_from_name(name):
    m = re.match(r'^(?:[\U0001F1E6-\U0001F1FF]{2}|🏳️|\S+)\s*[A-Za-z\u4e00-\u9fa5]+_([\u4e00-\u9fa5A-Za-z]+)_\d+', name)
    if m:
        candidate = m.group(1).strip()
        if candidate not in ('Key', 'Fast', 'Lnd', 'USAI', 'NF', 'God'):
            return candidate
    return ""


def parse_info_from_tag(tag):
    """从规范或已有节点标签中逆向解析国家代码、AI能力与流媒体标识"""
    m = re.search(r'([\U0001F1E6-\U0001F1FF]{2})', tag)
    cc = "UNK"
    if m:
        f = m.group(1)
        cc = chr(ord(f[0]) - 0x1F1E6 + ord('A')) + chr(ord(f[1]) - 0x1F1E6 + ord('A'))
    poison = re.search(r'_⚠️[A-Z]{2}', tag)
    return {
        "cc": cc,
        # 复测不重新判定属地，沿用原名中的送中/受限地区污染标记，避免重命名时丢失 _⚠️CN
        "poison_tag": poison.group(0) if poison else None,
        "ai_supported": ("❇️" in tag),
        "is_high_quality": ("♥" in tag and "_⚠️" not in tag),
        "is_key": ("Key" in tag),
        "is_fast": ("Fast" in tag),
        "is_landing": ("_Lnd" in tag or "_USAI" in tag),
        "is_usai": ("_USAI" in tag),
        "media_details": {"nf": ("_NF" in tag), "dp": ("_D+" in tag)},
        "city": parse_city_from_name(tag),
        "slot": parse_existing_slot(tag)
    }


def fast_probe_ip(proxies, timeout=2.0):
    """用共享 HTTPS 回显验证公网 IP，不从错误页中匹配任意数字。"""
    result = probe_egress(proxies, timeout=(timeout, timeout), ipv6=False)
    return result['ipv4']['ip'] or result['ipv6']['ip']


def run_fast_speed(proxies, max_sec=3.0, min_bytes=DEFAULT_STALL_MIN_BYTES, timeout=2.5):
    """默认 3 秒轻量防断流快检：累计不足 16KB 判定断流假死（与 Mihomo 流水线同一门槛）"""
    import requests
    url = "https://speed.cloudflare.com/__down?bytes=5000000"
    total = 0
    t0 = time.time()
    try:
        with requests.get(url, proxies=proxies, timeout=timeout, stream=True, headers={"User-Agent": "curl/7.88.1"}) as r:
            if r.status_code == 200:
                for chunk in r.iter_content(chunk_size=32768):
                    total += len(chunk)
                    if time.time() - t0 >= max_sec or total >= 2 * 1024 * 1024:
                        break
            r.close()
    except Exception:
        pass

    dur = max(time.time() - t0, 0.1)
    kbs = round(total / dur / 1024, 1)

    eliminated_reason = None
    if total == 0:
        eliminated_reason = "无法连通外网"
    elif 0 < total < min_bytes:
        eliminated_reason = "断流假死"

    return {
        "speed_kbs": kbs,
        "total_bytes": total,
        "eliminated_reason": eliminated_reason
    }


def probe_path(res, proxies):
    """在已确定的路径 (直连或经前置) 上执行防断流快检、属地、AI 与流媒体测试。"""
    orig_name = res['orig_name']

    # 3. 测速与断流
    sp = run_fast_speed(proxies)
    res.update(sp)
    if sp.get("eliminated_reason"):
        res['eliminated_reason'] = sp["eliminated_reason"]
        return res

    # 4. 与 Mihomo 共用属地判定，Google 可用时也查询第三方，不制造同源“共识”。
    res.update(probe_geolocation(proxies))
    g_region = res['google_region']
    if not res['exit_ip']:
        res['eliminated_reason'] = "属地复核时未验证到公网出口"
        return res
    res['city'] = parse_city_from_name(orig_name) if res['cc'] == parse_info_from_tag(orig_name)['cc'] else ''

    # 5. AI 解锁
    ai_res = probe_all_ai(proxies, google_region_info=g_region, timeout=(2.0, 3.5))
    res['ai_supported'] = bool(ai_res.get("ai_supported", False) and res['geo_decision']['egress_stable']
                               and not res['geo_decision']['is_pool'])
    res['ai_details'] = ai_res.get("details", {})

    # 6. 流媒体
    media_res = probe_all_media(proxies, timeout=(2.0, 3.5))
    res['media_details'] = media_res.get("details", {})

    # Fast/Key 只由主动测速授予；快检吞吐只用于断流淘汰
    res['is_fast'] = False

    return res


def test_target_node(target):
    """第一轮直连测试；直连拿不到公网出口的节点标记 direct_unreachable，留待选出前置后经前置重测。"""
    raw_node = target['raw']
    res = {
        'raw_node': raw_node,
        'orig_name': raw_node.get('tag', 'unknown'),
        'is_landing': False,
        'path': 'direct',
        'exit_ip': None,
        'eliminated_reason': None
    }

    # 1. 直连探测 (2.0s)
    direct_ip = fast_probe_ip(target['direct_proxies'], timeout=2.0)
    if not direct_ip:
        res['eliminated_reason'] = "直连不可达"
        res['direct_unreachable'] = True
        return res
    res['exit_ip'] = direct_ip
    return probe_path(res, target['direct_proxies'])


def test_via_front(target, blocked_ips, front_label):
    """经前置重测直连不可达的节点 (4.0s，为多跳握手留足时间)；出口不得与前置自身出口相同。"""
    res = target['result_ref']
    proxies = {"http": target['proxy_url'], "https": target['proxy_url']}
    front_ip = fast_probe_ip(proxies, timeout=4.0)
    if not front_ip:
        res['eliminated_reason'] = f"直连与经前置({front_label})均不可达"
        return res
    if front_ip in blocked_ips:
        res['eliminated_reason'] = "出口与前置出口重合(流量未经该节点转发)"
        return res
    res['exit_ip'] = front_ip
    return probe_path(res, proxies)


def run_speed_stage(qualified, eliminated, args):
    """
    主动完整下载测速：直连节点参与 Fast/Key 评选；稳态速度低于淘汰线的节点从合格列表移入淘汰列表。
    """
    directs = [r for r in qualified if not r.get('is_landing')]
    for r in directs:
        r['proxy'] = parse_singbox_outbound(deepcopy(r['raw_node'])) or {}
    opts = speed_options(args)
    targets_urls = [args.speed_target] if args.speed_target else DEFAULT_SUSTAINED_TARGETS
    print(f"\n[3.5/6] 主动完整下载测速 [Profile: {args.profile}] (单连接，观测 10~{args.speed_duration:.0f}s 取最后 6 秒稳态："
          f"Key/Fast 稳态≥{args.min_speed_mbps}Mbps 且最低≥{args.min_floor_mbps}Mbps，稳态<{args.drop_below_mbps}Mbps 淘汰；"
          f"上限 {args.rate_limit_mbps}Mbps，并发 {args.speed_concurrency}，共 {len(directs)} 个直连节点)...")

    for start in range(0, len(directs), 10):
        chunk = directs[start:start + 10]
        try:
            with singbox_active_listeners(chunk, singbox_bin=args.singbox_bin,
                                          relay=getattr(args, 'physical_relay', None)) as targets:
                measure_rows_speed([(target['proxy_url'], target['result_ref']) for target in targets], opts,
                                   targets=targets_urls, concurrency=args.speed_concurrency)
        except Exception as e:
            print(f"      测速批次 {start // 10 + 1} 异常: {e}")
            for r in chunk:
                r.setdefault('speed_result', {"complete": False, "status": "listener_error", "error": str(e)})

    for r in directs:
        r['speed_mbps'] = (r.get('speed_result') or {}).get('stable_mbps') or 0.0
        r['is_fast'] = bool(r.get('is_fast'))
        print(f"      [测速] {r.get('orig_name')}: {speed_verdict_text(r)} | {describe_speed(r.get('speed_result'))}")
        if r.get('speed_drop'):
            qualified.remove(r)
            r['eliminated_reason'] = r['speed_drop']
            eliminated.append(r)
    kept = [r for r in directs if not r.get('speed_drop')]
    chosen = select_key_nodes([r for r in kept if r['proxy']], max_keys=10, per_country_cap=3,
                              min_stable_mbps=args.min_speed_mbps, min_floor_mbps=args.min_floor_mbps)
    print(f"      Key/Fast 级: {sum(1 for r in kept if r['is_fast'])} 个 | 测速淘汰: {len(directs) - len(kept)} 个 | "
          f"评选 Key 优质前置跳板: {len(chosen)} 个")


def resolve_client_front(front_proxy):
    """解析本机客户端前置端口 (如 Karing 127.0.0.1:3067)；端口未监听时返回 None，不拿死端口去测。"""
    if not front_proxy:
        return None
    host, _, port = front_proxy.rpartition(":")
    try:
        address = (host or "127.0.0.1", int(port))
        socket.create_connection(address, timeout=1.0).close()
    except (OSError, ValueError):
        print(f"      本机客户端前置端口 {front_proxy} 未监听，不作兜底前置")
        return None
    exit_ip = None
    try:
        socks = f"socks5://{address[0]}:{address[1]}"
        exit_ip = fast_probe_ip({"http": socks, "https": socks}, timeout=4.0)
    except Exception:
        pass
    print(f"      本机客户端前置端口 {front_proxy} 可用，出口: {exit_ip or '未检测到'}")
    return {"address": address, "exit_ip": exit_ip, "label": f"本机客户端 {front_proxy}"}


def run_landing_stage(qualified, eliminated, args, client_front):
    """
    直连不可达节点经前置重测，区分"需前置的落地节点"与"彻底失效节点"。
    前置优先级：评分最高的 Key -> 未被淘汰的最佳可前置节点 (均需 --speed-test) -> 本机客户端前置端口。
    返回 (前置, 说明)：前置为 sing-box 节点出站 dict 或 (host, port)，供后续浏览器实测复用；无重测时为 (None, None)。
    """
    unreachable = [e for e in eliminated if e.get('direct_unreachable')]
    if not unreachable:
        return None, None

    front, label, blocked, kind = None, None, set(), None
    if args.speed_test and not args.no_landing_probe:
        directs = [r for r in qualified if not r.get('is_landing') and r.get('proxy')]
        fronts, kind = pick_front_nodes(directs, FRONT_FALLBACK_TIER)
        if fronts:
            front_row = fronts[0]
            front = front_row['raw_node']
            label = f"{'Key' if kind == 'key' else '备用前置'} {front_row['orig_name']}"
            if kind == 'fallback':
                for r in fronts:
                    r['is_front_fallback'] = True
            blocked = set((front_row.get('egress') or {}).get('observed_ips') or []) | {front_row.get('exit_ip')}
    if front is None and client_front and not args.no_landing_probe:
        front, label, blocked = client_front["address"], client_front["label"], {client_front["exit_ip"]}
    blocked.discard(None)

    if front is None:
        reason = ("直连不可达，且无合格前置可用于验证是否为落地节点" if args.speed_test and not args.no_landing_probe
                  else "直连不可达 (未经前置验证)")
        for e in unreachable:
            e['eliminated_reason'] = reason
        print(f"\n[3.6/6] {len(unreachable)} 个节点直连不可达，无可用前置，未经前置验证"
              + ("" if args.speed_test else " (开启 --speed-test 可用评出的 Key 或备用前置)"))
        return None, None

    print(f"\n[3.6/6] {len(unreachable)} 个节点直连不可达，经前置 [{label}] 重测...")
    eliminated[:] = [e for e in eliminated if not e.get('direct_unreachable')]
    rows = [{'raw_node': e['raw_node'], 'orig_name': e['orig_name'], 'is_landing': True, 'path': 'front',
             'front_node': label, 'exit_ip': None, 'eliminated_reason': None} for e in unreachable]
    opts = speed_options(args) if args.speed_test else None
    targets_urls = [args.speed_target] if args.speed_target else DEFAULT_SUSTAINED_TARGETS

    for start in range(0, len(rows), 10):
        chunk = rows[start:start + 10]
        failure = "经前置重测未完成"
        try:
            with singbox_active_listeners(chunk, front_proxy=front, singbox_bin=args.singbox_bin,
                                          relay=getattr(args, 'physical_relay', None)) as targets:
                with ThreadPoolExecutor(max_workers=max(1, min(args.workers, len(targets) or 1))) as pool:
                    list(pool.map(lambda target: test_via_front(target, blocked, label), targets))
                passed = [t for t in targets if not t['result_ref'].get('eliminated_reason')]
                if opts and passed:
                    measure_rows_speed([(t['proxy_url'], t['result_ref']) for t in passed], opts,
                                       targets=targets_urls, concurrency=args.speed_concurrency)
        except Exception as e:
            failure = f"前置重测批次异常:{e}"
            print(f"      前置重测批次 {start // 10 + 1} 异常: {e}")
        for r in chunk:
            if not r.get('eliminated_reason') and not r.get('exit_ip'):
                r['eliminated_reason'] = failure
            # 只有经 Key 前置时链路速度才代表落地节点能力；经备用前置/本机客户端时只记录、不按速度淘汰
            if not r.get('eliminated_reason') and r.get('speed_drop') and kind == 'key':
                r['eliminated_reason'] = r['speed_drop']
            if r.get('eliminated_reason'):
                eliminated.append(r)
                print(f"      [淘汰] {r['orig_name']}: {r['eliminated_reason']}")
            else:
                qualified.append(r)
                speed_text = f" | 测速 {speed_verdict_text(r)} {describe_speed(r.get('speed_result'))}" if opts else ""
                print(f"      [落地合格] {r['orig_name']} | IP: {r['exit_ip']}{speed_text}")
    return front, label


def parse_args():
    parser = argparse.ArgumentParser(description="sing-box 订阅节点双轨服务能力测试与配置导出工具 (probe_singbox.py)")
    parser.add_argument("--input", "-i", required=True, help="输入 sing-box JSON 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出最终去重、打标与排序的 sing-box JSON 配置文件路径")
    parser.add_argument("--yaml-output", "-y", help="显式指定输出的 Clash/Mihomo YAML 配置文件路径 (默认自动生成与 -o 同名的 .yaml 文件)")
    parser.add_argument("--front-proxy", default="127.0.0.1:3067",
                        help="本机客户端前置 SOCKS 端口 (默认 127.0.0.1:3067)：无 Key/备用前置时 (如未测速) "
                             "兜底用于验证直连不可达节点；端口未监听时跳过")
    parser.add_argument("--iface", help="物理网卡名称 (如 WLAN)；本机 TUN 接管系统路由时用于物理直连中继，不指定则自动探测")
    parser.add_argument("--singbox-bin", help="显式指定 sing-box 可执行文件路径")
    parser.add_argument("--batch-size", type=int, default=20, help="每批并发探测的节点数量 (默认: 20)")
    parser.add_argument("--workers", type=int, default=20, help="单批并发线程数 (默认: 20)")
    parser.add_argument("--no-browser", action="store_true", default=False,
                        help="降级选项: 跳过 Playwright 浏览器实测 (跳过 YouTube 与浏览器免盾，默认不开启)")
    parser.add_argument("--browser-only", action="store_true", default=False,
                        help="跳过阶段一基础初筛，直接对输入配置中的代理节点执行阶段二全量深度浏览器实测 (YouTube免登实播 + 4站免盾)")
    parser.add_argument("--browser-workers", type=int, default=6,
                        help="浏览器实测并发进程数 (默认: 6)")
    add_speed_arguments(parser)
    parser.add_argument("--resort", action="store_true", default=False,
                        help="仅在用户主动要求重排序时使用: 同地区按标签与信誉重排并从 1 重新编号 (默认保留原节点编号)")
    parser.add_argument("--report", "-r", help="保存测试详情报告的 JSON 路径")
    return parser.parse_args()


def start_physical_relay(stack, args):
    """
    检测本机客户端 TUN/系统代理是否接管了系统路由 (系统出口 != 物理网卡直连出口)。
    接管时返回绑定物理网卡的 mihomo DIRECT 中继地址，供 sing-box 节点出站经其出网；未接管返回 None。
    """
    try:
        port = stack.enter_context(direct_listener(args.iface))
    except Exception as e:
        print(f"      [警告] 无法启动物理直连中继 ({e})；若本机开着 TUN，测试流量会经过本机客户端当前使用的节点")
        return None
    url = f"http://127.0.0.1:{port}"
    physical = set(probe_egress({"http": url, "https": url})["observed_ips"])
    system = set(probe_egress(None)["observed_ips"])
    if physical and system and physical != system:
        print(f"      检测到本机 TUN/系统代理接管系统路由 (系统出口 {sorted(system)}，物理直连出口 {sorted(physical)})："
              f"sing-box 节点出站改经物理直连中继，正在使用的节点也照常测试")
        return ("127.0.0.1", port)
    return None


def main():
    args = parse_args()
    with ExitStack() as stack:
        args.physical_relay = start_physical_relay(stack, args)
        return run_pipeline(args)


def run_pipeline(args):
    start_time = time.time()
    apply_profile(args)
    option_error = validate_speed_options(args) if args.speed_test else None
    if option_error:
        print(f"错误: {option_error}")
        return 2
    try:
        template_path = check_template()
    except (OSError, ValueError) as e:
        print(f"错误: {e}")
        return 2

    print("=" * 80)
    print(">>> 启动 sing-box 备用流水线：服务探测与智能导出 (主流水线为 probe_services.py)")
    print("=" * 80)
    print(f"Clash 母版校验通过: {template_path}")

    if not os.path.isfile(args.input):
        print(f"错误: 输入文件不存在: {args.input}")
        return 1

    with open(args.input, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    all_outbounds = config_data.get("outbounds", [])
    raw_proxies = [ob for ob in all_outbounds if ob.get("type") not in ("urltest", "direct", "block", "dns", "selector")]
    print(f"[1/5] 输入节点解析: 原始代理节点共 {len(raw_proxies)} 个")

    candidates = []
    for ob in raw_proxies:
        c = clean_node_for_singbox(ob)
        if c:
            candidates.append({"raw": ob, "cleaned": c})

    print(f"      有效待测候选节点: {len(candidates)} 个 (已清洗过滤不支持的协议与私有扩展)")

    # 本机客户端前置端口仅作兜底前置 (无 Key / 备用前置时)
    client_front = resolve_client_front(args.front_proxy)
    landing_front, landing_front_label = None, None

    batch_size = max(5, args.batch_size)
    total = len(candidates)
    total_batches = (total + batch_size - 1) // batch_size

    qualified = []
    eliminated = []

    if args.browser_only:
        print(f"[模式] 启用 --browser-only: 跳过阶段一初筛，直接对 {len(raw_proxies)} 个已有合格节点执行阶段二全量深度实测...")
        for ob in raw_proxies:
            c = clean_node_for_singbox(ob)
            if not c:
                continue
            tag = ob.get('tag', '')
            info = parse_info_from_tag(tag)
            qualified.append({
                'raw_node': ob,
                'orig_name': tag,
                'exit_ip': None,
                'cc': info['cc'],
                'geo_decision': {'poison_tag': info['poison_tag']},
                'city': info['city'],
                'assigned_slot': info['slot'],
                'is_landing': info['is_landing'],
                'is_usai': info['is_usai'],
                'ai_supported': info['ai_supported'],
                'is_high_quality': info['is_high_quality'],
                'is_key': info['is_key'],
                'is_fast': info['is_fast'] and not info['is_key'],
                'media_details': info['media_details'],
                'speed_kbs': 500 if info['is_fast'] else 120
            })
        total = len(qualified)
        # 浏览器复测沿用标签中的 Key 作落地节点前置，没有 Key 时用本机客户端前置端口
        key_row = next((r for r in qualified if r['is_key'] and not r['is_landing']), None)
        if key_row:
            landing_front, landing_front_label = key_row['raw_node'], f"Key {key_row['orig_name']}"
        elif client_front:
            landing_front, landing_front_label = client_front['address'], client_front['label']
    else:
        print(f"[2/6] 启动分批直连探测 (共 {total_batches} 批，每批 {batch_size} 节点，as_completed 非阻塞保护)...")

        for b_idx in range(total_batches):
            chunk = candidates[b_idx * batch_size: (b_idx + 1) * batch_size]
            b_num = b_idx + 1
            t_b0 = time.time()
            b_results = []
            try:
                with singbox_dual_listeners(chunk, singbox_bin=args.singbox_bin,
                                            relay=args.physical_relay) as targets:
                    pool = ThreadPoolExecutor(max_workers=min(args.workers, len(targets)))
                    futures = {pool.submit(test_target_node, t): t for t in targets}
                    completed = set()
                    try:
                        for fut in as_completed(futures, timeout=BATCH_HARD_TIMEOUT):
                            completed.add(fut)
                            try:
                                res = fut.result()
                                b_results.append(res)
                            except Exception as e:
                                t_info = futures[fut]
                                b_results.append({'raw_node': t_info['raw'], 'orig_name': t_info['raw'].get('tag'), 'eliminated_reason': f"探测异常:{e}"})
                    except TimeoutError:
                        pass
                    finally:
                        for fut, t_info in futures.items():
                            if fut not in completed:
                                b_results.append({'raw_node': t_info['raw'], 'orig_name': t_info['raw'].get('tag'), 'eliminated_reason': f"探测整体硬超时(>{BATCH_HARD_TIMEOUT:.0f}s)"})
                        pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                print(f"      批次 {b_num} 异常: {e}")
                # 监听启动失败的节点记为淘汰并保留原因，不从报告中凭空消失
                done = {id(r.get('raw_node')) for r in b_results}
                b_results += [{'raw_node': c['raw'], 'orig_name': c['raw'].get('tag'),
                               'eliminated_reason': f"批次监听启动失败:{e}"}
                              for c in chunk if id(c['raw']) not in done]

            b_qual = [r for r in b_results if not r.get('eliminated_reason')]
            b_elim = [r for r in b_results if r.get('eliminated_reason')]
            qualified.extend(b_qual)
            eliminated.extend(b_elim)

            b_dur = time.time() - t_b0
            print(f"      批次 {b_num:02d}/{total_batches:02d} [{len(chunk)}节点] ({b_dur:.1f}s) | 本批合格: {len(b_qual)} | 累计合格: {len(qualified)}")

        unreachable_count = sum(1 for e in eliminated if e.get('direct_unreachable'))
        print(f"\n[3/6] 直连初筛完毕！耗时: {round(time.time() - start_time, 1)}s | 直连合格: {len(qualified)}/{total}"
              f" | 直连不可达: {unreachable_count}")

        if args.speed_test and qualified:
            run_speed_stage(qualified, eliminated, args)
        landing_front, landing_front_label = run_landing_stage(qualified, eliminated, args, client_front)

    if not qualified:
        print("错误: 本轮无节点通过基础测试。")
        return 1

    # [4/6] 全量深度浏览器实测 (YouTube 免登实播 + 4 站免盾)
    if not args.no_browser:
        # 落地节点经选定的前置实测；没有可用前置时无法为落地节点建立链路，跳过其浏览器实测
        browser_rows = [r for r in qualified if landing_front is not None or not r.get('is_landing')]
        browser_ids = {id(r) for r in browser_rows}
        for r in qualified:
            if id(r) not in browser_ids:
                r['youtube_passed'] = False
                r['shield_passed'] = False
                r['comprehensive_sparkle'] = False
                r['youtube_details'] = {"error": "无可用前置，未做浏览器实测"}
        print(f"\n[4/6] 启动全量深度浏览器实测 (YouTube 免登实播 + 4 站免盾，共 {len(browser_rows)} 个合格节点"
              + (f"，落地节点经前置 [{landing_front_label}]" if landing_front is not None else "") + ")...")
        qual_batch_size = 10
        qual_total_batches = (len(browser_rows) + qual_batch_size - 1) // qual_batch_size

        for qb_idx in range(qual_total_batches):
            q_chunk = browser_rows[qb_idx * qual_batch_size: (qb_idx + 1) * qual_batch_size]
            qb_num = qb_idx + 1
            t_qb0 = time.time()

            try:
                with singbox_active_listeners(q_chunk, front_proxy=landing_front, singbox_bin=args.singbox_bin,
                                              relay=args.physical_relay) as active_targets:
                    def test_browser_node(target_info):
                        r = target_info['result_ref']
                        p_url = target_info['proxy_url']
                        exit_ip = r.get('exit_ip')
                        if not exit_ip:
                            try:
                                exit_ip = fast_probe_ip({"http": p_url, "https": p_url}, timeout=3.0)
                                r['exit_ip'] = exit_ip
                            except Exception:
                                pass

                        # 1. 目标网站免盾测试 (HTTP 初查 + 必要时浏览器复核)
                        try:
                            http_shield = probe_sites_http({"http": p_url, "https": p_url}, timeout=(2.5, 4.0))
                            has_challenge = any(v.get("status") == "challenge" for v in http_shield.values())
                            if has_challenge:
                                browser_shield = probe_sites_browser(p_url)
                                combined_shield = {k: browser_shield.get(k) or v for k, v in http_shield.items()}
                            else:
                                combined_shield = http_shield
                            r['shield_passed'] = shield_passed(combined_shield)
                            r['shield_details'] = combined_shield
                        except Exception as e:
                            r['shield_passed'] = False
                            r['shield_details'] = {"error": str(e)}

                        # 2. YouTube 免登录实播测试 (Playwright Chromium 真实实播 >= 10s)
                        try:
                            yt_res = probe_youtube(p_url, expected_ip=exit_ip)
                            r['youtube_passed'] = (yt_res.get('status') == 'passed')
                            r['youtube_details'] = yt_res
                        except Exception as e:
                            r['youtube_passed'] = False
                            r['youtube_details'] = {"error": str(e)}

                        # 3. 综合全通资格判定: AI三大全通 + YouTube免登实播 + 4站免盾
                        r['comprehensive_sparkle'] = bool(r.get('ai_supported') and r.get('youtube_passed') and r.get('shield_passed'))
                        return r

                    b_pool = ThreadPoolExecutor(max_workers=min(args.browser_workers, len(active_targets)))
                    b_futures = {b_pool.submit(test_browser_node, t): t for t in active_targets}
                    try:
                        for fut in as_completed(b_futures, timeout=180.0):
                            try:
                                res_node = fut.result()
                                cc_flag = flag_emoji(res_node.get('cc'))
                                c_zh = country_name_zh(res_node.get('cc'))
                                sp_tag = " [✨️综合全通]" if res_node.get('comprehensive_sparkle') else ""
                                yt_st = "✓" if res_node.get('youtube_passed') else "✗"
                                sh_st = "✓" if res_node.get('shield_passed') else "✗"
                                ip_str = res_node.get('exit_ip') or '未知'
                                print(f"        {cc_flag} {c_zh} (IP: {ip_str}) | YT免登: {yt_st} | 免盾: {sh_st}{sp_tag}", flush=True)
                            except Exception:
                                pass
                    except TimeoutError:
                        print(f"      批次 {qb_num} 浏览器测试达到 180s 保护上限，自动推进下一批")
                    finally:
                        b_pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                print(f"      浏览器实测批次 {qb_num} 异常: {e}")

            qb_dur = time.time() - t_qb0
            sparkle_count = sum(1 for r in qualified if r.get('comprehensive_sparkle'))
            print(f"      浏览器批次 {qb_num:02d}/{qual_total_batches:02d} [{len(q_chunk)}节点] ({qb_dur:.1f}s) | 累计获赠✨️综合全通: {sparkle_count}")
    else:
        print("\n[4/6] 显式指定 --no-browser: 跳过 Playwright 浏览器实测...")
        for r in qualified:
            r['youtube_passed'] = False
            r['shield_passed'] = False
            r['comprehensive_sparkle'] = False

    # 规范打标与命名：与 Mihomo 流水线共用编号规则（默认保留原节点编号，新节点补空号；--resort 才重排并重编号）
    print("\n[5/6] 规范打标、原节点编号保留与新节点补位" + ("（主动重排序并从 1 重新编号）" if args.resort else "") + "...")
    tag_and_rename_nodes(qualified, resort=args.resort)

    print(f"\n[6/6] 导出双份标准配置文件 (sing-box JSON + Clash/Mihomo YAML)...")
    out_target = args.output
    if out_target.lower().endswith(".yaml") or out_target.lower().endswith(".yml"):
        yaml_path = out_target
        sb_path = args.yaml_output or (os.path.splitext(out_target)[0] + ".json")
    else:
        sb_path = out_target
        yaml_path = args.yaml_output or (os.path.splitext(out_target)[0] + ".yaml")

    # 1. 导出标准 sing-box JSON 配置文件
    exp_res = export_singbox_json(config_data, qualified, sb_path, singbox_bin=args.singbox_bin)

    print(f"      [1/2] sing-box JSON 导出成功: {sb_path} (节点数: {exp_res['total_nodes']})")
    if exp_res['check_ok']:
        print("            sing-box 内核校验: [通过] 100% 格式无误！")
    else:
        print(f"            sing-box 内核校验提示: {exp_res['check_msg']}")

    # 2. 同步导出标准 Clash/Mihomo YAML 配置文件 (以内置 template.yaml 为母版)
    clash_proxies = []
    for r in qualified:
        ob = deepcopy(r.get('raw_node', {}))
        ob['tag'] = r['final_name']
        cp = parse_singbox_outbound(ob)
        if cp:
            if r.get('is_front_fallback'):
                cp['_front_fallback'] = True
            clash_proxies.append(cp)

    export_clash_yaml(clash_proxies, yaml_path)
    print(f"      [2/2] Clash/Mihomo YAML 导出成功: {yaml_path} (节点数: {len(clash_proxies)} | 策略组及规则基于 template.yaml)")

    print("\n" + "=" * 125)
    print(f"{'序号':<4} | {'最终规范命名':<38} | {'类型':<6} | {'真实出口IP':<15} | {'AI全通':<6} | {'YT免登':<6} | {'免盾':<6} | {'流媒体':<8} | {'带宽':<10}")
    print("-" * 125)
    for idx, r in enumerate(qualified, 1):
        name = r['final_name']
        if len(name) > 36:
            name = name[:34] + ".."
        path_type = "落地" if r['is_landing'] else "备用前置" if r.get('is_front_fallback') else "直连"
        ip = r.get('exit_ip') or "未知"
        ai = "✓" if r.get('ai_supported') else "✗"
        yt = "✓" if r.get('youtube_passed') else "✗"
        sh = "✓" if r.get('shield_passed') else "✗"
        md = r.get('media_details') or {}
        m_list = []
        if md.get('nf'):
            m_list.append("NF")
        if md.get('dp'):
            m_list.append("D+")
        media = "+".join(m_list) if m_list else "-"
        spd = f"{r.get('speed_kbs', 0)}KB/s"
        print(f"{idx:<4} | {name:<38} | {path_type:<6} | {ip:<15} | {ai:<6} | {yt:<6} | {sh:<6} | {media:<8} | {spd:<10}")
    print("=" * 125)

    if args.report:
        report_data = {
            "timestamp": time.time(),
            "total_candidates": total,
            "qualified_count": len(qualified),
            "eliminated_count": len(eliminated),
            "landing_front": landing_front_label,
            "qualified": [
                {
                    "final_name": r['final_name'],
                    "is_landing": r['is_landing'],
                    "path": r.get('path'),
                    "front_node": r.get('front_node'),
                    "is_front_fallback": r.get('is_front_fallback', False),
                    "exit_ip": r.get('exit_ip'),
                    "cc": r.get('cc'),
                    "speed_kbs": r.get('speed_kbs'),
                    "ai_supported": r.get('ai_supported'),
                    "youtube_passed": r.get('youtube_passed'),
                    "shield_passed": r.get('shield_passed'),
                    "comprehensive_sparkle": r.get('comprehensive_sparkle'),
                    "media": r.get('media_details'),
                    "shield_details": r.get('shield_details'),
                    "is_key": r.get('is_key', False),
                    "is_fast": r.get('is_fast', False),
                    "key_score": r.get('key_score'),
                    "key_reason": r.get('key_reason'),
                    "speed_mbps": r.get('speed_mbps'),
                    "speed_result": r.get('speed_result'),
                    "geo_decision": r.get('geo_decision'),
                    "google_region": r.get('google_region'),
                    "egress": r.get('egress'),
                    "egress_after": r.get('egress_after'),
                    "ip_info": r.get('ip_info'),
                    "ip_info_by_ip": r.get('ip_info_by_ip'),
                    "ip_reputation": r.get('ip_reputation'),
                    "youtube_details": r.get('youtube_details')
                } for r in qualified
            ]
        }
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"报告已保存到: {args.report}")

    print(f"\n全部处理完毕！共耗时 {round(time.time() - start_time, 1)} 秒。")
    return 0


if __name__ == '__main__':
    ret = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(ret if isinstance(ret, int) else 0)
