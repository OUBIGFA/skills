# -*- coding: utf-8 -*-
"""sing-box 备用流水线的前置出站生成与"直连不可达 -> 经前置重测"遴选顺序的行为测试。"""
import os
import sys
import unittest
from argparse import Namespace
from contextlib import contextmanager
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import probe_singbox
from core.key_evaluator import select_key_nodes
from core.singbox_runner import apply_physical_relay, front_outbound, singbox_active_listeners

FOUR_K = {"status": "complete", "verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}
HD = {"status": "complete", "verdict": "keep", "stable_mbps": 8.0, "floor_mbps": 6.5}
CLIENT = {"address": ("127.0.0.1", 3067), "exit_ip": "7.7.7.7", "label": "本机客户端 127.0.0.1:3067"}


def direct_row(tag, speed, exit_ip):
    raw = {"type": "trojan", "tag": tag, "server": "1.1.1.1", "server_port": 443, "password": "x",
           "tls": {"enabled": True, "server_name": "a.example"}}
    row = {"raw_node": raw, "orig_name": tag, "is_landing": False, "exit_ip": exit_ip,
           "egress": {"observed_ips": [exit_ip]}, "speed_result": speed, "cc": "JP", "delay": 80.0}
    row["proxy"] = probe_singbox.parse_singbox_outbound(dict(raw))
    return row


def unreachable_row(tag):
    return {"raw_node": {"type": "socks", "tag": tag, "server": "landing.test", "server_port": 1080},
            "orig_name": tag, "eliminated_reason": "直连不可达", "direct_unreachable": True}


class TestFrontOutbound(unittest.TestCase):
    def test_node_front_keeps_protocol_and_drops_detour(self):
        out = front_outbound({"type": "shadowsocks", "tag": "k", "server": "s", "server_port": 1,
                              "method": "aes-128-gcm", "password": "p", "detour": "x"})
        self.assertEqual((out["type"], out["tag"]), ("shadowsocks", "front-anchor"))
        self.assertNotIn("detour", out)

    def test_client_port_front_is_socks(self):
        self.assertEqual(front_outbound(("127.0.0.1", 3067)),
                         {"type": "socks", "tag": "front-anchor", "server": "127.0.0.1", "server_port": 3067})
        self.assertIsNone(front_outbound(None))

    def test_landing_rows_require_a_front(self):
        with patch("core.singbox_runner.find_singbox_bin", return_value="sing-box"):
            with self.assertRaises(ValueError):
                with singbox_active_listeners([{"raw_node": {"type": "socks", "tag": "a", "server": "b",
                                                             "server_port": 1}, "is_landing": True}]):
                    pass


class TestPhysicalRelay(unittest.TestCase):
    def test_only_outbounds_leaving_the_machine_use_relay(self):
        outs = [{"type": "trojan", "tag": "node-0", "server": "1.1.1.1"},
                {"type": "vless", "tag": "front-anchor", "server": "2.2.2.2"},
                {"type": "socks", "tag": "node-1", "server": "landing.test", "detour": "front-anchor"},
                {"type": "socks", "tag": "client", "server": "127.0.0.1", "server_port": 3067}]
        apply_physical_relay(outs, ("127.0.0.1", 40001))
        detours = {o["tag"]: o.get("detour") for o in outs}
        self.assertEqual(detours["node-0"], "physical-relay")
        self.assertEqual(detours["front-anchor"], "physical-relay")
        self.assertEqual(detours["node-1"], "front-anchor")
        self.assertIsNone(detours["client"])
        self.assertEqual(outs[-1], {"type": "socks", "tag": "physical-relay", "server": "127.0.0.1",
                                    "server_port": 40001})

    def test_no_relay_leaves_outbounds_untouched(self):
        outs = [{"type": "trojan", "tag": "node-0", "server": "1.1.1.1"}]
        apply_physical_relay(outs, None)
        self.assertEqual(outs, [{"type": "trojan", "tag": "node-0", "server": "1.1.1.1"}])


class TestLandingStage(unittest.TestCase):
    def args(self, speed_test=True):
        return Namespace(speed_test=speed_test, no_landing_probe=False, singbox_bin=None, workers=4,
                         speed_target=None, speed_duration=20.0, rate_limit_mbps=40.0, min_speed_mbps=12.0,
                         min_floor_mbps=6.0, drop_below_mbps=6.0, speed_concurrency=1)

    def run_stage(self, qualified, args, client_front=None, landing_ip="5.5.5.5"):
        used_fronts = []

        @contextmanager
        def fake_listeners(rows, front_proxy=None, singbox_bin=None, relay=None):
            used_fronts.append(front_proxy)
            yield [{"result_ref": r, "proxy_url": f"http://127.0.0.1:{9000 + i}"} for i, r in enumerate(rows)]

        eliminated = [unreachable_row("lnd")]
        with patch.object(probe_singbox, "singbox_active_listeners", fake_listeners), \
                patch.object(probe_singbox, "fast_probe_ip", return_value=landing_ip), \
                patch.object(probe_singbox, "probe_path", side_effect=lambda res, proxies: res), \
                patch.object(probe_singbox, "measure_rows_speed"), \
                patch("builtins.print"):
            front, label = probe_singbox.run_landing_stage(qualified, eliminated, args, client_front)
        return front, label, eliminated, used_fronts

    def test_key_front_is_preferred_over_client_port(self):
        qualified = [direct_row("hd", HD, "2.2.2.2"), direct_row("k4", FOUR_K, "3.3.3.3")]
        select_key_nodes(qualified)
        front, label, eliminated, used = self.run_stage(qualified, self.args(), CLIENT)
        self.assertEqual(front["tag"], "k4")
        self.assertEqual(used, [front])
        landing = qualified[-1]
        self.assertEqual((landing["orig_name"], landing["is_landing"], landing["path"]), ("lnd", True, "front"))
        self.assertIn("k4", landing["front_node"])
        self.assertEqual(eliminated, [])

    def test_fallback_front_when_no_key(self):
        qualified = [direct_row("hd", HD, "2.2.2.2")]
        select_key_nodes(qualified)
        front, label, _, _ = self.run_stage(qualified, self.args(), CLIENT)
        self.assertEqual(front["tag"], "hd")
        self.assertIn("备用前置", label)
        self.assertTrue(qualified[0]["is_front_fallback"])

    def test_client_port_used_without_speed_test(self):
        qualified = [direct_row("hd", None, "2.2.2.2")]
        front, label, _, _ = self.run_stage(qualified, self.args(speed_test=False), CLIENT)
        self.assertEqual(front, ("127.0.0.1", 3067))

    def test_exit_equal_to_front_exit_is_rejected(self):
        qualified = [direct_row("k4", FOUR_K, "3.3.3.3")]
        select_key_nodes(qualified)
        _, _, eliminated, _ = self.run_stage(qualified, self.args(), landing_ip="3.3.3.3")
        self.assertEqual(len(qualified), 1)
        self.assertIn("出口与前置出口重合", eliminated[0]["eliminated_reason"])

    def test_speed_drop_applies_only_behind_key_front(self):
        slow = {"status": "complete", "verdict": "drop", "stable_mbps": 2.0, "floor_mbps": 1.0}

        def slow_speed(jobs, *args, **kwargs):
            for _, row in jobs:
                row.update(speed_result=slow, speed_drop="稳态速度 2.0Mbps 低于淘汰线", is_fast=False)

        for rows, dropped in (([direct_row("k4", FOUR_K, "3.3.3.3")], True), ([direct_row("hd", HD, "2.2.2.2")], False)):
            select_key_nodes(rows)
            with patch.object(probe_singbox, "measure_rows_speed", side_effect=slow_speed):
                eliminated = [unreachable_row("lnd")]

                @contextmanager
                def fake_listeners(chunk, front_proxy=None, singbox_bin=None, relay=None):
                    yield [{"result_ref": r, "proxy_url": "http://127.0.0.1:9000"} for r in chunk]

                with patch.object(probe_singbox, "singbox_active_listeners", fake_listeners),                         patch.object(probe_singbox, "fast_probe_ip", return_value="5.5.5.5"),                         patch.object(probe_singbox, "probe_path", side_effect=lambda res, proxies: res),                         patch("builtins.print"):
                    probe_singbox.run_landing_stage(rows, eliminated, self.args(), None)
            self.assertEqual(any(e["orig_name"] == "lnd" for e in eliminated), dropped)

    def test_no_front_keeps_node_eliminated_with_reason(self):
        qualified = [direct_row("slow", None, "2.2.2.2")]
        front, _, eliminated, used = self.run_stage(qualified, self.args(speed_test=False), None)
        self.assertIsNone(front)
        self.assertEqual(used, [])
        self.assertIn("未经前置验证", eliminated[0]["eliminated_reason"])


if __name__ == "__main__":
    unittest.main()
