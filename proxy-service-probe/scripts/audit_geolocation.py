#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仅做属地抽查，不测速、不改订阅；ip.cx 为不参与仲裁的留出复核来源。"""
import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from core.egress_geo import (fetch_evidence, normalize_country_code, parse_gemini_region,
                             probe_egress, probe_geolocation, public_ip)
from core.mihomo_runner import detect_physical_interface, find_mihomo_bin, node_listeners
from core.parsers import load_proxies


def named_country(name):
    match = re.search(r'([\U0001F1E6-\U0001F1FF]{2})', name or '')
    return normalize_country_code(''.join(chr(ord(c) - 127397) for c in match[1])) if match else None


def select_sample(proxies, count, seed, include=()):
    """原国旗仅用于分层抽样，不参与属地判定。链式节点需原拓扑，不能悄悄拆链抽查。"""
    eligible = [p for p in proxies if not p.get('dialer-proxy') and not p.get('detour')]
    by_name = {p['name']: p for p in eligible}
    selected = []
    for name in include:
        if name not in by_name:
            raise ValueError(f'指定节点不存在或为链式节点，不能在直连审计中测试: {name}')
        if by_name[name] not in selected:
            selected.append(by_name[name])
    if len(selected) > count or count > len(eligible):
        raise ValueError('抽样数量不足或必选节点超过 count')
    groups = defaultdict(list)
    for p in eligible:
        if p not in selected:
            groups[named_country(p['name']) or 'UNK'].append(p)
    rng = random.Random(seed)
    countries = sorted(groups, key=lambda cc: (-len(groups[cc]), cc))
    for cc in countries:
        rng.shuffle(groups[cc])
    while len(selected) < count:
        for cc in countries:
            if groups[cc] and len(selected) < count:
                selected.append(groups[cc].pop())
    return selected


def parse_ipcx(text):
    ip_match = re.search(r'id=["\']current-ip["\'][^>]*>\s*([^<]+)', text)
    row = re.search(r'国家/地区</span>(.*?)</div>', text, re.S)
    code = re.search(r'class=["\']dim mono["\']>\s*([A-Z]{2})\s*</span>', row[1]) if row else None
    ip = public_ip(ip_match[1]) if ip_match else None
    cc = normalize_country_code(code[1]) if code else None
    return {"ip": ip, "country_code": cc, "status": 'observed' if ip and cc else 'missing_marker'}


def review_status(row):
    if not row.get('exit_ip'):
        return 'offline'
    if row.get('runner_ip_match'):
        return 'runner_ip_match'
    decision = row['geo_decision']
    ipcx, gemini = row['ipcx_review'], row['gemini_review']
    if not decision['egress_stable'] or decision['is_pool']:
        return 'unstable_egress'
    if ipcx.get('ip') and ipcx['ip'] not in decision['observed_ips']:
        return 'different_review_egress'
    if decision.get('is_poisoned') and ipcx.get('country_code') == row['cc'] and \
            gemini.get('country_code') == decision.get('poisoned_cc'):
        return 'verified_sent_to_china' if decision['poisoned_cc'] == 'CN' else 'verified_geo_poisoning'
    if row['cc'] == 'UNK' and ipcx.get('country_code') == decision.get('geoip_cc') and \
            gemini.get('country_code') == row['google_region'].get('country_code') and gemini.get('country_code'):
        return 'region_conflict_confirmed'
    if ipcx.get('country_code') and ipcx['country_code'] != row['cc']:
        return 'disagreement'
    if gemini.get('country_code') and gemini['country_code'] != row['google_region'].get('country_code'):
        return 'google_changed'
    if ipcx.get('country_code') == row['cc'] and gemini.get('country_code') == row['cc']:
        return 'verified_with_db_conflict' if decision['conflict'] else 'verified'
    return 'insufficient_review_evidence'


def run_review(item, runner_ips, evidence_dir):
    index, (port, proxy, *_) = item
    url = f'http://127.0.0.1:{port}'
    proxies = {'http': url, 'https': url}
    row = {'index': index, 'original_name': proxy['name'], 'original_cc': named_country(proxy['name']),
           'protocol': proxy['type']}
    row.update(probe_geolocation(proxies))
    row['runner_ip_match'] = bool(set(row['geo_decision']['observed_ips']) & runner_ips)
    if row['exit_ip']:
        evidence, text = fetch_evidence('https://ip.cx/', proxies, timeout=(4, 10))
        if evidence.get('error') in ('ReadTimeout', 'ConnectTimeout', 'ConnectionError'):
            first_attempt = evidence
            evidence, text = fetch_evidence('https://ip.cx/', proxies, timeout=(4, 15))
            evidence['previous_attempt'] = first_attempt
        row['ipcx_review'] = {**evidence, **parse_ipcx(text)} if evidence['status'] == 'ok' else evidence
        if text:
            path = evidence_dir / f'{index:02d}-ipcx.html'
            path.write_text(text, encoding='utf-8')
            row['ipcx_review']['snapshot'] = path.name
        evidence, text = fetch_evidence('https://gemini.google.com/', proxies, timeout=(4, 10))
        row['gemini_review'] = {**evidence, **parse_gemini_region(text)} if evidence['status'] == 'ok' else evidence
        # 页面匿名取回，只保留匹配片段和指纹，不写整页大体积运行数据。
        fragments = re.findall(r'.{0,60},\s*2,\s*1,\s*200,\s*\\*"[A-Z]{3}\\*".{0,60}', text)
        row['gemini_review']['marker_excerpts'] = fragments[:5]
    else:
        row['ipcx_review'] = row['gemini_review'] = {'status': 'not_probed_no_egress'}
    row['review_status'] = review_status(row)
    row['name_mismatch'] = bool(row['cc'] != 'UNK' and row['original_cc'] != row['cc'])
    return row


