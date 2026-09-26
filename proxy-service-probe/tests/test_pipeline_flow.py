# -*- coding: utf-8 -*-
"""新流程 (测活 -> 服务检测线 ∥ 测速线 -> 汇总) 的行为测试。"""
import copy
import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import requests

from core import liveness, mihomo_runner
from core.pipeline import SERVICE, SPEED, DualLineScheduler, Job
from core.speed_probe import default_criteria, measure_with_retry
from core.traffic_monitor import TrafficMonitor, assess_contention


class TestScheduler(unittest.TestCase):
    def run_jobs(self, service_jobs, speed_jobs, service_workers=2, speed_workers=1):
        sched = DualLineScheduler(service_workers, speed_workers)
        sched.open_producer(SERVICE, SPEED)
        sched.start()
        for job in service_jobs:
            sched.add(SERVICE, job)
        for job in speed_jobs:
            sched.add(SPEED, job)
        sched.close_producer(SERVICE, SPEED)
        sched.join()
        return sched

    def recorder(self, log, name, node, seconds=0.05):
        def run():
            log.append((name, "start", time.monotonic()))
            time.sleep(seconds)
            log.append((name, "end", time.monotonic()))
        return Job(run, {node}, name=name)

    def spans(self, log):
        spans = {}
        for name, kind, when in log:
            spans.setdefault(name, {})[kind] = when
        return spans

    def test_same_node_never_serviced_and_speed_tested_at_once(self):
        log = []
        nodes = ["a", "b", "c"]
        self.run_jobs([self.recorder(log, f"svc-{n}", n) for n in nodes],
                      [self.recorder(log, f"spd-{n}", n) for n in nodes], service_workers=3)
        spans = self.spans(log)
        for n in nodes:
            svc, spd = spans[f"svc-{n}"], spans[f"spd-{n}"]
            self.assertTrue(svc["end"] <= spd["start"] or spd["end"] <= svc["start"], n)

    def test_speed_line_is_not_starved_by_service_workers(self):
        # 4 个节点、4 个服务工作线程：服务线不能把节点全部占住，测速线应立即拿到第一个节点
        log = []
        nodes = ["a", "b", "c", "d"]
        self.run_jobs([self.recorder(log, f"svc-{n}", n, 0.2) for n in nodes],
                      [self.recorder(log, f"spd-{n}", n, 0.02) for n in nodes], service_workers=4)
        spans = self.spans(log)
        first_speed = min(spans[f"spd-{n}"]["start"] for n in nodes)
        first_service_end = min(spans[f"svc-{n}"]["end"] for n in nodes)
        self.assertLess(first_speed, first_service_end)

    def test_quiet_job_waits_for_service_line(self):
        log = []
        sched = DualLineScheduler(1, 1)
        sched.open_producer(SERVICE, SPEED)
        sched.start()
        sched.add(SPEED, Job(lambda: log.append(("quiet", sched.service_finished())), {"x"}, quiet=True))
        sched.add(SERVICE, self.recorder(log, "svc", "y", 0.1))
        sched.close_producer(SERVICE, SPEED)
        sched.join()
        self.assertEqual([entry[:2] for entry in log], [("svc", "start"), ("svc", "end"), ("quiet", True)])

    def test_workers_wait_for_open_producer(self):
        done = []
        sched = DualLineScheduler(1, 1)
        sched.open_producer(SPEED)
        sched.start()
        time.sleep(0.05)
        sched.add(SPEED, Job(lambda: done.append("late"), {"n"}))
        sched.close_producer(SPEED)
        sched.join()
        self.assertEqual(done, ["late"])

    def test_job_exception_does_not_stop_line(self):
        done = []

        def boom():
            raise RuntimeError("x")
        jobs = [Job(boom, {"a"}), Job(lambda: done.append(1), {"b"})]
        self.run_jobs(jobs, [], service_workers=1)
        self.assertEqual(done, [1])
        self.assertIn("RuntimeError", jobs[0].error)


