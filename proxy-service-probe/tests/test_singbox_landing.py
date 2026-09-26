# -*- coding: utf-8 -*-
"""
sing-box 内核适配器的行为测试: 测试监听配置 (前置链、物理直连中继)、真实内核启动、被拒节点隔离与流量统计。
流水线层面的落地节点多前置备用、测活/服务/测速行为与 mihomo 共用 core.probe_flow，见 test_pipeline_flow。
"""
import os
import sys
import threading
import time
import unittest
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core.liveness import check_alive
from core.singbox_runner import SingboxKernel, _listener_config, apply_physical_relay, find_singbox_bin
from core.traffic_monitor import TrafficMonitor

TROJAN = {"type": "trojan", "tag": "jp", "server": "jp.example.com", "server_port": 443, "password": "x",
          "tls": {"enabled": True, "server_name": "jp.example.com"}, "detour": "stale-group"}
FRONT = {"type": "vless", "tag": "front", "server": "front.example.com", "server_port": 443,
         "uuid": "00000000-0000-0000-0000-000000000001", "tls": {"enabled": True, "server_name": "front.example.com"}}
# sing-box 严格解码配置，未知字段在启动时即被拒绝 (常见于新版客户端导出的私有扩展字段)
REJECTED = {"type": "vless", "tag": "bad", "server": "bad.example.com", "server_port": 443,
            "uuid": "00000000-0000-0000-0000-000000000002", "private_extension": 1}


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


class TestListenerConfig(unittest.TestCase):
    def test_each_node_gets_own_inbound_and_chains_share_one_front(self):
        keys = ["jp", ("us", 0), ("sg", 0)]
        config, ports = _listener_config([(keys[0], TROJAN, None), (keys[1], dict(TROJAN, tag="us"), FRONT),
                                          (keys[2], dict(TROJAN, tag="sg"), FRONT)])
        outs = {o["tag"]: o for o in config["outbounds"]}
        fronts = [tag for tag in outs if tag.startswith("front_")]
        self.assertEqual(len(fronts), 1)
        # 直连节点剥离输入里残留的 detour；经前置的节点 detour 指向同一个前置出站
        self.assertNotIn("detour", outs["node_0"])
        self.assertEqual((outs["node_1"]["detour"], outs["node_2"]["detour"]), (fronts[0], fronts[0]))
        self.assertEqual(TROJAN["detour"], "stale-group")  # 不改动调用方的节点配置
        rules = {rule["inbound"][0]: rule["outbound"] for rule in config["route"]["rules"]}
        for idx, key in enumerate(keys):
            inbound = config["inbounds"][idx]
            self.assertEqual((inbound["listen"], inbound["listen_port"]), ("127.0.0.1", ports[key]))
            self.assertEqual(rules[inbound["tag"]], f"node_{idx}")
        self.assertEqual(len(set(ports.values())), len(keys))

    def test_relay_carries_nodes_and_fronts_but_not_chained_nodes(self):
        config, _ = _listener_config([("jp", TROJAN, None), ("us", dict(TROJAN, tag="us"), FRONT)],
                                     relay=("127.0.0.1", 40001))
        detours = {o["tag"]: o.get("detour") for o in config["outbounds"]}
        self.assertEqual(detours["node_0"], "physical-relay")
        self.assertEqual(detours["front_0"], "physical-relay")
        self.assertEqual(detours["node_1"], "front_0")


class LocalTarget(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


class TestRealKernel(unittest.TestCase):
    """用技能自带 sing-box 内核实际启动测试监听 (无内核时跳过)。"""

    @classmethod
    def setUpClass(cls):
        cls.binary = find_singbox_bin()
        if not cls.binary:
            raise unittest.SkipTest("未找到 sing-box 内核")

    def test_rejected_node_is_isolated_and_others_serve_traffic(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalTarget)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        target = f"http://127.0.0.1:{server.server_address[1]}/generate_204"
        direct = {"type": "direct", "tag": "direct"}
        entries = [("a", direct, None), ("bad", REJECTED, None), ("b", direct, None), (("jp", 0), TROJAN, FRONT)]
        monitor = TrafficMonitor()
        try:
            with ExitStack() as stack:
                stack.callback(monitor.stop)
                # 中继地址无需真实监听：启动阶段只校验配置与出站依赖 (detour 链)
                ports, failed = SingboxKernel(self.binary, relay=("127.0.0.1", 9)).start(
                    stack, entries, monitor=monitor, shard_size=8)
                self.assertEqual(sorted(map(str, ports)), sorted(map(str, ["a", "b", ("jp", 0)])))
                self.assertIn("sing-box 启动失败", failed["bad"])
                self.assertIn("private_extension", failed["bad"])
                result = check_alive(f"http://127.0.0.1:{ports['a']}", targets=(target,), attempts=1, pause=0)
                self.assertTrue(result["alive"], result)
                deadline = time.monotonic() + 5
                while not monitor.available and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(monitor.available, "未收到 sing-box Clash API 的 /traffic 流量样本")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
