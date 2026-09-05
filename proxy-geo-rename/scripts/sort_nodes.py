# -*- coding: utf-8 -*-
"""
节点处理工具：默认主动去重与剥离链式代理，严格按需排序与重命名。

准则：
- 默认主动去重：自动按连接身份指纹执行去重，确保底库无重复节点（加 --keep-dup 可保留重复）。
- 默认主动剥离链式代理：自动移除代理节点上的 detour 属性，降级为直接连接（加 --keep-detour 可保留）。
- 严格不主动重命名：节点原有 Tag 100% 原样保留，仅在显式传入 --rename 时才规范化命名。
- 严格不主动排序：节点原有先后顺序 100% 原样保留，仅在显式传入 --sort 时才按地区排序。

支持通用标准格式（零硬编码）：
- 标准格式1: {emoji} {国家}_{编号}[手动内容]
  例如: 🇭🇰 香港_1、🇺🇸 美国_1🟩、🇭🇰 香港_11_base、🇺🇸 美国_8_USAI❇️
- 标准格式2: {emoji} {国家}_{地区}_{编号}[手动内容]
  例如: 🇯🇵 日本_东京_1、🇺🇸 美国_洛杉矶_2_USAI❇️、🇨🇳 中国_合肥_1

凡编号后的内容（如 🟩、🔴、_USAI❇️、_base、-专线 等）均视为用户手动添加的自定义内容，
全部通用、完整保留，绝不硬编码任何关键字，绝不误将编号后依附的符号误判为城市。

用法：
  python sort_nodes.py --config <配置.json> [--sort] [--rename] [--keep-dup] [--keep-detour] [--apply]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (NODE_TYPES, deduplicate_nodes, ensure_utf8_stdout, remap_refs,
                    reorder_outbounds, strip_node_detours, validate_config, write_config)
from geodata import (CITY_REGION_FIX, CITY_ZH, COLO, COUNTRY_ZH, flag,
                     region_rank, trim_admin)

ensure_utf8_stdout()

UNKNOWN = ('UNK', '🏳️ 未知')
ZH2CC = {v: k for k, v in COUNTRY_ZH.items()}
ZH_KEYS = sorted(ZH2CC, key=lambda x: (x == '中国', -len(x)))
ISO_RE = re.compile(r'(?:^|[_\- /])([A-Z]{2})(?=[_\- /]|$)', re.I)
FLAG_RE = re.compile(r'^([\U0001F1E6-\U0001F1FF]{2}|🏳️|\U0001F3F3\uFE0F?)\s*([^_]+)_(.*)$')
CITY_VOCAB = sorted(set(CITY_ZH.values()), key=len, reverse=True)
EN_CITY = {re.sub(r'[^a-z]', '', name.lower()): city
           for name, city in CITY_ZH.items() if name.isascii()}
IATA_CITY = {code: city for code, (city, _) in COLO.items()}
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
    for code, cname in IATA_CITY.items():
        if re.search(r'(?:^|[_\- /])' + re.escape(code) + r'(?=[_\- /0-9]|$)', tag, re.I):
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
    for cand in ISO_RE.findall(tag):
        cand = cand.upper()
        if cand in COUNTRY_ZH:
            return cand
    for code, (_, airport_cc) in COLO.items():
        if re.search(r'(?:^|[_\- /])' + re.escape(code) + r'(?=[_\- /0-9]|$)', tag, re.I):
            return airport_cc
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
    if cc:
        tag_clean = re.sub(rf'(?i)(?:^|(?<=[_\- /])){re.escape(cc)}(?=[_\- /]|$)', '', tag_clean)
    # 剔除已知城市词
    for c in CITY_VOCAB:
        if c in tag_clean:
            tag_clean = tag_clean.replace(c, '')
    for name in CITY_ZH:
        if name.isascii():
            tag_clean = re.sub(rf'(?i)(?:^|(?<=[_\- /])){re.escape(name)}(?=[_\- /]|$)', '', tag_clean)
    for code in COLO:
        tag_clean = re.sub(rf'(?i)(?:^|(?<=[_\- /])){re.escape(code)}(?=[_\- /0-9]|$)', '', tag_clean)

    segs = [s.strip() for s in re.split(r'[_\-\s/]+', tag_clean)]
    out = []
    for s in segs:
        if not s or s.isdigit() or IP_RE.match(s) or PROVIDER_RE.search(s) or PROTOCOL_NOISE_RE.search(s):
            continue
        if s not in out:
            out.append(s)
    return '_'.join(out)


def _build_plan(nodes):
    plan = []
    for i, o in enumerate(nodes):
        tag = o['tag']
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
    return plan


def process_config(d, do_sort=False, do_rename=False, keep_unknown=False,
                   dedup=True, strip_detour=True):
    removed = deduplicate_nodes(d) if dedup else []
    stripped = strip_node_detours(d) if strip_detour else 0
    nodes = [o for o in d.get('outbounds', []) if o.get('type') in NODE_TYPES]
    if not nodes:
        raise ValueError('配置中没有节点')

    plan = _build_plan(nodes)

    if do_sort:
        plan.sort(key=lambda p: (region_rank(p['cc']), p['cc'] or '', p['city'], p['i']))

    counters = {}
    rows = []
    for p in plan:
        if do_rename:
            if not p['cc'] and keep_unknown:
                p['new_tag'] = p['tag']
                rows.append((p['tag'], p['tag'], '保留原名'))
                continue
            key = (p['cc'] or UNKNOWN[0], p['city'])
            counters[key] = counters.get(key, 0) + 1
            new = format_tag(p['cc'], p['country'], p['city'], counters[key], p['suf'], p['sep'])
            p['new_tag'] = new
            rows.append((p['tag'], new, COUNTRY_ZH.get(p['cc'], '未知')))
        else:
            p['new_tag'] = p['tag']
            rows.append((p['tag'], p['tag'], COUNTRY_ZH.get(p['cc'], '')))

    finals = [p['new_tag'] for p in plan]
    if do_rename:
        duplicates = list(dict.fromkeys(tag for tag in finals if finals.count(tag) > 1))
        if duplicates:
            raise ValueError(f'重命名结果存在重名: {duplicates}')

    changed_names = sum(1 for p in plan if p['tag'] != p['new_tag'])
    if do_rename:
        for p in plan:
            p['obj']['tag'] = p['new_tag']
        mapping = {p['tag']: p['new_tag'] for p in plan}
        remap_refs(d, mapping)

    if do_sort:
        reorder_outbounds(d, {p['new_tag']: i for i, p in enumerate(plan)}, NODE_TYPES)
    validate_config(d)
    return {
        'removed': removed,
        'stripped': stripped,
        'rows': rows,
        'plan': plan,
        'renamed': changed_names,
        'sorted': do_sort,
    }


def _print_result(result, do_sort, do_rename):
    removed = result['removed']
    if removed:
        print(f'[去重] 清理 {len(removed)} 个重复节点：')
        for old, kept in removed:
            print(f'  {old}  ≡  {kept}')
    else:
        print('[去重] 配置中无重复节点')
    print(f'[移除链式代理] 处理 {result["stripped"]} 个节点')

    if do_rename:
        print('\n--- 重命名计划 ---')
        for old, new, _ in result['rows']:
            print(f'{old}  ->  {new}' if old != new else f'{old}  （名称不变）')
    elif do_sort:
        print('\n--- 地区排序计划（名称保持不变）---')
        for item in result['plan']:
            print(f'  [{COUNTRY_ZH.get(item["cc"], "未知")}] {item["tag"]}')
    order = '已按地区排序' if do_sort else '节点顺序保持不变'
    print(f'\n共 {len(result["rows"])} 个节点，改名 {result["renamed"]} 个，{order}')


def main():
    ap = argparse.ArgumentParser(description='节点操作工具（默认去重与剥离 detour，按需排序和重命名）')
    ap.add_argument('--config', required=True, help='sing-box 配置文件路径')
    ap.add_argument('--apply', action='store_true', help='实际写回（默认仅预览）')
    ap.add_argument('--sort', action='store_true', help='按地区排序（默认保持原序）')
    ap.add_argument('--rename', action='store_true', help='规范化重命名（默认保持原名）')
    ap.add_argument('--keep-dup', dest='dedup', action='store_false', help='保留重复节点')
    ap.add_argument('--keep-detour', dest='strip_detour', action='store_false', help='保留节点 detour')
    ap.add_argument('--keep-unknown', action='store_true', help='重命名时保留未识别节点的原名')
    ap.set_defaults(dedup=True, strip_detour=True)
    a = ap.parse_args()

    src = os.path.abspath(a.config)
    with open(src, encoding='utf-8-sig') as handle:
        config = json.load(handle)
    result = process_config(
        config, do_sort=a.sort, do_rename=a.rename, keep_unknown=a.keep_unknown,
        dedup=a.dedup, strip_detour=a.strip_detour,
    )
    _print_result(result, a.sort, a.rename)

    if not a.apply:
        print('\n[预览模式] 未写回。确认无误后加 --apply')
        return

    changed, backup = write_config(src, config, backup=True)
    if changed:
        print(f'\n已写回并校验通过；备份: {os.path.basename(backup)}')
    else:
        print('\n配置无变化，未写回，也未生成备份')


if __name__ == '__main__':
    main()
