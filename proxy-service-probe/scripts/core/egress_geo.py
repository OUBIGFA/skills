# -*- coding: utf-8 -*-
"""可追溯的出口、Google 服务地区和 GeoIP 证据；不把 CDN 机房当出口位置。"""
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pycountry
import requests

SKILL_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS_DIR)
from geodata import CITY_ZH, COLO, COUNTRY_ZH, region_rank

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
GEMINI_REGION_PATTERN = re.compile(r',\s*2,\s*1,\s*200,\s*\\*"([A-Z]{3})\\*"')
GEMINI_AVAILABILITY_PATTERN = re.compile(r'\[45631641\s*,\s*null\s*,\s*(true|false|null)')
YOUTUBE_GL_PATTERN = re.compile(r'"INNERTUBE_CONTEXT_GL"\s*:\s*"([A-Za-z]{2})"')
YOUTUBE_COUNTRY_PATTERN = re.compile(r'"countryCode"\s*:\s*"([A-Za-z]{2})"')
RESTRICTED_POISON_COUNTRIES = frozenset({"CN", "RU", "IR", "KP", "CU", "SY", "BY"})


def valid_reputation_score(value):
    """Net.Coffee trust_score is a 0-100 vendor estimate, not a measured success rate."""
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100 else None


def reputation_for_exits(info_by_ip, observed_ips):
    """For rotating/dual-stack exits, use the worst measured score or stay unknown."""
    ips = list(dict.fromkeys(observed_ips))
    entries = {ip: (info_by_ip.get(ip) or {}).get('reputation') or {} for ip in ips}
    values = [entry.get('score') for entry in entries.values()]
    complete = bool(ips) and all(valid_reputation_score(score) is not None for score in values)
    return {"score": min(values) if complete else None,
            "status": "observed" if complete else "unknown",
            "provider": "Net.Coffee", "by_ip": entries,
            "reason": None if complete else "missing_exit_or_reputation_evidence"}


# 保留现有渲染、排序接口。
CATEGORY_ORDER = {
    'HK': (0, 0, '香港'), 'MO': (0, 1, '澳门'), 'TW': (0, 2, '台湾'),
    'KR': (1, 0, '韩国'), 'JP': (1, 1, '日本'), 'SG': (1, 2, '新加坡'),
    'US': (2, 0, '美国'), 'CA': (2, 1, '加拿大'), 'MX': (2, 2, '墨西哥'),
    'GB': (3, 0, '英国'), 'DE': (3, 1, '德国'), 'FR': (3, 2, '法国'), 'NL': (3, 3, '荷兰'),
    'IT': (3, 4, '意大利'), 'ES': (3, 5, '西班牙'), 'CH': (3, 6, '瑞士'), 'SE': (3, 7, '瑞典'),
    'NO': (3, 8, '挪威'), 'FI': (3, 9, '芬兰'), 'DK': (3, 10, '丹麦'), 'IE': (3, 11, '爱尔兰'),
    'AT': (3, 12, '奥地利'), 'BE': (3, 13, '比利时'), 'LU': (3, 14, '卢森堡'), 'PL': (3, 15, '波兰'),
    'CZ': (3, 16, '捷克'), 'SK': (3, 17, '斯洛伐克'), 'HU': (3, 18, '匈牙利'), 'RO': (3, 19, '罗马尼亚'),
    'BG': (3, 20, '保加利亚'), 'GR': (3, 21, '希腊'), 'PT': (3, 22, '葡萄牙'), 'RU': (3, 23, '俄罗斯'),
    'UA': (3, 24, '乌克兰'), 'TR': (3, 25, '土耳其'),
    'AU': (4, 0, '澳大利亚'), 'NZ': (4, 1, '新西兰'),
    'BR': (4, 10, '巴西'), 'AR': (4, 11, '阿根廷'), 'CL': (4, 12, '智利'),
    'ZA': (4, 20, '南非'), 'EG': (4, 21, '埃及'),
    'MY': (5, 0, '马来西亚'), 'TH': (5, 1, '泰国'), 'VN': (5, 2, '越南'), 'PH': (5, 3, '菲律宾'),
    'ID': (5, 4, '印度尼西亚'), 'IN': (5, 10, '印度'), 'PK': (5, 11, '巴基斯坦'),
    'AE': (6, 1, '阿联酋'), 'SA': (6, 2, '沙特阿拉伯'), 'IL': (6, 3, '以色列'),
    'CN': (7, 0, '中国'), 'UNK': (7, 999, '未知')
}


