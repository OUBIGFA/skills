# -*- coding: utf-8 -*-
"""跑机出口基线的回归测试：本机客户端经 TUN/系统代理正在使用某节点时，该节点不能被误判为"出口与本机重合"。"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PHYSICAL_IP = "120.235.204.83"   # 物理网卡直连 (运营商) 出口
IN_USE_IP = "104.243.23.105"     # 本机客户端 TUN 正在使用的节点出口 = 系统路由出口
BASELINE_PORT = 40001
ALIVE = {"alive": True, "latency_ms": 80.0, "attempts": []}


def egress(ip):
    return {"ipv4": {"ip": ip}, "ipv6": {"ip": None}, "observed_ips": [ip] if ip else []}


def fake_probe_egress(proxies=None, *args, **kwargs):
    """系统路由被 TUN 接管 -> 正在使用的节点出口；物理直连监听 -> 运营商出口；节点监听 -> 节点自身出口。"""
    if proxies is None:
        return egress(IN_USE_IP)
    if proxies["http"].endswith(f":{BASELINE_PORT}"):
        return egress(PHYSICAL_IP)
    return egress(IN_USE_IP)


@contextmanager
def fake_direct_listener(iface=None, mihomo_bin=None):
    yield BASELINE_PORT


class TestRunnerBaseline(unittest.TestCase):
    def setUp(self):
        self.flow = importlib.import_module("core.probe_flow")

    def baseline(self, direct_proxy=None, listener=fake_direct_listener):
        args = Namespace(direct_proxy=direct_proxy, iface=None)
        with patch.object(self.flow, "direct_listener", listener), \
                patch.object(self.flow, "probe_egress", side_effect=fake_probe_egress), \
                patch("builtins.print"):
            return self.flow.probe_runner_baseline(args, "kernel")

    def test_baseline_uses_physical_direct_not_tun_route(self):
        self.assertEqual(self.baseline(), {PHYSICAL_IP})

    def test_explicit_direct_proxy_wins(self):
        self.assertEqual(self.baseline(direct_proxy="http://127.0.0.1:24999"), {IN_USE_IP})

    def test_failed_physical_baseline_disables_overlap_elimination(self):
        @contextmanager
        def broken(iface=None, mihomo_bin=None):
            raise RuntimeError("listener failed")
            yield  # pragma: no cover

        self.assertEqual(self.baseline(listener=broken), set())

    def test_singbox_physical_relay_does_not_depend_on_echo_ip_comparison(self):
        module = importlib.import_module("probe_singbox")
        with patch.object(module, "detect_physical_interface", return_value="WLAN"), \
                patch.object(module, "direct_listener", fake_direct_listener), \
                patch("builtins.print"), ExitStack() as stack:
            self.assertEqual(module.start_physical_relay(stack, Namespace(iface=None), "kernel"),
                             ("127.0.0.1", BASELINE_PORT))

    def test_failed_singbox_relay_must_not_fall_back_through_tun(self):
        module = importlib.import_module("probe_singbox")
        with patch.object(module, "direct_listener", side_effect=RuntimeError("cannot bind interface")), \
                ExitStack() as stack, self.assertRaisesRegex(RuntimeError, "拒绝改走"):
            module.start_physical_relay(stack, Namespace(iface="WLAN"), "kernel")

    def test_node_in_use_by_local_client_is_tested_not_eliminated(self):
        # 两条流水线共用同一基线逻辑，mihomo 与 sing-box 入口都不能误删本机正在使用的节点
        node = {"name": "🇺🇸 ❇️♥️美国_11_D+", "type": "vless", "server": "1.2.3.4", "port": 443,
                "uuid": "00000000-0000-0000-0000-000000000001"}
        geo = {"cc": "US", "exit_ip": IN_USE_IP, "google_region": {}, "ip_info": {}, "ip_info_by_ip": {},
               "geo_decision": {"egress_stable": True, "is_pool": False}}

        def listeners(stack, entries, **kwargs):
            return {key: 40002 for key, _, _ in entries}, {}

        for kernel in ("mihomo", "sing-box"):
            with self.subTest(kernel=kernel), tempfile.TemporaryDirectory() as temp, \
                    patch.object(self.flow, "check_alive", return_value=ALIVE), \
                    patch.object(self.flow, "direct_listener", fake_direct_listener), \
                    patch.object(self.flow, "probe_egress", side_effect=fake_probe_egress), \
                    patch.object(self.flow, "probe_geolocation", return_value=geo), \
                    patch("builtins.print"):
                report = Path(temp) / "report.json"
                argv = ["--tests", "ip", "--report", str(report)]
                if kernel == "mihomo":
                    module = importlib.import_module("probe_services")
                    with patch.object(module, "load_proxies", return_value=[dict(node)]), \
                            patch.object(module, "find_mihomo_bin", return_value="kernel"), \
                            patch("core.mihomo_runner.start_node_group", listeners):
                        self.assertEqual(module.main(["--input", "dummy", *argv]), 0)
                else:
                    module = importlib.import_module("probe_singbox")
                    source = Path(temp) / "in.json"
                    source.write_text(json.dumps({"outbounds": [
                        {"type": "vless", "tag": node["name"], "server": node["server"], "server_port": node["port"],
                         "uuid": node["uuid"]}]}, ensure_ascii=False), encoding="utf-8")
                    with patch.object(module, "find_singbox_bin", return_value="sing-box"), \
                            patch.object(module, "find_mihomo_bin", return_value="kernel"), \
                            patch.object(module, "start_physical_relay", return_value=None), \
                            patch("core.singbox_runner.start_singbox_group", listeners), \
                            patch("core.singbox_runner.find_singbox_bin", return_value=None):
                        output = Path(temp) / "out.json"
                        self.assertEqual(module.main(["--input", str(source), "--output", str(output), *argv]), 0)
                saved = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(saved["eliminated"], [])
                self.assertEqual(saved["results"][0]["exit_ip"], IN_USE_IP)


if __name__ == "__main__":
    unittest.main()
