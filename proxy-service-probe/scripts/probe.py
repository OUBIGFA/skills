# -*- coding: utf-8 -*-
"""
主检测：为配置中每个节点开一个本地端口（真实连接），通过节点向 5 个独立地理源
查询出口位置；代理侧查询失败的源用本机直连反查出口 IP 兜底；多数投票 +
Cloudflare 接入机房物理决胜。结果写入 <workdir>/probe_result.json。

用法：
  python probe.py --config <配置.json> --singbox <内核路径> [--iface WLAN]
                  [--workdir <目录>] [--base-port 42001]
本机开着 TUN 全局接管（Clash/karing 等客户端）时必须指定 --iface 物理网卡，
否则测试流量会被现有代理污染。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from common import NODE_TYPES, ensure_utf8_stdout, fp_of, save_session, start_kernel
from verdict import vote

ensure_utf8_stdout()

STRIP_FIELDS = {'domain_resolver', 'tls_fragment', 'detour'}  # 剥离非连接必需及链式代理字段，确保单节点独立直连探测
IPAPI_FIELDS = 'status,country,countryCode,regionName,city,query'


# ---------- 测试配置生成 ----------

def kernel_version(singbox):
    out = subprocess.run([singbox, 'version'], capture_output=True, text=True).stdout
    m = re.search(r'version (\d+)\.(\d+)', out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def build_config(nodes, base_port, iface, new_dns):
    inbounds, rules, outs = [], [], []
    for i, n in enumerate(nodes):
        node_clean = {k: v for k, v in n.items() if k not in STRIP_FIELDS}
        if 'tls' in node_clean and isinstance(node_clean['tls'], dict):
            node_clean['tls'] = dict(node_clean['tls'])
            node_clean['tls'].pop('tls_tricks', None)
        outs.append(node_clean)
        inbounds.append({'type': 'mixed', 'tag': f'in-{i}',
                         'listen': '127.0.0.1', 'listen_port': base_port + i})
        rules.append({'inbound': [f'in-{i}'], 'outbound': n['tag']})
    outs.append({'type': 'direct', 'tag': 'direct-out'})
    cfg = {'log': {'level': 'warn'},
           'inbounds': inbounds,
           'outbounds': outs,
           'route': {'rules': rules, 'final': 'direct-out'}}
    if new_dns:  # sing-box >= 1.12 的新式 DNS 语法
        cfg['dns'] = {'servers': [{'type': 'udp', 'tag': 'dns-main',
                                   'server': '223.5.5.5', 'detour': 'direct-out'}],
                      'strategy': 'ipv4_only'}
        cfg['route']['default_domain_resolver'] = {'server': 'dns-main'}
    else:
        cfg['dns'] = {'servers': [{'tag': 'dns-main', 'address': '223.5.5.5',
                                   'detour': 'direct-out'}],
                      'strategy': 'ipv4_only'}
    if iface:  # 出站绑定物理网卡，绕过本机已开启的 TUN 全局接管
        cfg['route']['default_interface'] = iface
    return cfg


def strip_unknown_fields(cfg, cfg_path, singbox, max_rounds=500):
    """内核不认识的字段/取值按报错逐个修正（均为非连接必需项），直到校验通过。"""
    for _ in range(max_rounds):
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        chk = subprocess.run([singbox, 'check', '-c', cfg_path],
                             capture_output=True, text=True)
        if chk.returncode == 0:
            return True
        err = chk.stderr or chk.stdout
        m = re.search(r'decode config at .*?: ([\w.\[\]-]+): json: unknown field', err)
        if m:
            path = m.group(1)
            tokens = [t or idx for t, idx in re.findall(r'([\w-]+)|\[(\d+)\]', path)]
            node = cfg
            for t in tokens[:-1]:
                node = node[int(t)] if t.isdigit() else node[t]
            del node[tokens[-1]]
            print(f'  剥离不兼容字段: {path}', flush=True)
            continue
        m = re.search(r'parse outbound\[(\d+)\]: unknown uTLS fingerprint: (\S+)', err)
        if m:
            i = int(m.group(1))
            cfg['outbounds'][i]['tls']['utls']['fingerprint'] = 'chrome'
            print(f'  outbounds[{i}] 指纹 {m.group(2)} -> chrome', flush=True)
            continue
        print('配置校验失败：')
        print(err[:3000])
        return False


# ---------- 数据源查询与解析 ----------

def via(port):
    p = f'http://127.0.0.1:{port}'
    return {'http': p, 'https': p}


def fetch(url, port=None, js=True, tries=2, timeout=(6, 10)):
    for _ in range(tries):
        try:
            r = requests.get(url, proxies=via(port) if port else None,
                             timeout=timeout,
                             headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            if r.status_code == 200:
                return r.json() if js else r.text
        except Exception:
            time.sleep(0.4)
    return None


def p_cf(t):
    if not t:
        return None
    kv = dict(l.split('=', 1) for l in t.strip().splitlines() if '=' in l)
    if not kv.get('ip'):
        return None
    return {'ip': kv.get('ip'), 'cc': kv.get('loc'), 'city': '', 'colo': kv.get('colo')}


def p_ipapi(j):
    if not j or j.get('status') != 'success':
        return None
    return {'ip': j.get('query'), 'cc': j.get('countryCode'),
            'city': j.get('city') or '', 'region': j.get('regionName') or '',
            'country_zh': j.get('country') or ''}


def p_ipinfo(j):
    if not j or not j.get('country'):
        return None
    return {'ip': j.get('ip'), 'cc': j.get('country'), 'city': j.get('city') or ''}


def p_ipsb(j):
    if not j or not j.get('country_code'):
        return None
    return {'ip': j.get('ip'), 'cc': j.get('country_code'), 'city': j.get('city') or ''}


def p_ipwho(j):
    if not j or not j.get('success', True) or not j.get('country_code'):
        return None
    return {'ip': j.get('ip'), 'cc': j.get('country_code'), 'city': j.get('city') or ''}


# 本机直连反查（代理侧查询失败时兜底补票；Cloudflare 无法反查）
DIRECT_LOOKUP = {
    'ip-api': lambda ip: p_ipapi(fetch(f'http://ip-api.com/json/{ip}?lang=zh-CN&fields={IPAPI_FIELDS}')),
    'ipinfo': lambda ip: p_ipinfo(fetch(f'https://ipinfo.io/{ip}/json')),
    'maxmind': lambda ip: p_ipsb(fetch(f'https://api.ip.sb/geoip/{ip}')),
    'ipwhois': lambda ip: p_ipwho(fetch(f'https://ipwho.is/{ip}')),
}


def probe_node(port, tag):
    src = {}
    src['cloudflare'] = p_cf(fetch('https://www.cloudflare.com/cdn-cgi/trace', port, js=False))
    src['ip-api'] = p_ipapi(fetch(f'http://ip-api.com/json/?lang=zh-CN&fields={IPAPI_FIELDS}', port))
    # 两个探针都不通 → 离线，不再浪费时间
    if src['cloudflare'] is None and src['ip-api'] is None:
        return {'tag': tag, 'status': 'offline', 'sources': {}}
    src['ipinfo'] = p_ipinfo(fetch('https://ipinfo.io/json', port))
    src['maxmind'] = p_ipsb(fetch('https://api.ip.sb/geoip', port))
    src['ipwhois'] = p_ipwho(fetch('https://ipwho.is/', port))

    ips = [r['ip'] for r in src.values() if r and r.get('ip')]
    ip_counts = Counter(ips).most_common()
    exit_ip = ip_counts[0][0] if ip_counts else None
    split_exit = len(set(ips)) > 1

    if exit_ip:
        for name, lookup in DIRECT_LOOKUP.items():
            if src.get(name) is None:
                r = lookup(exit_ip)
                if r:
                    r['via'] = 'direct'
                    src[name] = r
    return {'tag': tag, 'status': 'ok', 'port': port, 'exit_ip': exit_ip,
            'split_exit': split_exit, 'sources': src}


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description='代理节点出口地理检测')
    ap.add_argument('--config', required=True, help='sing-box 配置文件路径')
    ap.add_argument('--singbox', required=True, help='本机 sing-box 内核路径')
    ap.add_argument('--workdir', default=None, help='工作目录（默认为配置同目录下 proxy-geo-work）')
    ap.add_argument('--iface', default=None, help='物理网卡名（本机开 TUN 时必须指定以绕过）')
    ap.add_argument('--base-port', type=int, default=42001, help='本地测试端口起始值')
    a = ap.parse_args()

    config = os.path.abspath(a.config)
    workdir = os.path.abspath(a.workdir or
                              os.path.join(os.path.dirname(config), 'proxy-geo-work'))
    os.makedirs(workdir, exist_ok=True)

    d = json.load(open(config, encoding='utf-8'))
    if 'outbounds' not in d:
        print('未找到 outbounds，仅支持 sing-box 格式；Clash 配置请按 SKILL.md 适配解析层')
        sys.exit(1)
    nodes = [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]
    if not nodes:
        print('配置中没有可检测的节点')
        sys.exit(1)

    ver = kernel_version(a.singbox)
    new_dns = ver >= (1, 12)
    print(f'内核 sing-box {ver[0]}.{ver[1]}，共 {len(nodes)} 个节点，生成测试配置...', flush=True)
    cfg = build_config(nodes, a.base_port, a.iface, new_dns)
    cfg_path = os.path.join(workdir, 'test_config.json')
    if not strip_unknown_fields(cfg, cfg_path, a.singbox):
        sys.exit(1)
    save_session(workdir, {'config': config, 'singbox': a.singbox, 'iface': a.iface,
                           'base_port': a.base_port, 'format': 'sing-box'})

    proc = start_kernel(a.singbox, cfg_path, workdir, 'singbox.log', a.base_port)
    print('内核已启动，开始并行检测...', flush=True)

    recs = [None] * len(nodes)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(probe_node, a.base_port + i, n['tag']): i
                for i, n in enumerate(nodes)}
        done = 0
        for f in as_completed(futs):
            i = futs[f]
            try:
                r = vote(f.result())
            except Exception as e:
                r = {'tag': nodes[i]['tag'], 'status': 'error', 'error': repr(e)}
            recs[i] = r
            done += 1
            if r['status'] == 'ok':
                print(f"[{done}/{len(nodes)}] {r['tag']} -> {r['cc']} {r['country_zh']} "
                      f"{r['city_zh']} 票{r['votes']}/{r['answered']} {r['conf']} "
                      f"colo={r['colo'] or '-'}", flush=True)
            else:
                print(f"[{done}/{len(nodes)}] {r['tag']} -> {r['status']}", flush=True)

    # 第二轮：间隔后复测出口 IP，识别动态/漂移出口
    print('第二轮出口稳定性复测...', flush=True)
    time.sleep(10)

    def recheck_ip(i):
        t = p_cf(fetch('https://www.cloudflare.com/cdn-cgi/trace', a.base_port + i, js=False))
        return i, (t or {}).get('ip')

    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(recheck_ip, i) for i, r in enumerate(recs)
                               if r['status'] == 'ok']):
            i, ip2 = f.result()
            recs[i]['exit_ip_2nd'] = ip2
            recs[i]['exit_stable'] = (ip2 == recs[i]['exit_ip']) if ip2 else None

    proc.terminate()
    for i, n in enumerate(nodes):  # 关联指纹：后续脚本靠它匹配节点，不怕外部改名
        recs[i]['fp'] = fp_of(n)
    with open(os.path.join(workdir, 'probe_result.json'), 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)

    n_ok = sum(1 for r in recs if r['status'] == 'ok')
    n_high = sum(1 for r in recs if r.get('conf') == 'high')
    n_med = sum(1 for r in recs if r.get('conf') == 'medium')
    n_low = sum(1 for r in recs if r.get('conf') == 'low')
    print(f'完成，用时 {time.time() - t0:.0f}s：在线 {n_ok}（高 {n_high} / 中 {n_med} / 低 {n_low}），'
          f'离线或异常 {len(recs) - n_ok}。结果已写入 probe_result.json', flush=True)
    if n_med + n_low:
        print('存在中/低置信节点：先运行 recheck.py 补票复核，仍存疑再用 latency_arbiter.py 物理仲裁')


if __name__ == '__main__':
    main()
