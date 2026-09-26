# -*- coding: utf-8 -*-
"""测试 ai_probe 模块: 覆盖 OpenAI、Claude、Gemini、Groq、HuggingFace、Grok 六大 AI 平台检测逻辑与并发调度。"""
import unittest
from unittest.mock import MagicMock, patch
import requests

from scripts.core.ai_probe import (
    probe_openai,
    probe_claude,
    probe_gemini,
    probe_groq,
    probe_huggingface,
    probe_grok,
    probe_all_ai,
)


class TestAIProbe(unittest.TestCase):

    def test_gemini_detection(self):
        # 1. 正常解锁
        res = probe_gemini(None, google_region_info={"gemini_available": True, "is_sent_to_china": False})
        self.assertEqual(res["status"], "passed")

        # 2. 地区不支持
        res_unsupp = probe_gemini(None, google_region_info={"gemini_available": False, "is_sent_to_china": False})
        self.assertEqual(res_unsupp["status"], "blocked")

        # 3. 送中标记剥离
        res_cn = probe_gemini(None, google_region_info={"gemini_available": True, "is_sent_to_china": True})
        self.assertEqual(res_cn["status"], "blocked")
        self.assertEqual(res_cn["reason"], "google_region_cn")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_groq_passed(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        # console 200, chat 200, api 401
        r_console = MagicMock(status_code=200, text="<html>GroqCloud</html>", headers={})
        r_chat = MagicMock(status_code=200, text="<html>GroqChat</html>", headers={})
        r_api = MagicMock(status_code=401, text='{"error":{"message":"Invalid API Key"}}', headers={})
        session.get.side_effect = [r_console, r_chat, r_api]

        res = probe_groq(None)
        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["reason"], "expected_response")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_groq_blocked_access_denied(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        # console 403 Access denied
        r_console = MagicMock(status_code=403, text='{"error":{"message":"Access denied. Please check your network settings."}}', headers={})
        session.get.return_value = r_console

        res = probe_groq(None)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["reason"], "access_denied_403")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_groq_blocked_cf_challenge(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        r_console = MagicMock(status_code=403, text="<html>Just a moment...</html>", headers={"cf-mitigated": "challenge"})
        session.get.return_value = r_console

        res = probe_groq(None)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["reason"], "cloudflare_challenge")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_groq_timeout(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.exceptions.ConnectTimeout("Connection timed out")

        res = probe_groq(None)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("timeout", res["reason"])

    @patch("scripts.core.ai_probe.requests.Session")
    def test_huggingface_passed(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        r_web = MagicMock(status_code=200, text="<html><title>Hugging Face</title></html>", headers={})
        r_api = MagicMock(status_code=200, headers={})
        r_api.json.return_value = [{"id": "bert-base-uncased", "modelId": "bert-base-uncased"}]
        session.get.side_effect = [r_web, r_api]

        res = probe_huggingface(None)
        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["reason"], "expected_response")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_huggingface_blocked_cf(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        r_web = MagicMock(status_code=403, text="<html>Attention Required! Cloudflare</html>", headers={"cf-mitigated": "challenge"})
        session.get.return_value = r_web

        res = probe_huggingface(None)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["reason"], "web_http_403")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_huggingface_connection_error(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.exceptions.ConnectionError("Connection reset by peer")

        res = probe_huggingface(None)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("connection_error", res["reason"])

    @patch("scripts.core.ai_probe.requests.Session")
    def test_grok_passed(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        r_web = MagicMock(status_code=200, text="<html><link href='https://cdn.grok.com' /></html>", headers={})
        r_api = MagicMock(status_code=401, text='{"error":"No credentials presented."}', headers={})
        session.get.side_effect = [r_web, r_api]

        res = probe_grok(None)
        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["reason"], "expected_response")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_grok_blocked_region(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        r_web = MagicMock(status_code=200, text="<html>Not available in your country</html>", headers={})
        session.get.return_value = r_web

        res = probe_grok(None)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["reason"], "region_unsupported")

    @patch("scripts.core.ai_probe.requests.Session")
    def test_grok_timeout(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.exceptions.ReadTimeout("Read timed out")

        res = probe_grok(None)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("timeout", res["reason"])

    @patch("scripts.core.ai_probe.probe_grok")
    @patch("scripts.core.ai_probe.probe_huggingface")
    @patch("scripts.core.ai_probe.probe_groq")
    @patch("scripts.core.ai_probe.probe_claude")
    @patch("scripts.core.ai_probe.probe_openai")
    def test_probe_all_ai_all_passed(self, m_openai, m_claude, m_groq, m_hf, m_grok):
        m_openai.return_value = {"status": "passed", "reason": "ok"}
        m_claude.return_value = {"status": "passed", "reason": "ok"}
        m_groq.return_value = {"status": "passed", "reason": "ok"}
        m_hf.return_value = {"status": "passed", "reason": "ok"}
        m_grok.return_value = {"status": "passed", "reason": "ok"}

        geo_info = {"gemini_available": True, "is_sent_to_china": False}
        res = probe_all_ai(None, google_region_info=geo_info)

        self.assertTrue(res["ai_supported"])
        self.assertEqual(res["summary"]["score"], "5/5")
        self.assertEqual(res["summary"]["passed"], 5)
        self.assertEqual(len(res["summary"]["failed_services"]), 0)
        self.assertEqual(res["summary"]["all_passed"], 6)

    @patch("scripts.core.ai_probe.probe_grok")
    @patch("scripts.core.ai_probe.probe_huggingface")
    @patch("scripts.core.ai_probe.probe_groq")
    @patch("scripts.core.ai_probe.probe_claude")
    @patch("scripts.core.ai_probe.probe_openai")
    def test_probe_all_ai_groq_failed_still_passes_ai(self, m_openai, m_claude, m_groq, m_hf, m_grok):
        # 核心5平台全部通过，Groq 未通过：按照新规则，依然判定为 AI 全解锁 (ai_supported=True, score 5/5)
        m_openai.return_value = {"status": "passed", "reason": "ok"}
        m_claude.return_value = {"status": "passed", "reason": "ok"}
        m_groq.return_value = {"status": "blocked", "reason": "access_denied_403"}
        m_hf.return_value = {"status": "passed", "reason": "ok"}
        m_grok.return_value = {"status": "passed", "reason": "ok"}

        geo_info = {"gemini_available": True, "is_sent_to_china": False}
        res = probe_all_ai(None, google_region_info=geo_info)

        self.assertTrue(res["ai_supported"])
        self.assertTrue(res["summary"]["ai_core_passed"])
        self.assertFalse(res["summary"]["groq_passed"])
        self.assertEqual(res["summary"]["score"], "5/5")
        self.assertEqual(res["summary"]["all_passed"], 5)
        self.assertEqual(res["summary"]["all_total"], 6)

    @patch("scripts.core.ai_probe.probe_grok")
    @patch("scripts.core.ai_probe.probe_huggingface")
    @patch("scripts.core.ai_probe.probe_groq")
    @patch("scripts.core.ai_probe.probe_claude")
    @patch("scripts.core.ai_probe.probe_openai")
    def test_probe_all_ai_core_failed_disqualifies(self, m_openai, m_claude, m_groq, m_hf, m_grok):
        # 核心5平台之一（如 Grok）失败：ai_supported 必须为 False
        m_openai.return_value = {"status": "passed", "reason": "ok"}
        m_claude.return_value = {"status": "passed", "reason": "ok"}
        m_groq.return_value = {"status": "passed", "reason": "ok"}
        m_hf.return_value = {"status": "passed", "reason": "ok"}
        m_grok.return_value = {"status": "blocked", "reason": "timeout"}

        geo_info = {"gemini_available": True, "is_sent_to_china": False}
        res = probe_all_ai(None, google_region_info=geo_info)

        self.assertFalse(res["ai_supported"])
        self.assertFalse(res["summary"]["ai_core_passed"])

    def test_tagger_sparkle_requires_groq(self):
        from scripts.core.tagger import tag_and_rename_nodes

        # 样本1: AI 全解锁但未解锁 Groq -> 剥夺 ✨️
        r1 = {
            "proxy": {"name": "🇺🇸 ✨️美国_1"},
            "cc": "US",
            "ai_supported": True,
            "ai_details": {"groq": False},
            "youtube_passed": True,
            "shield_passed": True,
            "youtube_details": {"status": "passed"},
            "shield_details": {"cloudflare": "passed"},
        }
        tag_and_rename_nodes([r1])
        self.assertNotIn("✨️", r1["final_name"])
        self.assertIn("❇️", r1["final_name"])

        # 样本2: AI 全解锁且解锁了 Groq -> 成功授予 ✨️
        r2 = {
            "proxy": {"name": "🇺🇸 美国_2"},
            "cc": "US",
            "ai_supported": True,
            "ai_details": {"groq": True},
            "youtube_passed": True,
            "shield_passed": True,
            "youtube_details": {"status": "passed"},
            "shield_details": {"cloudflare": "passed"},
        }
        tag_and_rename_nodes([r2])
        self.assertIn("✨️", r2["final_name"])
        self.assertIn("❇️", r2["final_name"])


if __name__ == "__main__":
    unittest.main()
