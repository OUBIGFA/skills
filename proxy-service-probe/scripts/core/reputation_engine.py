# -*- coding: utf-8 -*-
"""新一代多源权威 IP 信誉评分与容灾引擎。

融合 Scamalytics 反欺诈评分、AbuseIPDB 恶意威胁、rDNS/PTR 反向解析、
DoH/DNSBL 黑名单与 Net.Coffee 兜底容灾，构建准确、权威、高吞吐的信誉判定体系。
"""
import concurrent.futures
import ipaddress
import json
import logging
import os
import re
import socket
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

from .local_cache import get_default_cache
from .residential_judge import (
    classify_residential,
    parse_asn_number,
    resolve_ptr,
)

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 默认 DNSBL 探测列表 (毫秒级反黑客/垃圾源检测)
DEFAULT_DNSBL_ZONES = [
    "bl.spamcop.net",
    "dnsbl.dronebl.org",
]


def reverse_ip_for_dnsbl(ip: str) -> Optional[str]:
    """将 IPv4 地址翻转为 DNSBL 查询前缀，如 1.2.3.4 -> 4.3.2.1。"""
    try:
        obj = ipaddress.ip_address(ip)
        if obj.version == 4:
            return ".".join(reversed(ip.split(".")))
    except ValueError:
        pass
    return None


def probe_dnsbl(ip: str, zones: Optional[List[str]] = None, timeout: float = 1.2) -> List[str]:
    """并发查询主流 DNSBL 黑名单，返回命中的黑名单列表。"""
    rev_ip = reverse_ip_for_dnsbl(ip)
    if not rev_ip:
        return []
    zones = zones or DEFAULT_DNSBL_ZONES
    hits = []

    def _check_zone(zone: str) -> Optional[str]:
        query_host = f"{rev_ip}.{zone}"
        try:
            # 采用 socket 快速解析，返回 127.0.0.x 即为命中黑名单
            res = socket.gethostbyname(query_host)
            if res.startswith("127.0.0."):
                return zone
        except Exception:
            pass
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(zones)) as executor:
            futures = [executor.submit(_check_zone, z) for z in zones]
            for fut in concurrent.futures.as_completed(futures, timeout=timeout + 0.3):
                res = fut.result()
                if res:
                    hits.append(res)
    except Exception:
        pass

    return hits


