# -*- coding: utf-8 -*-
"""针对持续下载测速、Key 节点优选、打标体系、策略组规则与防断网保护的单元测试。"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core.speed_probe import RateMeter, speed_qualified, precheck_target
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
    """测试 RateMeter 采样与达标判定"""

    def test_rate_meter_calculations(self):
        # 模拟 1 秒 warmup，5 秒观测
        started = 100.0
        meter = RateMeter(started_at=started, warmup_seconds=1.0, duration_seconds=5.0)

        # 0~1秒 (warmup 阶段): 收到 200KB (不计入测速有效时间窗的速率)
        meter.record(when=100.5, total_bytes=100 * 1024)
        meter.record(when=101.0, total_bytes=200 * 1024)

        # 1~6秒 (测速窗口): 每秒稳定传输 1.25 MB = 10 Mbps
        # 101.0 -> 106.0: 累计增加 5 * 1.25 * 10^6 bytes
        for sec in range(1, 6):
            t = 101.0 + sec
            meter.record(when=t, total_bytes=200 * 1024 + int(sec * 1.25 * 1000 * 1000))

        report = meter.report(status="complete", ended_at=106.0)
        self.assertTrue(report["complete"])
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["measured_seconds"], 5.0)
        self.assertIsNotNone(report["median_mbps"])
        # 预期约 10 Mbps 左右
        self.assertGreaterEqual(report["median_mbps"], 9.0)
        self.assertLessEqual(report["median_mbps"], 11.0)
        self.assertEqual(report["max_stall_seconds"], 0.0)

    def test_speed_qualified_criteria(self):
        # 1. 达标案例
        valid_res = {
            "complete": True,
            "status": "complete",
            "median_mbps": 12.5,
            "p10_mbps": 8.0,
            "max_stall_seconds": 0.2
        }
        self.assertTrue(speed_qualified(valid_res, min_median_mbps=5.0))

        # 2. 中位数不足 5 Mbps
        slow_res = {
            "complete": True,
            "status": "complete",
            "median_mbps": 3.2,
            "p10_mbps": 2.0,
            "max_stall_seconds": 0.0
        }
        self.assertFalse(speed_qualified(slow_res, min_median_mbps=5.0))

        # 3. 卡顿超时 (> 1.0s)
        stall_res = {
            "complete": True,
            "status": "complete",
            "median_mbps": 15.0,
            "p10_mbps": 5.0,
            "max_stall_seconds": 1.8
        }
        self.assertFalse(speed_qualified(stall_res, min_median_mbps=5.0, max_stall_seconds=1.0))

        # 4. 未完整测完
        incomp_res = {
            "complete": False,
            "status": "short_response",
            "median_mbps": 20.0,
            "p10_mbps": 15.0,
            "max_stall_seconds": 0.0
        }
        self.assertFalse(speed_qualified(incomp_res))


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
        speed_ok = {
            "complete": True,
            "status": "complete",
            "median_mbps": 15.0,
            "p10_mbps": 10.0,
            "max_stall_seconds": 0.0
        }
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
                "speed_result": {"complete": True, "status": "complete", "median_mbps": 20.0, "p10_mbps": 15.0, "max_stall_seconds": 0.0},
                "egress_result": {"exit_ip": "1.1.1.1", "runner_ip_match": False, "country": "JP"},
                "delay": 50.0
            },
            # 候选2: 香港 VMess (优质)
            {
                "proxy": {"name": "node_hk", "type": "vmess", "tls": True, "_country_code": "HK"},
                "cc": "HK",
                "speed_result": {"complete": True, "status": "complete", "median_mbps": 18.0, "p10_mbps": 12.0, "max_stall_seconds": 0.0},
                "egress_result": {"exit_ip": "2.2.2.2", "runner_ip_match": False, "country": "HK"},
                "delay": 40.0
            },
            # 候选3: 美国 HTTP (测速快但协议不允许)
            {
                "proxy": {"name": "node_us_http", "type": "http", "_country_code": "US"},
                "cc": "US",
                "speed_result": {"complete": True, "status": "complete", "median_mbps": 50.0, "p10_mbps": 40.0, "max_stall_seconds": 0.0},
                "egress_result": {"exit_ip": "3.3.3.3", "runner_ip_match": False, "country": "US"},
                "delay": 150.0
            },
            # 候选4: 台湾 落地节点 (不允许)
            {
                "proxy": {"name": "node_tw_lnd", "type": "ss", "_is_landing": True, "_country_code": "TW"},
                "cc": "TW",
                "speed_result": {"complete": True, "status": "complete", "median_mbps": 25.0, "p10_mbps": 20.0, "max_stall_seconds": 0.0},
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


class TestTaggerAndNaming(unittest.TestCase):
    """测试 Key 与 Fast 节点打标规范与重命名"""

    def test_format_node_name_variants(self):
        # 1. 综合全通 Key 节点: 🇯🇵 ❇️✨️Key日本_1
        name_key = format_node_name(cc="JP", slot=1, ai_supported=True, comprehensive_sparkle=True, is_key=True)
        self.assertEqual(name_key, "🇯🇵 ❇️✨️Key日本_1")

        # 2. 综合全通 Fast 节点 (非 Key): 🇺🇸 ❇️✨️Fast美国_1
        name_fast = format_node_name(cc="US", slot=1, ai_supported=True, comprehensive_sparkle=True, is_key=False, is_fast=True)
        self.assertEqual(name_fast, "🇺🇸 ❇️✨️Fast美国_1")

        # 3. Key 与 Fast 互斥 (Key 优先): 🇯🇵 ❇️Key日本_2
        name_conflict = format_node_name(cc="JP", slot=2, ai_supported=True, is_key=True, is_fast=True)
        self.assertEqual(name_conflict, "🇯🇵 ❇️Key日本_2")

        # 4. 普通节点: 🇭🇰 香港_1
        name_norm = format_node_name(cc="HK", slot=1)
        self.assertEqual(name_norm, "🇭🇰 香港_1")

    def test_parse_existing_slot_strips_tags(self):
        self.assertEqual(parse_existing_slot("🇯🇵 ❇️✨️Key日本_1"), 1)
        self.assertEqual(parse_existing_slot("🇺🇸 ❇️✨️Fast美国_12_USAI"), 12)
        self.assertEqual(parse_existing_slot("🇭🇰 香港_3_Lnd"), 3)


class TestRendererGroupingSync(unittest.TestCase):
    """测试分组规则同步与落地节点链式跳板绑定"""

    def test_front_and_fast_groups_with_keys(self):
        proxies = [
            {"name": "🇯🇵 ❇️✨️Key日本_1", "type": "trojan", "_is_key": True, "_key_score": 42.0},
            {"name": "🇭🇰 ❇️Key香港_1", "type": "vmess", "_is_key": True, "_key_score": 39.0},
            {"name": "🇺🇸 ❇️✨️Fast美国_1", "type": "http", "_is_fast": True},
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
        self.assertIn("🇯🇵 ❇️✨️Key日本_1", front_members)
        self.assertIn("🇭🇰 ❇️Key香港_1", front_members)
        self.assertNotIn("🇺🇸 ❇️美国_2_Lnd", front_members)

        # 2. 验证 ⚡ Fast自动选择 仅对 Key 优质跳板执行 url-test
        fast_members = groups["⚡ Fast自动选择"]["proxies"]
        self.assertIn("🇯🇵 ❇️✨️Key日本_1", fast_members)
        self.assertIn("🇭🇰 ❇️Key香港_1", fast_members)
        self.assertNotIn("🇺🇸 ❇️✨️Fast美国_1", fast_members)
        self.assertNotIn("🇺🇸 ❇️美国_2_Lnd", fast_members)

        # 3. 验证落地节点自动注入 dialer-proxy: 🛡️ Front前置
        clean_proxies = {p["name"]: p for p in cfg["proxies"]}
        self.assertEqual(clean_proxies["🇺🇸 ❇️美国_2_Lnd"].get("dialer-proxy"), "🛡️ Front前置")
        self.assertNotIn("dialer-proxy", clean_proxies["🇯🇵 ❇️✨️Key日本_1"])


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
