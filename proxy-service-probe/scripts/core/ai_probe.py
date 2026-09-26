# -*- coding: utf-8 -*-
"""AI 解锁检测模块: 支持 OpenAI/ChatGPT、Claude、Google Gemini、Groq、Hugging Face 及 Grok (xAI) 独立与全通判定。"""
import concurrent.futures
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
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
        result.update(status="blocked", reason=f"timeout:{type(e).__name__}")
    except requests.exceptions.ConnectionError as e:
        result.update(status="blocked", reason=f"connection_error:{type(e).__name__}")
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
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
        result.update(status="blocked", reason=f"timeout:{type(e).__name__}")
    except requests.exceptions.ConnectionError as e:
        result.update(status="blocked", reason=f"connection_error:{type(e).__name__}")
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


def probe_groq(proxies, timeout=(3.0, 6.0)):
    """检测 Groq (console.groq.com / chat.groq.com / api.groq.com) 解锁状态。"""
    session = requests.Session()
    session.trust_env = False
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    result = {"status": "failed", "reason": "unknown"}

    try:
        # 1. 探测 console.groq.com
        r_console = session.get("https://console.groq.com/", proxies=proxies, timeout=timeout, headers=headers)
        if r_console.status_code == 403:
            if "Access denied" in r_console.text:
                result.update(status="blocked", reason="access_denied_403")
                return result
            if (r_console.headers.get("cf-mitigated") == "challenge"
                    or "cf-chl-" in r_console.text or "Just a moment" in r_console.text):
                result.update(status="blocked", reason="cloudflare_challenge")
                return result
            result.update(status="blocked", reason="http_403")
            return result

        # 2. 探测 chat.groq.com
        r_chat = session.get("https://chat.groq.com/", proxies=proxies, timeout=timeout, headers=headers)
        if r_chat.status_code == 403:
            if "Access denied" in r_chat.text:
                result.update(status="blocked", reason="chat_access_denied_403")
                return result
            if (r_chat.headers.get("cf-mitigated") == "challenge"
                    or "cf-chl-" in r_chat.text or "Just a moment" in r_chat.text):
                result.update(status="blocked", reason="chat_cloudflare_challenge")
                return result
            result.update(status="blocked", reason="chat_http_403")
            return result

        # 3. 辅助探测 api.groq.com (无Key时401为已穿透WAF抵达鉴权层，403为网关封锁)
        api_headers = {"User-Agent": UA, "Accept": "application/json"}
        r_api = session.get("https://api.groq.com/openai/v1/models", proxies=proxies, timeout=timeout, headers=api_headers)
        if r_api.status_code == 403 and "Access denied" in r_api.text:
            result.update(status="blocked", reason="api_access_denied_403")
            return result

        if r_console.status_code == 200 and r_chat.status_code == 200:
            result.update(status="passed", reason="expected_response")
            return result

        result.update(status="failed", reason=f"console_{r_console.status_code}_chat_{r_chat.status_code}")
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
        result.update(status="blocked", reason=f"timeout:{type(e).__name__}")
    except requests.exceptions.ConnectionError as e:
        result.update(status="blocked", reason=f"connection_error:{type(e).__name__}")
    except requests.RequestException as e:
        result.update(status="unknown", reason=f"request_error:{type(e).__name__}")
    finally:
        session.close()

    return result


def probe_huggingface(proxies, timeout=(3.0, 6.0)):
    """检测 Hugging Face (huggingface.co) 解锁状态 (Web 与 模型 API 双重验证)。"""
    session = requests.Session()
    session.trust_env = False
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    result = {"status": "failed", "reason": "unknown"}

    try:
        # 1. 探测 Web 门户
        r_web = session.get("https://huggingface.co/", proxies=proxies, timeout=timeout, headers=headers)
        if r_web.status_code in (403, 1020):
            result.update(status="blocked", reason=f"web_http_{r_web.status_code}")
            return result
        if (r_web.headers.get("cf-mitigated") == "challenge"
                or "cf-chl-" in r_web.text or "Just a moment" in r_web.text):
            result.update(status="blocked", reason="cloudflare_challenge")
            return result
        text_lower = r_web.text.lower()
        if r_web.status_code != 200 or ("huggingface" not in text_lower and "hugging face" not in text_lower):
            result.update(status="failed", reason=f"web_http_{r_web.status_code}")
            return result

        # 2. 探测公开轻量 API (避免静态 CDN 假 200 误判)
        r_api = session.get("https://huggingface.co/api/models?limit=1", proxies=proxies, timeout=timeout,
                            headers={"User-Agent": UA, "Accept": "application/json"})
        if r_api.status_code == 200:
            try:
                data = r_api.json()
                if isinstance(data, list) and len(data) > 0 and ("id" in data[0] or "modelId" in data[0] or "_id" in data[0]):
                    result.update(status="passed", reason="expected_response")
                    return result
            except Exception:
                pass
        elif r_api.status_code in (403, 1020):
            result.update(status="blocked", reason=f"api_http_{r_api.status_code}")
            return result

        result.update(status="failed", reason=f"api_check_failed_http_{r_api.status_code}")
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
        result.update(status="blocked", reason=f"timeout:{type(e).__name__}")
    except requests.exceptions.ConnectionError as e:
        result.update(status="blocked", reason=f"connection_error:{type(e).__name__}")
    except requests.RequestException as e:
        result.update(status="unknown", reason=f"request_error:{type(e).__name__}")
    finally:
        session.close()

    return result


