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
        self.assertEqual(name_usai, "🇺🇸 ✨️❇️美国_1_USAI_NF_D+")

        # 优质日本直连跳板
        name_jp = format_node_name(
            cc="JP", slot=2, ai_supported=True, comprehensive_sparkle=True,
            media_details={"nf": True}
        )
        self.assertEqual(name_jp, "🇯🇵 ✨️❇️日本_2_NF")

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
        self.assertIn("✨️❇️美国_1_USAI_NF", results[1]["final_name"])

    def test_reputation_orders_same_country_same_capability(self):
        def row(name, score):
            return {
                "proxy": {"name": name, "type": "vless", "server": name, "port": 443},
                "cc": "JP", "ip_reputation": {"score": score, "status": "observed"},
                "ai_supported": False, "youtube_passed": False, "shield_passed": False,
            }
        results = [row("low", 20), row("high", 90)]
        tag_and_rename_nodes(results, resort=True)
        self.assertIn("日本_1", results[0]["final_name"])
        self.assertIn("日本_2", results[1]["final_name"])
        self.assertEqual(results[0]["ip_reputation"]["score"], 90)

    def test_tagged_names_match_exported_order(self):
        def row(name, key=False, sparkle=False):
            return {"proxy": {"name": name, "type": "vless", "server": name, "port": 443},
                    "cc": "JP", "is_key": key, "ai_supported": sparkle,
                    "youtube_passed": sparkle, "shield_passed": sparkle}
        for resort in (False, True):
            results = [row("key", key=True), row("sparkle", sparkle=True)]
            tag_and_rename_nodes(results, resort=resort)
            cfg = render_clash_config([dict(r["proxy"]) for r in results])
            self.assertEqual([r["final_name"] for r in results], [p["name"] for p in cfg["proxies"]])
            self.assertEqual([r["slot"] for r in results], [1, 2])
        self.assertIn("✨", results[0]["final_name"])

    def test_pipeline_keeps_original_slots_and_fills_new_nodes(self):
        def row(name, cc, **caps):
            return {"proxy": {"name": name, "type": "vless", "server": name, "port": 443},
                    "cc": cc, "ai_supported": caps.get("ai", False), "is_landing": caps.get("landing", False),
                    "ip_reputation": {"score": caps.get("score"), "status": "observed" if caps.get("score") else "unknown"}}
        results = [
            row("🇯🇵 日本_3", "JP"),                      # 原节点、属地与服务未变：名称原样保留
            row("🇯🇵 ❇️日本_5_Lnd", "JP", ai=True, landing=True),
            row("raw-new-a", "JP"), row("raw-new-b", "JP", score=95),  # 新节点从 1 补空号
            row("🇸🇬 新加坡_2", "JP"),                     # 属地变化视为新节点
            row("🇯🇵 日本_7", "JP", ai=True),              # 服务变化：徽章更新，编号保留
        ]
        tag_and_rename_nodes(results)
        names = [r["final_name"] for r in results]
        self.assertEqual(names, ["🇯🇵 日本_1", "🇯🇵 ♥️日本_2", "🇯🇵 日本_3", "🇯🇵 日本_4",
                                 "🇯🇵 ❇️日本_7", "🇯🇵 ❇️日本_5_Lnd"])
        self.assertEqual([r["proxy"]["server"] for r in results][:4],
                         ["raw-new-a", "raw-new-b", "🇯🇵 日本_3", "🇸🇬 新加坡_2"])
        cfg = render_clash_config([dict(r["proxy"]) for r in results])
        self.assertEqual([p["name"] for p in cfg["proxies"]], names)

    def test_poisoned_node_never_gets_reputation_badge(self):
        results = [{
            "proxy": {"name": "raw", "type": "vless", "server": "1.1.1.1", "port": 443},
            "cc": "SG", "ip_reputation": {"score": 95, "status": "observed"},
            "geo_decision": {"poison_tag": "_⚠️CN"},
        }]
        tag_and_rename_nodes(results)
        cfg = render_clash_config([dict(r["proxy"]) for r in results])
        self.assertNotIn("♥", results[0]["final_name"])
        self.assertNotIn("♥", cfg["proxies"][0]["name"])

    def test_reputation_ranks_only_within_same_tags_then_numbers(self):
        def proxy(name, score=None):
            rep = {"score": score, "status": "observed"} if score is not None else {"score": None, "status": "unknown"}
            return {"name": name, "type": "vless", "server": name, "port": 443, "_ip_reputation": rep}
        proxies = [
            proxy("🇯🇵 Fast日本_1", 60), proxy("🇯🇵 Fast日本_2"), proxy("🇯🇵 Fast日本_3", 92),
            proxy("🇯🇵 Key日本_4", 10), proxy("🇯🇵 Fast日本_5", 85),
        ]
        from core.renderer import sort_nodes_by_region_and_landing
        rendered = sort_nodes_by_region_and_landing(proxies, resort=True)
        names = [p["name"] for p in rendered]
        # Key 不被 ♥️ 的 Fast 越过；同为 Fast 时 ♥️/高分在前、未知最后；位置定好后再连续编号
        self.assertEqual(names, ["🇯🇵 Key日本_1", "🇯🇵 ♥️Fast日本_2", "🇯🇵 ♥️Fast日本_3",
                                 "🇯🇵 Fast日本_4", "🇯🇵 Fast日本_5"])
        self.assertEqual([p["server"] for p in rendered],
                         ["🇯🇵 Key日本_4", "🇯🇵 Fast日本_3", "🇯🇵 Fast日本_5",
                          "🇯🇵 Fast日本_1", "🇯🇵 Fast日本_2"])

    def test_resort_heart_never_crosses_media_tags(self):
        from core.renderer import sort_nodes_by_region_and_landing
        proxies = [
            {"name": "🇯🇵 ♥️日本_1", "type": "vless", "server": "hq", "port": 443,
             "_ip_reputation": {"score": 95, "status": "observed"}},
            {"name": "🇯🇵 日本_2_D+", "type": "vless", "server": "dp", "port": 443},
            {"name": "🇯🇵 日本_3_NF", "type": "vless", "server": "nf", "port": 443},
        ]
        rendered = sort_nodes_by_region_and_landing(proxies, resort=True)
        # _NF > _D+ 是标签层级，♥️ 只在标签完全相同时优先；位置定好后再从 1 编号
        self.assertEqual([p["server"] for p in rendered], ["nf", "dp", "hq"])
        self.assertEqual([p["name"] for p in rendered],
                         ["🇯🇵 日本_1_NF", "🇯🇵 日本_2_D+", "🇯🇵 ♥️日本_3"])

    def test_resort_keeps_heart_decided_by_tagger(self):
        # 浏览器复测沿用已有 ♥️（is_high_quality=True），重排序重编号时不能被信誉字段重新判掉
        results = [{"raw_node": {"tag": "🇯🇵 ♥️日本_2"}, "orig_name": "🇯🇵 ♥️日本_2", "cc": "JP",
                    "is_landing": False, "is_high_quality": True,
                    "ip_reputation": {"score": 70, "status": "observed"}}]
        tag_and_rename_nodes(results, resort=True)
        self.assertEqual(results[0]["final_name"], "🇯🇵 ♥️日本_1")

    def test_measured_direct_node_drops_stale_landing_suffix(self):
        results = [{"proxy": {"name": "🇯🇵 日本_2_Lnd", "type": "vless", "server": "a", "port": 443},
                    "cc": "JP", "is_landing": False}]
        tag_and_rename_nodes(results)
        self.assertEqual(results[0]["final_name"], "🇯🇵 日本_2")

    def test_browser_only_retest_keeps_poison_tag(self):
        import probe_singbox
        info = probe_singbox.parse_info_from_tag("🇰🇷 韩国_3_⚠️CN")
        self.assertEqual(info["poison_tag"], "_⚠️CN")
        results = [{"raw_node": {"tag": "🇰🇷 韩国_3_⚠️CN"}, "orig_name": "🇰🇷 韩国_3_⚠️CN",
                    "cc": info["cc"], "is_landing": False,
                    "geo_decision": {"poison_tag": info["poison_tag"]}}]
        tag_and_rename_nodes(results)
        self.assertEqual(results[0]["final_name"], "🇰🇷 韩国_3_⚠️CN")

    def test_clash_to_singbox_conversion_contracts(self):
        from core.clash_to_singbox import clash_to_singbox, convert_clash_proxies

        hy2 = clash_to_singbox({
            "name": "hy2-range", "type": "hysteria2", "server": "hy2.example",
            "ports": "443,8443-8450", "password": "secret", "sni": "hy2.example"
        })
        self.assertEqual(hy2["server_ports"], ["443:443", "8443:8450"])
        self.assertNotIn("server_port", hy2)

        reality = clash_to_singbox({
            "name": "reality", "type": "vless", "server": "reality.example", "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000001", "tls": True,
            "servername": "www.example.com",
            "reality-opts": {"public-key": "public", "short-id": "abcd"}
        })
        self.assertEqual(reality["tls"]["utls"], {"enabled": True, "fingerprint": "chrome"})
        self.assertEqual(reality["tls"]["reality"]["public_key"], "public")

        wireguard = clash_to_singbox({
            "name": "wg", "type": "wireguard", "server": "wg.example", "port": 51820,
            "ip": "10.0.0.2/32", "private-key": "private", "public-key": "public",
            "allowed-ips": ["0.0.0.0/0"]
        })
        self.assertEqual(wireguard["type"], "wireguard")
        self.assertEqual(wireguard["peers"][0]["address"], "wg.example")

        converted = convert_clash_proxies([
            {"name": "ok", "type": "http", "server": "proxy.example", "port": 8080},
            {"name": "bad", "type": "snell", "server": "snell.example", "port": 443}
        ])
        self.assertEqual([node["tag"] for node in converted["nodes"]], ["ok"])
        self.assertEqual(converted["skipped"], [("bad", "sing-box 不支持协议 snell")])

    def test_wireguard_endpoint_round_trips_to_clash(self):
        from core.renderer import convert_singbox_to_clash_yaml
        import tempfile
        import yaml

        endpoint = {
            "type": "wireguard", "tag": "wg", "address": ["10.0.0.2/32"],
            "private_key": "private",
            "peers": [{"address": "wg.example", "port": 51820,
                        "public_key": "public", "allowed_ips": ["0.0.0.0/0"]}]
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "out.yaml")
            convert_singbox_to_clash_yaml({"outbounds": [], "endpoints": [endpoint]}, output)
            with open(output, "r", encoding="utf-8") as stream:
                config = yaml.safe_load(stream)
        self.assertEqual(config["proxies"][0]["type"], "wireguard")
        self.assertEqual(config["proxies"][0]["name"], "wg")

    def test_yaml_input_is_converted_to_dual_output(self):
        import json
        import tempfile
        import convert_dual
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "in.yaml")
            output_json = os.path.join(tmp, "out.json")
            output_yaml = os.path.join(tmp, "out.yaml")
            with open(source, "w", encoding="utf-8") as stream:
                yaml.safe_dump({"proxies": [
                    {"name": "ok", "type": "trojan", "server": "proxy.example",
                     "port": 443, "password": "secret", "network": "ws",
                     "ws-opts": {"path": "/ws", "headers": {"Host": "front.example"}}},
                    {"name": "bad", "type": "snell", "server": "snell.example", "port": 443}
                ]}, stream, allow_unicode=True)
            result = convert_dual.convert_file_to_dual(source, output_json, output_yaml)
            with open(output_json, "r", encoding="utf-8") as stream:
                json_config = json.load(stream)
            with open(output_yaml, "r", encoding="utf-8") as stream:
                yaml_config = yaml.safe_load(stream)
            self.assertEqual(result["skipped"], [("bad", "sing-box 不支持协议 snell")])
            self.assertIn("ok", {o["tag"] for o in json_config["outbounds"]})
            self.assertEqual(yaml_config["proxies"][0]["ws-opts"]["headers"]["Host"], "front.example")
            self.assertEqual(yaml_config["proxies"][0]["ws-opts"]["path"], "/ws")
            self.assertEqual(len(yaml_config["proxies"]), 1)

    def test_json_input_keeps_port_ranges_and_endpoints(self):
        import json
        import tempfile
        import convert_dual
        import yaml

        source_config = {
            "outbounds": [{
                "type": "hysteria2", "tag": "🇯🇵 日本_1", "server": "hy2.example",
                "server_ports": ["443:443", "8443:8450"], "password": "secret",
                "tls": {"enabled": True, "server_name": "hy2.example"}
            }],
            "endpoints": [{
                "type": "wireguard", "tag": "🇯🇵 日本_2", "address": ["10.0.0.2/32"],
                "private_key": "private",
                "peers": [{"address": "wg.example", "port": 51820,
                            "public_key": "public", "allowed_ips": ["0.0.0.0/0"]}]
            }]
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "in.json")
            output_json = os.path.join(tmp, "out.json")
            output_yaml = os.path.join(tmp, "out.yaml")
            with open(source, "w", encoding="utf-8") as stream:
                json.dump(source_config, stream)
            convert_dual.convert_file_to_dual(source, output_json, output_yaml)
            with open(output_json, "r", encoding="utf-8") as stream:
                result_json = json.load(stream)
            with open(output_yaml, "r", encoding="utf-8") as stream:
                result_yaml = yaml.safe_load(stream)
        hy2 = next(node for node in result_json["outbounds"] if node.get("tag") == "🇯🇵 日本_1")
        self.assertEqual(hy2["server_ports"], ["443:443", "8443:8450"])
        self.assertNotIn("server_port", hy2)
        self.assertEqual(result_json["endpoints"][0]["type"], "wireguard")
        self.assertIn("wireguard", {node["type"] for node in result_yaml["proxies"]})

    def test_singbox_export_chains_landing_through_front(self):
        from core.singbox_runner import make_standard_singbox_config
        nodes = [
            {"type": "trojan", "tag": "🇯🇵 Key日本_1", "server": "a.example", "server_port": 443,
             "password": "a", "detour": "missing-anchor"},
            {"type": "trojan", "tag": "🇺🇸 美国_1_Lnd", "server": "b.example", "server_port": 443,
             "password": "b", "detour": "missing-anchor"},
        ]
        cfg = make_standard_singbox_config(nodes, [n["tag"] for n in nodes], [])
        by_tag = {o["tag"]: o for o in cfg["outbounds"]}
        self.assertNotIn("detour", by_tag["🇯🇵 Key日本_1"])
        self.assertEqual(by_tag["🇺🇸 美国_1_Lnd"]["detour"], "🛡️ Front前置")
        self.assertNotIn("🇺🇸 美国_1_Lnd", by_tag["🛡️ Front前置"]["outbounds"])

    def test_convert_dual_rejects_yaml_instead_of_empty_json(self):
        import tempfile
        import convert_dual
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.yaml")
            with open(src, "w", encoding="utf-8") as f:
                f.write("proxies: []\n")
            with self.assertRaises(ValueError):
                convert_dual.convert_file_to_dual(src, output_json=os.path.join(tmp, "out.json"))
            self.assertFalse(os.path.exists(os.path.join(tmp, "out.json")))

            src_json = os.path.join(tmp, "in.json")
            with open(src_json, "w", encoding="utf-8") as f:
                f.write('{"outbounds": []}')
            # 默认输出名与输入同名时拒绝就地覆盖
            with self.assertRaises(ValueError):
                convert_dual.convert_file_to_dual(src_json)

    def test_shield_requires_complete_resolved_observations(self):
        from core.shield_probe import SHIELD_TARGETS, shield_passed
        names = [t["name"] for t in SHIELD_TARGETS]

        def rows(*statuses):
            return {n: {"status": s} for n, s in zip(names, statuses)}
        # 至少 2 站直接通过或质询自动解除即判定免盾；未观测、阻断与未解除质询不计入
        self.assertTrue(shield_passed(rows("passed", "auto_passed", "blocked", "challenge")))
        self.assertTrue(shield_passed(rows("auto_passed", "auto_passed", "unknown", "unknown")))
        self.assertFalse(shield_passed(rows("passed", "challenge", "blocked", "unknown")))
        self.assertFalse(shield_passed(rows("unknown", "unknown", "unknown", "unknown")))
        self.assertFalse(shield_passed({}))

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
        self.assertEqual(name, "🇺🇸 ✨️❇️Fast美国_洛杉矶_1_USAI_NF_D+")

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
        from core.singbox_runner import make_standard_singbox_config, export_singbox_json, find_singbox_bin
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
            if find_singbox_bin():
                self.assertTrue(exp_res["check_ok"])
            else:
                self.assertFalse(exp_res["check_ok"])
                self.assertIn("未检测到", exp_res["check_msg"])

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

            # 6. 验证地区分组与落地节点规则：同地区落地排最后；若全节点首位地区仅有单个落地节点，则挪至下一个地区后面；
            #    导出不重排编号，名称原样保留（重编号只在打标阶段 resort=True 时发生）
            raw_outbounds = [o["tag"] for o in sb_cfg["outbounds"] if o["type"] not in ("selector", "urltest", "direct", "block", "dns")]
            self.assertEqual(raw_outbounds[0], "🇯🇵 日本_1_D+")
            self.assertEqual(raw_outbounds[1], "🇭🇰 香港_1_Lnd")
            self.assertEqual(raw_outbounds[2], "🇺🇸 ❇️✨️美国_8_NF_D+")
        finally:
            if os.path.exists(tmp_json):
                os.remove(tmp_json)


if __name__ == "__main__":
    unittest.main()

