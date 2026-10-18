# -*- coding: utf-8 -*-
"""新一代多引擎仿真“异构 5 站免盾与防降智”探测引擎 (v3.0 终极融合版)。

覆盖五大异构风控体系：
1. OpenAI Sentinel: ChatGPT AI 算力惩罚盾与 PoW difficulty 十六进制阈值精准量化识别；
2. Google & YouTube: Google reCAPTCHA Enterprise 与 YouTube 登录机器人验证墙；
3. Reddit Fastly: 严苛机房/代理 ASN 封禁与 302 登录墙；
4. TikTok / X Social: 商业社媒反爬与滑块验证码；
5. Cloudflare Strict & Trace: 边缘挑战头 (cf-mitigated: challenge) 与 WARP 套壳检测。

特性：
- 自适应双模 TLS 指纹 (curl_cffi Chrome 131 优先 + Tuned SSLContext 回退)；
- 响应头毫秒级短路 + 16KB 流式截断；
- 5 站四级灰度赋分 (满分 100 分)；
- 驱动 [✨️] / [❇️] / [Key] 徽章与 [⚡WARP] 污染标记。
"""
import concurrent.futures
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .tls_fingerprint import StreamingResponse, is_curl_cffi_available, request_streaming

logger = logging.getLogger(__name__)


