#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能自检与单元测试脚本。"""
import os
import sys
import unittest

# 将 scripts 目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.parsers import parse_node_uri, parse_singbox_outbound, load_proxies
from core.egress_geo import alpha3_to_alpha2, country_name_zh, flag_emoji
from core.tagger import SlotAllocator, format_node_name, tag_and_rename_nodes
from core.renderer import load_template, build_proxy_groups, render_clash_config


class TestProxyServiceProbe(unittest.TestCase):

    def test_geo_helpers(self):
        self.assertEqual(alpha3_to_alpha2("USA"), "US")
        self.assertEqual(alpha3_to_alpha2("HKG"), "HK")
        self.assertEqual(alpha3_to_alpha2("JPN"), "JP")
        self.assertEqual(country_name_zh("US"), "美国")
        self.assertEqual(country_name_zh("HK"), "香港")
        self.assertEqual(country_name_zh("JP"), "日本")
        self.assertEqual(flag_emoji("US"), "🇺🇸")
        self.assertEqual(flag_emoji("JP"), "🇯🇵")

    def test_node_parsers(self):
        # 1. Trojan URI
        uri_trojan = "trojan://test-pwd@1.2.3.4:443?sni=example.com#TestTrojan"
        p = parse_node_uri(uri_trojan)
        self.assertIsNotNone(p)
        self.assertEqual(p["type"], "trojan")
        self.assertEqual(p["server"], "1.2.3.4")
        self.assertEqual(p["port"], 443)
        self.assertEqual(p["password"], "test-pwd")
        self.assertEqual(p["sni"], "example.com")

        # 2. VLESS Reality URI
        uri_vless = "vless://01234567-89ab-cdef-0123-456789abcdef@5.6.7.8:443?security=reality&sni=target.com&fp=chrome&pbk=pubkey123&sid=shortid123#TestVless"
        p_vl = parse_node_uri(uri_vless)
        self.assertIsNotNone(p_vl)
        self.assertEqual(p_vl["type"], "vless")
        self.assertEqual(p_vl["client-fingerprint"], "chrome")
        self.assertEqual(p_vl["reality-opts"]["public-key"], "pubkey123")

        # 3. sing-box outbound
        sb_outbound = {
            "type": "hysteria2",
            "tag": "TestHy2",
            "server": "9.8.7.6",
            "server_port": 8443,
            "password": "hy2-secret",
            "tls": {"enabled": True, "server_name": "hy2.example.com"}
        }
        p_sb = parse_singbox_outbound(sb_outbound)
        self.assertIsNotNone(p_sb)
        self.assertEqual(p_sb["type"], "hysteria2")
        self.assertEqual(p_sb["sni"], "hy2.example.com")

    def test_tagger_and_naming(self):
        # 综合全通美国落地
        name_usai = format_node_name(
            cc="US", slot=1, ai_supported=True, comprehensive_sparkle=True,
            is_landing=True, is_usai=True, media_details={"nf": True, "dp": True}
        )
        self.assertEqual(name_usai, "🇺🇸 ❇️✨️美国_1_USAI_NF_D+")

        # 优质日本直连跳板
        name_jp_key = format_node_name(
            cc="JP", slot=2, ai_supported=True, comprehensive_sparkle=True,
            is_key=True, media_details={"nf": True}
        )
        self.assertEqual(name_jp_key, "🇯🇵 ❇️✨️Key日本_2_NF")

        # 批量打标与排序测试
        results = [
            {
                "proxy": {"name": "raw_us_node", "type": "ss", "server": "1.1.1.1", "port": 8388},
                "cc": "US",
                "is_landing": True,
                "ai_supported": True,
                "youtube_passed": True,
                "shield_passed": True,
                "media_details": {"nf": True}
            },
            {
                "proxy": {"name": "raw_hk_key", "type": "vless", "server": "2.2.2.2", "port": 443},
                "cc": "HK",
                "is_key": True,
                "ai_supported": False,
                "youtube_passed": False,
                "shield_passed": False
            }
        ]
        tag_and_rename_nodes(results)
        # 香港应排在美国前面
        self.assertEqual(results[0]["cc"], "HK")
        self.assertIn("Key香港_1", results[0]["final_name"])
        self.assertEqual(results[1]["cc"], "US")
        self.assertIn("❇️✨️美国_1_USAI_NF", results[1]["final_name"])

    def test_renderer(self):
        template = load_template()
        self.assertIn("rules", template)
        self.assertIn("dns", template)

        mock_proxies = [
            {"name": "🇭🇰 Key香港_1", "type": "vless", "server": "1.1.1.1", "port": 443},
            {"name": "🇺🇸 ❇️✨️美国_1_USAI_NF_D+", "type": "vmess", "server": "2.2.2.2", "port": 443},
            {"name": "🇸🇬 ❇️新加坡_1_Lnd", "type": "trojan", "server": "3.3.3.3", "port": 443}
        ]

        cfg = render_clash_config(mock_proxies)
        self.assertEqual(len(cfg["proxies"]), 3)

        # 验证落地节点自动绑定 dialer-proxy
        for p in cfg["proxies"]:
            if "_USAI" in p["name"] or "_Lnd" in p["name"]:
                self.assertEqual(p.get("dialer-proxy"), "🛡️ Front前置")
            else:
                self.assertNotIn("dialer-proxy", p)

        # 验证必需的核心策略组均已生成
        group_names = {g["name"] for g in cfg["proxy-groups"]}
        required = [
            "🛡️ Front前置", "⚡ Fast自动选择", "🌏️ 节点选择", "🚀 自动选择",
            "🔄 手动切换", "🔀 AI 服务", "🇺🇸 Google", "✅ 解锁USAI",
            "✅ 解锁 AI", "🎬 国际流媒体", "🎥 奈飞解锁", "✨ 解锁Disney+", "🔒️ 落地节点"
        ]
        for req in required:
            self.assertIn(req, group_names, f"缺少策略组: {req}")


if __name__ == "__main__":
    unittest.main()
