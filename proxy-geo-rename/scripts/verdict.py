# -*- coding: utf-8 -*-
"""投票判定模块：多地理库国家/城市裁决，Cloudflare 接入机房作物理决胜票。
sources 中 key 以 'ref:' 开头的为参考信息（如 RIR 注册国），不计票。"""
import re
from collections import Counter

from geodata import COUNTRY_ZH, CITY_ZH, COLO, CONTINENT, CITY_STATE

CJK = re.compile(r'[一-鿿]')


def norm_city(name):
    """归一化城市名：中文裁行政尾缀（先长后短），英文转小写。"""
    n = (name or '').strip()
    if not n:
        return ''
    if CJK.search(n):
        for suf in ('特别行政区', '特别市', '广域市', '直辖市', '自治州', '自治区'):
            if len(n) > len(suf) and n.endswith(suf):
                n = n[:-len(suf)]
                break
        if len(n) > 2 and n[-1] in '市县都府州區区':
            n = n[:-1]
        return n
    return n.lower()


def city_key(name):
    """聚合用键：英文名能映射成中文的先映射，使中英文/全称简称同城同桶。"""
    n = norm_city(name)
    return CITY_ZH.get(n, n)


def vote(rec):
    """对单个节点的多源检测结果做国家+城市裁决，原地更新并返回 rec。"""
    if rec.get('status') != 'ok':
        return rec
    src = rec['sources']
    valid = {k: r for k, r in src.items()
             if r and r.get('cc') and not k.startswith('ref:')}
    if not valid:
        rec['status'] = 'offline'
        return rec

    cnt = Counter(r['cc'].upper() for r in valid.values())
    colo = (src.get('cloudflare') or {}).get('colo') or ''
    colo_city, colo_cc = COLO.get(colo, ('', ''))

    # 有效票 = 库票数 + 接入机房所在国家的 1 张物理决胜票
    eff = dict(cnt)
    if colo_cc:
        eff[colo_cc] = eff.get(colo_cc, 0) + 1
    cc = max(eff, key=lambda c: (eff[c], cnt.get(c, 0)))
    t = cnt.get(cc, 0)
    lead = eff[cc] - max([v for c, v in eff.items() if c != cc], default=0)

    if t >= 4 and lead >= 2:
        conf = 'high'
    elif t >= 3 and lead >= 2:
        conf = 'high' if colo_cc == cc else 'medium'
    elif t >= 3:
        conf = 'medium'
    else:
        conf = 'low'

    if colo_cc:
        if colo_cc == cc:
            colo_rel = 'same-country'
        elif CONTINENT.get(colo_cc) and CONTINENT.get(colo_cc) == CONTINENT.get(cc):
            colo_rel = 'same-continent'
        else:
            colo_rel = 'cross-continent'
            if conf == 'high':
                conf = 'medium'
    else:
        colo_rel = ''

    ipapi = src.get('ip-api') or {}
    ipapi_same_cc = ipapi.get('cc', '').upper() == cc

    if cc in CITY_STATE:
        city_zh, city_basis = CITY_STATE[cc], 'city-state'
    else:
        buckets = {}
        for r in valid.values():
            if r.get('cc', '').upper() == cc and r.get('city'):
                buckets.setdefault(city_key(r['city']), []).append(r['city'].strip())
        top = max(buckets.items(), key=lambda kv: len(kv[1])) if buckets else None

        def display(key, raws):
            if CJK.search(key):
                return key
            if ipapi_same_cc and ipapi.get('city') and CJK.search(ipapi['city']):
                return norm_city(ipapi['city'])
            return raws[0]

        if top and len(top[1]) >= 2:
            city_zh, city_basis = display(*top), 'majority'
        elif colo_rel == 'same-country' and colo_city:
            city_zh, city_basis = colo_city, 'colo'
        elif top:
            city_zh, city_basis = display(*top), 'single-source'
        elif ipapi_same_cc and ipapi.get('region'):
            city_zh, city_basis = norm_city(ipapi['region']), 'region'
        else:
            city_zh, city_basis = '未知', 'none'

    # 国家中文名优先用内置规范简称（如"俄罗斯"），ip-api 中文全称仅兜底
    country_zh = (COUNTRY_ZH.get(cc)
                  or (ipapi.get('country_zh', '') if ipapi_same_cc else '')
                  or cc)

    rec.update({'cc': cc, 'votes': t, 'answered': len(valid), 'conf': conf,
                'colo': colo, 'colo_rel': colo_rel, 'country_zh': country_zh,
                'city_zh': city_zh, 'city_basis': city_basis})
    return rec
