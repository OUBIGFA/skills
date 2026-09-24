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
    {"name": "claude", "url": "https://www.anthropic.com/", "markers": ("anthropic", "claude")},
    {"name": "gemini", "url": "https://gemini.google.com/", "markers": ("gemini",)},
]
SHIELD_MIN_PASSED = 2

CHALLENGE_MARKERS = (
    "just a moment", "checking your browser", "verify you are human", "verify that you are human",
    "performing security verification", "cf-chl-", "checking if the site connection is secure",
    "请验证您是真人", "正在验证您是否是真人", "请完成安全验证",
)


def classify_http_response(status, headers, text, target):
    """分类 HTTP 初查结果。"""
    lower_headers = {k.lower(): v for k, v in headers.items()}
    lower_text = text.lower()

    if lower_headers.get("cf-mitigated", "").lower() == "challenge" or any(m in lower_text for m in CHALLENGE_MARKERS):
        return {"status": "challenge", "reason": "challenge_page"}
    if status in (403, 451):
        return {"status": "blocked", "reason": f"http_{status}"}
    if status == 429:
        return {"status": "unknown", "reason": "rate_limited"}
    if not (200 <= status < 300):
        return {"status": "unknown", "reason": f"http_{status}"}
    if any(m in lower_text for m in ("access denied", "you have been blocked", "error code: 1020")):
        return {"status": "blocked", "reason": "access_denied_page"}
    if not any(m in lower_text for m in target["markers"]):
        return {"status": "unknown", "reason": "unrecognized_page"}

    return {"status": "passed", "reason": "recognized_page_without_challenge"}


def probe_sites_http(proxies, targets=None, timeout=(3.0, 6.0)):
    """对监控目标执行 HTTP 快速免盾初查。"""
    targets = targets or SHIELD_TARGETS
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

        is_challenged = any(m in lower for m in CHALLENGE_MARKERS)
        if is_challenged:
            # 宽容等待自动解除挑战
            start_wait = time.monotonic()
            while time.monotonic() - start_wait < wait_sec:
                await asyncio.sleep(1.0)
                content = await page.content()
                lower = content.lower()
                if not any(m in lower for m in CHALLENGE_MARKERS) and any(m in lower for m in target["markers"]):
                    return {"status": "auto_passed", "reason": "challenge_resolved", "method": "browser"}
            return {"status": "challenge", "reason": "challenge_persisted", "method": "browser"}

        if status in (403, 451) or any(m in lower for m in ("access denied", "you have been blocked")):
            return {"status": "blocked", "reason": f"http_{status}", "method": "browser"}

        if any(m in lower for m in target["markers"]):
            return {"status": "passed", "reason": "clean_page", "method": "browser"}

        return {"status": "unknown", "reason": "marker_missing", "method": "browser"}
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
            headless=True,
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
    4 站中至少 SHIELD_MIN_PASSED 站直接通过或质询自动解除即判定免盾；
    未观测 (unknown)、阻断或质询未解除的站点不计入通过数。
    """
    if not results:
        return False
    rows = [results.get(t["name"]) or {} for t in SHIELD_TARGETS]
    return sum(item.get("status") in ("passed", "auto_passed") for item in rows) >= SHIELD_MIN_PASSED
