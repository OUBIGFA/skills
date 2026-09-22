# -*- coding: utf-8 -*-
"""真实出口探测、Google 地区码判定、多源 GeoIP 投票及 IP 信誉评估。"""
import json
import re
import time
from collections import Counter

import pycountry
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# Google 自身地区标识
GEMINI_REGION_PATTERN = re.compile(r',\s*2,\s*1,\s*200,\s*\\*"([A-Z]{3})\\*"')
GEMINI_AVAILABILITY_PATTERN = re.compile(r'\[45631641,null,(true|false|null)')
YOUTUBE_GL_PATTERN = re.compile(r'"INNERTUBE_CONTEXT_GL"\s*:\s*"([A-Za-z]{2})"')
YOUTUBE_COUNTRY_PATTERN = re.compile(r'"countryCode"\s*:\s*"([A-Za-z]{2})"')

# 国家/地区显示顺序及简中映射
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
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if pycountry.countries.get(alpha_2=code) else None


def alpha3_to_alpha2(alpha3):
    if not isinstance(alpha3, str) or len(alpha3) != 3:
        return None
    country = pycountry.countries.get(alpha_3=alpha3.upper())
    return normalize_country_code(country.alpha_2) if country else None


def flag_emoji(cc):
    if not cc or cc == 'UNK':
        return '🏳️'
    code = cc.upper()
    if code == 'TW':
        return '🇹🇼'
    if len(code) == 2 and all('A' <= c <= 'Z' for c in code):
        return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
    return '🏳️'


def country_name_zh(cc):
    if not cc:
        return "未知"
    cc = cc.upper()
    if cc in CATEGORY_ORDER:
        return CATEGORY_ORDER[cc][2]
    c = pycountry.countries.get(alpha_2=cc)
    return c.name if c else "未知"


# ----------------- 出口探测 -----------------

