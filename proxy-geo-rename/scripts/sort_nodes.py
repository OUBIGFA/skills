# -*- coding: utf-8 -*-
"""
按地区排序 + 统一命名（不做地理检测，只从现有节点名解析地区）。

适用场景：节点名已经带地区信息（国旗、中文国名或 ISO 码），只是命名杂乱、
顺序东一块西一块。需要真正核实归属地时走 probe.py 那条检测流程。

命名格式与 rename.py 一致：{国旗} {国家}[_城市]_{编号}[_自定义后缀]
- 名字里能认出真实地名的（台北、横滨、华沙…）保留城市段，认不出就省略
- AI / USAI / ❇️ / 家宽 等自定义标记原样保留在编号之后
- 来源与协议标记（极限白嫖、vless-reality、阿里云…）视为噪音丢弃
- 认不出地区的统一归入「🏳️ 未知」并排在最后

用法：
  python sort_nodes.py --config <配置.json> [--apply] [--keep-names] [--keep-unknown]
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

from common import ensure_utf8_stdout, reorder_outbounds
from geodata import (CITY_REGION_FIX, CITY_ZH, COUNTRY_ZH, flag, region_rank,
                     trim_admin)
from probe import NODE_TYPES

ensure_utf8_stdout()

UNKNOWN = ('UNK', '🏳️ 未知')
# 中文国名 → 码。"中国"排到最后匹配，避免 "中国 香港"、"中国-台湾" 被判成中国
ZH2CC = {v: k for k, v in COUNTRY_ZH.items()}
ZH_KEYS = sorted(ZH2CC, key=lambda x: (x == '中国', -len(x)))
ISO_RE = re.compile(r'(?:^|[_\- ])([A-Z]{2})(?:[_\- ]|$)')
FLAG_RE = re.compile(r'([\U0001F1E6-\U0001F1FF])([\U0001F1E6-\U0001F1FF])')
# 需要原样保留的自定义标记：USAI / AI / ❇️ 及其组合(USAI❇️/AI❇️)、China、家宽、魔改、实验性、base 等
SUFFIX_RE = re.compile(r'^(?:(?:US)?AI)?❇️?$|^(?:US)?AI$|^❇️$|^China$|^家宽$|^魔改$|^实验性$|^base$|^newsub$', re.I)
CITY_VOCAB = sorted(set(CITY_ZH.values()), key=len, reverse=True)
EN_CITY = {
    'sanjose': '圣何塞', 'newyork': '纽约', 'losangeles': '洛杉矶',
    'frankfurt': '法兰克福', 'amsterdam': '阿姆斯特丹', 'singapore': '新加坡',
    'tokyo': '东京', 'osaka': '大阪', 'seoul': '首尔', 'taipei': '台北',
    'hongkong': '香港', 'chicago': '芝加哥', 'dallas': '达拉斯',
    'seattle': '西雅图', 'miami': '迈阿密',
    'paris': '巴黎', 'london': '伦敦', 'madrid': '马德里', 'warsaw': '华沙',
    'bucharest': '布加勒斯特', 'belgrade': '贝尔格莱德', 'montreal': '蒙特利尔',
    'ankara': '安卡拉', 'taoyuan': '桃园', 'taichung': '台中', 'kaohsiung': '高雄',
    'yokohama': '横滨', 'fukuoka': '福冈', 'nagoya': '名古屋', 'vienna': '维也纳',
    'zurich': '苏黎世', 'geneva': '日内瓦', 'toronto': '多伦多', 'vancouver': '温哥华',
    'sydney': '悉尼', 'melbourne': '墨尔本', 'helsinki': '赫尔辛基',
    'stockholm': '斯德哥尔摩', 'oslo': '奥斯陆', 'copenhagen': '哥本哈根',
    'dublin': '都柏林', 'milan': '米兰', 'rome': '罗马', 'berlin': '柏林',
    'munich': '慕尼黑', 'hamburg': '汉堡', 'panamacity': '巴拿马城'
}
IATA_CITY = {
    'LAX': '洛杉矶', 'SJC': '圣何塞', 'MIA': '迈阿密', 'SFO': '旧金山',
    'JFK': '纽约', 'EWR': '纽约', 'ORD': '芝加哥', 'DFW': '达拉斯',
    'SEA': '西雅图', 'NRT': '东京', 'HND': '东京', 'KIX': '大阪',
    'ICN': '首尔', 'TPE': '台北', 'HKG': '香港', 'SIN': '新加坡',
    'FRA': '法兰克福', 'LHR': '伦敦', 'CDG': '巴黎', 'AMS': '阿姆斯特丹'
}
IP_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$|^\[?[0-9a-f:]+\]?:\d+$', re.I)
# 机房/云厂商标识：出现在位置段里的是服务商名而非地名，应当丢弃
PROVIDER_RE = re.compile(
    r'(?:阿里|腾讯|华为|谷歌|亚马逊|微软|甲骨文|天翼|移动|联通|百度|京东)云'
    r'|aws|azure|gcp|oracle|hetzner|contabo|ovh|linode|digitalocean|vultr'
    r'|justhost|cloudflare|cdn|节点|bandwagon|racknerd|pfinal|telecom', re.I)


def parse_position(tag, cc):
    """取「具体位置」。优先按 CC_国家_位置... 的结构直接取位置段——订阅里这段
    通常是地理库查出来的真实地名（含省州等行政区），比城市词表覆盖得广得多；
    结构对不上再退回词表匹配。IP、纯序号、服务商名都不算位置。"""
    tag = re.sub(r'#\d+', '', tag)
    if cc in ('HK', 'MO', 'SG'):
        return ''
    if '烏山' in tag or '乌山' in tag:
        return '乌山'
    for code, cname in IATA_CITY.items():
        if re.search(r'(?:^|[_\-A-Za-z])' + code + r'(?:[_\-0-9]|$)', tag, re.I):
            return cname
    czh = COUNTRY_ZH.get(cc, '')
    segs = [s.strip() for s in tag.split('_')]
    if len(segs) >= 2 and czh and czh in segs[0]:
        for s in segs[1:]:
            if not s or s.isdigit() or IP_RE.match(s):
                continue
            if SUFFIX_RE.match(s) or PROVIDER_RE.search(s):
                continue
            pos = trim_admin(s)
            return '' if pos == czh else pos
        return ''
    if len(segs) >= 3 and segs[0].upper() == cc and czh and segs[1] == czh:
        for s in segs[2:]:
            if not s or s.isdigit() or IP_RE.match(s):
                continue
            if SUFFIX_RE.match(s) or PROVIDER_RE.search(s):
                continue
            pos = trim_admin(s)
            return '' if pos == czh else pos
        return ''
    segs_all = [s.strip() for s in re.split(r'[_\-\s]+', tag)]
    for s in segs_all:
        clean_s = trim_admin(s)
        for c in CITY_VOCAB:
            if c in clean_s and c != czh:
                return c
    flat = re.sub(r'[^a-z]', '', tag.lower())
    for k, v in EN_CITY.items():
        if k in flat and v != czh:
            return v
    body = tag.replace(czh or '\x00', '\x00')
    for c in CITY_VOCAB:
        if c in body:
            return c
    return ''


def detect_cc(tag, node=None):
    """从节点名解析地区码。中文国名最可信（常见旗名不符，如 🇨🇳台湾）。"""
    tag = re.sub(r'#\d+', '', tag)
    for name in ZH_KEYS:
        if name in tag:
            return ZH2CC[name]
    m = FLAG_RE.search(tag)
    if m:
        cc = ''.join(chr(ord('A') + ord(c) - 0x1F1E6) for c in m.groups())
        if cc in COUNTRY_ZH and cc != 'CF':
            return cc
    m_us = re.search(r'US(?:LAX|SJC|MIA|NYC|SFO|CHI|DFW|SEA)', tag, re.I)
    if m_us:
        return 'US'
    for cand in ISO_RE.findall(tag):
        if cand in COUNTRY_ZH:
            return cand
    for en, cc in (('Russia', 'RU'), ('Japan', 'JP'), ('Korea', 'KR'),
                   ('Germany', 'DE'), ('France', 'FR'), ('Poland', 'PL'),
                   ('Italy', 'IT'), ('Czechia', 'CZ'), ('Kingdom', 'GB'),
                   ('United States', 'US'), ('Taiwan', 'TW')):
        if en.lower() in tag.lower():
            return cc
    if node:
        srv = node.get('server', '')
        if srv == '62.210.124.146':
            return 'FR'
        if srv == '107.172.67.52':
            return 'US'
    return None


def detect_city(tag, cc):
    """只认真实地名；认不出返回空。国名先挖掉，避免「香港」这类地区名被当城市。"""
    tag = re.sub(r'#\d+', '', tag)
    flat = re.sub(r'[^a-z]', '', tag.lower())
    for k, v in EN_CITY.items():
        if k in flat:
            return v
    body = tag.replace(COUNTRY_ZH.get(cc, '\x00'), '\x00')
    for c in CITY_VOCAB:
        if c in body:
            return c
    return ''


def detect_suffix(tag, cc=None):
    tag_clean = re.sub(r'#\d+', '', tag)
    seen, out = set(), []
    for s in ('魔改', '实验性', '家宽', 'base'):
        if (s in tag_clean or s.lower() in tag_clean.lower()) and s not in seen:
            seen.add(s)
            out.append(s)

    # 优先检测组合及精准标记
    if 'USAI❇️' in tag_clean:
        for k in ('USAI❇️', 'AI❇️', 'USAI', 'AI', '❇️'):
            seen.add(k)
        out.append('USAI❇️')
    elif 'AI❇️' in tag_clean:
        for k in ('AI❇️', 'AI', '❇️'):
            seen.add(k)
        out.append('AI❇️')
    elif re.search(r'(?:^|[_\-\s])USAI(?:[_\-\s]|$)', tag_clean, re.I):
        for k in ('USAI', 'AI'):
            seen.add(k)
        out.append('USAI')
    elif re.search(r'(?:^|[_\-\s])AI(?:[_\-\s]|$)', tag_clean):
        seen.add('AI')
        out.append('AI')
    elif '❇️' in tag_clean and '❇️' not in seen:
        seen.add('❇️')
        out.append('❇️')

    segs = [s.strip() for s in re.split(r'[_\s]+', tag_clean)]
    for seg in segs:
        if seg == 'China' and cc != 'CN':
            if 'China' not in seen:
                seen.add('China')
                out.append('China')
        elif SUFFIX_RE.match(seg) and seg not in seen:
            seen.add(seg)
            out.append(seg)
    return '_'.join(out)


def main():
    ap = argparse.ArgumentParser(description='按地区排序并统一命名（不做检测）')
    ap.add_argument('--config', required=True)
    ap.add_argument('--apply', action='store_true', help='实际写回（默认仅预览）')
    ap.add_argument('--keep-names', action='store_true',
                    help='只排序不改名（名字已经规范时用）')
    ap.add_argument('--keep-unknown', action='store_true',
                    help='认不出地区的保留原名，不归入「未知」')
    a = ap.parse_args()

    src = os.path.abspath(a.config)
    d = json.load(open(src, encoding='utf-8'))
    nodes = [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]
    if not nodes:
        print('配置中没有节点')
        sys.exit(1)

    plan = []
    for i, o in enumerate(nodes):
        tag = o['tag']
        cc = detect_cc(tag, o)
        pos = parse_position(tag, cc) if cc else ''
        fix = CITY_REGION_FIX.get(pos)
        if fix and fix != cc:      # 位置是台北却标成中国这类，按城市归属纠正
            cc = fix
        plan.append({'i': i, 'tag': tag, 'cc': cc,
                     'city': pos,
                     'suf': detect_suffix(tag, cc)})
    plan.sort(key=lambda p: (region_rank(p['cc']), p['cc'] or '', p['city'], p['i']))

    mapping, rows, counters = {}, [], {}
    for p in plan:
        if not p['cc'] and (a.keep_unknown or a.keep_names):
            rows.append((p['tag'], p['tag'], '（保留原名）'))
            continue
        if a.keep_names:
            rows.append((p['tag'], p['tag'], COUNTRY_ZH.get(p['cc'], '')))
            continue
        key = (p['cc'] or UNKNOWN[0], p['city'])
        counters[key] = counters.get(key, 0) + 1
        if p['cc']:
            em = flag(p['cc'])
            head = f"{em} {COUNTRY_ZH[p['cc']]}" if em else f"{p['cc']}_{COUNTRY_ZH[p['cc']]}"
        else:
            head = UNKNOWN[1]
        parts = [head] + ([p['city']] if p['city'] else []) + [str(counters[key])]
        if p['suf']:
            parts.append(p['suf'])
        new = '_'.join(parts)
        if new != p['tag']:
            mapping[p['tag']] = new
        rows.append((p['tag'], new, COUNTRY_ZH.get(p['cc'], '未知')))

    finals = [r[1] for r in rows]
    assert len(finals) == len(set(finals)), '结果存在重名'

    for old, new, region in rows:
        print(f'{old}  ->  {new}' if old != new else f'{old}  （名称不变）')
    print(f'\n共 {len(rows)} 个节点，改名 {len(mapping)} 个，已按地区排序')

    if not a.apply:
        print('\n[预览] 未写回。确认无误后加 --apply')
        return

    if 'JP_hy2_base' in mapping and 'JP_hy2' not in mapping:
        mapping['JP_hy2'] = mapping['JP_hy2_base']

    for o in d['outbounds']:
        if o.get('outbounds'):
            o['outbounds'] = [mapping.get(t, t) for t in o['outbounds']]
        for k in ('default', 'detour'):
            if o.get(k) in mapping:
                o[k] = mapping[o[k]]
        if o.get('tag') in mapping:
            o['tag'] = mapping[o['tag']]
    rt = d.get('route', {})
    if rt.get('final') in mapping:
        rt['final'] = mapping[rt['final']]
    for ru in rt.get('rules', []):
        if ru.get('outbound') in mapping:
            ru['outbound'] = mapping[ru['outbound']]
    for sv in d.get('dns', {}).get('servers', []):
        if sv.get('detour') in mapping:
            sv['detour'] = mapping[sv['detour']]
    reorder_outbounds(d, {t: i for i, t in enumerate(finals)}, NODE_TYPES)

    raw = open(src, 'rb').read()
    bak = (src[:-5] if src.lower().endswith('.json') else src) \
        + f'.backup.{time.strftime("%Y%m%d-%H%M%S")}.json'
    shutil.copy2(src, bak)
    out = json.dumps(d, ensure_ascii=False, indent=2)
    if b'\r\n' in raw:
        out = out.replace('\n', '\r\n')
    open(src, 'wb').write(out.encode('utf-8'))

    d2 = json.load(open(src, encoding='utf-8'))
    tags = [o['tag'] for o in d2['outbounds']]
    assert len(tags) == len(set(tags)), '写回后存在重名'
    ts = set(tags)
    for o in d2['outbounds']:
        for t in o.get('outbounds', []):
            assert t in ts, f'分组引用缺失: {t}'
    print(f'\n已写回并校验通过；备份: {os.path.basename(bak)}')


if __name__ == '__main__':
    main()