def normalize_country_code(value):
    code = value.strip().upper() if isinstance(value, str) else ""
    return code if pycountry.countries.get(alpha_2=code) else None


def alpha3_to_alpha2(alpha3):
    country = pycountry.countries.get(alpha_3=alpha3.upper()) if isinstance(alpha3, str) else None
    return country.alpha_2 if country else None


def flag_emoji(cc):
    cc = normalize_country_code(cc)
    return ''.join(chr(ord(c) + 127397) for c in cc) if cc else '🏳️'


def country_name_zh(cc):
    cc = normalize_country_code(cc)
    if not cc:
        return '未知'
    return COUNTRY_ZH.get(cc) or CATEGORY_ORDER.get(cc, (0, 0, None))[2] or pycountry.countries.get(alpha_2=cc).name


def public_ip(value):
    """不接受 HTML 中的任意数字、私网或畸形 IP。"""
    try:
        ip = ipaddress.ip_address(value.strip()) if isinstance(value, str) else None
        return str(ip) if ip and ip.is_global else None
    except ValueError:
        return None


def fetch_evidence(url, proxies=None, timeout=(3.0, 6.0)):
    """每次独立无 Cookie 会话；限时、限正文、保留错误和响应指纹。"""
    evidence = {"url": url, "observed_at": datetime.now(timezone.utc).isoformat()}
    deadline = time.monotonic() + (sum(timeout) if isinstance(timeout, tuple) else timeout) * 2
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, proxies=proxies, timeout=timeout, stream=True,
                             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}) as resp:
                evidence.update(http_status=resp.status_code, final_url=resp.url)
                if resp.status_code != 200:
                    return {**evidence, "status": "error", "error": f"http_{resp.status_code}"}, ""
                chunks, size = [], 0
                for chunk in resp.iter_content(65536):
                    size += len(chunk)
                    if size > 4 * 1024 * 1024 or time.monotonic() > deadline:
                        return {**evidence, "status": "error", "error": "response_limit_exceeded"}, ""
                    chunks.append(chunk)
                body = b''.join(chunks)
                evidence.update(status="ok", sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
                return evidence, body.decode('utf-8', errors='replace')
    except requests.RequestException as exc:
        return {**evidence, "status": "error", "error": type(exc).__name__}, ""


def probe_cloudflare_trace(proxies=None, timeout=(2.5, 4.0)):
    """loc 是 CF 的 GeoIP 视图；colo 仅表示 CF 接入机房，不参与国别投票。"""
    attempts = []
    for url in ("https://cloudflare.com/cdn-cgi/trace", "https://1.1.1.1/cdn-cgi/trace"):
        evidence, text = fetch_evidence(url, proxies, timeout)
        data = dict(re.findall(r'^(\w+)=(.*)$', text, re.M))
        ip = public_ip(data.get('ip'))
        if evidence['status'] == 'ok' and ip:
            colo = data.get('colo', '').strip().upper()
            city, cc = COLO.get(colo, (None, None))
            return {**evidence, "ip": ip, "loc": normalize_country_code(data.get('loc')),
                    "colo": colo, "colo_city": city, "colo_cc": cc}
        attempts.append({**evidence, "error": evidence.get('error', 'invalid_trace')})
    return {"status": "failed", "attempts": attempts}


def probe_egress(proxies=None, timeout=(2.5, 4.5), *, ipv6=True):
    """CF 与独立 HTTPS IPv4 回显交叉检查；IPv6 单列，不将双栈误称轮换池。"""
    result = {"ipv4": {"ip": None, "source": None}, "ipv6": {"ip": None, "source": None},
              "observed_ips": [], "observations": [], "status": "unknown"}

    def add(ip, source):
        family = f'ipv{ipaddress.ip_address(ip).version}'
        if not result[family]['ip']:
            result[family] = {"ip": ip, "source": source}
        if ip not in result['observed_ips']:
            result['observed_ips'].append(ip)

    cf = probe_cloudflare_trace(proxies, timeout)
    result['cf_trace'] = cf
    if cf.get('ip'):
        add(cf['ip'], 'cloudflare-trace')
    for family, urls in ((4, ("https://api.ipify.org?format=json", "https://ipv4.icanhazip.com")),
                         (6, ("https://api6.ipify.org?format=json",))):
        if family == 6 and not ipv6:
            continue
        for url in urls:
            evidence, text = fetch_evidence(url, proxies, timeout)
            try:
                data = json.loads(text)
                value = data.get('ip') if isinstance(data, dict) else None
            except ValueError:
                value = text.strip()
            ip = public_ip(value) if evidence['status'] == 'ok' else None
            if ip and ipaddress.ip_address(ip).version == family:
                add(ip, url)
                result['observations'].append({**evidence, "ip": ip})
                break
            result['observations'].append({**evidence, "status": "error",
                                           "error": evidence.get('error', 'invalid_ip_or_family')})
    result['status'] = 'ok' if result['observed_ips'] else 'failed'
    return result


def parse_gemini_region(text):
    codes = sorted({cc for raw in GEMINI_REGION_PATTERN.findall(text) if (cc := alpha3_to_alpha2(raw))})
    values = set(GEMINI_AVAILABILITY_PATTERN.findall(text))
    available = {'true': True, 'false': False, 'null': None}.get(next(iter(values))) if len(values) == 1 else None
    return {"country_code": codes[0] if len(codes) == 1 else None, "candidates": codes,
            "gemini_available": available, "status": 'observed' if len(codes) == 1 else 'ambiguous' if codes else 'missing_marker'}


def parse_youtube_region(text):
    gl = {cc for raw in YOUTUBE_GL_PATTERN.findall(text) if (cc := normalize_country_code(raw))}
    country = {cc for raw in YOUTUBE_COUNTRY_PATTERN.findall(text) if (cc := normalize_country_code(raw))}
    valid = len(gl) == 1 and gl == country
    return {"country_code": next(iter(gl)) if valid else None, "gl": sorted(gl), "country_codes": sorted(country),
            "status": 'observed' if valid else 'ambiguous' if gl or country else 'missing_marker'}


def probe_google_region(proxies, timeout=(2.5, 5.0)):
    """Gemini 显式地区优先，YT 双标记一致才兜底；不从域名或语言推断国家。"""
    signals = {}
    for name, url, parser in (("gemini", "https://gemini.google.com/", parse_gemini_region),
                              ("youtube", "https://www.youtube.com/premium", parse_youtube_region)):
        evidence, text = fetch_evidence(url, proxies, timeout)
        signals[name] = {**evidence, **parser(text)} if evidence['status'] == 'ok' else evidence
    gemini, youtube = signals['gemini'], signals['youtube']
    gcc, ycc = gemini.get('country_code'), youtube.get('country_code')
    cc = gcc or ycc
    sent_cn = 'CN' in gemini.get('candidates', []) or ycc == 'CN'
    return {"status": 'observed' if cc else 'unknown', "country_code": cc,
            "region_code": pycountry.countries.get(alpha_2=gcc).alpha_3 if gcc else None,
            "gemini_available": False if sent_cn else gemini.get('gemini_available'),
            "source": 'gemini_page' if gcc else 'youtube_premium' if ycc else None,
            "is_sent_to_china": sent_cn, "conflict": bool(gcc and ycc and gcc != ycc),
            "details": {"google_search": None, "gemini": gcc, "youtube": ycc}, "signals": signals}


def country_from_name(value):
    # ipapi.is 无密钥 free tier 当前返回英文 country，另一 schema 使用 location.country_code。
    if not isinstance(value, str):
        return None
    # 上游实际英文标签中有带冠词形式，不做模糊地名猜测。
    if value.strip() == 'The Netherlands':
        return 'NL'
    try:
        return pycountry.countries.lookup(value.strip()).alpha_2
    except LookupError:
        return None


def parse_geo_record(provider, data, target_ip):
    """校验回显 IP；注册国、ASN 国别、错误响应一律不冒充 geolocation。"""
    record = {"provider": provider, "family": provider, "target_ip": target_ip, "status": "invalid"}
    if not isinstance(data, dict) or data.get('error') or data.get('success') is False or data.get('is_bogon') or data.get('bogon'):
        return {**record, "error": "provider_error_or_bogon"}
    ip = public_ip(data.get('ip') or data.get('ipAddress'))
    if not ip or ip != public_ip(target_ip):
        return {**record, "ip": ip, "error": "ip_mismatch_or_missing"}
    if provider == 'ipinfo':
        cc, city = normalize_country_code(data.get('country')), data.get('city')
    elif provider == 'ipapi.is':
        location = data.get('location') if isinstance(data.get('location'), dict) else {}
        cc = (normalize_country_code(location.get('country_code')) or normalize_country_code(data.get('country_code'))
              or country_from_name(data.get('country')))
        city = location.get('city') or data.get('city')
    elif provider == 'dbip':
        cc, city = normalize_country_code(data.get('countryCode')), data.get('city')
    else:
        cc, city = normalize_country_code(data.get('country_code')), data.get('city')
    return {**record, "ip": ip, "cc": cc, "city": city, "status": 'ok' if cc else 'invalid',
            **({} if cc else {"error": "country_missing"})}


def geo_consensus(records):
    """来源族去重；平票/单票不定国，不对某些国家实施一刀切排除。"""
    families = defaultdict(set)
    for item in records:
        cc = normalize_country_code(item.get('cc'))
        if cc and item.get('status', 'ok') == 'ok':
            families[item.get('family') or item['provider']].add(cc)
    votes = Counter(next(iter(codes)) for codes in families.values() if len(codes) == 1)
    total = sum(votes.values())
    cc, count = votes.most_common(1)[0] if votes else ('UNK', 0)
    decided = count >= 2 and count > total / 2
    conflict = len(votes) > 1 or any(len(codes) > 1 for codes in families.values())
    return {"country_code": cc if decided else 'UNK', "votes": dict(votes),
            "status": ('majority' if conflict else 'confirmed') if decided else 'conflict' if conflict else 'insufficient',
            "confidence": ('medium' if conflict else 'high') if decided else 'low' if total else 'none'}


def empty_ip_info():
    return {**geo_consensus([]), "records": [], "score": None, "flags": {}}


def query_ip_info(ip, timeout=(3.0, 6.0)):
    target = public_ip(ip)
    if not target:
        return {**empty_ip_info(), "ip": ip, "error": "invalid_public_ip"}
    providers = [('ipinfo', f'https://ipinfo.io/{target}/json'),
                 ('ipwhois', f'https://ipwho.is/{target}'),
                 ('ipapi.is', f'https://api.ipapi.is/?q={target}'),
                 ('dbip', f'https://api.db-ip.com/v2/free/{target}')]

    def query(item):
        provider, url = item
        evidence, text = fetch_evidence(url, timeout=timeout)
        if evidence['status'] != 'ok':
            return {**evidence, "provider": provider, "target_ip": target}
        try:
            data = json.loads(text)
        except ValueError:
            return {**evidence, "provider": provider, "status": "invalid", "error": "invalid_json"}
        return {**evidence, **parse_geo_record(provider, data, target)}

    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(query, providers))
    # 信誉源只用于信誉，不把聚合商的同源 GeoIP 重复算作一票。
    evidence, text = fetch_evidence(f'https://ip.net.coffee/api/ip/lookup/{target}', timeout=timeout)
    coffee = {}
    try:
        data = json.loads(text)
        if evidence['status'] == 'ok' and isinstance(data, dict) and public_ip(data.get('ip')) == target:
            coffee = data
    except ValueError:
        pass
    if not coffee:
        evidence.update(status='invalid' if evidence['status'] == 'ok' else evidence['status'],
                        error=evidence.get('error', 'ip_mismatch_or_missing'))
    score = valid_reputation_score(coffee.get('trust_score'))
    flags = {k: coffee.get(v) if type(coffee.get(v)) is bool else None
             for k, v in {'residential': 'isResidential', 'datacenter': 'is_datacenter',
             'mobile': 'is_mobile', 'vpn': 'is_vpn', 'proxy': 'is_proxy', 'tor': 'is_tor',
             'crawler': 'is_crawler', 'abuser': 'is_abuser'}.items()}
    connection = coffee.get('connection') if isinstance(coffee.get('connection'), dict) else {}
    reputation = {"ip": target, "provider": "Net.Coffee", "score": score,
                  "status": "observed" if score is not None else "unknown", "flags": flags,
                  "checked_at": evidence.get('observed_at'), "source": evidence}
    return {**geo_consensus(records), "ip": target, "records": records,
            "score": score, "flags": flags, "asn": connection.get('asn'),
            "isp": connection.get('isp'), "reputation": reputation, "reputation_source": evidence}


