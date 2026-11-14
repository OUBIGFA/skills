# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from scripts.core.tls_fingerprint import (
    StreamingResponse,
    create_tuned_ssl_context,
    is_curl_cffi_available,
    request_streaming,
)


class TestTLSFingerprint(unittest.TestCase):
    def test_environment_and_context(self):
        ctx = create_tuned_ssl_context()
        self.assertIsNotNone(ctx)
        self.assertTrue(is_curl_cffi_available())

    def test_build_chrome_headers_modes(self):
        from scripts.core.tls_fingerprint import build_chrome_headers

        # 1. 默认导航模式 (navigate)
        nav_headers = build_chrome_headers(mode="navigate")
        self.assertEqual(nav_headers["sec-fetch-mode"], "navigate")
        self.assertEqual(nav_headers["sec-fetch-dest"], "document")
        self.assertEqual(nav_headers["sec-fetch-site"], "none")
        self.assertEqual(nav_headers.get("upgrade-insecure-requests"), "1")
        self.assertIn("text/html", nav_headers["accept"])

        # 2. API / Fetch 模式 (fetch / cors)
        api_headers = build_chrome_headers(mode="fetch", custom_headers={"origin": "https://chatgpt.com"})
        self.assertEqual(api_headers["sec-fetch-mode"], "cors")
        self.assertEqual(api_headers["sec-fetch-dest"], "empty")
        self.assertEqual(api_headers["sec-fetch-site"], "same-origin")
        self.assertNotIn("upgrade-insecure-requests", api_headers)
        self.assertEqual(api_headers.get("origin"), "https://chatgpt.com")

    def test_streaming_response_properties(self):
        # 1. 模拟 Cloudflare 质询头短路
        resp1 = StreamingResponse(
            status_code=403,
            headers={"cf-mitigated": "challenge", "content-type": "text/html"},
            body_bytes=b"",
            engine="curl_cffi:chrome131",
            short_circuited=True
        )
        self.assertTrue(resp1.is_cf_mitigated)
        self.assertFalse(resp1.is_google_sorry)
        self.assertEqual(resp1.text, "")

        # 2. 模拟 Google /sorry/ 重定向
        resp2 = StreamingResponse(
            status_code=302,
            headers={"location": "https://www.google.com/sorry/index?continue=..."},
            body_bytes=b"Redirecting",
            engine="tuned_ssl"
        )
        self.assertFalse(resp2.is_cf_mitigated)
        self.assertTrue(resp2.is_google_sorry)

        # 3. 模拟 JSON 解析
        resp3 = StreamingResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body_bytes=b'{"proofofwork": {"difficulty": "0fffff"}}',
            engine="curl_cffi:chrome131"
        )
        data = resp3.json()
        self.assertEqual(data["proofofwork"]["difficulty"], "0fffff")

    @patch("curl_cffi.requests.request")
    def test_request_streaming_stage1_short_circuit(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"cf-mitigated": "challenge", "server": "cloudflare"}
        mock_request.return_value = mock_resp

        res = request_streaming("GET", "https://chatgpt.com/", prefer_curl_cffi=True)
        self.assertTrue(res.is_cf_mitigated)
        self.assertTrue(res.short_circuited)
        self.assertEqual(res.body_bytes, b"")
        mock_resp.close.assert_called_once()

    @patch("curl_cffi.requests.request")
    def test_request_streaming_stage2_truncation(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        # 模拟生成 32KB 数据
        mock_resp.iter_content.return_value = [b"A" * 4096 for _ in range(8)]
        mock_request.return_value = mock_resp

        res = request_streaming("GET", "https://example.com/", max_body_bytes=8192, prefer_curl_cffi=True)
        self.assertFalse(res.short_circuited)
        self.assertEqual(len(res.body_bytes), 8192)
        mock_resp.close.assert_called_once()

    @patch("curl_cffi.requests.request")
    def test_request_streaming_fetch_mode(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.iter_content.return_value = [b'{"ok": true}']
        mock_request.return_value = mock_resp

        res = request_streaming(
            "POST",
            "https://chatgpt.com/backend-api/sentinel/chat-requirements",
            json_data={},
            headers={"origin": "https://chatgpt.com"},
            prefer_curl_cffi=True,
            mode="fetch"
        )
        self.assertEqual(res.status_code, 200)
        # 验证 curl_cffi 接收到的 headers
        call_kwargs = mock_request.call_args[1]
        sent_headers = call_kwargs["headers"]
        self.assertEqual(sent_headers["sec-fetch-mode"], "cors")
        self.assertEqual(sent_headers["sec-fetch-dest"], "empty")
        self.assertEqual(sent_headers["sec-fetch-site"], "same-origin")
        self.assertNotIn("upgrade-insecure-requests", sent_headers)
        self.assertEqual(sent_headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
