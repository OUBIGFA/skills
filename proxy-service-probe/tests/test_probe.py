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
        name_jp = format_node_name(
            cc="JP", slot=2, ai_supported=True, comprehensive_sparkle=True,
            media_details={"nf": True}
        )
        self.assertEqual(name_jp, "🇯🇵 ❇️✨️日本_2_NF")

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
                "proxy": {"name": "raw_hk", "type": "vless", "server": "2.2.2.2", "port": 443},
                "cc": "HK",
                "ai_supported": False,
                "youtube_passed": False,
                "shield_passed": False
            }
        ]
        tag_and_rename_nodes(results)
        # 香港应排在美国前面
        self.assertEqual(results[0]["cc"], "HK")
        self.assertIn("香港_1", results[0]["final_name"])
        self.assertEqual(results[1]["cc"], "US")
        self.assertIn("❇️✨️美国_1_USAI_NF", results[1]["final_name"])

    def test_renderer(self):
        template = load_template()
        self.assertIn("rules", template)
        self.assertIn("dns", template)

        mock_proxies = [
            {"name": "🇭🇰 香港_1", "type": "vless", "server": "1.1.1.1", "port": 443},
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

    def test_singbox_format_and_sparkle(self):
        import probe_singbox
        name = probe_singbox.format_node_name(
            cc="US", slot=1, city="洛杉矶", ai_supported=True,
            comprehensive_sparkle=True, is_fast=True, is_landing=True,
            is_usai=True, media_details={"nf": True, "dp": True}
        )
        self.assertEqual(name, "🇺🇸 ❇️✨️Fast美国_洛杉矶_1_USAI_NF_D+")

    def test_convert_singbox_to_clash_yaml(self):
        from core.renderer import convert_singbox_to_clash_yaml
        import tempfile
        import yaml

        mock_sb = {
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "🇺🇸 ❇️✨️美国_1_NF",
                    "server": "1.2.3.4",
                    "server_port": 443,
                    "uuid": "01234567-89ab-cdef-0123-456789abcdef"
                },
                {
                    "type": "vmess",
                    "tag": "🇭🇰 香港_1_Lnd",
                    "server": "5.6.7.8",
                    "server_port": 443,
                    "uuid": "01234567-89ab-cdef-0123-456789abcdef"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
            tmp_yaml = tf.name

        try:
            convert_singbox_to_clash_yaml(mock_sb, tmp_yaml)
            with open(tmp_yaml, "r", encoding="utf-8") as f:
                clash_cfg = yaml.safe_load(f)

            self.assertIn("proxies", clash_cfg)
            self.assertEqual(len(clash_cfg["proxies"]), 2)
            group_names = {g["name"] for g in clash_cfg["proxy-groups"]}
            self.assertIn("✨️ 综合全通", group_names)
            self.assertIn("🛡️ Front前置", group_names)
        finally:
            if os.path.exists(tmp_yaml):
                os.remove(tmp_yaml)

    def test_singbox_modern_dns_and_node_sorting(self):
        from core.singbox_runner import make_standard_singbox_config, export_singbox_json
        import tempfile
        import json

        proxies = [
            {"tag": "🇭🇰 香港_1_Lnd", "type": "vless", "server": "1.1.1.1", "server_port": 443},
            {"tag": "🇺🇸 ❇️✨️美国_8_NF_D+", "type": "vmess", "server": "2.2.2.2", "server_port": 443},
            {"tag": "🇯🇵 日本_1_D+", "type": "trojan", "server": "3.3.3.3", "server_port": 443}
        ]
        results = [
            {"final_name": p["tag"], "raw_node": p, "is_landing": ("_Lnd" in p["tag"])}
            for p in proxies
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tmp_json = tf.name

        try:
            exp_res = export_singbox_json({}, results, tmp_json)
            self.assertTrue(exp_res["check_ok"])

            with open(tmp_json, "r", encoding="utf-8") as f:
                sb_cfg = json.load(f)

            # 1. 验证 DNS 结构完全符合 1.12+/1.14+ 强类型规范 (无 address 废弃语法，具备 type: https/udp/local，直连/本地无冗余 detour)
            dns_servers = sb_cfg["dns"]["servers"]
            types = {s["tag"]: s.get("type") for s in dns_servers}
            self.assertEqual(types["dns_proxy"], "https")
            self.assertEqual(types["dns_direct"], "udp")
            self.assertEqual(types["dns_local"], "local")
            self.assertNotIn("dns_block", types)
            for s in dns_servers:
                self.assertNotIn("address", s, f"DNS 服务器 {s['tag']} 不应包含废弃的 address 字段")
                if s["tag"] in ("dns_direct", "dns_local"):
                    self.assertNotIn("detour", s, f"DNS 服务器 {s['tag']} 不应指向空 direct 出站")

            # 2. 验证 inbounds[0] 不含废弃的 sniff 字段 (符合 1.13+ 规范)
            for ib in sb_cfg["inbounds"]:
                self.assertNotIn("sniff", ib, "inbounds 不应包含废弃的 sniff 字段")

            # 3. 验证 outbounds 不含废弃的 dns 特殊出站 (符合 1.13+ 规范，DNS 使用 hijack-dns 规则劫持)
            out_types = {o.get("type") for o in sb_cfg["outbounds"]}
            self.assertNotIn("dns", out_types, "outbounds 不应包含废弃的 dns 出站")

            # 3.1 验证策略组完全同步 Clash/Mihomo 17 个标准策略组
            group_tags = {o.get("tag") for o in sb_cfg["outbounds"] if o.get("type") in ("selector", "urltest")}
            expected_groups = [
                "🛡️ Front前置", "⚡ Fast自动选择", "🌏️ 节点选择", "🚀 自动选择", "🔄 手动切换",
                "✨️ 综合全通", "🔀 AI 服务", "🇺🇸 Google", "✅ 解锁 AI", "✅ 解锁USAI",
                "🇺🇸 美国节点", "🎬 国际流媒体", "🎥 奈飞解锁", "✨ 解锁Disney+",
                "🔒️ 落地节点", "⛔️ 拦截广告", "↪️ 漏网之鱼"
            ]
            for eg in expected_groups:
                self.assertIn(eg, group_tags, f"sing-box 配置应包含与 YAML 一致的策略组: {eg}")

            # 4. 验证 route.rules 包含 action: sniff 与 action: hijack-dns
            rule_actions = [r.get("action") for r in sb_cfg["route"]["rules"] if "action" in r]
            self.assertIn("sniff", rule_actions)
            self.assertIn("hijack-dns", rule_actions)

            # 5. 验证 1.14+ 现代 http_clients 替代旧版 download_detour
            self.assertIn("http_clients", sb_cfg)
            self.assertEqual(sb_cfg["route"]["default_http_client"], "direct-client")
            rule_sets = sb_cfg["route"]["rule_set"]
            for rs in rule_sets:
                self.assertNotIn("download_detour", rs, "1.14+ 规则集不应包含已废弃的 download_detour")
            self.assertEqual(sb_cfg["route"]["default_domain_resolver"], "dns_direct")

            # 6. 验证地区分组与落地节点规则：同地区落地排最后；若全节点首位地区仅有单个落地节点，则挪至下一个地区后面；定好位置再严格从 1 重新编号
            raw_outbounds = [o["tag"] for o in sb_cfg["outbounds"] if o["type"] not in ("selector", "urltest", "direct", "block", "dns")]
            self.assertEqual(raw_outbounds[0], "🇯🇵 日本_1_D+")
            self.assertEqual(raw_outbounds[1], "🇭🇰 香港_1_Lnd")
            self.assertEqual(raw_outbounds[2], "🇺🇸 ❇️✨️美国_1_NF_D+")
        finally:
            if os.path.exists(tmp_json):
                os.remove(tmp_json)


if __name__ == "__main__":
    unittest.main()