def probe_openai_sentinel(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    探针 1: OpenAI Sentinel 哨兵探针 (检测 AI 隐性降智与算力惩罚)。
    端点: POST https://chatgpt.com/backend-api/sentinel/chat-requirements
    """
    url = "https://chatgpt.com/backend-api/sentinel/chat-requirements"
    try:
        resp = request_streaming(
            method="POST",
            url=url,
            proxy=proxy,
            json_data={},
            headers={"referer": "https://chatgpt.com/", "origin": "https://chatgpt.com"},
            timeout=timeout
        )
    except Exception as e:
        logger.debug("OpenAI Sentinel 请求异常: %s", e)
        return {
            "level": "BLOCKED",
            "score": 0,
            "cf_mitigated": False,
            "pow_difficulty": None,
            "degraded": True,
            "reason": f"request_error:{type(e).__name__}"
        }

    # 1. 显式 Cloudflare 拦截头
    if resp.is_cf_mitigated or resp.status_code in (403, 451):
        return {
            "level": "BLOCKED",
            "score": 0,
            "cf_mitigated": resp.is_cf_mitigated,
            "pow_difficulty": None,
            "degraded": True,
            "reason": "cf_mitigated_or_403"
        }

    # 2. 解析 JSON 中的 proofofwork.difficulty
    pow_diff_hex = None
    diff_val = None
    try:
        data = resp.json()
        if isinstance(data, dict):
            pow_obj = data.get("proofofwork") or {}
            pow_diff_hex = pow_obj.get("difficulty")
            if isinstance(pow_diff_hex, str):
                diff_val = int(pow_diff_hex, 16)
    except Exception:
        pass

    # 3. 四级灰度判定
    # Level-A: 满血直通 (20分) - 无拦截头，difficulty >= 0x0ffff (高信任低算力要求)
    if resp.status_code == 200:
        if diff_val is not None:
            if diff_val >= 0x0ffff:
                return {
                    "level": "PASS",
                    "score": 20,
                    "cf_mitigated": False,
                    "pow_difficulty": pow_diff_hex,
                    "degraded": False,
                    "reason": "full_power_clean"
                }
            elif diff_val >= 0x00010:
                # Level-B: 轻度受限 (12分) - 中度监控池
                return {
                    "level": "DEGRADED_LIGHT",
                    "score": 12,
                    "cf_mitigated": False,
                    "pow_difficulty": pow_diff_hex,
                    "degraded": False,
                    "reason": "moderate_pow_check"
                }
            else:
                # Level-C: 高危隐性降智 (6分) - 算力极度苛刻 (坐实模型降智惩罚)
                return {
                    "level": "DEGRADED_HEAVY",
                    "score": 6,
                    "cf_mitigated": False,
                    "pow_difficulty": pow_diff_hex,
                    "degraded": True,
                    "reason": "high_difficulty_ai_degraded"
                }
        else:
            # 200 但未返回 pow 字段 (可能为正常免验证直通)
            return {
                "level": "PASS",
                "score": 20,
                "cf_mitigated": False,
                "pow_difficulty": "none",
                "degraded": False,
                "reason": "unconstrained_pass"
            }

    return {
        "level": "BLOCKED",
        "score": 0,
        "cf_mitigated": False,
        "pow_difficulty": pow_diff_hex,
        "degraded": True,
        "reason": f"http_{resp.status_code}"
    }


def probe_google_youtube(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    探针 2: Google & YouTube 探针 (reCAPTCHA Enterprise 与机器人验证墙)。
    """
    google_sorry = False
    youtube_bot_wall = False

    # Google 搜索测验
    try:
        g_resp = request_streaming("GET", "https://www.google.com/search?q=ip&hl=en", proxy=proxy, timeout=timeout)
        if g_resp.is_google_sorry or g_resp.status_code == 429:
            google_sorry = True
        elif g_resp.status_code != 200:
            google_sorry = True
    except Exception:
        google_sorry = True

    # YouTube 播放测验
    try:
        yt_resp = request_streaming("GET", "https://www.youtube.com/watch?v=jNQXAC9IVRw", proxy=proxy, timeout=timeout)
        yt_lower = yt_resp.text.lower()
        if "login_required" in yt_lower or "confirm you’re not a bot" in yt_lower or "sign in to confirm" in yt_lower:
            youtube_bot_wall = True
        elif yt_resp.status_code not in (200, 302):
            youtube_bot_wall = True
    except Exception:
        youtube_bot_wall = True

    # 四级灰度
    if not google_sorry and not youtube_bot_wall:
        return {"level": "PASS", "score": 20, "google_sorry": False, "youtube_bot_wall": False}
    elif not youtube_bot_wall and google_sorry:
        return {"level": "DEGRADED", "score": 12, "google_sorry": True, "youtube_bot_wall": False}
    elif not google_sorry and youtube_bot_wall:
        return {"level": "SOFT_WALL", "score": 6, "google_sorry": False, "youtube_bot_wall": True}
    else:
        return {"level": "BLOCKED", "score": 0, "google_sorry": True, "youtube_bot_wall": True}


def probe_reddit_fastly(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    探针 3: Reddit Fastly 探针 (严苛机房 ASN 与代理封禁盾)。
    端点: GET https://www.reddit.com/r/all/top.json?limit=1
    """
    url = "https://www.reddit.com/r/all/top.json?limit=1"
    try:
        resp = request_streaming("GET", url, proxy=proxy, timeout=timeout)
    except Exception as e:
        return {"level": "BLOCKED", "score": 0, "network_blocked": True, "login_wall": False, "reason": str(e)}

    # 403 Blocked by network security (机房硬拦截)
    if resp.status_code == 403 or "blocked by network security" in resp.text.lower():
        return {"level": "BLOCKED", "score": 0, "network_blocked": True, "login_wall": False}

    # 302 重定向登录墙
    if resp.status_code in (301, 302):
        loc = resp.headers.get("location", "").lower()
        if "login" in loc or "register" in loc:
            return {"level": "SOFT_WALL", "score": 6, "network_blocked": False, "login_wall": True}

    if resp.status_code == 200:
        # 验证返回是否为合法 JSON 且包含数据
        try:
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return {"level": "PASS", "score": 20, "network_blocked": False, "login_wall": False}
        except Exception:
            pass
        return {"level": "DEGRADED", "score": 12, "network_blocked": False, "login_wall": False}

    return {"level": "BLOCKED", "score": 0, "network_blocked": True, "login_wall": False}


def probe_tiktok_social(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    探针 4: TikTok 商业社媒探针 (Akamai / 字节泛风控与滑块验证)。
    端点: GET https://www.tiktok.com/explore
    """
    url = "https://www.tiktok.com/explore"
    try:
        resp = request_streaming("GET", url, proxy=proxy, timeout=timeout)
    except Exception as e:
        return {"level": "BLOCKED", "score": 0, "captcha_triggered": False, "reason": str(e)}

    if resp.status_code in (403, 451):
        return {"level": "BLOCKED", "score": 0, "captcha_triggered": False}

    lower_text = resp.text.lower()
    # 检查前 16KB 是否命中验证滑块
    has_captcha = any(m in lower_text for m in ("verify-bar", "captcha", "security check", "verify that you are human"))

    if resp.status_code == 200:
        if has_captcha:
            return {"level": "SOFT_WALL", "score": 6, "captcha_triggered": True}
        # 检查是否正常收到 ttwid 或会话 Cookie
        set_cookie = resp.headers.get("set-cookie", "")
        if "ttwid" in set_cookie or len(resp.body_bytes) > 2048:
            return {"level": "PASS", "score": 20, "captcha_triggered": False}
        return {"level": "DEGRADED", "score": 12, "captcha_triggered": False}

    return {"level": "BLOCKED", "score": 0, "captcha_triggered": has_captcha}


def probe_cf_strict_trace(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    探针 5: Cloudflare Strict & Trace 探针 (CF 官方挑战头与 WARP 套壳核验)。
    端点:
    - https://1.1.1.1/cdn-cgi/trace
    - https://nowsecure.nl (严格防护站) 或 https://www.cloudflare.com/
    """
    warp_status = "off"
    trace_loc = None
    try:
        trace_resp = request_streaming("GET", "https://1.1.1.1/cdn-cgi/trace", proxy=proxy, timeout=timeout)
        if trace_resp.status_code == 200:
            for line in trace_resp.text.splitlines():
                if line.startswith("warp="):
                    warp_status = line.split("=", 1)[1].strip().lower()
                elif line.startswith("loc="):
                    trace_loc = line.split("=", 1)[1].strip().upper()
    except Exception:
        pass

    # 严格防护站质询检测
    cf_mitigated = False
    strict_pass = False
    try:
        strict_resp = request_streaming("GET", "https://www.cloudflare.com/", proxy=proxy, timeout=timeout)
        if strict_resp.is_cf_mitigated:
            cf_mitigated = True
        elif strict_resp.status_code == 200:
            strict_pass = True
        elif strict_resp.status_code in (403, 503):
            cf_mitigated = True
    except Exception:
        pass

    # 四级赋分
    if cf_mitigated:
        return {
            "level": "BLOCKED",
            "score": 0,
            "cf_mitigated": True,
            "warp": warp_status,
            "trace_loc": trace_loc
        }

    # 严格站直通
    if strict_pass:
        if warp_status in ("on", "plus"):
            # 检测到 WARP 套壳，扣 8 分
            return {
                "level": "DEGRADED",
                "score": 12,
                "cf_mitigated": False,
                "warp": warp_status,
                "trace_loc": trace_loc,
                "is_warp_wrapped": True
            }
        else:
            return {
                "level": "PASS",
                "score": 20,
                "cf_mitigated": False,
                "warp": warp_status,
                "trace_loc": trace_loc,
                "is_warp_wrapped": False
            }

    return {
        "level": "SOFT_WALL",
        "score": 6,
        "cf_mitigated": False,
        "warp": warp_status,
        "trace_loc": trace_loc
    }


def evaluate_waf_shield(proxy: Optional[Union[str, Dict[str, str]]] = None, timeout: float = 3.5) -> Dict[str, Any]:
    """
    多引擎并发执行 5 大异构探针，聚合计算免盾综合得分与徽章判定。

    标准输出契约：
    {
      "waf_shield_score": 92,
      "waf_grade": "S",
      "pass_count": 4,
      "unblocked_count": 5,
      "sparkle_badge": True,
      "ai_full_power": True,
      "is_warp_wrapped": False,
      "tls_engine": "curl_cffi:chrome131",
      "probes": {
        "openai_sentinel": {...},
        "google_youtube": {...},
        "reddit_fastly": {...},
        "tiktok_social": {...},
        "cf_strict_trace": {...}
      }
    }
    """
    probes_res: Dict[str, Any] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        fut_openai = executor.submit(probe_openai_sentinel, proxy, timeout)
        fut_google = executor.submit(probe_google_youtube, proxy, timeout)
        fut_reddit = executor.submit(probe_reddit_fastly, proxy, timeout)
        fut_tiktok = executor.submit(probe_tiktok_social, proxy, timeout)
        fut_cf = executor.submit(probe_cf_strict_trace, proxy, timeout)

        probes_res["openai_sentinel"] = fut_openai.result()
        probes_res["google_youtube"] = fut_google.result()
        probes_res["reddit_fastly"] = fut_reddit.result()
        probes_res["tiktok_social"] = fut_tiktok.result()
        probes_res["cf_strict_trace"] = fut_cf.result()

    # 计算总分 (满分 100)
    total_score = sum(p.get("score", 0) for p in probes_res.values())
    total_score = max(0, min(100, total_score))

    pass_count = sum(1 for p in probes_res.values() if p.get("level") == "PASS")
    unblocked_count = sum(1 for p in probes_res.values() if p.get("score", 0) >= 12)

    # 等级划分
    if total_score >= 90:
        grade = "S"
    elif total_score >= 80:
        grade = "A"
    elif total_score >= 65:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    else:
        grade = "F"

    # ✨️ 判定: WAF Shield Score >= 85 且 至少 4 站完美直通 (移除无 cf-mitigated 要求)
    any_cf_mitigated = any(p.get("cf_mitigated") for p in probes_res.values())
    sparkle_badge = total_score >= 85 and pass_count >= 4

    # ❇️ AI 满血推理判定: OpenAI Sentinel 无高危降智惩罚
    openai_p = probes_res.get("openai_sentinel", {})
    ai_full_power = bool(openai_p.get("degraded") is False and openai_p.get("score", 0) >= 12)

    # WARP 套壳识别
    is_warp_wrapped = probes_res.get("cf_strict_trace", {}).get("warp") in ("on", "plus")

    tls_engine = "curl_cffi:chrome131" if is_curl_cffi_available() else "tuned_ssl"

    return {
        "waf_shield_score": total_score,
        "waf_grade": grade,
        "pass_count": pass_count,
        "unblocked_count": unblocked_count,
        "sparkle_badge": sparkle_badge,
        "ai_full_power": ai_full_power,
        "is_warp_wrapped": is_warp_wrapped,
        "any_cf_mitigated": any_cf_mitigated,
        "tls_engine": tls_engine,
        "probes": probes_res,
        "shield_passed": total_score >= 70  # 兼容旧布尔接口
    }