def probe_egress(proxies=None, timeout=(3.0, 5.0)):
    """测试当前连接的 IPv4/IPv6 出口 IP。"""
    session = requests.Session()
    session.trust_env = False
    result = {
        "ipv4": {"ip": None, "source": None},
        "ipv6": {"ip": None, "source": None},
        "observed_ips": [],
        "status": "unknown"
    }

    # IPv4 端点 (优先轻量 HTTP 端点，避免二次 SSL 握手延迟)
    v4_endpoints = [
        ("ipify-http", "http://api.ipify.org?format=json"),
        ("icanhazip-http", "http://ipv4.icanhazip.com"),
        ("ipify-v4", "https://api.ipify.org?format=json"),
        ("icanhazip-v4", "https://ipv4.icanhazip.com"),
        ("ipwhois-v4", "https://ipwho.is/"),
        ("ipsb-v4", "https://api.ip.sb/geoip")
    ]
    for src, url in v4_endpoints:
        try:
            resp = session.get(url, proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
            if resp.status_code == 200:
                ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', resp.text)
                if ip_match:
                    ip = ip_match.group(0)
                    result["ipv4"] = {"ip": ip, "source": src}
                    result["observed_ips"].append(ip)
                    break
        except Exception:
            continue

    # IPv6 端点 (可选)
    v6_endpoints = [
        ("ipify-v6", "https://api6.ipify.org?format=json"),
        ("icanhazip-v6", "https://ipv6.icanhazip.com")
    ]
    for src, url in v6_endpoints:
        try:
            resp = session.get(url, proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
            if resp.status_code == 200:
                ip_match = re.search(r'\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b', resp.text)
                if ip_match:
                    ip = ip_match.group(0)
                    result["ipv6"] = {"ip": ip, "source": src}
                    result["observed_ips"].append(ip)
                    break
        except Exception:
            continue

    session.close()
    result["status"] = "ok" if result["observed_ips"] else "failed"
    return result


# ----------------- Google 地区判定 -----------------

def probe_google_region(proxies, timeout=(3.0, 7.0)):
    """
    通过 Google 自身页面判定其归属国家代码及 Gemini 服务可用性。
    优先：gemini.google.com；兜底：youtube.com/premium
    """
    session = requests.Session()
    session.trust_env = False
    result = {
        "status": "unknown",
        "country_code": None,
        "region_code": None,
        "gemini_available": None,
        "source": None,
        "is_sent_to_china": False
    }

    # 1. 尝试 Gemini 页面
    try:
        resp = session.get("https://gemini.google.com/", proxies=proxies, timeout=timeout,
                           headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        if resp.status_code == 200:
            content = resp.text
            m_reg = GEMINI_REGION_PATTERN.search(content)
            m_avail = GEMINI_AVAILABILITY_PATTERN.search(content)

            if m_reg:
                alpha3 = m_reg.group(1).upper()
                result["region_code"] = alpha3
                result["country_code"] = alpha3_to_alpha2(alpha3)
                result["source"] = "gemini_page"
                result["status"] = "observed"

            if m_avail:
                val = m_avail.group(1).lower()
                result["gemini_available"] = True if val == "true" else False if val == "false" else None
    except Exception:
        pass

    # 2. 兜底尝试 YouTube Premium
    if not result["country_code"]:
        try:
            resp = session.get("https://www.youtube.com/premium", proxies=proxies, timeout=timeout,
                               headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
            if resp.status_code == 200:
                content = resp.text
                m_gl = YOUTUBE_GL_PATTERN.search(content)
                m_cc = YOUTUBE_COUNTRY_PATTERN.search(content)
                if m_gl and m_cc and m_gl.group(1).upper() == m_cc.group(1).upper():
                    code = m_gl.group(1).upper()
                    result["country_code"] = normalize_country_code(code)
                    result["source"] = "youtube_premium"
                    result["status"] = "observed"
        except Exception:
            pass

    session.close()

    # 送中判定
    reg = (result.get("region_code") or "").upper()
    cc = (result.get("country_code") or "").upper()
    if reg in ("CHN", "CN") or cc in ("CN", "CHN"):
        result["is_sent_to_china"] = True
        result["gemini_available"] = False

    return result


# ----------------- 多源 GeoIP & 信誉查询 -----------------

def query_ip_info(ip, timeout=(3.0, 7.0)):
    """查询多源 GeoIP 与 Net.Coffee 欺诈信誉分。"""
    if not ip:
        return {"country_code": "UNK", "score": None, "flags": {}, "status": "unknown"}

    session = requests.Session()
    session.trust_env = False
    records = []
    coffee_data = {}

    # 1. ipwhois
    try:
        r = session.get(f"https://ipwho.is/{ip}", timeout=timeout, headers={"User-Agent": UA})
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                records.append({"provider": "ipwhois", "cc": normalize_country_code(d.get("country_code"))})
    except Exception:
        pass

    # 2. ipsb
    try:
        r = session.get(f"https://api.ip.sb/geoip/{ip}", timeout=timeout, headers={"User-Agent": UA})
        if r.status_code == 200:
            d = r.json()
            records.append({"provider": "ipsb", "cc": normalize_country_code(d.get("country_code"))})
    except Exception:
        pass

    # 3. coffee (Net.Coffee)
    try:
        r = session.get(f"https://ip.net.coffee/api/ip/lookup/{ip}", timeout=timeout, headers={"User-Agent": UA})
        if r.status_code == 200:
            d = r.json()
            records.append({"provider": "coffee", "cc": normalize_country_code(d.get("countryCode"))})
            coffee_data = d
    except Exception:
        pass

    session.close()

    # 投票裁定国家
    votes = Counter(item["cc"] for item in records if item.get("cc"))
    decided_cc = "UNK"
    confidence = "none"
    if votes:
        code, count = votes.most_common(1)[0]
        decided_cc = code
        confidence = "high" if count >= 2 and len(votes) == 1 else "medium" if count >= 2 else "low"

    # Net.Coffee 欺诈分与标签
    score = coffee_data.get("trust_score")
    if score is not None and not isinstance(score, (int, float)):
        score = None

    flags = {
        "residential": coffee_data.get("isResidential"),
        "datacenter": coffee_data.get("is_datacenter"),
        "vpn": coffee_data.get("is_vpn"),
        "proxy": coffee_data.get("is_proxy"),
        "tor": coffee_data.get("is_tor"),
        "crawler": coffee_data.get("is_crawler"),
        "abuser": coffee_data.get("is_abuser"),
    }

    return {
        "country_code": decided_cc,
        "confidence": confidence,
        "score": score,
        "flags": flags,
        "asn": (coffee_data.get("connection") or {}).get("asn"),
        "isp": (coffee_data.get("connection") or {}).get("isp"),
        "records": records
    }
