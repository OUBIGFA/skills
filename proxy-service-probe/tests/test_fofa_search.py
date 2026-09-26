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
    deduplicate_and_sort_proxies,
    fetch_subscription_nodes,
    get_default_config_path,
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
        self.assertEqual(resolve_query("recommended"), PRESET_QUERIES["recommended"])
        self.assertEqual(resolve_query("hy2"), PRESET_QUERIES["hy2"])
        self.assertEqual(resolve_query("vless"), PRESET_QUERIES["vless"])
        self.assertEqual(resolve_query("billing"), PRESET_QUERIES["billing"])
        # 自定义语法透传
        custom = 'body="test" && port="443"'
        self.assertEqual(resolve_query(custom), custom)
        # 空值默认
        self.assertEqual(resolve_query(None), PRESET_QUERIES[DEFAULT_PRESET])

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
        # 构造包含 205 个节点的庞大公开聚合配置
        nodes_list = [
            {"name": f"ss-{i}", "type": "ss", "server": f"10.0.0.{i%250}", "port": 1000 + i, "cipher": "aes-128-gcm", "password": "p"}
            for i in range(205)
        ]
        import yaml
        large_yaml = yaml.safe_dump({"proxies": nodes_list})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = large_yaml
        mock_request.return_value = mock_resp

        # 默认限制 200 个，超过 200 个的订阅源应被丢弃
        proxies_default = fetch_subscription_nodes(["http://aggregator.com"], config={"max_nodes_per_subscription": 200})
        self.assertEqual(len(proxies_default), 0)

        # 若显式放宽限制为 300，则应该被保留
        proxies_relaxed = fetch_subscription_nodes(["http://aggregator.com"], max_nodes_per_sub=300)
        self.assertEqual(len(proxies_relaxed), 205)

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


if __name__ == "__main__":
    unittest.main()