def fetch_scamalytics(ip: str, timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    """从 Scamalytics 公开端点解析提取权威反欺诈风控数据。"""
    url = f"https://scamalytics.com/ip/{ip}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        logger.debug("Scamalytics 请求失败 (%s): %s", ip, e)
        return None

    # 提取 Fraud Score: 形如 ">23</div>" 或 "Fraud Score: 23"
    score_match = re.search(r'(?i)Fraud\s*Score[^\d]{1,60}(\d{1,3})', html)
    if not score_match:
        score_match = re.search(r'(?i)<div class="score"[^>]*>(\d{1,3})</div>', html)
    fraud_score = int(score_match.group(1)) if score_match else None

    # 提取 Datacenter / Proxy / Residential Proxy 属性
    def _extract_flag(name: str) -> Optional[bool]:
        m = re.search(rf'(?i){name}\s*</th>\s*<td[^>]*>(?:<[^>]+>)*\s*(Yes|No)', html)
        if m:
            return m.group(1).lower() == "yes"
        return None

    is_dc = _extract_flag("Datacenter")
    is_proxy = _extract_flag("Proxy")
    is_res_proxy = _extract_flag("Residential Proxy")

    risk_match = re.search(r'(?i)Risk</th>\s*<td[^>]*>(?:<[^>]+>)*\s*([A-Za-z]+)', html)
    risk_level = risk_match.group(1).lower() if risk_match else "unknown"

    if fraud_score is None:
        return None

    return {
        "provider": "Scamalytics",
        "fraud_score": fraud_score,
        "is_datacenter": is_dc,
        "is_proxy": is_proxy,
        "is_residential_proxy": is_res_proxy,
        "risk_level": risk_level,
    }


def fetch_abuseipdb(ip: str, api_key: Optional[str] = None, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """查询 AbuseIPDB 威胁情报接口 (若提供 Key 则请求，未提供则安全短路跳过)。"""
    key = api_key or os.environ.get("ABUSEIPDB_API_KEY")
    if not key:
        return None

    url = f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90"
    req = urllib.request.Request(
        url,
        headers={
            "Key": key,
            "Accept": "application/json",
            "User-Agent": BROWSER_UA
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                data = body.get("data", {})
                return {
                    "provider": "AbuseIPDB",
                    "abuse_score": data.get("abuseConfidenceScore", 0),
                    "total_reports": data.get("totalReports", 0),
                    "is_whitelisted": data.get("isWhitelisted", False)
                }
    except Exception as e:
        logger.debug("AbuseIPDB 查询失败: %s", e)
    return None


def fetch_net_coffee_fallback(ip: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Net.Coffee 容灾兜底接口 (仅在主流权威数据源故障或超时时使用)。"""
    url = f"https://ip.net.coffee/api/ip/lookup/{ip}"
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict):
                    score = data.get("trust_score")
                    conn = data.get("connection", {}) if isinstance(data.get("connection"), dict) else {}
                    return {
                        "provider": "Net.Coffee(Fallback)",
                        "trust_score": int(score) if isinstance(score, (int, float)) else None,
                        "is_residential": data.get("isResidential"),
                        "is_datacenter": data.get("is_datacenter"),
                        "asn": conn.get("asn"),
                        "isp": conn.get("isp"),
                        "raw": data
                    }
    except Exception as e:
        logger.debug("Net.Coffee 兜底请求失败: %s", e)
    return None


def calculate_composite_reputation_score(
    scamalytics: Optional[Dict[str, Any]],
    abuseipdb: Optional[Dict[str, Any]],
    dnsbl_hits: List[str],
    residential_level: str,
    is_datacenter: bool,
    fallback_score: Optional[int] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    加权计算综合信誉评分 (Composite Reputation Score: 0–100)。

    计算公式：
    Score = Base(100) - Penalty_Fraud - Penalty_Abuse - Penalty_DC - Penalty_Blacklist + Bonus_CleanRes
    """
    # 容灾兜底：若 Scamalytics 与 AbuseIPDB 均不可用，直接采用兜底分
    if not scamalytics and not abuseipdb:
        final_score = fallback_score if fallback_score is not None else 60
        return max(0, min(100, int(final_score))), {
            "base": 100,
            "fallback_used": True,
            "final": final_score
        }

    base = 100.0
    penalties: Dict[str, float] = {}
    bonuses: Dict[str, float] = {}

    # 1. 欺诈惩罚 Penalty_Fraud (依据 Scamalytics 欺诈分 0–100)
    fraud_val = scamalytics.get("fraud_score", 0) if scamalytics else 0
    if fraud_val <= 15:
        p_fraud = 0.0
    elif fraud_val <= 40:
        p_fraud = (fraud_val - 15) * 0.5
    else:
        p_fraud = 25.0 + (fraud_val - 40) * 0.8
    penalties["fraud"] = round(p_fraud, 1)

    # 2. 恶意攻击惩罚 Penalty_Abuse (依据 AbuseIPDB)
    if abuseipdb:
        p_abuse = abuseipdb.get("abuse_score", 0) * 0.4
        penalties["abuse"] = round(p_abuse, 1)

    # 3. 数据中心基准扣分 Penalty_DC (纯机房基准上限设为 90)
    if is_datacenter:
        penalties["datacenter"] = 10.0

    # 4. 黑名单惩罚 Penalty_Blacklist (每命中一项扣 15 分)
    if dnsbl_hits:
        penalties["blacklist"] = len(dnsbl_hits) * 15.0

    # 5. 纯净真家宽奖励 Bonus_CleanResidential
    if residential_level == "Level 1: True Residential" and fraud_val < 10:
        bonuses["clean_residential"] = 5.0

    raw_score = base - sum(penalties.values()) + sum(bonuses.values())
    final_score = int(round(max(0.0, min(100.0, raw_score))))

    breakdown = {
        "base": base,
        "penalties": penalties,
        "bonuses": bonuses,
        "raw_score": raw_score,
        "final_score": final_score
    }
    return final_score, breakdown


def evaluate_ip_reputation(
    ip: str,
    asn_raw: Any = None,
    isp_name: str = "",
    ipinfo_flags: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
    timeout: float = 2.5
) -> Dict[str, Any]:
    """
    全流程 IP 信誉与家宽综合判定主入口 (渐进式流水线)。

    步骤：
    1. 检查 24 小时本地持久化缓存 (命中则 < 1ms 返回)；
    2. 执行本地反向解析 PTR (socket.gethostbyaddr，10~30ms)；
    3. 并发探测 DNSBL 黑名单 + Scamalytics 反欺诈 (带 2.5s 熔断)；
    4. 四级形态交叉仲裁 (Level 1 原生家宽 / Level 2 双ISP / Level 3 代理池 / Level 4 机房)；
    5. 加权计算综合信誉评分；
    6. 写入本地缓存并返回标准结构化数据。
    """
    if not ip:
        return {
            "score": None,
            "status": "unknown",
            "residential_level": "Level 4: Datacenter",
            "reason": "empty_ip"
        }

    cache = get_default_cache()
    if use_cache:
        cached_res = cache.get(ip)
        if cached_res:
            return cached_res

    # 1. 本地极速层：反向域名解析 (rDNS / PTR)
    ptr = resolve_ptr(ip, timeout=1.5)

    # 2. 并发探测层：DNSBL + Scamalytics + 可选 AbuseIPDB
    dnsbl_hits: List[str] = []
    scamalytics_data: Optional[Dict[str, Any]] = None
    abuse_data: Optional[Dict[str, Any]] = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_dnsbl = executor.submit(probe_dnsbl, ip, timeout=1.2)
        fut_scama = executor.submit(fetch_scamalytics, ip, timeout=timeout)
        fut_abuse = executor.submit(fetch_abuseipdb, ip, timeout=1.5)

        try:
            dnsbl_hits = fut_dnsbl.result(timeout=1.5)
        except Exception:
            dnsbl_hits = []

        try:
            scamalytics_data = fut_scama.result(timeout=timeout)
        except Exception:
            scamalytics_data = None

        try:
            abuse_data = fut_abuse.result(timeout=1.6)
        except Exception:
            abuse_data = None

    # 3. 容灾兜底检查：若权威反欺诈源均失败，启动 Net.Coffee 兜底
    fallback_coffee = None
    if not scamalytics_data and not abuse_data:
        fallback_coffee = fetch_net_coffee_fallback(ip, timeout=timeout)

    # 4. 家宽真实性四级形态交叉判定
    res_classification = classify_residential(
        ip=ip,
        ptr=ptr,
        asn_raw=asn_raw or (fallback_coffee.get("asn") if fallback_coffee else None),
        isp_name=isp_name or (fallback_coffee.get("isp") if fallback_coffee else ""),
        scamalytics=scamalytics_data,
        ipinfo_flags=ipinfo_flags,
        dnsbl_hits=len(dnsbl_hits)
    )

    res_level = res_classification["level"]
    is_dc = res_classification["is_datacenter"]

    # 5. 加权综合信誉评分计算
    fallback_sc = fallback_coffee.get("trust_score") if fallback_coffee else None
    score, breakdown = calculate_composite_reputation_score(
        scamalytics=scamalytics_data,
        abuseipdb=abuse_data,
        dnsbl_hits=dnsbl_hits,
        residential_level=res_level,
        is_datacenter=is_dc,
        fallback_score=fallback_sc
    )

    # 6. 构造标准化结果与契约兼容 flags
    flags = {
        "residential": res_classification["is_residential"],
        "dual_isp": res_classification["is_dual_isp"],
        "datacenter": res_classification["is_datacenter"],
        "proxy": bool(scamalytics_data.get("is_proxy")) if scamalytics_data else None,
        "residential_proxy": res_classification["is_proxy_pool"],
        "mobile": None,
        "vpn": None,
        "tor": None,
        "abuser": bool(abuse_data and abuse_data.get("abuse_score", 0) > 30),
    }

    result = {
        "ip": ip,
        "score": score,
        "residential_level": res_level,
        "status": "observed" if score is not None else "unknown",
        "provider": "CompositeConsensus",
        "flags": flags,
        "ptr": ptr,
        "dnsbl_hits": dnsbl_hits,
        "scamalytics": scamalytics_data,
        "abuseipdb": abuse_data,
        "score_breakdown": breakdown,
        "classification": res_classification,
        "can_grant_home_badge": res_classification["can_grant_home_badge"] and score >= 80,
        "can_grant_isp_suffix": (
            res_classification["can_grant_isp_suffix"] and (score < 80 or res_classification["is_dual_isp"])
        ),
        "can_grant_heart_badge": score >= 80 and not res_classification["can_grant_home_badge"],
        "source": "live",
        "checked_at": None
    }

    # 7. 写入本地 24h 缓存
    if use_cache and score is not None:
        cache.set(ip, score=score, res_level=res_level, data=result)

    return result
