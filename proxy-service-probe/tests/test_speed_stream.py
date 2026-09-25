# -*- coding: utf-8 -*-
"""持续下载测速 (内存流式、稳态窗口判定、防突发、带宽上限、目标回退、贴近门槛重测) 与运行环境 Profile 的行为测试。

测速用例经真实 HTTP 代理路径执行：本地服务同时充当代理，requests 以绝对 URI 向它发起 GET，
由服务端按场景控制下发速率。为缩短用时，网络用例把观测窗口缩小到秒级 (判定逻辑与默认参数相同)。
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from core import speed_probe
from core.speed_probe import (default_criteria, measure_download_sustained, measure_node_speed,
                              measure_rows_speed, speed_qualified, steady_stats, steady_verdict)
from core.run_profile import PROFILES, apply_profile, detect_profile, validate_speed_options
from core import mihomo_runner

CHUNK = 16 * 1024
MBPS = 125_000  # bytes/s

# 用户节点 "美国_11" 的真实逐秒曲线 (直连新建连接，YouTube 实测可流畅播放 4K、连接速度约 15 Mbps)
US11_DIRECT = [1.311, 2.49, 2.49, 3.801, 4.981, 2.053, 6.966, 8.845, 7.826, 8.738,
               8.607, 12.146, 7.602, 10.093, 10.617, 6.27, 15.37, 19.386, 10.486, 15.991]


def _rate_schedule(path):
    """按路径返回 (秒 -> 下发速率 bytes/s) 的场景；None 表示不限速。"""
    if path.endswith("/steady"):
        return lambda t: 16 * MBPS                             # 16 Mbps 稳定
    if path.endswith("/burst"):
        return lambda t: None if t < 1.5 else 2 * MBPS         # 先突发，1.5 秒后限到 2 Mbps
    if path.endswith("/slow"):
        return lambda t: 2 * MBPS                              # 2 Mbps
    return lambda t: None                                      # 不限速


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.endswith("/html"):
            body = b"<html>captive portal</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        schedule = _rate_schedule(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        started = time.monotonic()
        payload = b"\0" * CHUNK
        try:
            while time.monotonic() - started < 15:
                self.wfile.write(payload)
                rate = schedule(time.monotonic() - started)
                if rate:
                    time.sleep(CHUNK / rate)
        except (ConnectionError, OSError):
            pass


# 缩小的观测参数：至少 4 秒、最多 6 秒、稳态窗口取最后 3 秒
FAST_CRITERIA = {"window_seconds": 3, "min_observe_seconds": 4, "max_observe_seconds": 6,
                 "min_stable_mbps": 12.0, "min_floor_mbps": 6.0, "drop_below_mbps": 6.0}


class TestSustainedDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.proxy = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def measure(self, path, **options):
        options.setdefault("criteria", FAST_CRITERIA)
        options.setdefault("rate_limit_mbps", 0)
        return measure_download_sustained(f"http://speed.test{path}", self.proxy, **options)

    def test_steady_node_qualifies_after_min_observe(self):
        result = self.measure("/steady")
        self.assertEqual((result["status"], result["verdict"]), ("complete", "qualified"), result)
        self.assertTrue(speed_qualified(result))
        self.assertAlmostEqual(result["stable_mbps"], 16.0, delta=3.0)
        self.assertEqual(result["observed_seconds"], 4)
        self.assertIsNotNone(result["ttfb_ms"])

    def test_burst_then_throttle_is_dropped(self):
        # 开头突发的秒数不在稳态窗口内：限速后的 2 Mbps 决定结论
        result = self.measure("/burst")
        self.assertEqual(result["verdict"], "drop", result)
        self.assertFalse(speed_qualified(result))
        self.assertGreater(result["peak_mbps"], 50)
        self.assertLess(result["stable_mbps"], 4)

    def test_rate_cap_bounds_measurement_and_marks_capped(self):
        result = self.measure("/fast", rate_limit_mbps=20.0)
        self.assertEqual(result["verdict"], "qualified", result)
        self.assertLessEqual(result["stable_mbps"], 21.0)
        self.assertTrue(result["capped"])

    def test_html_target_falls_back_to_next_target(self):
        base = "http://speed.test"
        result = measure_node_speed(self.proxy, [f"{base}/html", f"{base}/steady"],
                                    criteria=FAST_CRITERIA, rate_limit_mbps=0)
        self.assertEqual(result["target"], f"{base}/steady")
        self.assertEqual(result["failed_targets"][0]["status"], "invalid_response")

    def test_slow_target_is_final_without_target_shopping(self):
        # 已开始传输的慢目标即为定论，不换下一个目标凑高速
        base = "http://speed.test"
        result = measure_node_speed(self.proxy, [f"{base}/slow", f"{base}/fast"],
                                    criteria=FAST_CRITERIA, rate_limit_mbps=0)
        self.assertEqual(result["target"], f"{base}/slow")
        self.assertEqual(result["verdict"], "drop")
        self.assertNotIn("failed_targets", result)

    def test_rows_stage_marks_drop_and_qualified(self):
        rows = [{}, {}]
        options = {"rate_limit_mbps": 0, "criteria": FAST_CRITERIA}
        measure_rows_speed([(self.proxy, rows[0])], options, targets=["http://speed.test/steady"])
        measure_rows_speed([(self.proxy, rows[1])], options, targets=["http://speed.test/slow"])
        self.assertTrue(rows[0]["is_fast"])
        self.assertIsNone(rows[0]["speed_drop"])
        self.assertFalse(rows[1]["is_fast"])
        self.assertIn("低于淘汰线", rows[1]["speed_drop"])


class TestSteadyVerdict(unittest.TestCase):
    criteria = default_criteria()

    def first_verdict(self, rates):
        for n in range(1, len(rates) + 1):
            decided = steady_verdict(rates[:n], self.criteria)
            if decided:
                return n, decided[0]
        return None

    def test_real_slow_ramp_node_qualifies(self):
        # 用户实测可流畅播放 4K 的节点：新建连接 19 秒才爬到稳态，应判 Key/Fast 级
        self.assertEqual(self.first_verdict(US11_DIRECT), (19, "qualified"))

    def test_fast_node_decided_at_min_observe(self):
        self.assertEqual(self.first_verdict([5, 12, 15, 16, 16, 15, 16, 17, 16, 15]), (10, "qualified"))

    def test_burst_then_throttle_dropped(self):
        n, verdict = self.first_verdict([40] * 7 + [3] * 13)
        self.assertEqual(verdict, "drop")
        self.assertLess(n, 20)

    def test_gradual_throttle_is_not_accepted_early(self):
        # 用户节点 "美国_4" 实测曲线：40 -> 11 Mbps 逐秒下滑 (慢慢限速型)，不能在第 10 秒就判达标
        declining = [6.77, 34.014, 39.572, 40.434, 40.13, 32.232, 26.298, 21.669, 14.242, 11.27]
        self.assertIsNone(steady_verdict(declining, self.criteria))
        n, verdict = self.first_verdict(declining + [9.0] * 10)
        self.assertEqual(verdict, "keep")
        self.assertLessEqual(n, 20)

    def test_clearly_slow_node_dropped_early(self):
        self.assertEqual(self.first_verdict([2.0] * 20), (10, "drop"))

    def test_near_threshold_node_is_observed_to_the_end(self):
        # 贴近淘汰线 (5 Mbps，未低于其 75%)：不提前删除，观测到上限再定
        self.assertEqual(self.first_verdict([5.0] * 20), (20, "drop"))
        self.assertEqual(self.first_verdict([9.0] * 20), (20, "keep"))

    def test_isolated_spike_cannot_lift_steady_speed(self):
        stable, _ = steady_stats([10] * 10 + [10, 10, 10, 10, 10, 40])
        self.assertLess(stable, 12)
        self.assertEqual(steady_verdict([10] * 15 + [40], self.criteria), None)

    def test_single_dip_tolerated_sustained_dip_rejected(self):
        one_dip = [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 3, 15, 15, 15, 15]
        stable, floor = steady_stats(one_dip)
        self.assertGreaterEqual(floor, 6)
        two_dip = [15] * 10 + [15, 3, 3, 15, 15, 15]
        stable, floor = steady_stats(two_dip)
        self.assertLess(floor, 6)

    def test_qualified_requires_complete_status(self):
        good = {"status": "complete", "stable_mbps": 15.0, "floor_mbps": 9.0}
        self.assertTrue(speed_qualified(good))
        self.assertFalse(speed_qualified({**good, "status": "stalled"}))
        self.assertFalse(speed_qualified({**good, "floor_mbps": 4.0}))
        self.assertFalse(speed_qualified({**good, "stable_mbps": 10.0}))


class TestRetryNearThreshold(unittest.TestCase):
    def run_rows(self, outcomes):
        calls = iter(outcomes)
        row = {}
        with patch.object(speed_probe, "measure_node_speed", side_effect=lambda *a, **k: dict(next(calls))):
            measure_rows_speed([("http://p", row)], {"rate_limit_mbps": 0, "criteria": default_criteria()})
        return row

    def test_near_miss_is_remeasured_and_best_kept(self):
        near = {"status": "complete", "verdict": "drop", "stable_mbps": 5.9, "floor_mbps": 5.3}
        good = {"status": "complete", "verdict": "qualified", "stable_mbps": 13.0, "floor_mbps": 8.0}
        row = self.run_rows([near, good])
        self.assertTrue(row["is_fast"])
        self.assertIsNone(row["speed_drop"])
        self.assertEqual([a["verdict"] for a in row["speed_result"]["attempts"]], ["drop", "qualified"])

    def test_clearly_slow_is_not_remeasured(self):
        slow = {"status": "complete", "verdict": "drop", "stable_mbps": 1.0, "floor_mbps": 0.5}
        row = self.run_rows([slow])
        self.assertNotIn("attempts", row["speed_result"])
        self.assertIsNotNone(row["speed_drop"])

    def test_qualified_is_not_remeasured(self):
        good = {"status": "complete", "verdict": "qualified", "stable_mbps": 20.0, "floor_mbps": 15.0}
        row = self.run_rows([good])
        self.assertNotIn("attempts", row["speed_result"])


class TestRunProfile(unittest.TestCase):
    def args(self, **overrides):
        values = {"profile": "auto", "rate_limit_mbps": None, "speed_concurrency": None, "min_speed_mbps": 12.0,
                  "speed_duration": 20.0, "drop_below_mbps": 6.0}
        values.update(overrides)
        return Namespace(**values)

    def test_auto_detects_github_actions(self):
        self.assertEqual(detect_profile({"GITHUB_ACTIONS": "true"}), "ci")
        self.assertEqual(detect_profile({"CI": "true"}), "ci")
        self.assertEqual(detect_profile({}), "local")

    def test_profile_fills_only_unset_values(self):
        args = self.args(speed_concurrency=3)
        name, _ = apply_profile(args, environ={"GITHUB_ACTIONS": "true"})
        self.assertEqual(name, "ci")
        self.assertEqual(args.rate_limit_mbps, PROFILES["ci"]["rate_limit_mbps"])
        self.assertEqual(args.speed_concurrency, 3)

        local = self.args(profile="local")
        apply_profile(local, environ={"GITHUB_ACTIONS": "true"})
        self.assertEqual(local.speed_concurrency, 1)

    def test_profile_caps_are_above_default_threshold(self):
        for name, settings in PROFILES.items():
            self.assertGreater(settings["rate_limit_mbps"], default_criteria()["min_stable_mbps"], name)

    def test_invalid_speed_options_are_rejected(self):
        ok = dict(rate_limit_mbps=40.0, speed_concurrency=1)
        self.assertIsNone(validate_speed_options(self.args(**ok)))
        self.assertIsNotNone(validate_speed_options(self.args(**{**ok, "rate_limit_mbps": 10.0})))
        self.assertIsNotNone(validate_speed_options(self.args(**{**ok, "rate_limit_mbps": 0})))
        self.assertIsNotNone(validate_speed_options(self.args(**{**ok, "rate_limit_mbps": 500})))
        self.assertIsNotNone(validate_speed_options(self.args(**{**ok, "speed_duration": 6.0})))
        self.assertIsNotNone(validate_speed_options(self.args(**{**ok, "drop_below_mbps": 20.0})))


class TestKernelLookup(unittest.TestCase):
    def test_bundled_kernel_found_from_any_working_directory(self):
        bundled = os.path.join(mihomo_runner.SKILL_CORE_DIR, "mihomo.exe" if sys.platform == "win32" else "mihomo")
        if not os.path.isfile(bundled):
            self.skipTest("本平台未附带 mihomo 内核")
        environ = {k: v for k, v in os.environ.items() if k != "MIHOMO_BIN"}
        with tempfile.TemporaryDirectory() as cwd, patch.dict(os.environ, environ, clear=True), \
                patch.object(mihomo_runner.shutil, "which", return_value=None):
            previous = os.getcwd()
            os.chdir(cwd)
            try:
                self.assertEqual(mihomo_runner.find_mihomo_bin(), os.path.abspath(bundled))
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
