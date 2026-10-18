# -*- coding: utf-8 -*-
"""目标网站免盾 / 过盾检测: 支持 HTTP 初查与 Playwright Chromium 真实无头浏览器复核。"""
import asyncio
import time
from urllib.parse import urlsplit

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

SHIELD_TARGETS = [
    {"name": "cloudflare", "url": "https://www.cloudflare.com/", "markers": ("cloudflare",)},
    {"name": "chatgpt", "url": "https://chatgpt.com/", "markers": ("chatgpt",)},
    {"name": "anthropic", "url": "https://www.anthropic.com/", "markers": ("anthropic", "claude")},
    {"name": "gemini", "url": "https://gemini.google.com/", "markers": ("gemini", "google")},
    {"name": "claude", "url": "https://claude.ai/", "markers": ("claude", "anthropic")},
]
SHIELD_MIN_PASSED = 2

CHALLENGE_MARKERS = (
    "just a moment", "checking your browser", "verify you are human", "verify that you are human",
    "performing security verification", "cf-chl-", "cf-browser-verification", "cf-challenge-",
    "checking if the site connection is secure", "challenge-running", "challenge-stage",
    "challenge-form", "cf_chl_opt",
    "请验证您是真人", "正在验证您是否是真人", "请完成安全验证",
)


def classify_http_response(status, headers, text, target):
    """分类 HTTP / 浏览器页面初查结果，准确区分真实拦截质询与正常业务页面。"""
    lower_headers = {k.lower(): v for k, v in headers.items()}
    lower_text = text.lower()

    # 1. 显式 Cloudflare 质询响应头
    if lower_headers.get("cf-mitigated", "").lower() == "challenge":
        return {"status": "challenge", "reason": "cf_mitigated_header"}

    # 2. 状态码阻断与质询
    if status in (403, 451):
        if any(m in lower_text for m in CHALLENGE_MARKERS):
            return {"status": "challenge", "reason": "challenge_page_403"}
        return {"status": "blocked", "reason": f"http_{status}"}
    if status == 429:
        return {"status": "unknown", "reason": "rate_limited"}
    if status == 503 and any(m in lower_text for m in CHALLENGE_MARKERS):
        return {"status": "challenge", "reason": "challenge_page_503"}
    if not (200 <= status < 300):
        return {"status": "unknown", "reason": f"http_{status}"}

    # 3. 200 响应下的访问阻断
    if any(m in lower_text for m in ("access denied", "you have been blocked", "error code: 1020")):
        return {"status": "blocked", "reason": "access_denied_page"}

    # 4. 200 响应下的硬性人机盾特征 (必须为真实拦截容器，避免正常网页包含介绍词被误判)
    has_challenge = any(m in lower_text for m in (
        "challenge-form", "challenge-stage", "challenge-running",
        "<title>just a moment", "<title>attention required", "cf-browser-verification",
        "checking if the site connection is secure"
    ))
    if has_challenge:
        return {"status": "challenge", "reason": "challenge_page_200"}

    # 5. 校验目标站标志性内容
    if not any(m in lower_text for m in target["markers"]):
        return {"status": "unknown", "reason": "unrecognized_page"}

    return {"status": "passed", "reason": "recognized_page_without_challenge"}


def probe_sites_http(proxies, targets=None, timeout=(3.0, 6.0)):
    """对监控目标执行异构 5 站免盾与防降智快速初查。

    若未传入自定义 targets，默认启动新一代 evaluate_waf_shield 异构五站探针引擎；
    若传入自定义 targets，则保持向后兼容的逐站 HTTP 探测。
    """
    if targets is not None:
        results = {}
        session = requests.Session()
        session.trust_env = False
        for target in targets:
            try:
                resp = session.get(target["url"], proxies=proxies, timeout=timeout, headers={"User-Agent": UA})
                res = classify_http_response(resp.status_code, resp.headers, resp.text, target)
                results[target["name"]] = {**res, "http_status": resp.status_code, "method": "http"}
            except requests.RequestException as e:
                results[target["name"]] = {"status": "unknown", "reason": f"request_error:{type(e).__name__}", "method": "http"}
        session.close()
        return results

    from .waf_shield_probe import evaluate_waf_shield

    to_sec = timeout[0] if isinstance(timeout, (list, tuple)) else timeout
    waf_res = evaluate_waf_shield(proxy=proxies, timeout=to_sec)
    probes = waf_res.get("probes", {})

    results = {
        "waf_evaluation": waf_res,
        "waf_shield_score": waf_res.get("waf_shield_score", 0),
        "waf_grade": waf_res.get("waf_grade", "F"),
        "sparkle_badge": waf_res.get("sparkle_badge", False),
        "ai_full_power": waf_res.get("ai_full_power", False),
        "is_warp_wrapped": waf_res.get("is_warp_wrapped", False),
        "any_cf_mitigated": waf_res.get("any_cf_mitigated", False),
        "cloudflare": {
            "status": "passed" if probes.get("cf_strict_trace", {}).get("level") == "PASS" else "challenge" if probes.get("cf_strict_trace", {}).get("cf_mitigated") else "blocked",
            "score": probes.get("cf_strict_trace", {}).get("score", 0),
            "method": "http_v3"
        },
        "chatgpt": {
            "status": "passed" if probes.get("openai_sentinel", {}).get("level") == "PASS" else "challenge" if probes.get("openai_sentinel", {}).get("cf_mitigated") else "blocked",
            "score": probes.get("openai_sentinel", {}).get("score", 0),
            "degraded": probes.get("openai_sentinel", {}).get("degraded", True),
            "method": "http_v3"
        },
        "gemini": {
            "status": "passed" if probes.get("google_youtube", {}).get("level") == "PASS" else "blocked",
            "score": probes.get("google_youtube", {}).get("score", 0),
            "method": "http_v3"
        },
        "reddit": {
            "status": "passed" if probes.get("reddit_fastly", {}).get("level") == "PASS" else "blocked",
            "score": probes.get("reddit_fastly", {}).get("score", 0),
            "method": "http_v3"
        },
        "tiktok": {
            "status": "passed" if probes.get("tiktok_social", {}).get("level") == "PASS" else "blocked",
            "score": probes.get("tiktok_social", {}).get("score", 0),
            "method": "http_v3"
        },
    }
    return results


