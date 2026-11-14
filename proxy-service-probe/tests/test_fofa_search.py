import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from core.fofa import (
    DEFAULT_PRESET,
    PRESET_QUERIES,
    _extract_nuxt_targets,
    _search_fofa_signed_web_api,
    _sign_fofa_web_message,
    check_fofa_auth,
    deduplicate_and_sort_proxies,
    fetch_subscription_nodes,
    get_default_config_path,
    inspect_jwt_token,
    load_fofa_config,
    resolve_query,
    search_and_fetch_proxies,
    search_fofa_targets,
)
from core.parsers import load_proxies


class TestFoFaSearch(unittest.TestCase):

    def test_get_default_config_path(self):
        path = get_default_config_path()
        self.assertTrue(path.endswith("fofa_config.json"))
        self.assertTrue(os.path.isabs(path))

    def test_load_fofa_config_from_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "token": "test_token_123",
                "key": "test_key",
                "email": "test@example.com",
                "proxy": "http://127.0.0.1:8888",
                "page_size": 20,
                "timeout": 15
            }, f)
            temp_path = f.name

        try:
            cfg = load_fofa_config(temp_path)
            self.assertEqual(cfg["token"], "test_token_123")
            self.assertEqual(cfg["key"], "test_key")
            self.assertEqual(cfg["email"], "test@example.com")
            self.assertEqual(cfg["proxy"], "http://127.0.0.1:8888")
            self.assertEqual(cfg["page_size"], 20)
            self.assertEqual(cfg["timeout"], 15)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_fofa_config_env_override(self):
        with patch.dict(os.environ, {
            "FOFA_TOKEN": "env_token",
            "FOFA_KEY": "env_key",
            "FOFA_EMAIL": "env@domain.com",
            "FOFA_PROXY": "http://env_proxy:1080"
        }):
            cfg = load_fofa_config("non_existent_file.json")
            self.assertEqual(cfg["token"], "env_token")
            self.assertEqual(cfg["key"], "env_key")
            self.assertEqual(cfg["email"], "env@domain.com")
            self.assertEqual(cfg["proxy"], "http://env_proxy:1080")

    def test_resolve_query(self):
        # 预设解析
        self.assertEqual(resolve_query("residential"), PRESET_QUERIES["residential"])
        self.assertEqual(resolve_query("recommended"), PRESET_QUERIES["recommended"])
        self.assertEqual(resolve_query("hy2"), PRESET_QUERIES["hy2"])
        self.assertEqual(resolve_query("vless"), PRESET_QUERIES["vless"])
        self.assertEqual(resolve_query("billing"), PRESET_QUERIES["billing"])
        # 自定义语法透传
        custom = 'body="test" && port="443"'
        self.assertEqual(resolve_query(custom), custom)
        # 空值默认
        self.assertEqual(DEFAULT_PRESET, "residential")
        self.assertEqual(resolve_query(None), PRESET_QUERIES["residential"])

    def test_extract_nuxt_targets(self):
        # 构造模拟 Nuxt 序列化数据: Nuxt 3 将状态序列化为 JSON 数组嵌于 <script> 中
        # "result-search-assets" 存在于字符串池中
        nuxt_json = [
            "result-search-assets",
            "link",
            "http://sub1.example.com",
            "1.2.3.4",
            8080,
            {"link": 2},
            {"ip": 3, "port": 4},
            "other",
            [5, 6]  # asset indices at position 8
        ]
        mock_html = f"""
        <html>
        <head>
          <script type="application/json">{json.dumps(nuxt_json)}</script>
        </head>
        <body><div>FoFa Search Result</div></body>
        </html>
        """
        targets = _extract_nuxt_targets(mock_html)
        self.assertIn("http://sub1.example.com", targets)
        self.assertIn("http://1.2.3.4:8080", targets)

    def test_extract_fallback_html_targets(self):
        mock_html = """
        <html><body>
          <a href="https://example.com/sub/clash">Subscription</a>
          <a href="http://198.51.100.1:8080/config.yaml">Node</a>
          <a href="https://beian.miit.gov.cn/">ICP</a>
        </body></html>
        """
        targets = _extract_nuxt_targets(mock_html)
        self.assertIn("https://example.com/sub/clash", targets)
        self.assertIn("http://198.51.100.1:8080/config.yaml", targets)
        self.assertFalse(any("beian" in t for t in targets))

    def test_deduplicate_and_sort_proxies(self):
        raw_proxies = [
            {"name": "vmess_1", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
            {"name": "vmess_dup", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},  # 重复
            {"name": "hy2_node", "type": "hysteria2", "server": "2.2.2.2", "port": 8443, "password": "p2"},
            {"name": "vless_node", "type": "vless", "server": "3.3.3.3", "port": 443, "uuid": "u3"},
        ]
        deduped = deduplicate_and_sort_proxies(raw_proxies)
        self.assertEqual(len(deduped), 3)
        # hysteria2 应该排在最前面
        self.assertEqual(deduped[0]["type"], "hysteria2")
        self.assertEqual(deduped[1]["type"], "vless")
        self.assertEqual(deduped[2]["type"], "vmess")

    @patch("core.fofa._make_request")
    def test_search_fofa_targets_api(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": False,
            "results": [
                ["1.1.1.1", "8080", "node1.com", "https://node1.com/sub"],
                ["2.2.2.2", "443", "node2.com", ""]
            ]
        }
        mock_request.return_value = mock_resp

        cfg = {
            "email": "test@fofa.so",
            "key": "test_key",
            "token": "",
            "default_query": "header=\"subscription-userinfo\""
        }
        targets = search_fofa_targets("recommended", config=cfg)
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0], "https://node1.com/sub")
        self.assertEqual(targets[1], "https://node2.com")

    @patch("core.fofa._make_request")
    def test_fetch_subscription_nodes(self, mock_request):
        sample_yaml = """
proxies:
  - name: "node-1"
    type: ss
    server: 1.2.3.4
    port: 8388
    cipher: aes-128-gcm
    password: pass
  - name: "node-2"
    type: hysteria2
    server: 5.6.7.8
    port: 443
    password: hy2pass
"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_yaml
        mock_request.return_value = mock_resp

        proxies = fetch_subscription_nodes(["http://mock-target.com"], config={"timeout": 5})
        self.assertEqual(len(proxies), 2)
        # hysteria2 优先
        self.assertEqual(proxies[0]["type"], "hysteria2")
        self.assertEqual(proxies[1]["type"], "ss")

    @patch("core.fofa._make_request")
    def test_fetch_subscription_nodes_filters_oversized_sources(self, mock_request):
        # 构造包含 305 个节点的庞大公开聚合配置
        nodes_list = [
            {"name": f"ss-{i}", "type": "ss", "server": f"10.0.0.{i%250}", "port": 1000 + i, "cipher": "aes-128-gcm", "password": "p"}
            for i in range(305)
        ]
        import yaml
        large_yaml = yaml.safe_dump({"proxies": nodes_list})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = large_yaml
        mock_request.return_value = mock_resp

        # 默认限制 300 个，超过 300 个的订阅源应被丢弃
        proxies_default = fetch_subscription_nodes(["http://aggregator.com"], config={"max_nodes_per_subscription": 300})
        self.assertEqual(len(proxies_default), 0)

        # 若显式放宽限制为 400，则应该被保留
        proxies_relaxed = fetch_subscription_nodes(["http://aggregator.com"], max_nodes_per_sub=400)
        self.assertEqual(len(proxies_relaxed), 305)

    @patch("core.fofa.search_all_targets")
    @patch("core.fofa.fetch_subscription_nodes")
    def test_search_and_fetch_proxies(self, mock_fetch, mock_search_all):
        mock_search_all.return_value = (["http://sub.com"], {"fofa": 1, "quake": 0, "deduped": 1})
        mock_fetch.return_value = [{"name": "n1", "type": "hysteria2", "server": "1.1.1.1", "port": 443, "password": "p"}]

        proxies, targets = search_and_fetch_proxies("recommended")
        self.assertEqual(len(targets), 1)
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0]["type"], "hysteria2")

    @patch("core.fofa.search_and_fetch_proxies")
    def test_load_proxies_fofa_prefix(self, mock_search_and_fetch):
        mock_search_and_fetch.return_value = ([
            {"name": "fofa_node", "type": "hysteria2", "server": "8.8.8.8", "port": 443, "password": "pwd"}
        ], ["http://sub.target"])

        # 测试 load_proxies("fofa:recommended")
        nodes1 = load_proxies("fofa:recommended")
        self.assertEqual(len(nodes1), 1)
        self.assertEqual(nodes1[0]["name"], "fofa_node")

        # 测试 load_proxies("fofa")
        nodes2 = load_proxies("fofa")
        self.assertEqual(len(nodes2), 1)
        self.assertEqual(nodes2[0]["name"], "fofa_node")

    def test_normalize_and_dedup_targets(self):
        from core.fofa import normalize_and_dedup_targets
        raw = [
            "http://example.com/sub",
            "http://EXAMPLE.COM/sub/",       # 大小写与结尾斜杠重复
            "http://example.com:80/sub",     # 默认 80 端口重复
            "https://secure.org/clash.yaml",
            "https://secure.org:443/clash.yaml", # 默认 443 端口重复
            "http://unique.com:8080/feed"
        ]
        deduped = normalize_and_dedup_targets(raw)
        self.assertEqual(len(deduped), 3)
        self.assertEqual(deduped[0], "http://example.com/sub")
        self.assertEqual(deduped[1], "https://secure.org/clash.yaml")
        self.assertEqual(deduped[2], "http://unique.com:8080/feed")

    @patch("core.quake._post_quake_request")
    def test_search_quake_targets_success(self, mock_post):
        from core.quake import search_quake_targets
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": 0,
            "message": "Successful.",
            "data": [
                {
                    "ip": "1.2.3.4",
                    "port": 8080,
                    "service": {"name": "http", "http": {"host": "sub1.org"}}
                },
                {
                    "ip": "5.6.7.8",
                    "port": 443,
                    "service": {"name": "http/ssl", "http": {"host": "sub2.org", "url": "https://sub2.org/clash"}}
                }
            ]
        }
        mock_post.return_value = mock_resp

        targets = search_quake_targets("recommended", config={"quake_key": "test_quake_token"})
        self.assertEqual(len(targets), 2)
        self.assertIn("http://sub1.org:8080", targets)
        self.assertIn("https://sub2.org/clash", targets)

    def test_search_quake_targets_missing_key(self):
        from core.quake import search_quake_targets
        targets = search_quake_targets("recommended", config={"quake_key": ""})
        self.assertEqual(targets, [])

    @patch("core.fofa.search_fofa_targets")
    @patch("core.quake.search_quake_targets")
    def test_search_all_targets_deduplication(self, mock_quake, mock_fofa):
        from core.fofa import search_all_targets
        mock_fofa.return_value = ["http://overlap.com/clash", "http://fofa-only.com/sub"]
        mock_quake.return_value = ["http://overlap.com/clash/", "https://quake-only.com/feed"]

        targets, stats = search_all_targets("recommended", config={"token": "t", "quake_key": "qk"})
        self.assertEqual(len(targets), 3)  # 重合源被去重
        self.assertEqual(stats["fofa"], 2)
        self.assertEqual(stats["quake"], 2)
        self.assertEqual(stats["deduped"], 3)

    @patch("core.fofa.search_fofa_targets")
    @patch("core.quake.search_quake_targets")
    def test_search_all_targets_fault_tolerance(self, mock_quake, mock_fofa):
        from core.fofa import search_all_targets
        # 1. 模拟 FoFa 报错挂掉，Quake 正常
        mock_fofa.side_effect = Exception("FoFa API Connection Timeout")
        mock_quake.return_value = ["http://quake-survivor.com/sub"]

        targets1, stats1 = search_all_targets("recommended", config={"token": "t", "quake_key": "qk"})
        self.assertEqual(targets1, ["http://quake-survivor.com/sub"])
        self.assertEqual(stats1["quake"], 1)

        # 2. 模拟 Quake 报错挂掉，FoFa 正常
        mock_fofa.side_effect = None
        mock_fofa.return_value = ["http://fofa-survivor.com/sub"]
        mock_quake.side_effect = Exception("Quake Token Expired")

        targets2, stats2 = search_all_targets("recommended", config={"token": "t", "quake_key": "qk"})
        self.assertEqual(targets2, ["http://fofa-survivor.com/sub"])
        self.assertEqual(stats2["fofa"], 1)

    @patch("core.fofa.search_and_fetch_proxies")
    def test_load_proxies_quake_and_spatial_prefixes(self, mock_search_and_fetch):
        mock_search_and_fetch.return_value = ([
            {"name": "spatial_node", "type": "vless", "server": "9.9.9.9", "port": 443, "uuid": "u"}
        ], ["http://sub.target"])

        # 测试 load_proxies("quake:recommended")
        nodes_q = load_proxies("quake:recommended")
        self.assertEqual(len(nodes_q), 1)
        mock_search_and_fetch.assert_called_with(query_or_preset="recommended", engine="quake")

        # 测试 load_proxies("spatial:billing")
        nodes_s = load_proxies("spatial:billing")
        self.assertEqual(len(nodes_s), 1)
        mock_search_and_fetch.assert_called_with(query_or_preset="billing", engine="all")

    def test_inspect_jwt_token(self):
        # 1. 空或非字符串
        self.assertFalse(inspect_jwt_token("")["valid"])
        self.assertFalse(inspect_jwt_token(None)["valid"])

        # 2. 非 JWT 格式 (保持透传)
        res_non_jwt = inspect_jwt_token("simple-opaque-token")
        self.assertTrue(res_non_jwt["valid"])
        self.assertFalse(res_non_jwt["is_jwt"])

        # 3. 构造已过期的 JWT
        expired_payload = {"username": "tester", "exp": 1500000000}  # 2017年
        p_b64 = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
        expired_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_b64}.mocksignature"
        res_exp = inspect_jwt_token(expired_jwt)
        self.assertTrue(res_exp["is_jwt"])
        self.assertTrue(res_exp["expired"])
        self.assertFalse(res_exp["valid"])
        self.assertEqual(res_exp["username"], "tester")

        # 4. 构造未来的有效 JWT
        valid_payload = {"username": "future_user", "exp": 2500000000}
        p_val_b64 = base64.urlsafe_b64encode(json.dumps(valid_payload).encode()).decode().rstrip("=")
        valid_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_val_b64}.mocksignature"
        res_val = inspect_jwt_token(valid_jwt)
        self.assertTrue(res_val["is_jwt"])
        self.assertFalse(res_val["expired"])
        self.assertTrue(res_val["valid"])
        self.assertEqual(res_val["username"], "future_user")

    def test_load_fofa_config_tokens_list(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "token": "tok1, tok2\ntok3",
                "tokens": ["tok4", "tok1"],
                "base_url": "https://custom.fofa.relay"
            }, f)
            temp_path = f.name

        try:
            cfg = load_fofa_config(temp_path)
            self.assertEqual(cfg["base_url"], "https://custom.fofa.relay")
            # 应该解析出去重且保序的 tokens_list
            self.assertIn("tok1", cfg["tokens_list"])
            self.assertIn("tok2", cfg["tokens_list"])
            self.assertIn("tok3", cfg["tokens_list"])
            self.assertIn("tok4", cfg["tokens_list"])
            self.assertEqual(len(cfg["tokens_list"]), 4)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_search_fofa_signed_web_api_expired_token(self):
        # 过期 Token 应当在本地直接拦截并返回错误，不发出任何网络请求
        expired_payload = {"username": "test_user", "exp": 1000}
        p_b64 = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
        expired_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_b64}.mocksignature"

        targets, err = _search_fofa_signed_web_api("test_query", token=expired_jwt)
        self.assertEqual(targets, [])
        self.assertIsNotNone(err)
        self.assertIn("过期", err)

    def test_sign_fofa_web_message(self):
        sig = _sign_fofa_web_message("fullfalsepage1qbase64Ym9keT0icHJveGllczoic2l6ZTEwdHMxMDAw")
        self.assertTrue(bool(sig))
        self.assertGreater(len(sig), 50)

    @patch("core.fofa._make_request")
    def test_check_fofa_auth(self, mock_make_request):
        # 模拟官方 API /api/v1/info/my 响应
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": False,
            "email": "user@domain.com",
            "vip_level": 2,
            "fcoin": 50
        }
        mock_make_request.return_value = mock_resp

        cfg = {
            "key": "test_key",
            "token": "",
            "quake_key": ""
        }
        report = check_fofa_auth(cfg)
        self.assertEqual(report["fofa_api"]["status"], "valid")
        self.assertEqual(report["fofa_api"]["email"], "user@domain.com")

    def test_update_fofa_config_token(self):
        from core.fofa_login import update_fofa_config_token
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "token": "old_token",
                "tokens": ["old_token"],
                "quake_key": "qk_123",
                "proxy": "http://127.0.0.1:3067"
            }, f)
            temp_path = f.name

        try:
            ok = update_fofa_config_token("new_token_456", email="new@fofa.so", config_path=temp_path)
            self.assertTrue(ok)
            with open(temp_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["token"], "new_token_456")
            self.assertEqual(saved["email"], "new@fofa.so")
            self.assertEqual(saved["tokens"], ["new_token_456", "old_token"])
            # 保持已有配置不丢失
            self.assertEqual(saved["quake_key"], "qk_123")
            self.assertEqual(saved["proxy"], "http://127.0.0.1:3067")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_ensure_fofa_token_valid(self):
        from core.fofa import ensure_fofa_token
        # 构造有效未来 token
        future_payload = {"username": "valid_user", "exp": 2500000000}
        p_b64 = base64.urlsafe_b64encode(json.dumps(future_payload).encode()).decode().rstrip("=")
        valid_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_b64}.sig"

        cfg = {"token": valid_jwt, "tokens_list": [valid_jwt]}
        ok, msg = ensure_fofa_token(cfg, auto_login=False)
        self.assertTrue(ok)
        self.assertIn("有效", msg)

    @patch("core.fofa_login.login_fofa_and_extract_token")
    def test_ensure_fofa_token_expired_triggers_refresh(self, mock_login):
        from core.fofa import ensure_fofa_token
        # 构造已过期 token
        expired_payload = {"username": "expired_user", "exp": 1000}
        p_b64 = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
        expired_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_b64}.sig"

        new_jwt = "eyJhbGciOiJIUzI1NiJ9.mock_new_payload.sig"
        mock_login.return_value = (True, new_jwt, "续期成功")

        cfg = {
            "token": expired_jwt,
            "tokens_list": [expired_jwt],
            "email": "user@example.com",
            "password": "pwd"
        }
        ok, msg = ensure_fofa_token(cfg, auto_login=True)
        self.assertTrue(ok)
        self.assertEqual(cfg["token"], new_jwt)
        self.assertIn("成功", msg)

    def test_cli_login_arguments(self):
        import fofa_search
        args = fofa_search.parse_args(["--login", "--username", "test_user", "--password", "test_pass", "--headless"])
        self.assertTrue(args.login)
        self.assertEqual(args.username, "test_user")
        self.assertEqual(args.password, "test_pass")
        self.assertTrue(args.headless)

    @patch("core.fofa._search_fofa_signed_web_api")
    @patch("core.fofa_login.login_fofa_and_extract_token")
    def test_search_fofa_targets_auto_refreshes_expired_token(self, mock_login, mock_web_api):
        expired_payload = {"username": "expired_user", "exp": 1000}
        p_exp = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
        expired_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_exp}.sig"

        future_payload = {"username": "refreshed_user", "exp": 2500000000}
        p_new = base64.urlsafe_b64encode(json.dumps(future_payload).encode()).decode().rstrip("=")
        new_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_new}.sig"

        mock_login.return_value = (True, new_jwt, "自动续期成功")
        mock_web_api.return_value = (["https://refreshed-node.example.com/sub"], None)

        cfg = {
            "token": expired_jwt,
            "tokens_list": [expired_jwt],
            "account": {"username": "user@example.com", "password": "secret"},
        }
        targets = search_fofa_targets("recommended", config=cfg)
        self.assertEqual(targets, ["https://refreshed-node.example.com/sub"])
        mock_login.assert_called_once()
        mock_web_api.assert_called_once()
        self.assertEqual(mock_web_api.call_args.kwargs.get("token"), new_jwt)


if __name__ == "__main__":
    unittest.main()

