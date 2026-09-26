# -*- coding: utf-8 -*-
"""YouTube 免登录实播检测: 基于 Playwright Chromium、HTML5 观察者及双向出口复核。"""
import asyncio
import json
import time
import re

from .egress_geo import public_ip

YOUTUBE_VIDEO_IDS = ("jNQXAC9IVRw", "YE7VzlLtp-4", "M7lc1UVf-VE")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# 注入给页面的 HTML5 播放观察脚本
OBSERVER_JS = """
(() => {
    const probe = window.__yt_probe = {
        playedSeconds: 0, lastTime: null, lastWall: null,
        stalled: true, readyState: 0, inAd: false,
        error: null, botRequired: false, signInRequired: false
    };
    let previousVideo = null;
    const check = () => {
        const text = document.body ? document.body.innerText : "";
        if (/sign in to confirm you['’]re not a bot/i.test(text) || text.includes("正在验证您是否是真人")) {
            probe.botRequired = true;
        }
        if (/sign in to confirm your age|this video is age-restricted/i.test(text)) {
            probe.signInRequired = true;
        }
        const video = document.querySelector('video');
        if (!video) {
            probe.stalled = true;
            probe.lastTime = probe.lastWall = null;
            return;
        }
        if (video !== previousVideo) {
            probe.lastTime = probe.lastWall = null;
            previousVideo = video;
        }
        const now = performance.now();
        const delta = probe.lastTime === null ? 0 : video.currentTime - probe.lastTime;
        const elapsed = probe.lastWall === null ? 0 : (now - probe.lastWall) / 1000;
        probe.readyState = video.readyState;
        probe.inAd = !!document.querySelector('.html5-video-player.ad-showing, .html5-video-player.ad-interrupting');
        probe.error = video.error ? video.error.code : null;
        const healthy = !video.paused && !video.seeking && video.readyState >= 3 && !probe.error && !probe.inAd;
        probe.stalled = !healthy || delta <= 0;
        // 只计健康实播，跳进度、广告或倍速不能伪造 10 秒观看；墙钟为计时上限。
        if (healthy && elapsed > 0 && delta > 0 && delta <= elapsed * 1.5 + 0.1) {
            probe.playedSeconds += Math.min(delta, elapsed);
        }
        probe.lastTime = video.currentTime;
        probe.lastWall = now;
        video.muted = true;
        if (video.paused && !video.ended) video.play().catch(() => {});
    };
    setInterval(check, 300);
})();
"""


async def _get_context_ip(context, expected_ip=None):
    """浏览器实际导航回显公网 IP；独立 HTTPS 端点兜底，拒绝从 HTML 错误页中抽取任意 IP。"""
    ipv6 = bool(expected_ip and ":" in expected_ip)
    urls = (("https://api6.ipify.org?format=json", "https://ipv6.icanhazip.com") if ipv6 else
            ("https://api.ipify.org?format=json", "https://ipv4.icanhazip.com"))
    page = await context.new_page()
    try:
        for url in urls:
            try:
                resp = await page.goto(url, timeout=8000, wait_until="domcontentloaded")
                if not resp or resp.status != 200:
                    continue
                text = await resp.text()
                if "format=json" in url:
                    data = json.loads(text)
                    value = data.get("ip") if isinstance(data, dict) else None
                else:
                    value = text
                ip = public_ip(value)
                if ip and (":" in ip) == ipv6:
                    return ip
            except Exception:
                continue
    finally:
        await page.close()
    return None