def arbitrate_geo(cf_trace=None, google_region=None, ip_info=None, exit_ips=None, orig_cc=None):
    """命名沿用 Google 服务地区优先，但显式暴露数据库分歧和待复核状态。

    orig_cc 只保留调用兼容性，绝不把旧名字作为检测证据。colo 不参与投票。
    """
    cf, google, info = cf_trace or {}, google_region or {}, ip_info or {}
    ips = list(dict.fromkeys(ip for value in (exit_ips or []) if (ip := public_ip(value))))
    families = Counter(ipaddress.ip_address(ip).version for ip in ips)
    is_pool = any(count > 1 for count in families.values())
    records = [r for r in info.get('records', []) if r.get('status') == 'ok']
    cf_loc = normalize_country_code(cf.get('loc')) if cf.get('status') == 'ok' and cf.get('ip') in ips else None
    if cf_loc and (not info.get('ip') or cf.get('ip') == info['ip']):
        records.append({"provider": "cloudflare", "cc": cf_loc, "status": "ok"})
    consensus = geo_consensus(records)
    # 旧 google_multi_signals 缓存不能复用：只接收已校验的显式地区来源。
    g_cc = normalize_country_code(google.get('country_code')) if google.get('source') in ('gemini_page', 'youtube_premium') else None
    candidate_cc = g_cc or consensus['country_code']
    cc = candidate_cc
    basis = google.get('source') if g_cc else 'geoip_cf_consensus' if cc != 'UNK' else 'insufficient_or_conflicting_evidence'
    restricted = 'CN' if google.get('is_sent_to_china') else g_cc if g_cc in RESTRICTED_POISON_COUNTRIES else None
    geographic_cc = consensus['country_code']
    poisoned = bool(restricted and geographic_cc != 'UNK' and geographic_cc not in RESTRICTED_POISON_COUNTRIES)
    if poisoned:
        # 沿用已有送中/受限地区污染方案：保留实际属地，另行标记服务污染。
        cc, basis = geographic_cc, 'geoip_with_google_poisoning'
    elif g_cc and geographic_cc not in ('UNK', g_cc):
        cc, basis = 'UNK', 'google_geoip_conflict'
    countries = {r['cc'] for r in records if normalize_country_code(r.get('cc'))}
    if g_cc:
        countries.add(g_cc)
    conflict = len(countries) > 1 or bool(google.get('conflict'))
    confidence = consensus['confidence'] if not g_cc else 'high' if g_cc in consensus['votes'] and not conflict else 'medium'
    if conflict or is_pool:
        confidence = 'low'
    if poisoned and not is_pool and google.get('status') != 'unstable':
        confidence = consensus['confidence']
    needs_review = cc == 'UNK' or confidence != 'high'
    geo_cc = info.get('country_code', 'UNK')
    return {"cc": cc, "country_zh": country_name_zh(cc), "flag": flag_emoji(cc),
            "basis": basis, "candidate_cc": candidate_cc,
            "scope": 'google_service_region' if g_cc and not poisoned else 'ip_geolocation', "confidence": confidence,
            "needs_review": needs_review, "conflict": conflict, "is_pool": is_pool, "observed_ips": ips,
            "cf_loc": cf_loc, "cf_colo": cf.get('colo'), "google_cc": g_cc, "geoip_cc": geo_cc,
            "votes": consensus['votes'], "is_poisoned": poisoned, "poisoned_cc": restricted if poisoned else None,
            "poison_tag": f'_⚠️{restricted}' if poisoned else None}


