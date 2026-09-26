# -*- coding: utf-8 -*-
"""浏览器实播的出口证据和播放计时回归；真实 Chromium 测试只打开本地空白页。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import shield_probe, youtube_probe


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        pass


class BrowserEgressTests(unittest.IsolatedAsyncioTestCase):
    async def run_probe(self, before, after):
        context = SimpleNamespace(close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        chromium = SimpleNamespace(launch=AsyncMock(return_value=browser))
        playwright = AsyncContext(SimpleNamespace(chromium=chromium))
        samples = [{'status': 'passed', 'played': 10.1}, {'status': 'passed', 'played': 10.1}]
        with patch('playwright.async_api.async_playwright', return_value=playwright), \
                patch.object(youtube_probe, '_get_context_ip', AsyncMock(side_effect=[before, after])), \
                patch.object(youtube_probe, 'probe_single_video', AsyncMock(side_effect=samples)):
            result = await youtube_probe.probe_youtube_async('http://127.0.0.1:40000', expected_ip='1.1.1.1')
        browser.close.assert_awaited_once()
        return result, context, chromium

    async def test_missing_browser_exit_before_playback_does_not_pass(self):
        result, context, _ = await self.run_probe(None, '1.1.1.1')
        self.assertNotEqual(result['status'], 'passed')
        self.assertEqual(result['samples'], [])
        self.assertEqual(result['reason'], 'browser_egress_unverified')
        context.close.assert_awaited_once()

    async def test_missing_browser_exit_after_playback_does_not_pass(self):
        result, context, _ = await self.run_probe('1.1.1.1', None)
        self.assertNotEqual(result['status'], 'passed')
        self.assertEqual(len(result['samples']), 2)
        self.assertFalse(result['egress']['verified'])
        context.close.assert_awaited_once()

    async def test_changed_browser_exit_never_passes(self):
        result, _, _ = await self.run_probe('1.1.1.1', '8.8.8.8')
        self.assertNotEqual(result['status'], 'passed')

    async def test_verified_two_video_run_uses_full_chromium(self):
        result, context, chromium = await self.run_probe('1.1.1.1', '1.1.1.1')
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['egress']['verified'])
        self.assertEqual(chromium.launch.call_args.kwargs['channel'], 'chromium')
        context.close.assert_awaited_once()

    async def test_browser_ip_rejects_html_and_uses_independent_fallback(self):
        responses = [SimpleNamespace(status=200, text=AsyncMock(return_value='<html>error from 9.9.9.9</html>')),
                     SimpleNamespace(status=200, text=AsyncMock(return_value='8.8.8.8\n'))]
        page = SimpleNamespace(goto=AsyncMock(side_effect=responses), close=AsyncMock(),
                               content=AsyncMock(return_value='<html>error from 9.9.9.9</html>'))
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        self.assertEqual(await youtube_probe._get_context_ip(context), '8.8.8.8')
        self.assertEqual(page.goto.await_count, 2)
        page.close.assert_awaited_once()


class ShieldBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_pages_with_brand_names_do_not_pass(self):
        target = {"name": "gemini", "url": "https://gemini.google.com/", "markers": ("gemini",)}
        for status in (429, 500, 503):
            with self.subTest(status=status):
                response = SimpleNamespace(status=status, headers={})
                page = SimpleNamespace(goto=AsyncMock(return_value=response),
                                       content=AsyncMock(return_value='<html>Gemini temporarily unavailable</html>'))
                context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
                browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
                result = await shield_probe._probe_one_browser(browser, 'http://127.0.0.1:40000', target)
                self.assertEqual(result['status'], 'unknown')
                self.assertEqual(result['http_status'], status)
                context.close.assert_awaited_once()


class PlaybackObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.driver = sync_playwright().start()
        try:
            cls.browser = cls.driver.chromium.launch(headless=True, channel='chromium')
        except Exception as error:
            cls.driver.stop()
            raise unittest.SkipTest(f'Full Chromium unavailable: {error}')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content('<video></video>')
        self.page.evaluate('''() => {
            window.state = {time: 1, paused: false, seeking: false, ready: 4, clock: 0};
            const video = document.querySelector('video');
            Object.defineProperties(video, {
                currentTime: {get: () => state.time}, paused: {get: () => state.paused},
                seeking: {get: () => state.seeking}, readyState: {get: () => state.ready}
            });
            video.play = () => Promise.resolve();
            window.setInterval = callback => {window.tick = callback; return 1;};
            Object.defineProperty(performance, 'now', {value: () => state.clock});
        }''')
        self.page.evaluate(youtube_probe.OBSERVER_JS)
        self.page.evaluate('tick()')

    def tearDown(self):
        self.page.close()

    def tick(self, media_time, clock_ms, **values):
        return self.page.evaluate('''values => {
            Object.assign(state, values); tick(); return window.__yt_probe;
        }''', {'time': media_time, 'clock': clock_ms, **values})

    def test_normal_playback_accumulates_ten_real_seconds(self):
        for second in range(1, 12):
            result = self.tick(1 + second, second * 1000)
        self.assertGreaterEqual(result['playedSeconds'], 10)
        self.assertFalse(result['stalled'])

    def test_seek_jump_is_not_counted_as_playback(self):
        self.tick(501, 300)
        result = self.tick(501.3, 600)
        self.assertLess(result['playedSeconds'], 1)

    def test_buffering_never_counts_as_healthy_playback(self):
        for second in range(1, 12):
            result = self.tick(1 + second, second * 1000, ready=1)
        self.assertEqual(result['playedSeconds'], 0)
        self.assertTrue(result['stalled'])

    def test_advertisement_is_not_the_requested_video(self):
        self.page.evaluate("document.body.className = 'html5-video-player ad-showing'")
        for second in range(1, 12):
            result = self.tick(1 + second, second * 1000)
        self.assertEqual(result['playedSeconds'], 0)

    def test_ascii_apostrophe_bot_prompt_is_detected(self):
        self.page.evaluate('''document.body.append("Sign in to confirm you're not a bot")''')
        result = self.tick(2, 1000)
        self.assertTrue(result['botRequired'])


if __name__ == '__main__':
    unittest.main()