async def probe_single_video(context, video_id, target_duration=10.0, max_wait=20.0):
    """测试单个视频的免登录真实播放。"""
    page = await context.new_page()
    url = f"https://www.youtube.com/watch?v={video_id}&hl=en"
    try:
        await page.add_init_script(OBSERVER_JS)
        response = await page.goto(url, timeout=18000, wait_until="domcontentloaded")
        if response and response.status == 429:
            return {"status": "rate_limited", "reason": "http_429", "played": 0}

        # 单个按钮缺失不能阻止后续 Cookie 同意按钮；不点击会把已播放视频暂停的控制条按钮。
        for selector in ("button[aria-label*='Accept']", "button[aria-label*='Agree']", ".ytp-large-play-button"):
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click(timeout=1500)
            except Exception:
                continue
        try:
            consent = page.get_by_role("button", name=re.compile(r"^(Accept all|I agree|Agree)$", re.I)).first
            if await consent.is_visible():
                await consent.click(timeout=1500)
        except Exception:
            pass

        start_time = time.monotonic()
        status = {}
        while time.monotonic() - start_time < max_wait:
            status = await page.evaluate("() => window.__yt_probe") or {}
            if status.get("botRequired"):
                return {"status": "bot_required", "reason": "bot_verification_required", "played": 0}
            if status.get("signInRequired"):
                return {"status": "sign_in_required", "reason": "login_prompted", "played": 0}

            played = status.get("playedSeconds", 0)
            if played >= target_duration and status.get("readyState", 0) >= 3 and not status.get("stalled", True):
                return {"status": "passed", "reason": "video_played_cleanly", "played": round(played, 1),
                        "ready_state": status["readyState"]}

            await asyncio.sleep(0.5)

        return {"status": "failed", "reason": "playback_timeout_or_buffering",
                "played": round(status.get("playedSeconds", 0), 1), "ready_state": status.get("readyState")}
    except Exception as e:
        return {"status": "unknown", "reason": f"error:{type(e).__name__}", "played": 0}
    finally:
        await page.close()


async def probe_youtube_async(proxy_url, expected_ip=None, videos=YOUTUBE_VIDEO_IDS):
    """两段真实播放 + 播放前后完整公网出口证据；缺失证据不能判通过。"""
    from playwright.async_api import async_playwright
    results = []
    expected = public_ip(expected_ip)
    egress = {"expected": expected, "before": None, "after": None, "verified": False}

    def unverified(phase):
        return {"status": "failed", "reason": "browser_egress_unverified", "phase": phase,
                "passed_count": 0, "samples": results, "egress": dict(egress)}

    if expected_ip and not expected:
        return unverified("invalid_expected_ip")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, channel="chromium",
            args=["--disable-quic", "--disable-blink-features=AutomationControlled",
                  "--autoplay-policy=no-user-gesture-required"]
        )
        try:
            context = await browser.new_context(
                proxy={"server": proxy_url, "bypass": "<-loopback>"}, user_agent=UA,
                locale="en-US", viewport={"width": 960, "height": 600}
            )
            try:
                egress["before"] = await _get_context_ip(context, expected_ip=expected)
                if not egress["before"] or (expected and egress["before"] != expected):
                    return unverified("before")
                for vid in videos:
                    res = await probe_single_video(context, vid)
                    res["video_id"] = vid
                    results.append(res)
                    if sum(r["status"] == "passed" for r in results) >= 2:
                        break
                    if res["status"] in ("bot_required", "sign_in_required", "rate_limited"):
                        break
                egress["after"] = await _get_context_ip(context, expected_ip=expected)
                if not egress["after"] or egress["after"] != egress["before"]:
                    return unverified("after")
                egress["verified"] = True
            finally:
                await context.close()
        finally:
            await browser.close()

    passed_count = sum(r["status"] == "passed" for r in results)
    return {
        "status": "passed" if passed_count >= 2 else "failed", "passed_count": passed_count,
        "samples": results, "egress": egress,
        "reason": "two_videos_played_cleanly" if passed_count >= 2 else "insufficient_passed_samples"
    }


def probe_youtube(proxy_url, expected_ip=None):
    """同步包装入口。"""
    try:
        return asyncio.run(probe_youtube_async(proxy_url, expected_ip=expected_ip))
    except Exception as e:
        return {
            "status": "unknown",
            "passed_count": 0,
            "samples": [],
            "reason": f"playwright_unavailable:{type(e).__name__}"
        }
