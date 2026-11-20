# -*- coding: utf-8 -*-
import base64
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import yaml

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core.fofa import fetch_subscription_nodes
from core.gist import fetch_gist_nodes
from core.parsers import load_proxies
from core.sub_filter import (
    check_subscription_non_long_term,
    filter_non_long_term_nodes,
    filter_subscription_batch,
    get_node_non_long_term_reason,
    match_non_long_term_reason,
)


class TestSubFilter(unittest.TestCase):
    def test_positive_trial_and_short_term_names(self):
        positives = [
            "试用节点-香港01",
            "免费试用-JP",
            "1元试用",
            "体验版-US",
            "体验套餐-SG",
            "免费体验01",
            "香港体验01",
            "临时节点-TW",
            "限时免费-HK",
            "短期线路",
            "短效代理",
            "一次性套餐",
            "日抛-US-01",
            "周抛节点",
            "已过期节点",
            "即将失效-JP",
            "非长期使用",
            "有效期3天",
            "24小时有效",
            "今日有效-HK",
            "新人专享-SG",
            "Trial-HK-01",
            "Free Trial Node",
            "freetrial_us",
            "temp-us-01",
            "temp_01",
            "Temporary-JP",
            "short-term-sg",
            "time-limited-hk",
            "disposable-proxy",
            "ephemeral-node",
            "one-time-sub",
            "expired-node",
            "24h only",
            "valid for 3 days",
        ]
        for name in positives:
            with self.subTest(name=name):
                self.assertIsNotNone(match_non_long_term_reason(name), f"Should match: {name}")

    def test_negative_normal_names_not_filtered(self):
        negatives = [
            "香港 01 | IPLC",
            "🇺🇸 美国 住宅家宽 01",
            "JP-Tokyo-HY2",
            "template-node-01",
            "attempt-01",
            "极速体验-HK",
            "丝滑体验-SG",
            "test-node-01",
            "测试节点-01",
            "HK-Premium-01",
            "industrial-datacenter",
        ]
        for name in negatives:
            with self.subTest(name=name):
                self.assertIsNone(match_non_long_term_reason(name), f"Should NOT match: {name}")

    def test_subscription_level_checks(self):
        # 1. URL 含 trial 或 URL 编码的「试用」
        self.assertIsNotNone(check_subscription_non_long_term(url="https://example.com/sub/free-trial.yaml"))
        self.assertIsNotNone(check_subscription_non_long_term(url="https://example.com/%E8%AF%95%E7%94%A8.yaml"))

        # 2. 文件名
        self.assertIsNotNone(check_subscription_non_long_term(filename="试用订阅.yaml"))

        # 3. 响应头 Content-Disposition / Profile-Title / Subscription-Userinfo
        self.assertIsNotNone(
            check_subscription_non_long_term(
                headers={"Content-Disposition": "attachment; filename*=UTF-8''%E8%AF%95%E7%94%A8.yaml"}
            )
        )
        b64_title = base64.b64encode("免费试用订阅".encode("utf-8")).decode("ascii")
        self.assertIsNotNone(
            check_subscription_non_long_term(headers={"Profile-Title": f"base64:{b64_title}"})
        )
        self.assertIsNotNone(
            check_subscription_non_long_term(
                headers={"Subscription-Userinfo": "upload=0; download=0; total=1024; expire=1700000000"},
                now_ts=1800000000,
            )
        )
        # expire=0 或未过期不应被判为过期
        self.assertIsNone(
            check_subscription_non_long_term(
                headers={"Subscription-Userinfo": "upload=0; download=0; total=1024; expire=0"},
                now_ts=1800000000,
            )
        )
        self.assertIsNone(
            check_subscription_non_long_term(
                headers={"Subscription-Userinfo": "upload=0; download=0; total=1024; expire=1900000000"},
                now_ts=1800000000,
            )
        )

        # 4. 头部注释
        self.assertIsNotNone(check_subscription_non_long_term(raw_text="# 限时体验订阅\nproxies:\n"))

        # 5. 节点中包含套餐/状态提示或过半为试用节点
        self.assertIsNotNone(
            check_subscription_non_long_term(
                nodes=[
                    {"name": "试用套餐：剩余1天"},
                    {"name": "香港01"},
                    {"name": "日本01"},
                ]
            )
        )
        self.assertIsNotNone(
            check_subscription_non_long_term(
                nodes=[
                    {"name": "试用-HK"},
                    {"name": "临时-JP"},
                    {"name": "美国01"},
                ]
            )
        )
        # 少数试用节点 + 多数正常节点：不淘汰整源，只淘汰单个试用节点
        normal_mixed = [
            {"name": "试用-HK", "type": "ss", "server": "1.1.1.1", "port": 443},
            {"name": "香港01", "type": "ss", "server": "1.1.1.2", "port": 443},
            {"name": "日本01", "type": "ss", "server": "1.1.1.3", "port": 443},
            {"name": "美国01", "type": "ss", "server": "1.1.1.4", "port": 443},
        ]
        self.assertIsNone(check_subscription_non_long_term(nodes=normal_mixed))
        kept = filter_subscription_batch(normal_mixed, "test-sub", limit=300)
        self.assertEqual([n["name"] for n in kept], ["香港01", "日本01", "美国01"])

    def test_load_proxies_filters_trial_nodes(self):
        yaml_text = yaml.safe_dump({
            "proxies": [
                {"name": "试用节点-HK", "type": "ss", "server": "1.1.1.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "HK-LongTerm-01", "type": "ss", "server": "1.1.1.2", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "Temp-US-01", "type": "ss", "server": "1.1.1.3", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "US-Residential-01", "type": "ss", "server": "1.1.1.4", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "JP-01", "type": "ss", "server": "1.1.1.5", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
            ]
        })
        nodes = load_proxies(yaml_text)
        names = [n["name"] for n in nodes]
        self.assertEqual(names, ["HK-LongTerm-01", "US-Residential-01", "JP-01"])

    @patch("core.fofa._make_request")
    def test_fofa_fetch_filters_trial_source_and_nodes(self, mock_request):
        mixed_yaml = yaml.safe_dump({
            "proxies": [
                {"name": "免费试用-HK", "type": "ss", "server": "1.1.1.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "HK-01", "type": "hysteria2", "server": "1.1.1.2", "port": 443, "password": "p"},
                {"name": "JP-01", "type": "vless", "server": "1.1.1.3", "port": 443, "uuid": "11111111-1111-1111-1111-111111111111"},
                {"name": "US-01", "type": "ss", "server": "1.1.1.4", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
            ]
        })
        trial_sub_yaml = yaml.safe_dump({
            "proxies": [
                {"name": "香港01", "type": "ss", "server": "2.2.2.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "日本01", "type": "ss", "server": "2.2.2.2", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
            ]
        })

        def side_effect(url, headers=None, proxy_url=None, timeout=6):
            resp = MagicMock()
            resp.status_code = 200
            if "header-sub" in url:
                resp.headers = {"Profile-Title": "免费试用订阅"}
                resp.text = trial_sub_yaml
            else:
                resp.headers = {}
                resp.text = mixed_yaml
            return resp

        mock_request.side_effect = side_effect
        proxies = fetch_subscription_nodes(
            [
                "http://example.com/free-trial/sub",
                "http://example.com/header-sub",
                "http://example.com/normal-sub",
            ],
            config={"max_nodes_per_subscription": 300},
        )
        names = [p["name"] for p in proxies]
        self.assertEqual(set(names), {"HK-01", "JP-01", "US-01"})

    @patch("core.gist._make_http_request")
    def test_gist_fetch_filters_trial_file_and_nodes(self, mock_http):
        normal_yaml = yaml.safe_dump({
            "proxies": [
                {"name": "临时-HK", "type": "ss", "server": "3.3.3.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
                {"name": "Node-1", "type": "hysteria2", "server": "3.3.3.2", "port": 443, "password": "p"},
                {"name": "Node-2", "type": "vless", "server": "3.3.3.3", "port": 443, "uuid": "11111111-1111-1111-1111-111111111111"},
                {"name": "Node-3", "type": "ss", "server": "3.3.3.4", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
            ]
        })
        trial_yaml = yaml.safe_dump({
            "proxies": [
                {"name": "ShouldDrop-1", "type": "ss", "server": "4.4.4.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"},
            ]
        })

        def fake_request(url, headers=None, proxy_url=None, timeout=12):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            if "normal.yaml" in url:
                resp.text = normal_yaml
            elif "trial.yaml" in url:
                resp.text = trial_yaml
            elif "gist1234567890abcdef1234" in url:
                resp.text = """
                <html>
                <a href="/user/gist1234567890abcdef1234/raw/hash/normal.yaml">Raw</a>
                <a href="/user/gist1234567890abcdef1234/raw/hash/trial.yaml">Raw</a>
                </html>
                """
            else:
                resp.text = ""
            return resp

        mock_http.side_effect = fake_request
        target = {
            "username": "user",
            "gist_id": "gist1234567890abcdef1234",
            "gist_url": "https://gist.github.com/user/gist1234567890abcdef1234",
        }
        proxies = fetch_gist_nodes([target], max_nodes_per_sub=300)
        names = [p["name"] for p in proxies]
        self.assertEqual(set(names), {"Node-1", "Node-2", "Node-3"})

    @patch("core.parsers.requests.get")
    def test_load_proxies_http_url_enforces_300_node_limit_by_default(self, mock_get):
        nodes_250 = [
            {"name": f"Node-{i}", "type": "ss", "server": f"10.1.0.{i%250}", "port": 1000 + i, "cipher": "aes-128-gcm", "password": "p"}
            for i in range(250)
        ]
        nodes_305 = [
            {"name": f"Node-{i}", "type": "ss", "server": f"10.2.0.{i%250}", "port": 1000 + i, "cipher": "aes-128-gcm", "password": "p"}
            for i in range(305)
        ]

        def side_effect(url, headers=None, timeout=25):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            resp.text = yaml.safe_dump({"proxies": nodes_250 if "250" in url else nodes_305})
            return resp

        mock_get.side_effect = side_effect
        # 250 节点（在 200~300 之间）按最新 300 规则应正常保留，不得被旧 200 阈值误杀
        kept_250 = load_proxies("https://example.com/sub250.yaml")
        self.assertEqual(len(kept_250), 250)
        # 305 节点超过默认 300 上限，应整源淘汰
        dropped_305 = load_proxies("https://example.com/sub305.yaml")
        self.assertEqual(len(dropped_305), 0)


if __name__ == "__main__":
    unittest.main()
