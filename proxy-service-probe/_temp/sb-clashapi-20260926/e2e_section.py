# ---------------- 端到端流程 (mihomo 与 sing-box 两条流水线同一套场景) ----------------
RUNNER_IP = "120.0.0.1"
NODES = [
    {"name": "🇯🇵 日本_1", "type": "trojan", "server": "jp1", "port": 443, "udp": True},   # 快 -> Key
    {"name": "🇯🇵 日本_2", "type": "trojan", "server": "jp2", "port": 443},                # 慢 -> 测速淘汰
    {"name": "🇺🇸 美国_1_Lnd", "type": "tuic", "server": "us1", "port": 8080,
     "dialer-proxy": "🛡️ Front前置"},                                                       # 直连不通、经前置通
    {"name": "🇭🇰 香港_9", "type": "vless", "server": "198.51.100.1", "port": 443},       # 假节点
    {"name": "🇸🇬 新加坡_1", "type": "trojan", "server": "sg1", "port": 443},             # 首测受干扰 -> 空闲重测达标
    {"name": "🇰🇷 韩国_1", "type": "hysteria2", "server": "kr1", "port": 443},           # 首轮被并发误伤 -> 复测通过
]
EXIT_IP = {"jp1": "1.0.0.1", "jp2": "1.0.0.2", "us1": "1.0.0.3", "sg1": "1.0.0.5", "kr1": "1.0.0.6", "hk1": "1.0.0.7"}
CC = {"jp1": "JP", "jp2": "JP", "us1": "US", "sg1": "SG", "kr1": "KR", "hk1": "HK"}
SPEED_PLAN = {
    "jp1": [{"verdict": "qualified", "stable_mbps": 30.0, "floor_mbps": 25.0}],
    "jp2": [{"verdict": "drop", "stable_mbps": 2.0, "floor_mbps": 1.0}],
    "us1": [{"verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}],
    "sg1": [{"verdict": "drop", "stable_mbps": 3.0, "floor_mbps": 1.0, "contention": {"contended": True}},
            {"verdict": "qualified", "stable_mbps": 25.0, "floor_mbps": 20.0}],
    "kr1": [{"verdict": "keep", "stable_mbps": 9.0, "floor_mbps": 7.0}],
}
UNREACHABLE = {"verdict": "drop", "stable_mbps": None, "floor_mbps": None, "reason": "ProxyError: 前置到节点不通"}


def to_singbox(node):
    """把用例中的 Clash 节点写成等价的 sing-box 出站 (dialer-proxy 对应 detour)。"""
    out = {"type": node["type"], "tag": node["name"], "server": node["server"], "server_port": node["port"]}
    if node["type"] in ("trojan", "hysteria2"):
        out["password"] = "secret"
    else:
        out["uuid"] = "00000000-0000-0000-0000-000000000001"
    if node["type"] == "trojan":
        out["tls"] = {"enabled": True, "server_name": node["server"]}
    if node.get("dialer-proxy"):
        out["detour"] = node["dialer-proxy"]
    return out


class FlowHarness(unittest.TestCase):
    """
    端到端夹具：本地监听端口映射到 (节点服务器, 前置服务器)，测活、出口、属地与测速按场景模拟。
    同一场景分别经 probe_services (mihomo) 与 probe_singbox (sing-box) 入口运行，两条流水线应得出相同结论。
    """
    NODES = NODES
    SPEED_PLAN = SPEED_PLAN

    def setUp(self):
        self.speed = copy.deepcopy(self.SPEED_PLAN)
        self.port_owner = {}
        self.events = []
        self.lock = threading.Lock()
        self.alive_calls = 0
        self.probes = {}

    # ---- 场景 (子类可覆盖) ----
    def is_alive(self, server, front, attempt):
        """attempt: 同一 (节点, 前置) 的第几次测活。"""
        if server == "kr1" and front is None:
            return attempt > 1  # 首轮高并发下被误伤，低并发复测通过
        return server in ("jp1", "jp2", "sg1") or (server == "us1" and front is not None)

    def exit_for(self, server, front):
        return EXIT_IP[server]

    # ---- 模拟 ----
    def fake_group(self, stack, entries, **kwargs):
        ports = {}
        with self.lock:
            for key, node, front in entries:
                port = 50000 + len(self.port_owner)
                self.port_owner[port] = (node["server"], front["server"] if front else None)
                ports[key] = port
        return ports, {}

    def owner(self, url):
        return self.port_owner[int(str(url).rsplit(":", 1)[1])]

    def fake_alive(self, url, **kwargs):
        with self.lock:
            self.alive_calls += 1
            server, front = self.owner(url)
            self.probes[(server, front)] = attempt = self.probes.get((server, front), 0) + 1
        alive = self.is_alive(server, front, attempt)
        return {"alive": alive, "latency_ms": 90.0 if alive else None, "attempts": []}

    def fake_egress(self, proxies=None, *args, **kwargs):
        ip = self.exit_for(*self.owner(proxies["http"]))
        return {"ipv4": {"ip": ip}, "ipv6": {"ip": None}, "observed_ips": [ip] if ip else []}

    def fake_geo(self, proxies, egress=None, **kwargs):
        server = self.owner(proxies["http"])[0]
        return {"cc": CC[server], "exit_ip": EXIT_IP[server], "egress": egress, "google_region": {}, "ip_info": {},
                "ip_info_by_ip": {}, "geo_decision": {"egress_stable": True, "is_pool": False}}

    def fake_measure(self, proxy_url, targets=None, **options):
        server, front = self.owner(proxy_url)
        with self.lock:
            self.events.append(("speed", server, front))
            plan = self.speed[(server, front)] if (server, front) in self.speed else self.speed[server]
            measured = dict(plan.pop(0))
        if measured["stable_mbps"] is None:
            measured.update(status="transfer_error", sample_mbps=[], started_monotonic=None, bytes_received=0)
        else:
            measured.update(status="complete", sample_mbps=[measured["stable_mbps"]] * 10,
                            started_monotonic=time.monotonic())
        return measured

    def shared_patches(self, stack):
        for target, fake in (("core.probe_flow.check_alive", self.fake_alive),
                             ("core.liveness.check_alive", self.fake_alive),
                             ("core.probe_flow.probe_egress", self.fake_egress),
                             ("core.probe_flow.probe_geolocation", self.fake_geo),
                             ("core.speed_probe.measure_node_speed", self.fake_measure)):
            stack.enter_context(patch(target, side_effect=fake))
        stack.enter_context(patch("core.probe_flow.probe_runner_baseline", return_value={RUNNER_IP}))
        stack.enter_context(patch("core.probe_flow.assess_contention",
                                  side_effect=lambda measured, *a, **k: measured.get("contention") or {"contended": False}))
        stack.enter_context(patch("builtins.print"))

    def run_flow(self, kernel, extra=(), speed=True):
        """以指定入口 (mihomo / sing-box) 运行完整流程，返回 (退出码, 报告, 导出的配置内容)。"""
        flags = ["--tests", "ip", "--profile", "local", *(["--speed-test"] if speed else []), *extra]
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            self.shared_patches(stack)
            report = Path(temp) / "report.json"
            if kernel == "mihomo":
                module = importlib.import_module("probe_services")
                stack.enter_context(patch.object(module, "load_proxies",
                                                 return_value=[dict(p) for p in self.NODES]))
                stack.enter_context(patch.object(module, "find_mihomo_bin", return_value="kernel"))
                stack.enter_context(patch("core.mihomo_runner.start_node_group", self.fake_group))
                output = Path(temp) / "out.yaml"
                code = module.main(["--input", "dummy", "--output", str(output), "--report", str(report), *flags])
                exported = {"yaml": output.read_text(encoding="utf-8")}
            else:
                module = importlib.import_module("probe_singbox")
                source = Path(temp) / "in.json"
                source.write_text(json.dumps({"outbounds": [to_singbox(p) for p in self.NODES]}, ensure_ascii=False),
                                  encoding="utf-8")
                stack.enter_context(patch.object(module, "find_singbox_bin", return_value="sing-box"))
                stack.enter_context(patch.object(module, "find_mihomo_bin", return_value="kernel"))
                stack.enter_context(patch.object(module, "start_physical_relay", return_value=None))
                stack.enter_context(patch("core.singbox_runner.start_singbox_group", self.fake_group))
                stack.enter_context(patch("core.singbox_runner.find_singbox_bin", return_value=None))  # 导出时不跑内核校验
                output = Path(temp) / "out.json"
                code = module.main(["--input", str(source), "--output", str(output), "--report", str(report), *flags])
                exported = {"json": json.loads(output.read_text(encoding="utf-8")),
                            "yaml": output.with_suffix(".yaml").read_text(encoding="utf-8")}
            return code, json.loads(report.read_text(encoding="utf-8")), exported


class TestEndToEndFlow(FlowHarness):
    def check_full_flow(self, kernel):
        code, report, exported = self.run_flow(kernel)
        self.assertEqual(code, 0)
        self.assertEqual(report["kernel"], kernel)
        by_name = {r["orig_name"]: r for r in report["results"]}
        dropped = {e["name"]: e["reason"] for e in report["eliminated"]}

        # 假节点: 直连与经前置都不通 -> 淘汰；慢节点 -> 测速淘汰
        self.assertIn("均不可达", dropped["🇭🇰 香港_9"])
        self.assertIn("低于淘汰线", dropped["🇯🇵 日本_2"])
        # 直连不通、经前置测通的节点判为落地，且经前置完成服务检测与测速
        landing = by_name["🇺🇸 美国_1_Lnd"]
        self.assertEqual((landing["path"], landing["is_landing"]), ("front", True))
        self.assertIsNotNone(landing["speed_result"])
        self.assertIn(("speed", "us1", "jp1"), self.events)
        self.assertEqual(landing["speed_front_node"], "🇯🇵 日本_1")
        # 受干扰的慢结果不直接淘汰，链路空闲时重测达标
        sg = by_name["🇸🇬 新加坡_1"]
        self.assertTrue(sg["is_key"])
        self.assertIn("quiet_retest", sg["speed_result"])
        self.assertTrue(by_name["🇯🇵 日本_1"]["is_key"])
        # 首轮直连不通、低并发复测通过的节点按直连处理，不判落地
        kr = by_name["🇰🇷 韩国_1"]
        self.assertEqual((kr["path"], kr["is_landing"]), ("direct", False))
        self.assertFalse(kr["liveness"]["first_round"]["alive"])
        self.assertIn("lines_done", report["timeline_seconds"])
        # 统一导出: 落地节点在配置中经前置组链式出网
        self.assertIn("dialer-proxy: 🛡️ Front前置", exported["yaml"])
        return report, exported

    def test_full_flow_mihomo(self):
        self.check_full_flow("mihomo")

    def test_full_flow_singbox_matches_mihomo(self):
        report, exported = self.check_full_flow("sing-box")
        outbounds = {o["tag"]: o for o in exported["json"]["outbounds"]}
        landing = next(o for tag, o in outbounds.items() if tag.endswith("_Lnd"))
        self.assertEqual(landing["detour"], "🛡️ Front前置")
        self.assertNotIn("detour", next(o for tag, o in outbounds.items() if "Key日本" in tag))
        self.setUp()
        mihomo_report, _ = self.check_full_flow("mihomo")

        def verdicts(rep):
            return sorted((r["orig_name"], r["final_name"], r["path"], r["is_key"]) for r in rep["results"])
        self.assertEqual(verdicts(report), verdicts(mihomo_report))
        self.assertEqual({e["name"] for e in report["eliminated"]}, {e["name"] for e in mihomo_report["eliminated"]})

    def test_cloud_profile_skips_chain_liveness(self):
        for kernel in ("mihomo", "sing-box"):
            with self.subTest(kernel=kernel):
                self.setUp()
                code, report, _ = self.run_flow(kernel, ["--profile", "ci"])
                dropped = {e["name"]: e["reason"] for e in report["eliminated"]}
                self.assertIn("云端", dropped["🇺🇸 美国_1_Lnd"])
                self.assertNotIn(("speed", "us1", "jp1"), self.events)

    def test_checkpoint_resume_reuses_finished_nodes(self):
        for kernel in ("mihomo", "sing-box"):
            with self.subTest(kernel=kernel), tempfile.TemporaryDirectory() as temp:
                self.setUp()
                checkpoint = str(Path(temp) / "ckpt.json")
                _, first, _ = self.run_flow(kernel, ["--checkpoint", checkpoint])
                self.setUp()
                code, second, _ = self.run_flow(kernel, ["--checkpoint", checkpoint])
                self.assertEqual(code, 0)
                self.assertEqual((self.events, self.alive_calls), ([], 0))
                self.assertEqual(sorted(r["orig_name"] for r in first["results"]),
                                 sorted(r["orig_name"] for r in second["results"]))
                self.assertEqual({e["name"] for e in first["eliminated"]}, {e["name"] for e in second["eliminated"]})

    def test_checkpoint_from_other_kernel_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = str(Path(temp) / "ckpt.json")
            self.run_flow("mihomo", ["--checkpoint", checkpoint])
            self.setUp()
            self.run_flow("sing-box", ["--checkpoint", checkpoint])
        self.assertGreater(self.alive_calls, 0)
        self.assertIn(("speed", "jp1", None), self.events)


# 落地节点多前置备用: 三个快的直连节点均可作前置，落地节点只能经前置连通
FRONTED_NODES = [
    {"name": "🇯🇵 日本_1", "type": "trojan", "server": "jp1", "port": 443},
    {"name": "🇸🇬 新加坡_1", "type": "trojan", "server": "sg1", "port": 443},
    {"name": "🇭🇰 香港_1", "type": "trojan", "server": "hk1", "port": 443},
    {"name": "🇺🇸 美国_1_Lnd", "type": "trojan", "server": "us1", "port": 443, "dialer-proxy": "🛡️ Front前置"},
]
FRONTED_SPEED = {
    "jp1": [{"verdict": "qualified", "stable_mbps": 30.0, "floor_mbps": 25.0}],
    "sg1": [{"verdict": "qualified", "stable_mbps": 25.0, "floor_mbps": 20.0}],
    "hk1": [{"verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}],
}


class TestLandingFrontFallback(FlowHarness):
    """某个前置到落地节点不通时换下一个前置 (最多 3 个)，不因单个前置不兼容而误删落地节点。两条流水线行为一致。"""
    NODES = FRONTED_NODES
    SPEED_PLAN = FRONTED_SPEED

    def is_alive(self, server, front, attempt):
        if server != "us1":
            return True
        if front is None:
            return False
        if front != "jp1":
            time.sleep(0.3)  # 经日本_1 的测活先返回，首个服务检测前置即为日本_1
        return True

    def run_both(self, check, **kwargs):
        for kernel in ("mihomo", "sing-box"):
            with self.subTest(kernel=kernel):
                self.setUp()
                code, report, _ = self.run_flow(kernel, **kwargs)
                self.assertEqual(code, 0)
                check(report)

    @staticmethod
    def landing(report):
        return {r["orig_name"]: r for r in report["results"]}.get("🇺🇸 美国_1_Lnd")

    @staticmethod
    def drop_reason(report):
        return {e["name"]: e["reason"] for e in report["eliminated"]}.get("🇺🇸 美国_1_Lnd")

    def test_service_switches_front_when_first_front_cannot_reach_node(self):
        self.exit_for = lambda server, front: None if (server, front) == ("us1", "jp1") else EXIT_IP[server]

        def check(report):
            row = self.landing(report)
            self.assertIsNotNone(row, report["eliminated"])
            self.assertEqual((row["front_node"], row["exit_ip"]), ("🇸🇬 新加坡_1", EXIT_IP["us1"]))
            self.assertEqual([(a["stage"], a["front"]) for a in row["front_attempts"]], [("service", "🇯🇵 日本_1")])
        self.run_both(check, speed=False)

    def test_speed_switches_front_when_front_yields_no_samples(self):
        self.SPEED_PLAN = {**FRONTED_SPEED, ("us1", "jp1"): [UNREACHABLE, UNREACHABLE],
                           ("us1", "sg1"): [{"verdict": "qualified", "stable_mbps": 18.0, "floor_mbps": 12.0}]}

        def check(report):
            row = self.landing(report)
            self.assertIsNotNone(row, report["eliminated"])
            self.assertEqual(row["speed_front_node"], "🇸🇬 新加坡_1")
            self.assertEqual(row["speed_result"]["stable_mbps"], 18.0)
            self.assertEqual([(a["stage"], a["front"]) for a in row["front_attempts"]], [("speed", "🇯🇵 日本_1")])
            self.assertLess(self.events.index(("speed", "us1", "jp1")), self.events.index(("speed", "us1", "sg1")))
            self.assertNotIn(("speed", "us1", "hk1"), self.events)
            self.assertEqual([f["orig_name"] for f in report["landing_speed_fronts"]],
                             ["🇯🇵 日本_1", "🇸🇬 新加坡_1", "🇭🇰 香港_1"])
        self.run_both(check)

    def test_unreachable_through_all_fronts_including_key_is_eliminated(self):
        self.SPEED_PLAN = {**FRONTED_SPEED, **{("us1", f): [UNREACHABLE, UNREACHABLE] for f in ("jp1", "sg1", "hk1")}}

        def check(report):
            self.assertIsNone(self.landing(report))
            self.assertIn("均取不到测速样本", self.drop_reason(report))
            self.assertEqual(sum(1 for e in self.events if e[1] == "us1"), 6)  # 3 个前置，各含一次无样本重测
        self.run_both(check)

    def test_unreachable_through_non_key_fronts_is_only_noted(self):
        keep = {"verdict": "keep", "stable_mbps": 8.0, "floor_mbps": 6.5}
        self.SPEED_PLAN = {"jp1": [keep, keep], "sg1": [keep, keep], "hk1": [keep, keep],
                           **{("us1", f): [UNREACHABLE, UNREACHABLE] for f in ("jp1", "sg1", "hk1")}}

        def check(report):
            row = self.landing(report)
            self.assertIsNotNone(row, report["eliminated"])
            self.assertIn("前置均未入选 Key", row["speed_note"])
            self.assertTrue(any(r["is_front_fallback"] for r in report["results"]))
        self.run_both(check)

    def test_slow_landing_behind_key_front_is_eliminated(self):
        self.SPEED_PLAN = {**FRONTED_SPEED, "us1": [{"verdict": "drop", "stable_mbps": 2.0, "floor_mbps": 1.0}]}

        def check(report):
            self.assertIsNone(self.landing(report))
            self.assertIn("低于淘汰线", self.drop_reason(report))
        self.run_both(check)

    def test_landing_exit_equal_to_front_exit_is_rejected(self):
        self.exit_for = lambda server, front: EXIT_IP["jp1"] if server == "us1" else EXIT_IP[server]

        def check(report):
            self.assertIn("出口与前置节点或本机出口重合", self.drop_reason(report))
        self.run_both(check, speed=False)


