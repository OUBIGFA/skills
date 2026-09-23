# -*- coding: utf-8 -*-
"""AI 解锁检测模块: 支持 OpenAI/ChatGPT、Claude 及 Google Gemini 独立与全通判定。"""
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def probe_openai(proxies, timeout=(3.0, 6.0)):
    """检测 OpenAI / ChatGPT 解锁状态。"""
    session = requests.Session()
    session.trust_env = False
    result = {"status": "failed", "reason": "unknown"}

    try:
        # 1. 合规接口 (地区允许判定)
        comp_url = "https://api.openai.com/compliance/cookie_requirements"
        r_comp = session.get(comp_url, proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
        if r_comp.status_code == 403:
            result.update(status="blocked", reason="unsupported_region")
            return result
        if r_comp.status_code != 200 or "cookie_consent_required" not in r_comp.text:
            result.update(status="failed", reason="compliance_check_failed")
            return result

        # 2. 状态接口或模型接口 (服务连通判定)
        mobile_url = "https://ios.chat.openai.com/public-api/mobile/server_status/v1"
        r_mobile = session.get(mobile_url, proxies=proxies, timeout=timeout,
                               headers={"User-Agent": "ChatGPT/1.2024.000"})
        if r_mobile.status_code == 200:
            result.update(status="passed", reason="expected_response")
            return result

        models_url = "https://api.openai.com/v1/models"
        r_models = session.get(models_url, proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
        if r_models.status_code == 401:
            result.update(status="passed", reason="expected_auth_error")
            return result

        result.update(status="failed", reason=f"http_{r_models.status_code}")
    except requests.RequestException as e:
        result.update(status="unknown", reason=f"request_error:{type(e).__name__}")
    finally:
        session.close()

    return result


def probe_claude(proxies, timeout=(3.0, 6.0)):
    """检测 Anthropic Claude 解锁状态。"""
    session = requests.Session()
    session.trust_env = False
    result = {"status": "failed", "reason": "unknown"}

    try:
        url = "https://api.anthropic.com/v1/models"
        resp = session.get(url, proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
        if resp.status_code in (200, 401):
            result.update(status="passed", reason="expected_response")
        elif resp.status_code == 403:
            result.update(status="blocked", reason="region_unsupported")
        else:
            result.update(status="failed", reason=f"http_{resp.status_code}")
    except requests.RequestException as e:
        result.update(status="unknown", reason=f"request_error:{type(e).__name__}")
    finally:
        session.close()

    return result


def probe_gemini(proxies, google_region_info=None, timeout=(3.0, 7.0)):
    """检测 Google Gemini 解锁状态（结合 Google 地区码与可用性标志）。"""
    # 只采集一次。缺标记、YT 兜底或旧报告来源都不能导致递归重试。
    if google_region_info is None:
        from .egress_geo import probe_google_region
        google_region_info = probe_google_region(proxies, timeout=timeout)
    avail = google_region_info.get("gemini_available")
    if google_region_info.get("is_sent_to_china", False):
        return {"status": "blocked", "reason": "google_region_cn"}
    if avail is True:
        return {"status": "passed", "reason": "region_supported"}
    if avail is False:
        return {"status": "blocked", "reason": "unsupported_region"}
    return {"status": "unknown", "reason": "availability_marker_missing"}


def probe_all_ai(proxies, google_region_info=None, timeout=(3.0, 6.0)):
    """测试全部 AI 平台并判定 AI 三大全通。"""
    openai_res = probe_openai(proxies, timeout=timeout)
    claude_res = probe_claude(proxies, timeout=timeout)
    gemini_res = probe_gemini(proxies, google_region_info=google_region_info, timeout=timeout)

    is_cn = bool(google_region_info and google_region_info.get("is_sent_to_china"))
    details = {
        "openai": openai_res.get("status") == "passed",
        "claude": claude_res.get("status") == "passed",
        "gemini": gemini_res.get("status") == "passed",
    }
    ai_supported = (details["openai"] and details["claude"] and details["gemini"] and not is_cn)

    return {
        "details": details,
        "observations": {
            "openai": openai_res,
            "claude": claude_res,
            "gemini": gemini_res,
        },
        "ai_supported": ai_supported
    }