class TestTrafficMonitor(unittest.TestCase):
    def monitor_with(self, per_second_mbps, start=100.0):
        monitor = TrafficMonitor()
        for i, mbps in enumerate(per_second_mbps):
            monitor.add_sample(start + i + 1, mbps * 125_000)
        return monitor

    def test_buckets_align_with_seconds(self):
        monitor = self.monitor_with([10, 20, 30])
        self.assertAlmostEqual(monitor.total_mbps(101, 102), 20.0)
        self.assertAlmostEqual(monitor.total_mbps(100.5, 101.5), 15.0)
        self.assertIsNone(monitor.total_mbps(200, 201))
        self.assertAlmostEqual(monitor.capacity_mbps(), 25.0)

    def measured(self, rates, start=100.0):
        return {"sample_mbps": rates, "started_monotonic": start}

    def test_saturated_link_with_heavy_background_is_contended(self):
        # 测速 5 Mbps + 服务检测 50 Mbps，链路容量约 58
        monitor = self.monitor_with([58] * 4 + [55] * 8)
        result = assess_contention(self.measured([5.0] * 12), monitor, capacity_floor=40)
        self.assertTrue(result["contended"])
        self.assertGreater(result["background_mbps"], 40)

    def test_slow_node_with_light_background_is_not_contended(self):
        monitor = self.monitor_with([58, 58] + [8] * 10)   # 此前观测到容量 58，本次测速期间总计仅 8
        result = assess_contention(self.measured([3.0] * 10, start=102.0), monitor, capacity_floor=40)
        self.assertFalse(result["contended"])

    def test_missing_traffic_falls_back_to_service_activity(self):
        busy = assess_contention(self.measured([3.0] * 10), TrafficMonitor(), 40, service_busy=lambda s, e: True)
        idle = assess_contention(self.measured([3.0] * 10), TrafficMonitor(), 40, service_busy=lambda s, e: False)
        self.assertEqual((busy["method"], busy["contended"]), ("activity", True))
        self.assertFalse(idle["contended"])


class TestDeferredSpeed(unittest.TestCase):
    OPTIONS = {"rate_limit_mbps": 40, "criteria": default_criteria()}

    def results(self, *measurements):
        calls = iter(measurements)
        return patch("core.speed_probe.measure_node_speed", side_effect=lambda *a, **k: dict(next(calls)))

    def test_contended_non_qualified_result_is_deferred_without_immediate_retry(self):
        keep = {"verdict": "keep", "status": "complete", "stable_mbps": 11.0, "floor_mbps": 7.0}
        with self.results(keep) as fake:
            measured, deferred = measure_with_retry("http://p", self.OPTIONS, assess=lambda m: {"contended": True})
        self.assertTrue(deferred)
        self.assertEqual(fake.call_count, 1)
        self.assertTrue(measured["contention"]["contended"])

    def test_contended_but_qualified_result_is_accepted(self):
        good = {"verdict": "qualified", "status": "complete", "stable_mbps": 20.0, "floor_mbps": 15.0}
        with self.results(good):
            measured, deferred = measure_with_retry("http://p", self.OPTIONS, assess=lambda m: {"contended": True})
        self.assertFalse(deferred)
        self.assertEqual(measured["verdict"], "qualified")

    def test_clean_near_threshold_result_still_retries_once(self):
        near = {"verdict": "keep", "status": "complete", "stable_mbps": 11.0, "floor_mbps": 7.0}
        good = {"verdict": "qualified", "status": "complete", "stable_mbps": 14.0, "floor_mbps": 9.0}
        with self.results(near, good) as fake:
            measured, deferred = measure_with_retry("http://p", self.OPTIONS, assess=lambda m: {"contended": False})
        self.assertFalse(deferred)
        self.assertEqual(fake.call_count, 2)
        self.assertEqual(measured["verdict"], "qualified")


class FakeResponse:
    def __init__(self, status):
        self.status_code = status
        self.content = b""