def google_fallback_region(google):
    """未知属地的兜底地区: Gemini 优先于 YouTube，最近一次观测优先；只取已校验的显式地区码。"""
    google = google or {}
    observations = [google.get('confirmation'), google, google.get('initial_observation')]
    for source in ('gemini', 'youtube'):
        for obs in observations:
            cc = normalize_country_code(((obs or {}).get('details') or {}).get(source))
            if cc:
                return cc, source
    return None, None


def apply_google_fallback(decision, google):
    """所有判为未知的节点最终以 Google/Gemini 观测地区为准，保留原未知原因与待复核标志。"""
    if decision['cc'] != 'UNK':
        return
    cc, source = google_fallback_region(google)
    if not cc:
        return
    decision.update(cc=cc, country_zh=country_name_zh(cc), flag=flag_emoji(cc), scope='google_service_region',
                    basis=f'google_fallback_{source}', unknown_basis=decision['basis'], needs_review=True,
                    confidence='low' if decision['confidence'] != 'none' else 'none')


def probe_geolocation(proxies, *, egress=None, timeout=(3.0, 6.0)):
    """两条服务流水线和抽查工具共用；检测前后出口，分别查询每个实际出口。"""
    before = egress if egress is not None else probe_egress(proxies, timeout)
    google = probe_google_region(proxies, timeout)
    after = probe_egress(proxies, timeout)
    ips = list(dict.fromkeys(before.get('observed_ips', []) + after.get('observed_ips', [])))
    info_by_ip = {ip: query_ip_info(ip, timeout) for ip in ips}
    primary = before['ipv4']['ip'] or before['ipv6']['ip']
    info = info_by_ip.get(primary, empty_ip_info())
    initial_google_cc = google.get('country_code')
    if (not initial_google_cc or google.get('conflict')
            or info['country_code'] not in ('UNK', initial_google_cc)):
        # 仅冲突/缺失时再读一次；两次显式地区变化则撤销 Google 定国资格。
        repeated = probe_google_region(proxies, timeout)
        old_google = google
        if not initial_google_cc:
            google = {**repeated, 'initial_observation': old_google}
        else:
            google = {**old_google, 'confirmation': repeated}
            if repeated.get('country_code') and repeated['country_code'] != initial_google_cc:
                google.update(country_code=None, source=None, status='unstable', conflict=True,
                              region_candidates=sorted({initial_google_cc, repeated['country_code']}))
            elif not repeated.get('country_code'):
                google['confirmation_failed'] = True
        google['is_sent_to_china'] = bool(old_google.get('is_sent_to_china') or repeated.get('is_sent_to_china'))
        if google['is_sent_to_china']:
            google['gemini_available'] = False
        after = probe_egress(proxies, timeout)
        ips = list(dict.fromkeys(ips + after.get('observed_ips', [])))
        for ip in ips:
            if ip not in info_by_ip:
                info_by_ip[ip] = query_ip_info(ip, timeout)
    decision = arbitrate_geo(before.get('cf_trace'), google, info, ips)
    if google.get('confirmation_failed'):
        decision.update(confidence='low', needs_review=True)
    before_ips, after_ips = set(before.get('observed_ips', [])), set(after.get('observed_ips', []))
    stable = bool(before_ips and after_ips and before_ips == after_ips)
    per_ip_countries = {i['country_code'] for i in info_by_ip.values() if i['country_code'] != 'UNK'}
    if not primary:
        decision.update(cc='UNK', country_zh='未知', flag='🏳️', basis='egress_unverified', confidence='none', needs_review=True)
    if not stable or len(per_ip_countries) > 1 or decision['is_pool']:
        decision.update(confidence='low', needs_review=True)
        if len(per_ip_countries) > 1:
            decision['conflict'] = True
            if not decision['google_cc']:
                decision.update(cc='UNK', country_zh='未知', flag='🏳️', basis='cross_ip_country_conflict')
    apply_google_fallback(decision, google)
    decision['egress_stable'] = stable
    reputation = reputation_for_exits(info_by_ip, ips)
    if not stable:
        reputation.update(score=None, status='unknown', reason='egress_unstable')
    return {"cc": decision['cc'], "exit_ip": primary, "egress": before, "egress_after": after,
            "google_region": google, "ip_info": info, "ip_info_by_ip": info_by_ip,
            "ip_reputation": reputation, "geo_decision": decision}