def probe_grok(proxies, timeout=(3.0, 6.0)):
    """检测 xAI Grok (grok.com) 解锁状态。"""
    session = requests.Session()
    session.trust_env = False
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    result = {"status": "failed", "reason": "unknown"}

    try:
        # 1. 探测 grok.com 门户
        r_web = session.get("https://grok.com/", proxies=proxies, timeout=timeout, headers=headers)
        if r_web.status_code in (403, 451, 1020):
            result.update(status="blocked", reason=f"http_{r_web.status_code}")
            return result
        if (r_web.headers.get("cf-mitigated") == "challenge"
                or "cf-chl-" in r_web.text or "Just a moment" in r_web.text):
            result.update(status="blocked", reason="cloudflare_challenge")
            return result
        if "not available in your region" in r_web.text.lower() or "not available in your country" in r_web.text.lower():
            result.update(status="blocked", reason="region_unsupported")
            return result

        # 2. 辅助探测 api.x.ai 模型接口 (无密钥时返回 401 证明已成功触达 xAI 网关；403 为网关封锁)
        api_headers = {"User-Agent": UA, "Accept": "application/json"}
        r_api = session.get("https://api.x.ai/v1/models", proxies=proxies, timeout=timeout, headers=api_headers)
        if r_api.status_code in (403, 1020):
            result.update(status="blocked", reason=f"api_http_{r_api.status_code}")
            return result

        if r_web.status_code == 200:
            result.update(status="passed", reason="expected_response")
            return result

        result.update(status="failed", reason=f"http_{r_web.status_code}")
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
        result.update(status="blocked", reason=f"timeout:{type(e).__name__}")
    except requests.exceptions.ConnectionError as e:
        result.update(status="blocked", reason=f"connection_error:{type(e).__name__}")
    except requests.RequestException as e:
        result.update(status="unknown", reason=f"request_error:{type(e).__name__}")
    finally:
        session.close()

    return result


def probe_all_ai(proxies, google_region_info=None, timeout=(3.0, 6.0)):
    """
    测试全部 AI 平台并判定 AI 六大核心全解锁。
    涵盖: OpenAI/ChatGPT, Claude, Gemini, Groq, HuggingFace, Grok (xAI)。
    采用线程池并发探测，控制总检测耗时在最慢单个端点耗时内。
    """
    # Gemini 依赖已获得的 google_region_info 判断，无耗时网络请求
    gemini_res = probe_gemini(proxies, google_region_info=google_region_info, timeout=timeout)

    tasks = {
        "openai": lambda: probe_openai(proxies, timeout=timeout),
        "claude": lambda: probe_claude(proxies, timeout=timeout),
        "groq": lambda: probe_groq(proxies, timeout=timeout),
        "huggingface": lambda: probe_huggingface(proxies, timeout=timeout),
        "grok": lambda: probe_grok(proxies, timeout=timeout),
    }

    obs = {"gemini": gemini_res}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                obs[name] = future.result()
            except Exception as e:
                obs[name] = {"status": "unknown", "reason": f"thread_error:{type(e).__name__}"}

    is_cn = bool(google_region_info and google_region_info.get("is_sent_to_china"))
    details = {
        "openai": obs.get("openai", {}).get("status") == "passed",
        "claude": obs.get("claude", {}).get("status") == "passed",
        "gemini": obs.get("gemini", {}).get("status") == "passed",
        "groq": obs.get("groq", {}).get("status") == "passed",
        "huggingface": obs.get("huggingface", {}).get("status") == "passed",
        "grok": obs.get("grok", {}).get("status") == "passed",
    }

    # AI 全解锁核心5大平台: OpenAI, Claude, Gemini, HuggingFace, Grok (Groq 剔除出 AI 门槛，仅作综合全通加分)
    ai_core_keys = ("openai", "claude", "gemini", "huggingface", "grok")
    ai_core_passed = all(details[k] for k in ai_core_keys)
    ai_supported = (ai_core_passed and not is_cn)

    core_passed = sum(1 for k in ai_core_keys if details.get(k))
    core_total = len(ai_core_keys)
    failed_core_services = [k for k in ai_core_keys if not details.get(k)]

    summary = {
        "score": f"{core_passed}/{core_total}",
        "passed": core_passed,
        "total": core_total,
        "failed_services": failed_core_services,
        "ai_core_passed": ai_core_passed,
        "groq_passed": details.get("groq", False),
        "all_passed": sum(1 for v in details.values() if v),
        "all_total": len(details),
    }

    return {
        "details": details,
        "observations": obs,
        "summary": summary,
        "ai_supported": ai_supported,
    }
