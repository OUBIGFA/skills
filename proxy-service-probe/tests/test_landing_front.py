# -*- coding: utf-8 -*-
"""需前置节点 (落地) 的前置遴选与配置前置池渲染的行为测试。"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core.key_evaluator import is_front_capable, pick_front_nodes, select_key_nodes
from core.renderer import render_clash_config
from core.speed_probe import FRONT_FALLBACK_TIER

FOUR_K = {"status": "complete", "verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}
HD = {"status": "complete", "verdict": "keep", "stable_mbps": 8.0, "floor_mbps": 6.5}
SLOW = {"status": "complete", "verdict": "drop", "stable_mbps": 4.0, "floor_mbps": 3.0}


def row(name, proto="trojan", speed=None, cc="JP", **extra):
    proxy = {"name": name, "type": proto, "server": "1.1.1.1", "port": 443}
    proxy.update(extra)
    return {"proxy": proxy, "orig_name": name, "cc": cc, "exit_ip": "9.9.9.9", "speed_result": speed, "delay": 80.0}


class TestPickFrontNodes(unittest.TestCase):
    def test_key_is_preferred_over_faster_fallback(self):
        rows = [row("hd", speed=HD), row("k4", speed=FOUR_K)]
        select_key_nodes(rows)
        fronts, kind = pick_front_nodes(rows, FRONT_FALLBACK_TIER)
        self.assertEqual(kind, "key")
        self.assertEqual(fronts[0]["orig_name"], "k4")

    def test_falls_back_to_kept_front_when_no_key(self):
        rows = [row("slow", speed=SLOW), row("hd", speed=HD), row("socks-hd", proto="socks5", speed=HD),
                row("lnd-hd", speed=HD, **{"dialer-proxy": "x"})]
        select_key_nodes(rows)
        fronts, kind = pick_front_nodes(rows, FRONT_FALLBACK_TIER)
        self.assertEqual(kind, "fallback")
        self.assertEqual([r["orig_name"] for r in fronts], ["hd"])

    def test_no_front_when_nothing_kept(self):
        rows = [row("slow", speed=SLOW), row("none", speed=None)]
        select_key_nodes(rows)
        self.assertEqual(pick_front_nodes(rows, FRONT_FALLBACK_TIER), ([], None))

    def test_front_capability_ignores_speed(self):
        self.assertTrue(is_front_capable({"name": "a", "type": "ss"}))
        self.assertFalse(is_front_capable({"name": "a", "type": "http"}))
        self.assertFalse(is_front_capable({"name": "a_Lnd", "type": "ss"}))


class TestFallbackFrontRendering(unittest.TestCase):
    def test_landing_nodes_default_to_fallback_front(self):
        proxies = [
            {"name": "🇯🇵 日本_1", "type": "trojan", "server": "a", "port": 443, "_front_fallback": True},
            {"name": "🇯🇵 日本_2", "type": "trojan", "server": "b", "port": 443},
            {"name": "🇺🇸 美国_1_Lnd", "type": "ss", "server": "c", "port": 8388},
        ]
        cfg = render_clash_config(proxies)
        groups = {g["name"]: g for g in cfg["proxy-groups"]}
        self.assertEqual(groups["⚡ Fast自动选择"]["proxies"], ["🇯🇵 日本_1"])
        self.assertIn("🇯🇵 日本_1", groups["🛡️ Front前置"]["proxies"])
        self.assertNotIn("🇯🇵 日本_2", groups["🛡️ Front前置"]["proxies"])
        landing = next(p for p in cfg["proxies"] if p["name"].endswith("_Lnd"))
        self.assertEqual(landing["dialer-proxy"], "🛡️ Front前置")
        self.assertFalse(any(k.startswith("_") for p in cfg["proxies"] for k in p))

    def test_key_nodes_still_take_precedence(self):
        proxies = [
            {"name": "🇯🇵 Key日本_1", "type": "trojan", "server": "a", "port": 443},
            {"name": "🇯🇵 日本_2", "type": "trojan", "server": "b", "port": 443, "_front_fallback": True},
        ]
        groups = {g["name"]: g for g in render_clash_config(proxies)["proxy-groups"]}
        self.assertEqual(groups["⚡ Fast自动选择"]["proxies"], ["🇯🇵 Key日本_1"])


if __name__ == "__main__":
    unittest.main()