def markdown_report(report):
    lines = ['# IP 属地抽查', '', f"- 时间：{report['started_at']}",
             f"- 输入：`{report['input']}`（SHA-256：`{report['input_sha256']}`）",
             f"- 样本：{len(report['results'])}；随机种子：{report['seed']}；按原国旗分层，必选节点先加入。",
             '- ip.cx 不参与自动判定，只作为留出来源；Gemini 另发一次无 Cookie 请求复核。',
             '- 仅检测 IP 属地；未测速、未重新检测 AI/流媒体能力，未改原订阅。',
             '- Google 服务地区不等于可证明的物理机房。多源一致也不是地理真值保证。',
             f"- 状态统计：`{json.dumps(report['summary'], ensure_ascii=False)}`", '',
             '| # | 原节点 | 出口 IPv4/IPv6 | 新判定 | GeoIP / CF loc | ip.cx | Gemini复核 | 状态 |',
             '|---|---|---|---|---|---|---|---|']
    for r in report['results']:
        d = r['geo_decision']
        ips = '<br>'.join(d['observed_ips']) or '—'
        info = '/'.join(f"{x['provider']}:{x.get('cc', x.get('error', '?'))}" for x in r['ip_info']['records'])
        lines.append(f"| {r['index']} | {r['original_name']} | {ips} | {r['cc']} ({d['confidence']}) | {info}; CF:{d['cf_loc'] or '—'} | {r['ipcx_review'].get('country_code', '—')} | {r['gemini_review'].get('country_code', '—')} | {r['review_status']} |")
    lines += ['', '## 解读', '',
              '- `verified`：出口稳定，ip.cx、再次请求的 Gemini 与自动判定一致。',
              '- `verified_with_db_conflict`：以上复核一致，但第三方库或 Google 子服务仍有分歧，保留待复核标志。',
              '- `verified_sent_to_china`：ip.cx 确认实际属地，Gemini 确认送中；保留属地，标 `_⚠️CN` 并剥离 AI 全通资格。',
              '- `verified_geo_poisoning`：同类受限地区污染，沿用已有污染标记。',
              '- `region_conflict_confirmed`：IP 库属地与非受限 Google 服务地区的分歧被复核重现，自动国别保留未知，不强改国旗。',
              '- `disagreement` / `google_changed`：复核分歧，不算通过。',
              '- `offline` / `insufficient_review_evidence`：不可达或证据不足，不算准确。',
              '- `unstable_egress` / `different_review_egress`：出口轮换或按目的站分流，不能混合不同 IP 投票。',
              '- 详细 HTTP 状态、时间、目标/回显 IP、响应 SHA-256 见同名 JSON；ip.cx 原页见 evidence 目录。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--seed', type=int, default=20260923)
    parser.add_argument('--include', action='append', default=[])
    parser.add_argument('--mihomo', required=True)
    parser.add_argument('--iface')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=5)
    args = parser.parse_args(argv)
    if min(args.count, args.workers, args.batch_size) < 1:
        parser.error('count/workers/batch-size 必须为正数')
    binary = find_mihomo_bin(args.mihomo)
    if not binary:
        parser.error('Mihomo 内核不存在')
    source, output = Path(args.input).resolve(), Path(args.report).resolve()
    if not source.is_file() or source == output:
        parser.error('input 必须为本地文件，report 不得覆盖输入')
    if output.exists():
        parser.error('报告已存在，请指定新路径，避免覆盖已有抽查证据')
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    proxies = load_proxies(str(source))
    sample = select_sample(proxies, args.count, args.seed, args.include)
    iface = args.iface or detect_physical_interface()
    if sys.platform == 'win32' and not iface:
        parser.error('未检测到物理网卡，请显式传 --iface')
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_dir = output.with_suffix('.evidence')
    evidence_dir.mkdir(exist_ok=False)
    report = {'schema_version': 2, 'started_at': datetime.now(timezone.utc).isoformat(),
              'input': str(source), 'input_sha256': source_hash, 'seed': args.seed,
              'iface': iface, 'scope': 'geolocation_only', 'results': [],
              'sample_names': [p['name'] for p in sample]}
    # 通过同一隔离内核的 DIRECT 出站绑定物理网卡，不把 TUN 出口当本机基线。
    with node_listeners([{'name': 'audit-baseline', 'type': 'direct'}], iface=iface, mihomo_bin=binary) as targets:
        url = f'http://127.0.0.1:{targets[0][0]}'
        baseline = probe_egress({'http': url, 'https': url})
    report['baseline'] = baseline
    runner_ips = set(baseline['observed_ips'])
    if not runner_ips:
        raise RuntimeError('无法建立绑定物理网卡的直连基线，停止以避免伪验证')
    for start in range(0, len(sample), args.batch_size):
        with node_listeners(sample[start:start + args.batch_size], iface=iface, mihomo_bin=binary) as targets:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                rows = pool.map(lambda item: run_review(item, runner_ips, evidence_dir), enumerate(targets, start + 1))
                for row in rows:
                    report['results'].append(row)
                    report['summary'] = dict(Counter(r['review_status'] for r in report['results']))
                    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(f"[{row['index']}/{len(sample)}] {row['original_name']} -> {row['cc']} : {row['review_status']}", flush=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError('检测期间输入文件发生变化，报告样本不再对应当前输入')
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['input_unchanged'] = True
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    output.with_suffix('.md').write_text(markdown_report(report), encoding='utf-8')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
