# -*- coding: utf-8 -*-
import os, sys, time
from contextlib import ExitStack
sys.path.insert(0, os.path.abspath("scripts"))
from core import mihomo_runner, singbox_runner
from core.traffic_monitor import TrafficMonitor

good_sb = {"type": "direct"}
bad_sb = {"type": "vless", "server": "example.com", "server_port": 443, "uuid": "00000000-0000-0000-0000-000000000001", "bogus_field": 1}
t0 = time.monotonic()
with ExitStack() as stack:
    mon = TrafficMonitor()
    ports, failed = singbox_runner.start_singbox_group(
        stack, [("a", good_sb, None), ("bad", bad_sb, None), ("b", good_sb, None)], monitor=mon, shard_size=8)
    print("sing-box ports", sorted(ports), "failed", {k: v[:160] for k, v in failed.items()}, round(time.monotonic() - t0, 1), "s")

good_mh = {"name": "g", "type": "direct"}
bad_mh = {"name": "x", "type": "no-such-type", "server": "example.com", "port": 443}
t0 = time.monotonic()
with ExitStack() as stack:
    ports, failed = mihomo_runner.start_node_group(
        stack, [("a", good_mh, None), ("bad", bad_mh, None), ("b", good_mh, None)], monitor=TrafficMonitor(), shard_size=8)
    print("mihomo ports", sorted(ports), "failed", {k: v[:160] for k, v in failed.items()}, round(time.monotonic() - t0, 1), "s")
