#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sing-box 订阅节点双轨服务能力测试、智能打标与配置导出命令行工具 (probe_singbox.py)。
支持对 sing-box JSON 执行全量直连与 Karing/前置跳板双轨探测、严格 Schema 清洗与导出。
"""
import sys
import os
import io
import json
import time
import re
import socket
import argparse
from copy import deepcopy
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

# 全局底层套接字保护 (>=6.0s 杜绝多跳 TLS Reality 握手被掐断)
socket.setdefaulttimeout(6.0)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.singbox_runner import find_singbox_bin, clean_node_for_singbox, singbox_dual_listeners, singbox_active_listeners, export_singbox_json
from core.egress_geo import probe_google_region, query_ip_info, CATEGORY_ORDER, country_name_zh, flag_emoji
from core.ai_probe import probe_all_ai
from core.media_probe import probe_all_media
from core.speed_probe import measure_speed_and_stall
from core.youtube_probe import probe_youtube
from core.shield_probe import probe_sites_http, probe_sites_browser, shield_passed
from core.parsers import parse_singbox_outbound
from core.renderer import export_clash_yaml


class SlotAllocator:
    def __init__(self, surviving_indices=()):
        self.surviving = set(surviving_indices)
        self.next_new = 1

    def next_slot(self):
        while self.next_new in self.surviving:
            self.next_new += 1
        slot = self.next_new
        self.surviving.add(slot)
        self.next_new += 1
        return slot


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
    return {
        "cc": cc,
        "ai_supported": ("❇️" in tag),
        "is_fast": ("Fast" in tag),
        "is_landing": ("_Lnd" in tag or "_USAI" in tag),
        "is_usai": ("_USAI" in tag),
        "media_details": {"nf": ("_NF" in tag), "dp": ("_D+" in tag)},
        "city": parse_city_from_name(tag),
        "slot": parse_existing_slot(tag)
    }


def format_node_name(cc, slot, city="", ai_supported=False, comprehensive_sparkle=False,
                      is_fast=False, is_landing=False, is_usai=False, media_details=None):
    flag = flag_emoji(cc)
    cname = country_name_zh(cc)

    prefix_badges = ""
    if ai_supported:
        prefix_badges += "❇️"
    if comprehensive_sparkle:
        prefix_badges += "✨️"
    if is_fast:
        prefix_badges += "Fast"

    country_part = f"{prefix_badges}{cname}"
    if city:
        country_part += f"_{city}"
    country_part += f"_{slot}"

    lnd_suffix = ""
    if is_landing:
        lnd_suffix = "_USAI" if is_usai else "_Lnd"

    md = media_details or {}
    media_suffix = ""
    if md.get("nf"):
        media_suffix += "_NF"
    if md.get("dp"):
        media_suffix += "_D+"

    return f"{flag} {country_part}{lnd_suffix}{media_suffix}"


def fast_probe_ip(proxies, timeout=2.0):
    """高效探测出口 IP (优先轻量 HTTP 端点)"""
    import requests
    session = requests.Session()
    session.trust_env = False
    endpoints = [
        ("http://api.ipify.org?format=json", "json"),
        ("https://api.ipify.org?format=json", "json"),
        ("http://ipv4.icanhazip.com", "text")
    ]
    for url, fmt in endpoints:
        try:
            r = session.get(url, proxies=proxies, timeout=timeout, headers={"User-Agent": "curl/7.88.1"})
            if r.status_code == 200:
                if fmt == "json":
                    ip = r.json().get('ip')
                    if ip:
                        session.close()
                        return ip
                else:
                    m = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                    if m:
                        session.close()
                        return m.group(0)
        except requests.exceptions.RequestException:
            break
        except Exception:
            continue
    session.close()
    return None


def run_fast_speed(proxies, max_sec=1.5, min_bytes=4*1024, timeout=2.5):
    """轻量流式吞吐检测"""
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


def test_target_node(target, baseline_ip=None):
    raw_node = target['raw']
    orig_name = raw_node.get('tag', 'unknown')
    dp = target['direct_proxies']
    fp = target['front_proxies']

    res = {
        'raw_node': raw_node,
        'orig_name': orig_name,
        'is_landing': False,
        'exit_ip': None,
        'eliminated_reason': None
    }

    # 1. 直连探测 (2.0s)
    direct_ip = fast_probe_ip(dp, timeout=2.0)
    active_proxies = None

    if direct_ip:
        res['exit_ip'] = direct_ip
        res['is_landing'] = False
        active_proxies = dp
    else:
        # 2. 前置落地跳板探测 (4.0s，为多跳握手给予充分时间)
        front_ip = fast_probe_ip(fp, timeout=4.0)
        if front_ip:
            if baseline_ip and front_ip == baseline_ip:
                res['eliminated_reason'] = "前置穿透失败(出口等于前置本地出口)"
                return res
            res['exit_ip'] = front_ip
            res['is_landing'] = True
            active_proxies = fp
        else:
            res['eliminated_reason'] = "直连与前置均不可达"
            return res

    # 3. 测速与断流
    sp = run_fast_speed(active_proxies, max_sec=1.5, min_bytes=4*1024, timeout=2.5)
    res.update(sp)
    if sp.get("eliminated_reason"):
        res['eliminated_reason'] = sp["eliminated_reason"]
        return res

    # 4. Google 官方属地与地区判定
    g_region = probe_google_region(active_proxies, timeout=(2.0, 3.5))
    res['google_region'] = g_region

    cc = g_region.get("country_code")
    if not cc or cc == "UNK":
        try:
            info = query_ip_info(res['exit_ip'], timeout=(1.0, 1.5))
            res['ip_info'] = info
            cc = info.get("country_code") or "UNK"
        except Exception:
            res['ip_info'] = {}
    else:
        res['ip_info'] = {"country_code": cc}

    if cc == "UNK":
        m_cc = re.search(r'([\U0001F1E6-\U0001F1FF]{2})', orig_name)
        if m_cc:
            f = m_cc.group(1)
            cc = chr(ord(f[0]) - 0x1F1E6 + ord('A')) + chr(ord(f[1]) - 0x1F1E6 + ord('A'))
    res['cc'] = cc
    res['city'] = parse_city_from_name(orig_name)

    # 5. AI 解锁
    ai_res = probe_all_ai(active_proxies, google_region_info=g_region, timeout=(2.0, 3.5))
    res['ai_supported'] = ai_res.get("ai_supported", False)
    res['ai_details'] = ai_res.get("details", {})

    # 6. 流媒体
    media_res = probe_all_media(active_proxies, timeout=(2.0, 3.5))
    res['media_details'] = media_res.get("details", {})

    speed_kbs = res.get('speed_kbs', 0)
    res['is_fast'] = bool(speed_kbs >= 500)

    return res


def parse_args():
    parser = argparse.ArgumentParser(description="sing-box 订阅节点双轨服务能力测试与配置导出工具 (probe_singbox.py)")
    parser.add_argument("--input", "-i", required=True, help="输入 sing-box JSON 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出最终去重、打标与排序的 sing-box JSON 配置文件路径")
    parser.add_argument("--yaml-output", "-y", help="显式指定输出的 Clash/Mihomo YAML 配置文件路径 (默认自动生成与 -o 同名的 .yaml 文件)")
    parser.add_argument("--front-proxy", default="127.0.0.1:3067", help="本地前置跳板代理地址 (默认: 127.0.0.1:3067)")
    parser.add_argument("--singbox-bin", help="显式指定 sing-box 可执行文件路径")
    parser.add_argument("--batch-size", type=int, default=20, help="每批并发探测的节点数量 (默认: 20)")
    parser.add_argument("--workers", type=int, default=20, help="单批并发线程数 (默认: 20)")
    parser.add_argument("--no-browser", action="store_true", default=False,
                        help="降级选项: 跳过 Playwright 浏览器实测 (跳过 YouTube 与浏览器免盾，默认不开启)")
    parser.add_argument("--browser-only", action="store_true", default=False,
                        help="跳过阶段一基础初筛，直接对输入配置中的代理节点执行阶段二全量深度浏览器实测 (YouTube免登实播 + 4站免盾)")
    parser.add_argument("--browser-workers", type=int, default=6,
                        help="浏览器实测并发进程数 (默认: 6)")
    parser.add_argument("--report", "-r", help="保存测试详情报告的 JSON 路径")
    return parser.parse_args()


def main():
    args = parse_args()
    start_time = time.time()

    print("=" * 80)
    print(">>> 启动 sing-box 订阅双轨服务探测与智能导出流水线")
    print("=" * 80)

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

    front_parts = args.front_proxy.split(":")
    front_host = front_parts[0]
    front_port = int(front_parts[1]) if len(front_parts) > 1 else 3067

    # 获取前置基线出口
    baseline_ip = None
    try:
        baseline_proxies = {"http": f"socks5://{front_host}:{front_port}", "https": f"socks5://{front_host}:{front_port}"}
        baseline_ip = fast_probe_ip(baseline_proxies, timeout=4.0)
        print(f"      本地前置跳板基线出口: {baseline_ip or '未检测到'}")
    except Exception:
        pass

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
                'city': info['city'],
                'assigned_slot': info['slot'],
                'is_landing': info['is_landing'],
                'is_usai': info['is_usai'],
                'ai_supported': info['ai_supported'],
                'is_fast': info['is_fast'],
                'media_details': info['media_details'],
                'speed_kbs': 500 if info['is_fast'] else 120
            })
        total = len(qualified)
    else:
        print(f"[2/6] 启动分批双轨探测 (共 {total_batches} 批，每批 {batch_size} 节点，as_completed 非阻塞保护)...")

        for b_idx in range(total_batches):
            chunk = candidates[b_idx * batch_size: (b_idx + 1) * batch_size]
            b_num = b_idx + 1
            t_b0 = time.time()
            base_port = 26000 + (b_idx % 20) * 100

            b_results = []
            try:
                with singbox_dual_listeners(chunk, front_proxy=(front_host, front_port),
                                           singbox_bin=args.singbox_bin, base_port=base_port) as targets:
                    pool = ThreadPoolExecutor(max_workers=min(args.workers, len(targets)))
                    futures = {pool.submit(test_target_node, t, baseline_ip): t for t in targets}
                    completed = set()
                    try:
                        for fut in as_completed(futures, timeout=24.0):
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
                                b_results.append({'raw_node': t_info['raw'], 'orig_name': t_info['raw'].get('tag'), 'eliminated_reason': "探测整体硬超时(>24s)"})
                        pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                print(f"      批次 {b_num} 异常: {e}")

            b_qual = [r for r in b_results if not r.get('eliminated_reason')]
            b_elim = [r for r in b_results if r.get('eliminated_reason')]
            qualified.extend(b_qual)
            eliminated.extend(b_elim)

            b_dur = time.time() - t_b0
            print(f"      批次 {b_num:02d}/{total_batches:02d} [{len(chunk)}节点] ({b_dur:.1f}s) | 本批合格: {len(b_qual)} | 累计合格: {len(qualified)}")

    print(f"\n[3/6] 基础双轨初筛完毕！耗时: {round(time.time() - start_time, 1)}s | 初筛合格: {len(qualified)}/{total}")
    if not qualified:
        print("错误: 本轮无节点通过基础测试。")
        return 1

    # [4/6] 全量深度浏览器实测 (YouTube 免登实播 + 4 站免盾)
    if not args.no_browser:
        print(f"\n[4/6] 启动全量深度浏览器实测 (YouTube 免登实播 + 4 站免盾，共 {len(qualified)} 个合格节点)...")
        qual_batch_size = 10
        qual_total_batches = (len(qualified) + qual_batch_size - 1) // qual_batch_size

        for qb_idx in range(qual_total_batches):
            q_chunk = qualified[qb_idx * qual_batch_size: (qb_idx + 1) * qual_batch_size]
            qb_num = qb_idx + 1
            t_qb0 = time.time()
            base_port = 28000 + (qb_idx % 20) * 50

            try:
                with singbox_active_listeners(q_chunk, front_proxy=(front_host, front_port),
                                              singbox_bin=args.singbox_bin, base_port=base_port) as active_targets:
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

    # 规范打标与命名
    print("\n[5/6] 规范打标、Slot 分配与地区优先级重排序...")
    claimed_slots = defaultdict(set)
    for r in qualified:
        orig_slot = parse_existing_slot(r['orig_name'])
        cc = r.get('cc') or 'UNK'
        if orig_slot and orig_slot > 0 and orig_slot not in claimed_slots[cc]:
            claimed_slots[cc].add(orig_slot)
            r['assigned_slot'] = orig_slot
        else:
            r['assigned_slot'] = None

    allocators = {cc: SlotAllocator(slots) for cc, slots in claimed_slots.items()}
    for r in qualified:
        cc = r.get('cc') or 'UNK'
        if cc not in allocators:
            allocators[cc] = SlotAllocator()
        if r['assigned_slot'] is None:
            r['assigned_slot'] = allocators[cc].next_slot()

    seen_names = set()
    for r in qualified:
        cc = r.get('cc') or 'UNK'
        slot = r['assigned_slot']
        is_usai = bool(r.get('is_landing') and cc == 'US' and r.get('ai_supported'))
        sparkle = r.get('comprehensive_sparkle', False)
        name = format_node_name(
            cc=cc,
            slot=slot,
            city=r.get('city', ''),
            ai_supported=r.get('ai_supported', False),
            comprehensive_sparkle=sparkle,
            is_fast=r.get('is_fast', False),
            is_landing=r.get('is_landing', False),
            is_usai=is_usai,
            media_details=r.get('media_details', {})
        )
        if name in seen_names:
            slot = allocators[cc].next_slot()
            name = format_node_name(
                cc=cc,
                slot=slot,
                city=r.get('city', ''),
                ai_supported=r.get('ai_supported', False),
                comprehensive_sparkle=sparkle,
                is_fast=r.get('is_fast', False),
                is_landing=r.get('is_landing', False),
                is_usai=is_usai,
                media_details=r.get('media_details', {})
            )
        seen_names.add(name)
        r['final_name'] = name
        r['slot'] = slot

    def sort_key(row):
        cc = row.get("cc") or "UNK"
        order_info = CATEGORY_ORDER.get(cc, (7, 999, '未知'))
        reg_rank = order_info[0]
        cntry_rank = order_info[1]
        sparkle_rank = 0 if row.get("comprehensive_sparkle") else 1
        ai_rank = 0 if row.get("ai_supported") else 1
        fast_rank = 0 if row.get("is_fast") else 1
        slot = row.get("slot", 9999)
        return (reg_rank, cntry_rank, sparkle_rank, ai_rank, fast_rank, slot)

    qualified.sort(key=sort_key)

    print(f"\n[6/6] 导出双份标准配置文件 (sing-box JSON + Clash/Mihomo YAML)...")
    out_target = args.output
    if out_target.lower().endswith(".yaml") or out_target.lower().endswith(".yml"):
        yaml_path = out_target
        sb_path = args.yaml_output or (os.path.splitext(out_target)[0] + ".json")
    else:
        sb_path = out_target
        yaml_path = args.yaml_output or (os.path.splitext(out_target)[0] + ".yaml")

    # 1. 导出标准 sing-box JSON 配置文件
    exp_res = export_singbox_json(config_data, qualified, sb_path,
                                 front_proxy=(front_host, front_port),
                                 singbox_bin=args.singbox_bin)

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
        path_type = "落地" if r['is_landing'] else "直连"
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
            "qualified": [
                {
                    "final_name": r['final_name'],
                    "is_landing": r['is_landing'],
                    "exit_ip": r.get('exit_ip'),
                    "cc": r.get('cc'),
                    "speed_kbs": r.get('speed_kbs'),
                    "ai_supported": r.get('ai_supported'),
                    "youtube_passed": r.get('youtube_passed'),
                    "shield_passed": r.get('shield_passed'),
                    "comprehensive_sparkle": r.get('comprehensive_sparkle'),
                    "media": r.get('media_details'),
                    "shield_details": r.get('shield_details'),
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
