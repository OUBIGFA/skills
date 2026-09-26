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
