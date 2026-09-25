# -*- coding: utf-8 -*-
"""针对持续下载测速、Key 节点优选、打标体系、策略组规则与防断网保护的单元测试。"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core.speed_probe import RateMeter, speed_qualified
from core.key_evaluator import (
    is_key_protocol_allowed,
    protocol_class,
    evaluate_key_node,
    select_key_nodes,
    KEY_DISALLOWED_PROTOCOLS
)
from core.tagger import format_node_name, tag_and_rename_nodes, parse_existing_slot
from core.renderer import build_proxy_groups, render_clash_config
from core.mihomo_runner import get_free_port, detect_physical_interface, BLACKLIST_PORTS


class TestSpeedProbe(unittest.TestCase):
    """测试 RateMeter 逐秒分桶与达标判定"""

    def test_rate_meter_buckets_bytes_per_second(self):
        # 起点 100 秒，观测 5 秒；每秒稳定传输 1.25 MB = 10 Mbps
        meter = RateMeter(started_at=100.0, warmup_seconds=0.0, duration_seconds=5.0)
        for sec in range(1, 6):
            meter.record(when=100.0 + sec, total_bytes=int(sec * 1.25 * 1000 * 1000))
        rates = [count * 8 / 1_000_000 for count in meter.buckets]
        for rate in rates:
            self.assertAlmostEqual(rate, 10.0, delta=0.01)
        self.assertEqual(meter.max_stall, 0.0)

    def test_speed_qualified_criteria(self):
        valid = {"status": "complete", "stable_mbps": 15.0, "floor_mbps": 9.0}
        self.assertTrue(speed_qualified(valid))
        # 稳态不足 12 Mbps
        self.assertFalse(speed_qualified({**valid, "stable_mbps": 10.0}))
        # 稳态窗口内出现连续下滑 (2 秒滑动最低 < 6 Mbps)
        self.assertFalse(speed_qualified({**valid, "floor_mbps": 4.0}))
        # 中途断流的测量不授予资格
        self.assertFalse(speed_qualified({**valid, "status": "stalled"}))
        # 自定义门槛
        self.assertTrue(speed_qualified({**valid, "stable_mbps": 10.0}, min_stable_mbps=8.0))


class TestKeyEvaluator(unittest.TestCase):
    """测试 Key 前置跳板资格审查与优选"""

    def test_protocol_whitelist(self):
        # 严禁 HTTP/HTTPS/SOCKS
        for disallowed in KEY_DISALLOWED_PROTOCOLS:
            self.assertFalse(is_key_protocol_allowed({"type": disallowed}))

        # 允许强加密协议
        self.assertTrue(is_key_protocol_allowed({"type": "ss"}))
        self.assertTrue(is_key_protocol_allowed({"type": "vmess", "tls": True}))
        self.assertTrue(is_key_protocol_allowed({"type": "trojan"}))
        self.assertTrue(is_key_protocol_allowed({"type": "hysteria2"}))
        self.assertTrue(is_key_protocol_allowed({"type": "tuic"}))
        self.assertTrue(is_key_protocol_allowed({"type": "vless", "tls": True}))
        # vless 无 TLS 但使用 ws
        self.assertTrue(is_key_protocol_allowed({"type": "vless", "network": "ws"}))
        # vless 无 TLS 且无安全传输层
        self.assertFalse(is_key_protocol_allowed({"type": "vless", "network": "tcp"}))

    def test_evaluate_key_node(self):
        speed_ok = {"status": "complete", "verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}
        egress_ok = {
            "exit_ip": "1.2.3.4",
            "runner_ip_match": False,
            "country": "JP"
        }

        # 1. 落地节点绝不可作为 Key
        lnd_node = {"name": "🇯🇵 日本_1_Lnd", "type": "ss", "_is_landing": True}
        ok, _, reason = evaluate_key_node(lnd_node, speed_ok, egress_ok)
        self.assertFalse(ok)
        self.assertIn("落地节点", reason)

        # 2. HTTP 节点绝不可作为 Key
        http_node = {"name": "🇯🇵 日本_1", "type": "http"}
        ok, _, reason = evaluate_key_node(http_node, speed_ok, egress_ok)
        self.assertFalse(ok)
        self.assertIn("HTTP", reason)

        # 3. 真实出口与本地跑机重合
        match_egress = {"exit_ip": "1.2.3.4", "runner_ip_match": True}
        ss_node = {"name": "🇯🇵 日本_1", "type": "ss"}
        ok, _, reason = evaluate_key_node(ss_node, speed_ok, match_egress)
        self.assertFalse(ok)
        self.assertIn("重合", reason)

        # 4. 优质直连通过审查
        direct_node = {"name": "🇯🇵 日本_1", "type": "trojan", "_country_code": "JP"}
        ok, score, reason = evaluate_key_node(direct_node, speed_ok, egress_ok, delay=60.0)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertGreater(score, 25.0)

    def test_select_key_nodes_selection(self):
        nodes = [
            # 候选1: 日本 Trojan (优质)
            {
                "proxy": {"name": "node_jp", "type": "trojan", "_country_code": "JP"},
                "cc": "JP",
                "speed_result": {"status": "complete", "verdict": "qualified", "stable_mbps": 45.0, "floor_mbps": 38.0},
                "egress_result": {"exit_ip": "1.1.1.1", "runner_ip_match": False, "country": "JP"},
                "delay": 50.0
            },
            # 候选2: 香港 VMess (优质)
            {
                "proxy": {"name": "node_hk", "type": "vmess", "tls": True, "_country_code": "HK"},
                "cc": "HK",
                "speed_result": {"status": "complete", "verdict": "qualified", "stable_mbps": 40.0, "floor_mbps": 33.0},
                "egress_result": {"exit_ip": "2.2.2.2", "runner_ip_match": False, "country": "HK"},
                "delay": 40.0
            },
            # 候选3: 美国 HTTP (测速快但协议不允许)
            {
                "proxy": {"name": "node_us_http", "type": "http", "_country_code": "US"},
                "cc": "US",
                "speed_result": {"status": "complete", "verdict": "qualified", "stable_mbps": 50.0, "floor_mbps": 40.0},
                "egress_result": {"exit_ip": "3.3.3.3", "runner_ip_match": False, "country": "US"},
                "delay": 150.0
            },
            # 候选4: 台湾 落地节点 (不允许)
            {
                "proxy": {"name": "node_tw_lnd", "type": "ss", "_is_landing": True, "_country_code": "TW"},
                "cc": "TW",
                "speed_result": {"status": "complete", "verdict": "qualified", "stable_mbps": 25.0, "floor_mbps": 20.0},
                "egress_result": {"exit_ip": "4.4.4.4", "runner_ip_match": False, "country": "TW"},
                "delay": 60.0
            }
        ]

        chosen = select_key_nodes(nodes, max_keys=5, per_country_cap=2)
        chosen_names = [r["proxy"]["name"] for r in chosen]
        self.assertIn("node_jp", chosen_names)
        self.assertIn("node_hk", chosen_names)
        self.assertNotIn("node_us_http", chosen_names)
        self.assertNotIn("node_tw_lnd", chosen_names)
        self.assertTrue(nodes[0]["proxy"]["_is_key"])
        self.assertFalse(nodes[2]["proxy"].get("_is_key", False))

    def test_key_selection_honors_raised_speed_threshold(self):
        # 用户调高 --min-speed-mbps 后，Key 与 Fast 使用同一门槛，不再固定按默认门槛放行
        row = {
            "proxy": {"name": "node_jp", "type": "trojan"}, "cc": "JP",
            "speed_result": {"status": "complete", "verdict": "qualified", "stable_mbps": 14.0, "floor_mbps": 10.0},
            "egress_result": {"exit_ip": "1.1.1.1", "runner_ip_match": False},
        }
        self.assertEqual(select_key_nodes([row], min_stable_mbps=16.0), [])
        self.assertEqual(len(select_key_nodes([row], min_stable_mbps=12.0)), 1)

    def test_asia_bonus_uses_pipeline_country_code(self):
        # 流水线结果行只有 cc（无 _country_code / country），亚太加分仍需生效
        speed = {"status": "complete", "verdict": "qualified", "stable_mbps": 40.0, "floor_mbps": 35.0}
        row = {"exit_ip": "1.1.1.1", "cc": "JP"}
        _, jp_score, _ = evaluate_key_node({"name": "a", "type": "trojan"}, speed, row, delay=50.0)
        _, us_score, _ = evaluate_key_node({"name": "b", "type": "trojan"}, speed, {**row, "cc": "US"}, delay=50.0)
        self.assertAlmostEqual(jp_score - us_score, 8.0, places=6)


class TestTaggerAndNaming(unittest.TestCase):
    """测试 Key 与 Fast 节点打标规范与重命名"""

    def test_format_node_name_variants(self):
        # 1. 综合全通 Key 节点: 🇯🇵 ✨️❇️Key日本_1
        name_key = format_node_name(cc="JP", slot=1, ai_supported=True, comprehensive_sparkle=True, is_key=True)
        self.assertEqual(name_key, "🇯🇵 ✨️❇️Key日本_1")

        # 2. 综合全通 Fast 节点 (非 Key): 🇺🇸 ✨️❇️Fast美国_1
        name_fast = format_node_name(cc="US", slot=1, ai_supported=True, comprehensive_sparkle=True, is_key=False, is_fast=True)
        self.assertEqual(name_fast, "🇺🇸 ✨️❇️Fast美国_1")

        # 3. Key 与 Fast 互斥 (Key 优先): 🇯🇵 ❇️Key日本_2
        name_conflict = format_node_name(cc="JP", slot=2, ai_supported=True, is_key=True, is_fast=True)
        self.assertEqual(name_conflict, "🇯🇵 ❇️Key日本_2")

        # 4. 普通节点: 🇭🇰 香港_1
        name_norm = format_node_name(cc="HK", slot=1)
        self.assertEqual(name_norm, "🇭🇰 香港_1")

    def test_canonical_name_parsing_for_slot_preservation(self):
        from core.tagger import parse_canonical_node
        self.assertEqual(parse_canonical_node("🇯🇵 ✨️❇️♥️Key日本_12_NF"), {"cc": "JP", "slot": 12, "city": ""})
        self.assertEqual(parse_canonical_node("🇺🇸 Fast美国_洛杉矶_3_USAI"), {"cc": "US", "slot": 3, "city": "洛杉矶"})
        self.assertEqual(parse_canonical_node("🇰🇷 韩国_2_⚠️CN")["slot"], 2)
        # 非本技能规范命名、国旗与国家名不一致均视为新节点
        for name in ("JP-Tokyo-01", "🇯🇵 东京_1", "🇯🇵 美国_1", "日本_1", "🇯🇵 日本", "🇯🇵 日本_0"):
            self.assertIsNone(parse_canonical_node(name), name)

    def test_parse_existing_slot_strips_tags(self):
        self.assertEqual(parse_existing_slot("🇯🇵 ✨️❇️Key日本_1"), 1)
        self.assertEqual(parse_existing_slot("🇺🇸 ✨️❇️Fast美国_12_USAI"), 12)
        self.assertEqual(parse_existing_slot("🇭🇰 香港_3_Lnd"), 3)


class TestRendererGroupingSync(unittest.TestCase):
    """测试分组规则同步与落地节点链式跳板绑定"""

    def test_front_and_fast_groups_with_keys(self):
        proxies = [
            {"name": "🇯🇵 ✨️❇️Key日本_1", "type": "trojan", "_is_key": True, "_key_score": 42.0},
            {"name": "🇭🇰 ❇️Key香港_1", "type": "vmess", "_is_key": True, "_key_score": 39.0},
            {"name": "🇺🇸 ✨️❇️Fast美国_1", "type": "http", "_is_fast": True},
            {"name": "🇺🇸 ❇️美国_2_Lnd", "type": "ss", "_is_landing": True}
        ]

        cfg = render_clash_config(proxies)
        groups = {g["name"]: g for g in cfg["proxy-groups"]}

        self.assertIn("🛡️ Front前置", groups)
        self.assertIn("⚡ Fast自动选择", groups)
        self.assertIn("🔒️ 落地节点", groups)

        # 1. 验证 🛡️ Front前置 包含 Key 节点，且绝不包含落地节点
        front_members = groups["🛡️ Front前置"]["proxies"]
        self.assertIn("⚡ Fast自动选择", front_members)
        self.assertIn("DIRECT", front_members)
        self.assertIn("🇯🇵 ✨️❇️Key日本_1", front_members)
        self.assertIn("🇭🇰 ❇️Key香港_1", front_members)
        self.assertNotIn("🇺🇸 ❇️美国_2_Lnd", front_members)

        # 2. 验证 ⚡ Fast自动选择 仅对 Key 优质跳板执行 url-test
        fast_members = groups["⚡ Fast自动选择"]["proxies"]
        self.assertIn("🇯🇵 ✨️❇️Key日本_1", fast_members)
        self.assertIn("🇭🇰 ❇️Key香港_1", fast_members)
        self.assertNotIn("🇺🇸 ✨️❇️Fast美国_1", fast_members)
        self.assertNotIn("🇺🇸 ❇️美国_2_Lnd", fast_members)

        # 3. 验证落地节点自动注入 dialer-proxy: 🛡️ Front前置
        clean_proxies = {p["name"]: p for p in cfg["proxies"]}
        self.assertEqual(clean_proxies["🇺🇸 ❇️美国_2_Lnd"].get("dialer-proxy"), "🛡️ Front前置")
        self.assertNotIn("dialer-proxy", clean_proxies["🇯🇵 ✨️❇️Key日本_1"])


class TestSafetyAndIsolation(unittest.TestCase):
    """测试端口黑名单避让与物理网卡探测安全机制"""

    def test_port_avoids_blacklist(self):
        for _ in range(20):
            port = get_free_port()
            self.assertNotIn(port, BLACKLIST_PORTS)

    def test_detect_physical_interface_non_throwing(self):
        # 无论系统环境如何，该方法绝不应抛出未捕获异常
        iface = detect_physical_interface()
        if iface:
            self.assertIsInstance(iface, str)


if __name__ == "__main__":
    unittest.main()