class TestLiveness(unittest.TestCase):
    def fake_get(self, outcomes, calls):
        def get(session, url, **kwargs):
            calls.append(url)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(outcome)
        return get

    def test_dead_only_after_all_attempts_fail_on_rotating_targets(self):
        calls = []
        outcomes = [requests.ConnectionError(), requests.Timeout(), requests.ConnectionError()]
        with patch.object(requests.Session, "get", self.fake_get(outcomes, calls)):
            result = liveness.check_alive("http://p", pause=0)
        self.assertFalse(result["alive"])
        self.assertEqual(calls, list(liveness.LIVENESS_TARGETS))

    def test_single_success_after_failures_is_alive_and_warm_request_reuses_target(self):
        calls = []
        outcomes = [requests.ConnectionError(), 503, 204, 204]
        with patch.object(requests.Session, "get", self.fake_get(outcomes, calls)):
            result = liveness.check_alive("http://p", pause=0)
        self.assertTrue(result["alive"])
        self.assertEqual(calls[2], calls[3])
        self.assertEqual(len(calls), 4)

    def test_first_passing_front_wins_without_waiting_for_failing_fronts(self):
        def fake_check(url, **kwargs):
            if url.endswith(":1"):
                time.sleep(0.5)
                return {"alive": False, "latency_ms": None, "attempts": []}
            return {"alive": True, "latency_ms": 60.0, "attempts": []}
        started = time.monotonic()
        with patch.object(liveness, "check_alive", side_effect=fake_check):
            best, results = liveness.check_alive_via_fronts({"slow-dead": 1, "ok": 2})
        self.assertEqual(best, "ok")
        self.assertLess(time.monotonic() - started, 0.4)

    def test_all_fronts_failing_means_unreachable(self):
        with patch.object(liveness, "check_alive", return_value={"alive": False, "latency_ms": None, "attempts": []}):
            self.assertEqual(liveness.check_alive_via_fronts({"a": 1, "b": 2})[0], None)
        self.assertEqual(liveness.check_alive_via_fronts({}), (None, {}))

    def test_chain_fronts_dedupe_servers_and_prefer_udp_for_udp_nodes(self):
        def row(name, server, latency, proto="trojan", udp=False, **extra):
            proxy = {"name": name, "type": proto, "server": server, "port": 443, "udp": udp, **extra}
            return {"proxy": proxy, "liveness": {"latency_ms": latency}}
        rows = [row("a", "s1", 30), row("a-dup", "s1", 20), row("b", "s2", 40, udp=True), row("c", "s3", 50, udp=True),
                row("http", "s4", 10, proto="http"), row("lnd", "s5", 10, **{"dialer-proxy": "x"})]
        tuic = {"name": "t", "type": "tuic"}
        self.assertEqual([r["proxy"]["name"] for r in liveness.rank_chain_fronts(rows, tuic)], ["b", "c", "a-dup"])
        self.assertEqual([r["proxy"]["name"] for r in liveness.rank_chain_fronts(rows, {"type": "trojan"}, limit=2)],
                         ["a-dup", "b"])


class TestNodeGroupIsolation(unittest.TestCase):
    def test_rejected_node_is_isolated_without_failing_the_group(self):
        started = []

        @contextmanager
        def fake_run(binary, config, ports, monitor=None):
            names = {p["name"]: p for p in config["proxies"]}
            if any(p.get("server") == "bad" for p in names.values()):
                raise mihomo_runner.KernelStartError("Parse config error")
            started.append(len(ports))
            yield

        entries = [(i, {"name": f"n{i}", "type": "ss", "server": "bad" if i == 5 else "ok", "port": 1}, None)
                   for i in range(8)]
        with patch.object(mihomo_runner, "_run_mihomo", fake_run), \
                patch.object(mihomo_runner, "find_mihomo_bin", return_value="kernel"), \
                patch.object(mihomo_runner, "detect_physical_interface", return_value=None), ExitStack() as stack:
            ports, failed = mihomo_runner.start_node_group(stack, entries, shard_size=8)
        self.assertEqual(sorted(failed), [5])
        self.assertEqual(sorted(ports), [0, 1, 2, 3, 4, 6, 7])
        self.assertEqual(sum(started), 7)

    def test_chain_entries_load_each_front_once(self):
        front = {"name": "f", "type": "vless", "server": "f", "port": 443}
        entries = [(("a", 0), {"name": "a", "type": "tuic", "server": "a", "port": 1}, front),
                   (("b", 0), {"name": "b", "type": "tuic", "server": "b", "port": 1}, front)]
        config, ports = mihomo_runner._listener_config(entries, None)
        fronts = [p for p in config["proxies"] if p["name"].startswith("front_")]
        self.assertEqual(len(fronts), 1)
        self.assertTrue(all(p.get("dialer-proxy") == fronts[0]["name"]
                            for p in config["proxies"] if p["name"].startswith("node_")))
        self.assertEqual(len(set(ports.values())), 2)

    def test_real_mihomo_isolates_rejected_node(self):
        binary = mihomo_runner.find_mihomo_bin()
        if not binary:
            self.skipTest("未找到 mihomo 内核")
        entries = [("a", {"name": "a", "type": "direct"}, None),
                   ("bad", {"name": "bad", "type": "no-such-type", "server": "x", "port": 1}, None),
                   ("b", {"name": "b", "type": "direct"}, None)]
        monitor = TrafficMonitor()
        with ExitStack() as stack:
            stack.callback(monitor.stop)
            ports, failed = mihomo_runner.start_node_group(stack, entries, mihomo_bin=binary, monitor=monitor,
                                                           shard_size=8)
            self.assertEqual(sorted(ports), ["a", "b"])
            self.assertIn("unsupport proxy type", failed["bad"])
            self.assertTrue(all(mihomo_runner.wait_port_open(port, timeout=1) for port in ports.values()))


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
        # 真实属地判定沿用传入的出口证据，出口 IP 与 fake_egress 一致
        server, front = self.owner(proxies["http"])
        return {"cc": CC[server], "exit_ip": self.exit_for(server, front), "egress": egress, "google_region": {},
                "ip_info": {}, "ip_info_by_ip": {}, "geo_decision": {"egress_stable": True, "is_pool": False}}

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
                exported = {"yaml": output.read_text(encoding="utf-8")} if output.exists() else {}
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
                exported = ({"json": json.loads(output.read_text(encoding="utf-8")),
                             "yaml": output.with_suffix(".yaml").read_text(encoding="utf-8")} if output.exists() else {})
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


