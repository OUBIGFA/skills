# -*- coding: utf-8 -*-
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from core.gist import (
    DEFAULT_GIST_PRESET,
    PRESET_GIST_QUERIES,
    extract_nested_subscription_urls,
    extract_raw_urls_from_gist,
    fetch_gist_nodes,
    get_default_gist_config_path,
    is_within_max_age,
    load_gist_config,
    parse_gist_search_html,
    parse_iso_datetime,
    resolve_gist_query,
    search_and_fetch_gist_proxies,
    search_gist_targets,
)


class TestGistSearchBasics(unittest.TestCase):

    def test_get_default_gist_config_path(self):
        path = get_default_gist_config_path()
        self.assertTrue(path.endswith("gist_config.json"))
        self.assertTrue(os.path.isabs(path))

    def test_load_gist_config_from_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "max_age_hours": 72,
                "default_targets": 30,
                "max_nodes_per_subscription": 150,
                "proxy": "http://127.0.0.1:8888",
                "timeout": 20
            }, f)
            temp_path = f.name

        try:
            cfg = load_gist_config(temp_path)
            self.assertEqual(cfg["max_age_hours"], 72)
            self.assertEqual(cfg["default_targets"], 30)
            self.assertEqual(cfg["max_nodes_per_subscription"], 150)
            self.assertEqual(cfg["proxy"], "http://127.0.0.1:8888")
            self.assertEqual(cfg["timeout"], 20)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_gist_config_env_override(self):
        with patch.dict(os.environ, {
            "GIST_PROXY": "http://env_proxy:1080",
            "GIST_MAX_AGE_HOURS": "24",
            "GIST_DEFAULT_TARGETS": "15",
            "GIST_MAX_NODES_PER_SUB": "100",
            "GIST_TIMEOUT": "9"
        }):
            cfg = load_gist_config("non_existent_file.json")
            self.assertEqual(cfg["proxy"], "http://env_proxy:1080")
            self.assertEqual(cfg["max_age_hours"], 24)
            self.assertEqual(cfg["default_targets"], 15)
            self.assertEqual(cfg["max_nodes_per_subscription"], 100)
            self.assertEqual(cfg["timeout"], 9)

    def test_resolve_gist_query(self):
        self.assertEqual(resolve_gist_query("recommended"), PRESET_GIST_QUERIES["recommended"])
        self.assertEqual(resolve_gist_query("subs"), PRESET_GIST_QUERIES["subs"])
        self.assertEqual(resolve_gist_query("hy2"), PRESET_GIST_QUERIES["hy2"])
        custom = 'filename:yaml "my-secret-proxy"'
        self.assertEqual(resolve_gist_query(custom), custom)
        self.assertEqual(resolve_gist_query(None), PRESET_GIST_QUERIES[DEFAULT_GIST_PRESET])


