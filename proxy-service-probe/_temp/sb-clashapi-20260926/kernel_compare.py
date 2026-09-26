# -*- coding: utf-8 -*-
"""同一批节点经 mihomo 与 sing-box 真实内核各测活一次，保留 sing-box info 日志，定位差异。"""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
sys.path.insert(0, os.path.abspath("scripts"))
from probe_singbox import load_singbox_nodes
from core import mihomo_runner, singbox_runner
from core.liveness import check_alive

HERE = os.path.abspath("_temp/sb-clashapi-20260926")
_, proxies, _ = load_singbox_nodes(r"D:\Data\Desktop\_scratch\test.json")
names = [p["name"] for p in proxies]

def alive(port):
    r = check_alive(f"http://127.0.0.1:{port}", attempts=2, pause=0.2)
    return "OK %.0fms" % r["latency_ms"] if r["alive"] else "DEAD " + ",".join(a.get("error", "?") for a in r["attempts"])

with ExitStack() as stack:
    clash = [{k: v for k, v in p.items() if not k.startswith("_")} for p in proxies]
    mports, mfailed = mihomo_runner.start_node_group(stack, [(i, c, None) for i, c in enumerate(clash)], shard_size=64)
    config, sports = singbox_runner._listener_config([(i, p["_singbox_outbound"], None) for i, p in enumerate(proxies)])
    config["log"] = {"level": "info", "timestamp": False}
    cfg = os.path.join(HERE, "cmp_singbox.json")
    json.dump(config, open(cfg, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log = open(os.path.join(HERE, "cmp_singbox.log"), "wb")
    proc = subprocess.Popen([singbox_runner.find_singbox_bin(), "run", "--disable-color", "-c", cfg], stdout=log, stderr=subprocess.STDOUT)
    stack.callback(lambda: (proc.kill(), proc.wait(5), log.close()))
    print("sing-box ready", mihomo_runner.wait_port_open(list(sports.values())[-1], 8, proc), "mihomo failed", mfailed)
    with ThreadPoolExecutor(24) as pool:
        mres = {i: pool.submit(alive, p) for i, p in mports.items()}
        sres = {i: pool.submit(alive, p) for i, p in sports.items()}
        for i, n in enumerate(names):
            print(f"{n:28} mihomo={mres[i].result() if i in mres else 'N/A':38} sing-box={sres[i].result()}")
