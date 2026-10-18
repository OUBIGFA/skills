# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from scripts.core.tls_fingerprint import StreamingResponse
from scripts.core.waf_shield_probe import (
    evaluate_waf_shield,
    probe_cf_strict_trace,
    probe_google_youtube,
    probe_openai_sentinel,
    probe_reddit_fastly,
)


class TestWAFShieldProbe(unittest.TestCase):
    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_openai_sentinel_full_power(self, mock_stream):
        mock_stream.return_value = StreamingResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body_bytes=b'{"proofofwork": {"difficulty": "0fffff"}}',
            engine="curl_cffi:chrome131"
        )
        res = probe_openai_sentinel()
        self.assertEqual(res["level"], "PASS")
        self.assertEqual(res["score"], 20)
        self.assertFalse(res["degraded"])

    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_openai_sentinel_degraded_heavy(self, mock_stream):
        mock_stream.return_value = StreamingResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body_bytes=b'{"proofofwork": {"difficulty": "000005"}}',
            engine="curl_cffi:chrome131"
        )
        res = probe_openai_sentinel()
        self.assertEqual(res["level"], "DEGRADED_HEAVY")
        self.assertEqual(res["score"], 6)
        self.assertTrue(res["degraded"])

    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_openai_sentinel_cf_mitigated(self, mock_stream):
        mock_stream.return_value = StreamingResponse(
            status_code=403,
            headers={"cf-mitigated": "challenge"},
            body_bytes=b"",
            engine="curl_cffi:chrome131",
            short_circuited=True
        )
        res = probe_openai_sentinel()
        self.assertEqual(res["level"], "BLOCKED")
        self.assertEqual(res["score"], 0)
        self.assertTrue(res["degraded"])

    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_google_youtube_levels(self, mock_stream):
        # 模拟 Google 200，YouTube 200 无机器人墙
        mock_stream.side_effect = [
            StreamingResponse(200, {}, b"Google Search IP", "curl_cffi"),
            StreamingResponse(200, {}, b"YouTube Watch Normal Video", "curl_cffi")
        ]
        res = probe_google_youtube()
        self.assertEqual(res["level"], "PASS")
        self.assertEqual(res["score"], 20)

    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_reddit_fastly_blocked(self, mock_stream):
        mock_stream.return_value = StreamingResponse(
            403, {}, b"Blocked by network security", "curl_cffi"
        )
        res = probe_reddit_fastly()
        self.assertEqual(res["level"], "BLOCKED")
        self.assertEqual(res["score"], 0)
        self.assertTrue(res["network_blocked"])

    @patch("scripts.core.waf_shield_probe.request_streaming")
    def test_cf_strict_trace_warp_wrapped(self, mock_stream):
        # 模拟 trace 返回 warp=on，且严格站通过
        mock_stream.side_effect = [
            StreamingResponse(200, {}, b"warp=on\nloc=US\n", "curl_cffi"),
            StreamingResponse(200, {}, b"Cloudflare Page Normal", "curl_cffi")
        ]
        res = probe_cf_strict_trace()
        self.assertEqual(res["level"], "DEGRADED")
        self.assertEqual(res["score"], 12)
        self.assertTrue(res.get("is_warp_wrapped"))

    @patch("scripts.core.waf_shield_probe.probe_cf_strict_trace")
    @patch("scripts.core.waf_shield_probe.probe_tiktok_social")
    @patch("scripts.core.waf_shield_probe.probe_reddit_fastly")
    @patch("scripts.core.waf_shield_probe.probe_google_youtube")
    @patch("scripts.core.waf_shield_probe.probe_openai_sentinel")
    def test_evaluate_waf_shield_aggregation(self, p_ai, p_gy, p_red, p_tik, p_cf):
        p_ai.return_value = {"level": "PASS", "score": 20, "degraded": False}
        p_gy.return_value = {"level": "PASS", "score": 20}
        p_red.return_value = {"level": "PASS", "score": 20}
        p_tik.return_value = {"level": "PASS", "score": 20}
        p_cf.return_value = {"level": "PASS", "score": 20, "warp": "off"}

        res = evaluate_waf_shield()
        self.assertEqual(res["waf_shield_score"], 100)
        self.assertEqual(res["waf_grade"], "S")
        self.assertEqual(res["pass_count"], 5)
        self.assertTrue(res["sparkle_badge"])
        self.assertTrue(res["ai_full_power"])
        self.assertFalse(res["is_warp_wrapped"])
        self.assertFalse(res["any_cf_mitigated"])

    @patch("scripts.core.waf_shield_probe.probe_cf_strict_trace")
    @patch("scripts.core.waf_shield_probe.probe_tiktok_social")
    @patch("scripts.core.waf_shield_probe.probe_reddit_fastly")
    @patch("scripts.core.waf_shield_probe.probe_google_youtube")
    @patch("scripts.core.waf_shield_probe.probe_openai_sentinel")
    def test_evaluate_waf_shield_sparkle_granted_despite_cf_mitigated(self, p_ai, p_gy, p_red, p_tik, p_cf):
        # 模拟 4 站满分 (80分)，第 5 站虽然有 cf_mitigated 触发且有部分得分 (如总分达到 86 分且 4 站 PASS)
        p_ai.return_value = {"level": "PASS", "score": 25, "degraded": False}
        p_gy.return_value = {"level": "PASS", "score": 20}
        p_red.return_value = {"level": "PASS", "score": 20}
        p_tik.return_value = {"level": "PASS", "score": 20}
        p_cf.return_value = {"level": "BLOCKED", "score": 5, "cf_mitigated": True, "warp": "off"}

        res = evaluate_waf_shield()
        self.assertEqual(res["waf_shield_score"], 90)
        self.assertEqual(res["pass_count"], 4)
        self.assertTrue(res["any_cf_mitigated"])
        # ✨️ 条件移除了无 cf-mitigated 的限制，因此仍然获得 sparkle_badge
        self.assertTrue(res["sparkle_badge"])


if __name__ == "__main__":
    unittest.main()