class TestGistParsingAndFiltering(unittest.TestCase):

    def test_parse_iso_datetime(self):
        dt1 = parse_iso_datetime("2026-09-27T01:32:33Z")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 9)
        self.assertEqual(dt1.day, 27)

        dt2 = parse_iso_datetime("2026-09-27T09:32:33+08:00")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.astimezone(timezone.utc).hour, 1)

        self.assertIsNone(parse_iso_datetime(""))
        self.assertIsNone(parse_iso_datetime("invalid-date"))

    def test_is_within_max_age(self):
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        # 2 hours ago -> within 48h
        t_recent = (now - timedelta(hours=2)).isoformat()
        self.assertTrue(is_within_max_age(t_recent, max_age_hours=48, now_utc=now))

        # 50 hours ago -> outside 48h
        t_old = (now - timedelta(hours=50)).isoformat()
        self.assertFalse(is_within_max_age(t_old, max_age_hours=48, now_utc=now))

    def test_parse_gist_search_html(self):
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        t_fresh = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        t_expired = (now - timedelta(hours=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_html = f"""
        <div class="gist-snippet">
            <a href="/user_fresh/abcdef0123456789abcdef0123456789">UserFresh / gist1</a>
            <relative-time datetime="{t_fresh}">1 hour ago</relative-time>
            <a href="/user_fresh/abcdef0123456789abcdef0123456789#file-clash-yaml">clash.yaml</a>
        </div>
        <div class="gist-snippet">
            <a href="/user_expired/1234567890abcdef1234567890abcdef">UserExpired / gist2</a>
            <relative-time datetime="{t_expired}">4 days ago</relative-time>
            <a href="/user_expired/1234567890abcdef1234567890abcdef#file-test-yaml">test.yaml</a>
        </div>
        """
        cards, expired = parse_gist_search_html(mock_html, max_age_hours=48, now_utc=now)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["username"], "user_fresh")
        self.assertEqual(cards[0]["gist_id"], "abcdef0123456789abcdef0123456789")
        self.assertTrue(expired)

    def test_extract_nested_subscription_urls(self):
        text = """
        https://api.airport.com/api/v1/client/subscribe?token=secret123
        https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/latest/geoip.dat
        https://sub.panel.xyz/link/abcdef?mu=2
        ftp://invalid.com
        not a url
        https://api.airport.com/api/v1/client/subscribe?token=secret123
        """
        urls = extract_nested_subscription_urls(text)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://api.airport.com/api/v1/client/subscribe?token=secret123", urls)
        self.assertIn("https://sub.panel.xyz/link/abcdef?mu=2", urls)


class TestGistFetchingAndNodeExtraction(unittest.TestCase):

    @patch("core.gist._make_http_request")
    def test_extract_raw_urls_from_gist(self, mock_http):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html>
            <a href="/testuser/11223344556677889900aabbccddeeff/raw/commit1/proxies.yaml" class="btn">Raw</a>
            <a href="/testuser/11223344556677889900aabbccddeeff/raw/commit1/subscribes.txt" class="btn">Raw</a>
        </html>
        """
        mock_http.return_value = mock_resp

        target = {
            "username": "testuser",
            "gist_id": "11223344556677889900aabbccddeeff",
            "gist_url": "https://gist.github.com/testuser/11223344556677889900aabbccddeeff"
        }
        files = extract_raw_urls_from_gist(target)
        self.assertEqual(len(files), 2)
        urls = [f["raw_url"] for f in files]
        self.assertIn("https://gist.githubusercontent.com/testuser/11223344556677889900aabbccddeeff/raw/commit1/proxies.yaml", urls)
        self.assertIn("https://gist.githubusercontent.com/testuser/11223344556677889900aabbccddeeff/raw/commit1/subscribes.txt", urls)

    @patch("core.gist._make_http_request")
    def test_fetch_gist_nodes_with_limit_filter(self, mock_http):
        # 构造节点数据: 正常源 2 个节点，超量源 205 个节点
        normal_yaml = """
proxies:
  - name: "Node-1"
    type: hysteria2
    server: 1.1.1.1
    port: 443
    auth: pass1
  - name: "Node-2"
    type: vless
    server: 2.2.2.2
    port: 443
    uuid: 12345678-1234-1234-1234-123456789012
        """

        huge_nodes = [{"name": f"Huge-{i}", "type": "ss", "server": f"10.0.0.{i}", "port": 8388, "cipher": "aes-128-gcm", "password": "pass"} for i in range(205)]
        import yaml
        huge_yaml = yaml.dump({"proxies": huge_nodes})

        def fake_request(url, headers=None, proxy_url=None, timeout=12):
            resp = MagicMock()
            resp.status_code = 200
            if "normal.yaml" in url:
                resp.text = normal_yaml
            elif "huge.yaml" in url:
                resp.text = huge_yaml
            elif "gist1234567890abcdef1234" in url:
                resp.text = """
                <html>
                <a href="/user/gist1234567890abcdef1234/raw/hash/normal.yaml">Raw</a>
                <a href="/user/gist1234567890abcdef1234/raw/hash/huge.yaml">Raw</a>
                </html>
                """
            else:
                resp.text = ""
            return resp

        mock_http.side_effect = fake_request

        target = {
            "username": "user",
            "gist_id": "gist1234567890abcdef1234",
            "gist_url": "https://gist.github.com/user/gist1234567890abcdef1234"
        }

        # 限制单源最大 200 节点
        proxies = fetch_gist_nodes([target], max_nodes_per_sub=200)

        # 应该只保留 normal.yaml 的 2 个节点，超量源 205 个节点被直接熔断丢弃
        self.assertEqual(len(proxies), 2)
        names = [p["name"] for p in proxies]
        self.assertIn("Node-1", names)
        self.assertIn("Node-2", names)
        # 协议排序校验: hysteria2 应该排在 vless 之前
        self.assertEqual(proxies[0]["type"], "hysteria2")
        self.assertEqual(proxies[1]["type"], "vless")

    @patch("core.gist.search_gist_targets")
    @patch("core.gist.fetch_gist_nodes")
    def test_search_and_fetch_gist_proxies_integration(self, mock_fetch, mock_search):
        mock_targets = [{"gist_id": "123", "username": "user"}]
        mock_search.return_value = (mock_targets, {"total": 1})
        mock_nodes = [{"name": "Mock-Node", "type": "vless", "server": "1.2.3.4", "port": 443}]
        mock_fetch.return_value = mock_nodes

        nodes, targets = search_and_fetch_gist_proxies("recommended", max_targets=10)
        self.assertEqual(nodes, mock_nodes)
        self.assertEqual(targets, mock_targets)
        mock_search.assert_called_once()
        mock_fetch.assert_called_once()

    @patch("core.gist._search_single_query_targets")
    def test_search_gist_targets_multi_query(self, mock_single):
        # 模拟两路搜索结果，其中包含了重复卡片以及不同更新时间
        mock_single.side_effect = [
            (
                [
                    {"gist_id": "id1", "username": "user1", "updated_at": "2026-09-27T01:00:00Z"},
                    {"gist_id": "shared_id", "username": "shared_user", "updated_at": "2026-09-27T02:00:00Z"},
                ],
                {"pages_searched": 1, "total_cards_found": 2}
            ),
            (
                [
                    {"gist_id": "shared_id", "username": "shared_user", "updated_at": "2026-09-27T02:00:00Z"},
                    {"gist_id": "id2", "username": "user2", "updated_at": "2026-09-27T03:00:00Z"},
                ],
                {"pages_searched": 1, "total_cards_found": 2}
            )
        ]

        queries = ["filename:yaml proxies", 'filename:txt "subscribe?token="']
        cards, stats = search_gist_targets(queries, max_targets=10)

        # 验证去重后的总卡片数
        self.assertEqual(len(cards), 3)
        # 验证时间倒序重排：最新的 03:00 (id2) > 02:00 (shared_id) > 01:00 (id1)
        self.assertEqual(cards[0]["gist_id"], "id2")
        self.assertEqual(cards[1]["gist_id"], "shared_id")
        self.assertEqual(cards[2]["gist_id"], "id1")
        self.assertEqual(stats["pages_searched"], 2)



class TestGistCLIAndParsersIntegration(unittest.TestCase):

    @patch("core.gist.search_and_fetch_gist_proxies")
    def test_load_proxies_gist_prefix(self, mock_search):
        mock_search.return_value = ([{"name": "GistNode", "server": "1.1.1.1"}], [])
        from core.parsers import load_proxies

        # 1. 直接传入 "gist"
        nodes1 = load_proxies("gist")
        mock_search.assert_called_with(query_or_preset=None)
        self.assertEqual(len(nodes1), 1)

        # 2. 传入 "gist:subs"
        nodes2 = load_proxies("gist:subs")
        mock_search.assert_called_with(query_or_preset="subs")
        self.assertEqual(len(nodes2), 1)

        # 3. 传入 "gist:recommended"
        nodes3 = load_proxies("gist:recommended")
        mock_search.assert_called_with(query_or_preset="recommended")
        self.assertEqual(len(nodes3), 1)

    def test_gist_search_cli_args(self):
        import gist_search
        args = gist_search.parse_args([
            "--preset", "subs",
            "--max-targets", "15",
            "--max-age-hours", "24",
            "--max-nodes-per-sub", "100",
            "--dry-run-targets",
            "-o", "custom_gist.yaml"
        ])
        self.assertEqual(args.preset, "subs")
        self.assertEqual(args.max_targets, 15)
        self.assertEqual(args.max_age_hours, 24.0)
        self.assertEqual(args.max_nodes_per_sub, 100)
        self.assertTrue(args.dry_run_targets)
        self.assertEqual(args.output, "custom_gist.yaml")

    def test_fofa_search_cli_with_gist_engine(self):
        import fofa_search
        args = fofa_search.parse_args([
            "--engine", "gist",
            "--preset", "recommended",
            "-o", "fofa_gist.yaml"
        ])
        self.assertEqual(args.engine, "gist")
        self.assertEqual(args.preset, "recommended")
        self.assertEqual(args.output, "fofa_gist.yaml")


if __name__ == "__main__":
    unittest.main()
