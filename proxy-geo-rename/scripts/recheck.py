# -*- coding: utf-8 -*-
"""
二次复核（在 probe.py 之后运行）：
1. 离线节点低并发重试（排除首轮并发抢带宽造成的误判）
2. 出口不稳定节点多次采样，记录出口池
3. 对全部在线出口 IP 增补 3 个独立地理库 + RIR 注册国参考
4. 统一重投票，写入 <workdir>/probe_result_final.json

用法：python recheck.py --workdir <目录>
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import (NODE_TYPES, ensure_utf8_stdout, find_local_proxies, load_session,
                    pair_nodes, start_kernel)
from probe import (STRIP_FIELDS, fetch, kernel_version, p_cf,
                   probe_node, strip_unknown_fields)
from verdict import vote

ensure_utf8_stdout()


def p_ipapico(j):
    if not j or j.get('error'):
        return None
    cc = j.get('country_code')
    return {'ip': j.get('ip'), 'cc': cc, 'city': j.get('city') or ''} if cc else None


def p_ipapis(j):
    loc = (j or {}).get('location') or {}
    cc = loc.get('country_code')
    if not cc:
        return None
    ip = j.get('ip')
    return {'ip': ip if isinstance(ip, str) else None, 'cc': cc,
            'city': loc.get('city') or ''}


def p_freeip(j):
    cc = (j or {}).get('countryCode')
    if not cc:
        return None
    return {'ip': j.get('ipAddress'), 'cc': cc, 'city': j.get('cityName') or ''}


def p_ripe(j):
    try:
        lr = j['data']['located_resources'][0]
        loc = (lr.get('locations') or [{}])[0].get('country') or lr.get('location') or ''
        cc = loc[:2].upper()
        return {'ip': None, 'cc': cc, 'city': ''} if len(cc) == 2 and cc.isalpha() else None
    except Exception:
        return None


# 前 3 个为计票地理库；ref: 前缀的是注册地参考信息，verdict 不计票
# （注册地≠物理位置，计票会稀释真实判定，只作报告展示）
EXTRA_SOURCES = {
    'ipapi.co': lambda ip: p_ipapico(fetch(f'https://ipapi.co/{ip}/json/')),
    'ipapi.is': lambda ip: p_ipapis(fetch(f'https://api.ipapi.is/?q={ip}')),
    'freeipapi': lambda ip: p_freeip(fetch(f'https://freeipapi.com/api/json/{ip}')),
    'ref:ripe-rir': lambda ip: p_ripe(fetch(f'https://stat.ripe.net/data/rir-geo/data.json?resource={ip}')),
}


def revive_via_front(recs, still_offline, node_of, s, workdir):
    """直连两轮仍离线的节点，经本机正在运行的代理客户端中转再测一次。
    场景：节点服务器 IP 从本机直连被墙，但节点本身活着（用户客户端 TUN 环境
    下实际走隐性中转所以"能用"）。中转不影响出口判定——出口仍是节点自己的
    出口 IP。复活节点标 via_front，报告会注明"直连被墙"。"""
    fronts = find_local_proxies()
    if not fronts:
        print('未探测到本机前置代理，跳过中转复活（直连失败的节点维持离线）')
        return
    fport, fkind = fronts[0]
    print(f'探测到本机前置代理 127.0.0.1:{fport}（{fkind}），离线节点尝试经中转复活...',
          flush=True)
    if fkind == 'http':
        print('  注意：HTTP 前置无法转发 UDP，hysteria2/tuic 类节点仍可能失败')

    fbase = s['base_port'] + 500
    outs, inb, rules, port_of = [], [], [], {}
    for j, i in enumerate(still_offline):
        n2 = {k: v for k, v in node_of[i].items() if k not in STRIP_FIELDS}
        n2['detour'] = 'front'
        outs.append(n2)
        inb.append({'type': 'mixed', 'tag': f'fin-{j}', 'listen': '127.0.0.1',
                    'listen_port': fbase + j})
        rules.append({'inbound': [f'fin-{j}'], 'outbound': n2['tag']})
        port_of[i] = fbase + j
    front = ({'type': 'socks', 'tag': 'front', 'server': '127.0.0.1',
              'server_port': fport, 'version': '5'} if fkind == 'socks' else
             {'type': 'http', 'tag': 'front', 'server': '127.0.0.1',
              'server_port': fport})
    outs += [front, {'type': 'direct', 'tag': 'direct-out'}]
    # 不绑物理网卡（front 走回环）；DNS 用 DoH 经前置，避开本机 TUN 的 DNS 劫持
    cfg = {'log': {'level': 'warn'}, 'inbounds': inb, 'outbounds': outs,
           'route': {'rules': rules, 'final': 'direct-out'}}
    if kernel_version(s['singbox']) >= (1, 12):
        cfg['dns'] = {'servers': [{'type': 'https', 'tag': 'dns-front',
                                   'server': '8.8.8.8', 'detour': 'front'}]}
        cfg['route']['default_domain_resolver'] = {'server': 'dns-front'}
    else:
        cfg['dns'] = {'servers': [{'tag': 'dns-front',
                                   'address': 'https://8.8.8.8/dns-query',
                                   'detour': 'front'}]}
    cfg_path = os.path.join(workdir, 'front_config.json')
    if not strip_unknown_fields(cfg, cfg_path, s['singbox']):
        print('中转测试配置生成失败，跳过')
        return

    proc = start_kernel(s['singbox'], cfg_path, workdir, 'singbox_front.log', fbase)
    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(probe_node, port_of[i], recs[i]['tag']): i
                    for i in still_offline}
            for f in as_completed(futs):
                i = futs[f]
                r = f.result()
                if r['status'] == 'ok':
                    r['via_front'] = True
                    r['front'] = f'127.0.0.1:{fport}({fkind})'
                    samples = []  # 出口稳定性就地采样（中转内核关闭后无法再测）
                    for _ in range(2):
                        time.sleep(2)
                        t = p_cf(fetch('https://www.cloudflare.com/cdn-cgi/trace',
                                       r['port'], js=False))
                        if t and t.get('ip'):
                            samples.append(t['ip'])
                    r['exit_ip_2nd'] = samples[0] if samples else None
                    r['exit_stable'] = (all(x == r['exit_ip'] for x in samples)
                                        if samples else None)
                    r['port'] = None  # 端口随中转内核关闭失效，防下游误用
                    recs[i] = r
                    print(f"  中转复活: {r['tag']} exit={r['exit_ip']}（直连被墙）", flush=True)
                else:
                    print(f"  仍离线: {recs[i]['tag']}（中转亦不通，确认死节点）", flush=True)
    finally:
        proc.terminate()


def main():
    ap = argparse.ArgumentParser(description='节点检测二次复核')
    ap.add_argument('--workdir', required=True, help='probe.py 使用的工作目录')
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    s = load_session(workdir)
    base = s['base_port']
    recs = json.load(open(os.path.join(workdir, 'probe_result.json'), encoding='utf-8'))
    # 与配置节点重新配对（配置可能在检测后被客户端改名），并回填指纹
    d = json.load(open(s['config'], encoding='utf-8'))
    nodes = [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]
    pairs = pair_nodes(recs, nodes)
    node_of = {i: nodes[j] for i, j in pairs.items()}
    missing = [r['tag'] for i, r in enumerate(recs) if i not in node_of]
    if missing:
        print(f'警告：{len(missing)} 个检测结果在当前配置中找不到对应节点'
              f'（可能已被删除）：{missing[:3]}...')

    proc = start_kernel(s['singbox'], os.path.join(workdir, 'test_config.json'),
                        workdir, 'singbox_recheck.log', base)

    offline_idx = [i for i, r in enumerate(recs) if r['status'] != 'ok']
    revived = []
    if offline_idx:
        print(f'离线节点二次复测（{len(offline_idx)} 个，低并发）...', flush=True)
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(probe_node, base + i, recs[i]['tag']): i
                    for i in offline_idx}
            for f in as_completed(futs):
                i = futs[f]
                r = f.result()
                if r['status'] == 'ok':
                    recs[i] = r
                    revived.append(i)
                    print(f"  复活: {r['tag']} exit={r['exit_ip']}", flush=True)
                else:
                    print(f"  仍离线: {recs[i]['tag']}", flush=True)

    # 出口池采样：复活节点 + 首轮发现出口漂移/分流的节点
    need_sample = sorted(set(revived) | {
        i for i, r in enumerate(recs)
        if r.get('status') == 'ok' and (r.get('split_exit') or r.get('exit_stable') is False)})
    if need_sample:
        print(f'出口稳定性采样（{len(need_sample)} 个节点 × 3 次）...', flush=True)
        for i in need_sample:
            r = recs[i]
            pool = set(filter(None, [r.get('exit_ip'), r.get('exit_ip_2nd')]))
            samples = []
            for _ in range(3):
                t = p_cf(fetch('https://www.cloudflare.com/cdn-cgi/trace', base + i, js=False))
                if t and t.get('ip'):
                    samples.append(t['ip'])
                    pool.add(t['ip'])
                time.sleep(2)
            r['exit_pool'] = sorted(pool)
            if r.get('exit_stable') is None:
                r['exit_ip_2nd'] = samples[0] if samples else None
                r['exit_stable'] = (all(x == r['exit_ip'] for x in samples)
                                    if samples else None)
    proc.terminate()

    # 中转复活：直连仍离线的节点，经本机现有代理客户端中转再给最后一次机会
    still_offline = [i for i, r in enumerate(recs)
                     if r['status'] != 'ok' and i in node_of]
    if still_offline:
        revive_via_front(recs, still_offline, node_of, s, workdir)

    # 补充地理库（直连查出口 IP；按源限速、源间并行；缺票可接受）
    ips = sorted({r['exit_ip'] for r in recs if r.get('status') == 'ok' and r.get('exit_ip')})
    print(f'补充地理库查询：{len(ips)} 个出口 IP × {len(EXTRA_SOURCES)} 源...', flush=True)
    cache = {}

    def query_source(name, fn):
        out = {}
        for ip in ips:
            try:
                r = fn(ip)
            except Exception:
                r = None
            if r:
                out[(ip, name)] = r
            time.sleep(1.2 if name == 'ipapi.co' else 0.3)
        return out

    with ThreadPoolExecutor(max_workers=len(EXTRA_SOURCES)) as ex:
        for f in as_completed([ex.submit(query_source, n, fn)
                               for n, fn in EXTRA_SOURCES.items()]):
            cache.update(f.result())

    for r in recs:
        if r.get('status') != 'ok':
            continue
        for name in EXTRA_SOURCES:
            hit = cache.get((r.get('exit_ip'), name))
            if hit:
                h = dict(hit)
                h['via'] = 'direct'
                r['sources'][name] = h
        vote(r)

    with open(os.path.join(workdir, 'probe_result_final.json'), 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)

    print('\n===== 终判 =====')
    for r in recs:
        if r['status'] == 'ok':
            extra = ''
            if r.get('exit_pool') and len(r['exit_pool']) > 1:
                extra = f" 出口池={len(r['exit_pool'])}个"
            if r.get('via_front'):
                extra += ' [经中转复活，直连被墙]'
            print(f"{r['tag']} -> {r['cc']} {r['country_zh']} {r['city_zh']} "
                  f"票{r['votes']}/{r['answered']} {r['conf']} colo={r.get('colo') or '-'} "
                  f"稳定={r.get('exit_stable')}{extra}", flush=True)
        else:
            print(f"{r['tag']} -> 离线", flush=True)
    n_ok = sum(1 for r in recs if r['status'] == 'ok')
    n_high = sum(1 for r in recs if r.get('conf') == 'high')
    n_med = sum(1 for r in recs if r.get('conf') == 'medium')
    n_low = sum(1 for r in recs if r.get('conf') == 'low')
    print(f'\n在线 {n_ok}/{len(recs)}（高 {n_high} / 中 {n_med} / 低 {n_low}），'
          f'已写入 probe_result_final.json')
    if n_med + n_low:
        print('仍有中/低置信节点：运行 latency_arbiter.py 做物理测距仲裁')


if __name__ == '__main__':
    main()