class TestFlowResilience(FlowHarness):
    """实跑发现的前置依赖与不完整结果不能假成功，两种内核使用同一验收。"""
    FAST = {"verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}

    def each_kernel(self):
        for kernel in ("mihomo", "sing-box"):
            self.setUp()
            yield kernel

    def test_landing_is_not_exported_when_its_only_capable_front_is_dropped(self):
        self.NODES = [NODES[0], FRONTED_NODES[-1], dict(NODES[4], type="http")]
        self.SPEED_PLAN = {"jp1": [{"verdict": "drop", "stable_mbps": 2.0, "floor_mbps": 1.0}],
                           "sg1": [self.FAST]}
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, exported = self.run_flow(kernel)
                self.assertEqual(code, 0)
                self.assertEqual([r["orig_name"] for r in report["results"]], ["🇸🇬 新加坡_1"])
                dropped = {e["name"]: e for e in report["eliminated"]}
                self.assertIn("无已验证且保留", dropped["🇺🇸 美国_1_Lnd"]["reason"])
                self.assertIn("无法为落地节点测速", dropped["🇺🇸 美国_1_Lnd"]["speed_note"])
                self.assertNotIn("美国_1_Lnd", exported["yaml"])

    def test_landing_waits_for_only_front_quiet_retest(self):
        self.NODES = [NODES[0], FRONTED_NODES[-1]]
        self.SPEED_PLAN = {"jp1": [{"verdict": "drop", "stable_mbps": 3.0, "floor_mbps": 1.0,
                                    "contention": {"contended": True}}, self.FAST], "us1": [self.FAST]}
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, _ = self.run_flow(kernel)
                self.assertEqual(code, 0)
                rows = {r["orig_name"]: r for r in report["results"]}
                self.assertIn("quiet_retest", rows["🇯🇵 日本_1"]["speed_result"])
                self.assertTrue(rows["🇺🇸 美国_1_Lnd"]["speed_final"])
                self.assertEqual(rows["🇺🇸 美国_1_Lnd"]["speed_front_node"], "🇯🇵 日本_1")

    def test_landing_waits_for_front_exit_evidence(self):
        self.NODES = [NODES[0], FRONTED_NODES[-1]]
        self.SPEED_PLAN = {"jp1": [self.FAST], "us1": [self.FAST]}
        original_egress = self.fake_egress

        def slow_egress(proxies, **kwargs):
            if self.owner(proxies["http"])[0] == "jp1":
                time.sleep(0.15)
            return original_egress(proxies, **kwargs)
        self.fake_egress = slow_egress
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, _ = self.run_flow(kernel)
                self.assertEqual(code, 0)
                landing = next(r for r in report["results"] if r["is_landing"])
                self.assertTrue(landing["speed_final"])
                self.assertEqual(landing["speed_front_node"], "🇯🇵 日本_1")

    def test_unmarked_front_only_node_never_becomes_key(self):
        self.NODES = [NODES[0], {k: v for k, v in dict(FRONTED_NODES[-1], name="🏳️ 未知_1").items()
                                if k != "dialer-proxy"}]
        self.SPEED_PLAN = {"jp1": [self.FAST], "us1": [dict(self.FAST, stable_mbps=40.0)]}
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, exported = self.run_flow(kernel)
                self.assertEqual(code, 0)
                landing = next(r for r in report["results"] if r["orig_name"] == "🏳️ 未知_1")
                self.assertEqual((landing["path"], landing["is_landing"], landing["is_key"]), ("front", True, False))
                self.assertNotIn("Key", landing["final_name"])
                import yaml
                groups = {g["name"]: g for g in yaml.safe_load(exported["yaml"])["proxy-groups"]}
                self.assertNotIn(landing["final_name"], groups["🛡️ Front前置"]["proxies"])
                if "json" in exported:
                    groups = {g["tag"]: g for g in exported["json"]["outbounds"]}
                    self.assertNotIn(landing["final_name"], groups["🛡️ Front前置"]["outbounds"])

    def test_all_dead_run_writes_report_without_export(self):
        self.NODES = [NODES[3]]
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, exported = self.run_flow(kernel)
                self.assertEqual(code, 1)
                self.assertEqual(exported, {})
                self.assertEqual((report["qualified_count"], report["eliminated_count"]), (0, 1))
                self.assertFalse(report["eliminated"][0]["alive"])

    def test_failed_speed_task_cannot_be_exported_as_qualified(self):
        self.NODES = [NODES[0]]

        def fail_measure(*args, **kwargs):
            raise RuntimeError("measurement failed")
        self.fake_measure = fail_measure
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel):
                code, report, exported = self.run_flow(kernel)
                self.assertEqual(code, 1)
                self.assertEqual(exported, {})
                self.assertIn("测速失败", report["eliminated"][0]["reason"])

    def test_unhandled_worker_exception_cannot_silently_pass(self):
        self.NODES = [NODES[0]]
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel), \
                    patch("core.probe_flow.measure_with_retry", side_effect=RuntimeError("unexpected worker error")):
                code, report, exported = self.run_flow(kernel)
                self.assertEqual(code, 1)
                self.assertEqual(exported, {})
                self.assertIn("检测任务未完成", report["eliminated"][0]["reason"])

    def test_service_report_keeps_browser_and_api_evidence(self):
        self.NODES = [NODES[0]]
        self.SPEED_PLAN = {"jp1": [self.FAST]}
        youtube = {"status": "failed", "reason": "browser_egress_unverified", "samples": [], "passed_count": 0}
        shield = {name: {"status": "passed"} for name in ("cloudflare", "chatgpt", "claude", "gemini")}
        ai = {"ai_supported": True, "details": {"openai": True, "claude": True, "gemini": True},
              "observations": {"openai": {"status": 200}}}
        for kernel in self.each_kernel():
            with self.subTest(kernel=kernel), \
                    patch("core.probe_flow.probe_youtube", return_value=youtube), \
                    patch("core.probe_flow.probe_all_ai", return_value=ai), \
                    patch("core.probe_flow.probe_all_media", return_value={"media_supported": False, "details": {}}), \
                    patch("core.probe_flow.probe_sites_http", return_value=shield), \
                    patch("core.probe_flow.probe_sites_browser", return_value=shield):
                code, report, _ = self.run_flow(kernel, extra=["--tests", "all"])
                self.assertEqual(code, 0)
                row = report["results"][0]
                self.assertEqual(row["youtube_details"], youtube)
                self.assertEqual(row["shield_details"], shield)
                self.assertEqual(row["ai_observations"], ai["observations"])
                self.assertFalse(row["youtube_passed"])
                self.assertTrue(report["test_dimensions"]["browser_shield"])
                self.assertEqual(report["pipeline"]["service_workers"], 4)
                self.assertEqual(report["pipeline"]["speed_workers"], 1)


if __name__ == "__main__":
    unittest.main()
