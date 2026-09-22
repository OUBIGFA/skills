# -*- coding: utf-8 -*-
"""YouTube 免登录实播检测: 基于 Playwright Chromium、HTML5 观察者及双向出口复核。"""
import asyncio
import time
import re

YOUTUBE_VIDEO_IDS = ("jNQXAC9IVRw", "YE7VzlLtp-4", "M7lc1UVf-VE")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# 注入给页面的 HTML5 播放观察脚本
OBSERVER_JS = """
(() => {
    window.__yt_probe = {
        startTime: -1,
        playedSeconds: 0,
        lastTime: 0,
        stalled: false,
        error: null,
        botRequired: false,
        signInRequired: false
    };

    const check = () => {
        // 检查风控提示
        const text = document.body ? document.body.innerText : "";
        if (text.includes("Sign in to confirm you’re not a bot") || text.includes("正在验证您是否是真人")) {
            window.__yt_probe.botRequired = true;
        }
        if (text.includes("Sign in to confirm your age") || text.includes("This video is age-restricted")) {
            window.__yt_probe.signInRequired = true;
        }

        const video = document.querySelector('video');
        if (!video) return;

        // 确保静音并尝试触发播放 (突破 Chrome Autoplay Policy)
        video.muted = true;
        if (video.paused) {
            video.play().catch(() => {});
        }

        if (video.currentTime > 0 && !video.paused) {
            if (window.__yt_probe.startTime < 0) {
                window.__yt_probe.startTime = Date.now();
                window.__yt_probe.lastTime = video.currentTime;
            } else {
                const diff = video.currentTime - window.__yt_probe.lastTime;
                if (diff > 0) {
                    window.__yt_probe.playedSeconds += diff;
                    window.__yt_probe.lastTime = video.currentTime;
                }
            }
        }
    };

    setInterval(check, 300);
})();
"""


async def _get_context_ip(context):
    """获取当前浏览器上下文的出口公网 IP。"""
    try:
        page = await context.new_page()
        try:
            resp = await page.goto("https://api.ipify.org?format=json", timeout=8000)
            if resp and resp.status == 200:
                text = await page.content()
                m = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
                if m:
                    return m.group(0)
        finally:
            await page.close()
    except Exception:
        pass
    return None


async def probe_single_video(context, video_id, target_duration=10.0, max_wait=20.0):
    """测试单个视频的免登录真实播放。"""
    page = await context.new_page()
    url = f"https://www.youtube.com/watch?v={video_id}&hl=en"
    try:
        await page.add_init_script(OBSERVER_JS)
        await page.goto(url, timeout=18000, wait_until="domcontentloaded")

        # 尝试点击潜在的 Cookie 弹窗或播放按钮
        try:
            for selector in (".ytp-large-play-button", "button[aria-label*='Play']", "button[aria-label*='Accept']", "button[aria-label*='Agree']", ".ytp-play-button"):
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=800):
                    await btn.click()
        except Exception:
            pass

        start_time = time.monotonic()
        while time.monotonic() - start_time < max_wait:
            status = await page.evaluate("() => window.__yt_probe")
            if status.get("botRequired"):
                return {"status": "bot_required", "reason": "bot_verification_required", "played": 0}
            if status.get("signInRequired"):
                return {"status": "sign_in_required", "reason": "login_prompted", "played": 0}

            played = status.get("playedSeconds", 0)
            if played >= target_duration:
                return {"status": "passed", "reason": "video_played_cleanly", "played": round(played, 1)}

            await asyncio.sleep(0.5)

        return {"status": "failed", "reason": "playback_timeout_or_buffering", "played": 0}
    except Exception as e:
        return {"status": "unknown", "reason": f"error:{type(e).__name__}", "played": 0}
    finally:
        await page.close()


async def probe_youtube_async(proxy_url, expected_ip=None, videos=YOUTUBE_VIDEO_IDS):
    """异步执行 YouTube 免登实播检测。"""
    from playwright.async_api import async_playwright
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-quic",
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required"
            ]
        )
        try:
            context = await browser.new_context(
                proxy={"server": proxy_url, "bypass": "<-loopback>"},
                user_agent=UA,
                locale="en-US",
                viewport={"width": 960, "height": 600}
            )

            # 播放前出口复核
            if expected_ip:
                ctx_ip_before = await _get_context_ip(context)
                if ctx_ip_before and ctx_ip_before != expected_ip:
                    return {
                        "status": "failed",
                        "reason": f"egress_mismatch_before:{ctx_ip_before}!={expected_ip}",
                        "passed_count": 0,
                        "samples": []
                    }

            for vid in videos:
                res = await probe_single_video(context, vid)
                res["video_id"] = vid
                results.append(res)
                # 若已通过 2 个视频则提前达标
                passed_so_far = sum(r["status"] == "passed" for r in results)
                if passed_so_far >= 2:
                    break
                if res["status"] in ("bot_required", "sign_in_required"):
                    break

            # 播放后出口复核
            if expected_ip:
                ctx_ip_after = await _get_context_ip(context)
                if ctx_ip_after and ctx_ip_after != expected_ip:
                    return {
                        "status": "failed",
                        "reason": f"egress_mismatch_after:{ctx_ip_after}!={expected_ip}",
                        "passed_count": 0,
                        "samples": results
                    }

            await context.close()
        finally:
            await browser.close()

    passed_count = sum(r["status"] == "passed" for r in results)
    status = "passed" if passed_count >= 2 else "failed"
    return {
        "status": status,
        "passed_count": passed_count,
        "samples": results,
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
