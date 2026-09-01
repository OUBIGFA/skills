# -*- coding: utf-8 -*-
"""
按地区排序 + 统一命名（不做地理检测，只从现有节点名解析地区）。

支持通用标准格式（零硬编码）：
- 标准格式1: {emoji} {国家}_{编号}[手动内容]
  例如: 🇭🇰 香港_1、🇺🇸 美国_1🟩、🇭🇰 香港_11_base、🇺🇸 美国_8_USAI❇️
- 标准格式2: {emoji} {国家}_{地区}_{编号}[手动内容]
  例如: 🇯🇵 日本_东京_1、🇺🇸 美国_洛杉矶_2_USAI❇️、🇨🇳 中国_合肥_1

凡编号后的内容（如 🟩、🔴、_USAI❇️、_base、-专线 等）均视为用户手动添加的自定义内容，
全部通用、完整保留，绝不硬编码任何关键字，绝不误将编号后依附的符号误判为城市。

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'C:\Users\BIGFA\.gemini\config\skills\proxy-geo-rename\scripts')

from common import ensure_utf8_stdout, reorder_outbounds
from geodata import (CITY_REGION_FIX, CITY_ZH, COUNTRY_ZH, flag, region_rank,
                     trim_admin)
from probe import NODE_TYPES

ensure_utf8_stdout()

UNKNOWN = ('UNK', '🏳️ 未知')
ZH2CC = {v: k for k, v in COUNTRY_ZH.items()}
ZH_KEYS = sorted(ZH2CC, key=lambda x: (x == '中国', -len(x)))
ISO_RE = re.compile(r'(?:^|[_\- ])([A-Z]{2})(?:[_\- ]|$)')
FLAG_RE = re.compile(r'^([\U0001F1E6-\U0001F1FF]{2}|🏳️|\U0001F3F3\uFE0F?)\s*([^_]+)_(.*)$')
CITY_VOCAB = sorted(set(CITY_ZH.values()), key=len, reverse=True)
EN_CITY = {
    'sanjose': '圣何塞', 'newyork': '纽约', 'losangeles': '洛杉矶',
    'frankfurt': '法兰克福', 'amsterdam': '阿姆斯特丹', 'singapore': '新加坡',
    'tokyo': '东京', 'osaka': '大阪', 'seoul': '首尔', 'taipei': '台北',
    'hongkong': '香港', 'chicago': '芝加哥', 'dallas': '达拉斯',
    'seattle': '西雅图', 'miami': '迈阿密',
    'paris': '巴黎', 'london': '伦敦', 'madrid': '马德里', 'warsaw': '华沙',
    'fremont': '弗里蒙特', 'hefei': '合肥',
    'bucharest': '布加勒斯特', 'belgrade': '贝尔格莱德', 'montreal': '蒙特利尔',
    'ankara': '安卡拉', 'taoyuan': '桃园', 'taichung': '台中', 'kaohsiung': '高雄',
    'yokohama': '横滨', 'fukuoka': '福冈', 'nagoya': '名古屋', 'vienna': '维也纳',
    'zurich': '苏黎世', 'geneva': '日内瓦', 'toronto': '多伦多', 'vancouver': '温哥华',
    'sydney': '悉尼', 'melbourne': '墨尔本', 'helsinki': '赫尔辛基',
    'stockholm': '斯德哥尔摩', 'oslo': '奥斯陆', 'copenhagen': '哥本哈根',
    'dublin': '都柏林', 'milan': '米兰', 'rome': '罗马', 'berlin': '柏林',
    'munich': '慕尼黑', 'hamburg': '汉堡', 'panamacity': '巴拿马城',
    'phoenix': '凤凰城', 'buffalo': '水牛城', 'falkenstein': '法尔肯施泰因',
    'stpetersburg': '圣彼得堡', 'nuremberg': '纽伦堡', 'nuernberg': '纽伦堡',
    'gravelines': '格拉沃利讷'
}
IATA_CITY = {
    'LAX': '洛杉矶', 'SJC': '圣何塞', 'MIA': '迈阿密', 'SFO': '旧金山',
    'JFK': '纽约', 'EWR': '纽约', 'ORD': '芝加哥', 'DFW': '达拉斯',
    'SEA': '西雅图', 'NRT': '东京', 'HND': '东京', 'KIX': '大阪',
    'ICN': '首尔', 'TPE': '台北', 'HKG': '香港', 'SIN': '新加坡',
    'FRA': '法兰克福', 'LHR': '伦敦', 'CDG': '巴黎', 'AMS': '阿姆斯特丹'
}
IP_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$|^\[?[0-9a-f:]+\]?:\d+$', re.I)
PROVIDER_RE = re.compile(
    r'(?:阿里|腾讯|华为|谷歌|亚马逊|微软|甲骨文|天翼|移动|联通|百度|京东)云'
    r'|aws|azure|gcp|oracle|hetzner|contabo|ovh|linode|digitalocean|vultr'
    r'|justhost|cloudflare|cdn|节点|bandwagon|racknerd|pfinal|telecom', re.I)
PROTOCOL_NOISE_RE = re.compile(
    r'\b(?:vmess|vless|trojan|ss|shadowsocks|hysteria2?|hy2?|tuic|wireguard|wg|http|socks5?|anytls|reality)\b', re.I)


def _extract_sep_content(extra):
    """提取编号后的连接符与自定义手动内容（容错处理历史遗留追加）"""
    if not extra:
        return '', ''
    # 容错：去除之前脚本错误在已有后缀后再次追加的末尾 _数字（例如 1🟩_1 -> 提取 '🟩'）
    m_fix = re.match(r'^([^_\d]+)_\d+$', extra)
    if m_fix:
        return '', m_fix.group(1)
    if extra.startswith('_'):
        return '_', extra[1:]
    elif extra.startswith('-'):
        return '-', extra[1:]
    elif extra.startswith(' '):
        return ' ', extra[1:]
    else:
        return '', extra


def parse_standard_tag(tag):
    """
    通用、健壮的标准命名解析器（无任何硬编码关键字）：
    标准格式1: {emoji} {国家}_{编号}[手动内容]
             例如: 🇭🇰 香港_1, 🇺🇸 美国_1🟩, 🇭🇰 香港_11_base, 🇺🇸 美国_8_USAI❇️
    标准格式2: {emoji} {国家}_{地区}_{编号}[手动内容]
             例如: 🇯🇵 日本_东京_1, 🇺🇸 美国_洛杉矶_2_USAI❇️, 🇨🇳 中国_合肥_1

    返回 dict 或 None
    """
    m = FLAG_RE.match(tag.strip())
    if not m:
        return None

    flag_symbol, country_str, rest = m.groups()
    country_str = country_str.strip()

    # 解析国家代码 cc
    if flag_symbol in ('🏳️', '🏳'):
        cc = None
    elif len(flag_symbol) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in flag_symbol):
        cc = ''.join(chr(ord(c) - 0x1F1E6 + ord('A')) for c in flag_symbol)
    else:
        cc = None

    if not cc or cc not in COUNTRY_ZH:
        for k, v in COUNTRY_ZH.items():
            if v == country_str:
                cc = k
                break

    # 格式1: 国家_编号[手动内容] -> rest 以数字开头（如 1, 11_base, 1🟩）
    m_num = re.match(r'^(\d+)(.*)$', rest, re.DOTALL)
    if m_num:
        num_str = m_num.group(1)
        extra = m_num.group(2)
        sep, content = _extract_sep_content(extra)
        return {
            'standard': True,
            'cc': cc,
            'country': country_str,
            'city': '',
            'num': int(num_str),
            'sep': sep,
            'content': content
        }

    # 格式2: 国家_地区_编号[手动内容] -> rest 为 地区_编号[手动内容]
    # 地区段首字符不能是数字
    m_city = re.match(r'^([^\d_][^_]*)_(\d+)(.*)$', rest, re.DOTALL)
    if m_city:
        city_str = m_city.group(1).strip()
        num_str = m_city.group(2)
        extra = m_city.group(3)
        sep, content = _extract_sep_content(extra)
        return {
            'standard': True,
            'cc': cc,
            'country': country_str,
            'city': city_str,
            'num': int(num_str),
            'sep': sep,
            'content': content
        }

    return None


def format_tag(cc, country, city, num, manual_content, sep='_'):
    """按规范组装节点名称：无城市为 {国旗} {国家}_{编号}{自定义}；有城市为 {国旗} {国家}_{城市}_{编号}{自定义}"""
    if cc:
        em = flag(cc)
        czh = country or COUNTRY_ZH.get(cc, cc)
        head = f"{em} {czh}" if em else f"{cc}_{czh}"
    else:
        head = UNKNOWN[1]

    if city:
        base = f"{head}_{city}_{num}"
    else:
        base = f"{head}_{num}"

    if not manual_content:
        return base

    if sep == '':
        return f"{base}{manual_content}"
    else:
        s = sep if sep else '_'
        return f"{base}{s}{manual_content}"


def parse_position(tag, cc):
    """取「具体位置」（用于非标准命名的后备提取）。数字开头的段绝不误判为位置。"""
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
            if not s or re.match(r'^\d', s) or IP_RE.match(s) or s.upper() in COUNTRY_ZH:
                continue
            if PROVIDER_RE.search(s) or PROTOCOL_NOISE_RE.search(s):
                continue
            pos = trim_admin(s)
            return '' if pos == czh else pos
        return ''
    if len(segs) >= 3 and segs[0].upper() == cc and czh and segs[1] == czh:
        for s in segs[2:]:
            if not s or re.match(r'^\d', s) or IP_RE.match(s) or s.upper() in COUNTRY_ZH:
                continue
            if PROVIDER_RE.search(s) or PROTOCOL_NOISE_RE.search(s):
                continue
            pos = trim_admin(s)
            return '' if pos == czh else pos
        return ''
    segs_all = [s.strip() for s in re.split(r'[_\-\s/]+', tag)]
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
    """从节点名解析地区码。"""
    tag = re.sub(r'#\d+', '', tag)
    m_pipe = re.match(r'^([a-zA-Z]{2})\|', tag)
    if m_pipe:
        cc_cand = m_pipe.group(1).upper()
        if cc_cand in COUNTRY_ZH:
            return cc_cand
    for name in ZH_KEYS:
        if name in tag:
            return ZH2CC[name]
    m = re.search(r'([\U0001F1E6-\U0001F1FF])([\U0001F1E6-\U0001F1FF])', tag)
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
                   ('United States', 'US'), ('Taiwan', 'TW'),
                   ('Canada', 'CA'), ('Netherlands', 'NL'), ('Australia', 'AU'),
                   ('Singapore', 'SG'), ('Hong Kong', 'HK'), ('HongKong', 'HK'),
                   ('Malaysia', 'MY'), ('Thailand', 'TH'), ('Vietnam', 'VN'),
                   ('Indonesia', 'ID'), ('Philippines', 'PH'), ('Brazil', 'BR')):
        if en.lower() in tag.lower():
            return cc
    flat = re.sub(r'[^a-z]', '', tag.lower())
    if any(k in flat for k in ('sanjose', 'losangeles', 'seattle', 'fremont', 'chicago', 'dallas', 'miami', 'newyork')):
        return 'US'
    if node:
        srv = node.get('server', '')
        if srv == '62.210.124.146':
            return 'FR'
        if srv == '107.172.67.52':
            return 'US'
    return None


def detect_suffix(tag, cc=None):
    """
    提取自定义后缀标记（零硬编码白名单）：
    优先从标准命名解析；非标准命名中剔除国名、城市、协议及云厂商噪音后保留全部用户标记。
    """
    std = parse_standard_tag(tag)
    if std and std['content']:
        return std['content']

    tag_clean = re.sub(r'#\d+', '', tag)
    # 剔除国旗
    tag_clean = re.sub(r'[\U0001F1E6-\U0001F1FF]{2}|🏳️|\U0001F3F3\uFE0F?', '', tag_clean)
    czh = COUNTRY_ZH.get(cc, '')
    if czh:
        tag_clean = tag_clean.replace(czh, '')
    # 剔除已知城市词
    for c in CITY_VOCAB:
        if c in tag_clean:
            tag_clean = tag_clean.replace(c, '')
    for k in EN_CITY:
        tag_clean = re.sub(rf'\b{k}\b', '', tag_clean, flags=re.I)

    segs = [s.strip() for s in re.split(r'[_\-\s/]+', tag_clean)]
    out = []
    for s in segs:
        if not s or s.isdigit() or IP_RE.match(s) or PROVIDER_RE.search(s) or PROTOCOL_NOISE_RE.search(s):
            continue
        if s not in out:
            out.append(s)
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
        # 优先使用通用标准格式解析器
        std = parse_standard_tag(tag)
        if std:
            cc = std['cc']
            pos = std['city']
            suf = std['content']
            sep = std['sep']
            country = std['country']
        else:
            cc = detect_cc(tag, o)
            pos = parse_position(tag, cc) if cc else ''
            fix = CITY_REGION_FIX.get(pos)
            if fix and fix != cc:
                cc = fix
            suf = detect_suffix(tag, cc)
            sep = '_'
            country = COUNTRY_ZH.get(cc, '') if cc else ''

        plan.append({
            'i': i,
            'tag': tag,
            'cc': cc,
            'city': pos,
            'suf': suf,
            'sep': sep,
            'country': country,
            'obj': o
        })

    # 排序：按地区顺位 -> 国家代码 -> 城市 -> 原始先后次序
    plan.sort(key=lambda p: (region_rank(p['cc']), p['cc'] or '', p['city'], p['i']))

    counters = {}
    rows = []
    for p in plan:
        if not p['cc'] and (a.keep_unknown or a.keep_names):
            p['new_tag'] = p['tag']
            rows.append((p['tag'], p['tag'], '（保留原名）'))
            continue
        if a.keep_names:
            p['new_tag'] = p['tag']
            rows.append((p['tag'], p['tag'], COUNTRY_ZH.get(p['cc'], '')))
            continue

        key = (p['cc'] or UNKNOWN[0], p['city'])
        counters[key] = counters.get(key, 0) + 1
        new = format_tag(p['cc'], p['country'], p['city'], counters[key], p['suf'], p['sep'])
        p['new_tag'] = new
        rows.append((p['tag'], new, COUNTRY_ZH.get(p['cc'], '未知')))

    finals = [p['new_tag'] for p in plan]
    assert len(finals) == len(set(finals)), f'结果存在重名: {[t for t in finals if finals.count(t) > 1]}'

    changed = sum(1 for p in plan if p['tag'] != p['new_tag'])
    for old, new, region in rows:
        print(f'{old}  ->  {new}' if old != new else f'{old}  （名称不变）')
    print(f'\n共 {len(rows)} 个节点，改名 {changed} 个，已按地区排序')

    if not a.apply:
        print('\n[预览] 未写回。确认无误后加 --apply')
        return

    # 直接在每个节点对象上赋值新 tag，杜绝由于输入配置存在重复 tag 导致的写回冲突
    for p in plan:
        p['obj']['tag'] = p['new_tag']
        if p['obj'].get('type') in NODE_TYPES:
            p['obj'].pop('detour', None)

    # 建立映射表用于更新分组、规则、DNS
    mapping = {p['tag']: p['new_tag'] for p in plan}
    finals_set = set(finals)
    other_outbound_tags = {o.get('tag') for o in d['outbounds'] if o.get('type') not in NODE_TYPES}

    for o in d['outbounds']:
        if o.get('outbounds'):
            valid_non_nodes = [t for t in o['outbounds'] if t in other_outbound_tags]
            o['outbounds'] = valid_non_nodes + finals
        if o.get('default') in mapping:
            o['default'] = mapping[o['default']]
        elif o.get('detour') in mapping:
            o['detour'] = mapping[o['detour']]

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
