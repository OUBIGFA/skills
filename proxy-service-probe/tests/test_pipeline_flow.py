# -*- coding: utf-8 -*-
"""新流程 (测活 -> 服务检测线 ∥ 测速线 -> 汇总) 的行为测试。"""
import copy
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
                raise mihomo_runner.MihomoStartError("Parse config error")
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


# ---------------- 端到端流程 ----------------
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
EXIT_IP = {"jp1": "1.0.0.1", "jp2": "1.0.0.2", "us1": "1.0.0.3", "sg1": "1.0.0.5", "kr1": "1.0.0.6"}
SPEED_PLAN = {
    "jp1": [{"verdict": "qualified", "stable_mbps": 30.0, "floor_mbps": 25.0}],
    "jp2": [{"verdict": "drop", "stable_mbps": 2.0, "floor_mbps": 1.0}],
    "us1": [{"verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}],
    "sg1": [{"verdict": "drop", "stable_mbps": 3.0, "floor_mbps": 1.0, "contention": {"contended": True}},
            {"verdict": "qualified", "stable_mbps": 25.0, "floor_mbps": 20.0}],
    "kr1": [{"verdict": "keep", "stable_mbps": 9.0, "floor_mbps": 7.0}],
}


class TestEndToEndFlow(unittest.TestCase):
    def setUp(self):
        import importlib
        self.module = importlib.import_module("probe_services")
        self.speed = copy.deepcopy(SPEED_PLAN)
        self.port_owner = {}
        self.events = []
        self.lock = threading.Lock()

    def fake_group(self, stack, entries, **kwargs):
        ports = {}
        for key, proxy, front in entries:
            port = 50000 + len(self.port_owner)
            self.port_owner[port] = (proxy["server"], front["server"] if front else None)
            ports[key] = port
        return ports, {}

    def owner(self, url):
        return self.port_owner[int(str(url).rsplit(":", 1)[1])]

    def fake_alive(self, url, **kwargs):
        self.alive_calls = getattr(self, "alive_calls", 0) + 1
        server, front = self.owner(url)
        if server == "kr1" and front is None:
            self.kr1_direct = getattr(self, "kr1_direct", 0) + 1
            alive = self.kr1_direct > 1
        else:
            alive = server in ("jp1", "jp2", "sg1") or (server == "us1" and front is not None)
        return {"alive": alive, "latency_ms": 90.0 if alive else None, "attempts": []}

    def fake_egress(self, proxies=None, *args, **kwargs):
        ip = EXIT_IP[self.owner(proxies["http"])[0]]
        return {"ipv4": {"ip": ip}, "ipv6": {"ip": None}, "observed_ips": [ip]}

    def fake_geo(self, proxies, egress=None, **kwargs):
        server = self.owner(proxies["http"])[0]
        cc = {"jp1": "JP", "jp2": "JP", "us1": "US", "sg1": "SG", "kr1": "KR"}[server]
        return {"cc": cc, "exit_ip": EXIT_IP[server], "egress": egress, "google_region": {}, "ip_info": {},
                "ip_info_by_ip": {}, "geo_decision": {"egress_stable": True, "is_pool": False}}

    def fake_measure(self, proxy_url, targets=None, **options):
        server, front = self.owner(proxy_url)
        with self.lock:
            self.events.append(("speed", server, front))
            measured = dict(self.speed[server].pop(0))
        measured.update(status="complete", sample_mbps=[measured["stable_mbps"]] * 10, started_monotonic=time.monotonic())
        return measured

    def run_main(self, extra=()):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(self.module, "load_proxies", return_value=[dict(p) for p in NODES]), \
                patch.object(self.module, "find_mihomo_bin", return_value="kernel"), \
                patch.object(self.module, "start_node_group", self.fake_group), \
                patch.object(self.module, "check_alive", side_effect=self.fake_alive), \
                patch("core.liveness.check_alive", side_effect=self.fake_alive), \
                patch.object(self.module, "probe_runner_baseline", return_value={RUNNER_IP}), \
                patch.object(self.module, "probe_egress", side_effect=self.fake_egress), \
                patch.object(self.module, "probe_geolocation", side_effect=self.fake_geo), \
                patch("core.speed_probe.measure_node_speed", side_effect=self.fake_measure), \
                patch.object(self.module, "assess_contention",
                             side_effect=lambda measured, *a, **k: measured.get("contention") or {"contended": False}), \
                patch("builtins.print"):
            report = Path(temp) / "report.json"
            code = self.module.main(["--input", "dummy", "--tests", "ip", "--speed-test", "--profile", "local",
                                     "--report", str(report), *extra])
            return code, json.loads(report.read_text(encoding="utf-8"))

    def test_full_flow(self):
        code, report = self.run_main()
        self.assertEqual(code, 0)
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

    def test_cloud_profile_skips_chain_liveness(self):
        code, report = self.run_main(["--profile", "ci"])
        dropped = {e["name"]: e["reason"] for e in report["eliminated"]}
        self.assertIn("云端", dropped["🇺🇸 美国_1_Lnd"])
        self.assertNotIn(("speed", "us1", "jp1"), self.events)

    def test_checkpoint_resume_reuses_finished_nodes(self):
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = str(Path(temp) / "ckpt.json")
            _, first = self.run_main(["--checkpoint", checkpoint])
            self.speed = copy.deepcopy(SPEED_PLAN)
            self.events.clear()
            self.alive_calls = 0
            code, second = self.run_main(["--checkpoint", checkpoint])
        self.assertEqual(code, 0)
        self.assertEqual((self.events, self.alive_calls), ([], 0))
        self.assertEqual(sorted(r["orig_name"] for r in first["results"]),
                         sorted(r["orig_name"] for r in second["results"]))
        self.assertEqual({e["name"] for e in first["eliminated"]}, {e["name"] for e in second["eliminated"]})


if __name__ == "__main__":
    unittest.main()