async def _probe_one_browser(browser, proxy_url, target, wait_sec=8):
    """在 Playwright Chromium 中测试单站。"""
    context = None
    try:
        context = await browser.new_context(
            proxy={"server": proxy_url, "bypass": "<-loopback>"},
            user_agent=UA,
            locale="en-US",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        resp = await page.goto(target["url"], timeout=15000, wait_until="domcontentloaded")
        status = resp.status if resp else 0
        content = await page.content()
        lower = content.lower()

        classified = classify_http_response(status, resp.headers if resp else {}, content, target)
        if classified["status"] == "challenge":
            # 宽容等待自动解除挑战
            start_wait = time.monotonic()
            while time.monotonic() - start_wait < wait_sec:
                await asyncio.sleep(1.0)
                content = await page.content()
                lower = content.lower()
                if classify_http_response(200, {}, content, target)["status"] == "passed":
                    return {"status": "auto_passed", "reason": "challenge_resolved", "method": "browser"}
            return {"status": "challenge", "reason": "challenge_persisted", "method": "browser"}

        return {**classified, "http_status": status, "method": "browser"}
    except Exception as e:
        return {"status": "unknown", "reason": f"browser_error:{type(e).__name__}", "method": "browser"}
    finally:
        if context:
            await context.close()


async def probe_sites_browser_async(proxy_url, targets=None):
    """使用 Playwright 异步测试 4 站免盾。"""
    from playwright.async_api import async_playwright
    targets = targets or SHIELD_TARGETS
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, channel="chromium",
            args=["--disable-quic", "--disable-blink-features=AutomationControlled"]
        )
        try:
            for target in targets:
                res = await _probe_one_browser(browser, proxy_url, target)
                results[target["name"]] = res
        finally:
            await browser.close()

    return results


def probe_sites_browser(proxy_url, targets=None):
    """同步包装入口。"""
    try:
        return asyncio.run(probe_sites_browser_async(proxy_url, targets))
    except Exception as e:
        targets = targets or SHIELD_TARGETS
        return {t["name"]: {"status": "unknown", "reason": f"playwright_unavailable:{type(e).__name__}", "method": "none"}
                for t in targets}


def shield_passed(results):
    """
    免盾判定标准 (若有浏览器观测则以浏览器为准，否则以 HTTP 为准):
    免盾的核心是节点未被 Cloudflare WAF / 人机验证拦截，能够顺畅访问受保护的站点。
    判定标准:
    1. 真实浏览器体系 (若包含浏览器观测): Cloudflare 官网 或 Claude/Anthropic 官方体系至少一站通过，且总通过数 >= 2；
    2. 新一代 WAF 体系 (纯 HTTP 无浏览器观测): 若包含 waf_shield_score / waf_evaluation，则要求得分 >= 70；
    3. 传统/逐站 HTTP 体系兜底: 核心盾标至少一站通过，且总通过数 >= 2。
    """
    if not results:
        return False

    def _passed(item):
        if isinstance(item, dict):
            return item.get("status") in ("passed", "auto_passed")
        if isinstance(item, str):
            return item in ("passed", "auto_passed")
        return False

    # 1. 优先以真实浏览器观测结果为准 (Playwright 真实访问过盾)
    has_browser = any(isinstance(v, dict) and v.get("method") == "browser" for v in results.values())
    if has_browser:
        cf_pass = _passed(results.get("cloudflare"))
        claude_pass = _passed(results.get("claude")) or _passed(results.get("claude_ai")) or _passed(results.get("anthropic"))
        total_passed = sum(1 for t in SHIELD_TARGETS if _passed(results.get(t["name"])))
        if (cf_pass or claude_pass) and total_passed >= SHIELD_MIN_PASSED:
            return True

    # 2. 纯 HTTP 模式下的 WAF 评分体系
    if "waf_shield_score" in results or "waf_evaluation" in results:
        waf_eval = results.get("waf_evaluation") or {}
        score = results.get("waf_shield_score", waf_eval.get("waf_shield_score", 0))
        return score >= 70

    # 3. 传统/逐站 HTTP 体系兜底
    cf_pass = _passed(results.get("cloudflare"))
    claude_pass = _passed(results.get("claude")) or _passed(results.get("claude_ai")) or _passed(results.get("anthropic"))

    # 核心盾标 (Cloudflare 或 Claude/Anthropic 官方体系) 必须有通过
    if not (cf_pass or claude_pass):
        return False

    # 且全部监控站点中至少 2 站通过
    total_passed = sum(1 for t in SHIELD_TARGETS if _passed(results.get(t["name"])))
    return total_passed >= SHIELD_MIN_PASSED
