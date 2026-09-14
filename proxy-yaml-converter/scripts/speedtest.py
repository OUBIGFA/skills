#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proxy Speedtest & Healthcheck:
Test proxy node connectivity and latency using a local temporary Mihomo/Clash-Meta core instance.
Supports physical network interface binding for genuine direct connection testing.
"""

import argparse
import json
import os
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import yaml


def find_available_port(start_port=19000, end_port=29000):
    """Find a free local TCP port."""
    for _ in range(50):
        port = random.randint(start_port, end_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return 19090


def find_mihomo_core(custom_path=None):
    """Locate mihomo / clash-meta core binary."""
    if custom_path and os.path.exists(custom_path):
        return custom_path

    # Check environment variable
    env_core = os.environ.get("MIHOMO_PATH") or os.environ.get("CLASH_META_PATH")
    if env_core and os.path.exists(env_core):
        return env_core

    # Common candidate paths on Windows
    candidates = [
        r"D:\Software\Clash Party\resources\sidecar\mihomo.exe",
        r"D:\Software\Clash Party\resources\sidecar\mihomo-alpha.exe",
        r"C:\Program Files\Clash Party\resources\sidecar\mihomo.exe",
        r"C:\Program Files\Clash Verge\resources\sidecar\mihomo.exe",
        r"C:\Program Files\Mihomo Party\resources\sidecar\mihomo.exe",
        r"D:\Program Files\Clash Party\resources\sidecar\mihomo.exe",
        r"D:\Program Files\Clash Verge\resources\sidecar\mihomo.exe",
    ]

    for c in candidates:
        if os.path.exists(c):
            return c

    # Search in PATH
    for name in ["mihomo.exe", "mihomo", "clash-meta.exe", "clash-meta"]:
        path = shutil.which(name) if 'shutil' in globals() else None
        if path:
            return path

    return None


def detect_physical_interface():
    """Detect active physical network adapter to bypass TUN/virtual adapters in direct mode."""
    if sys.platform != "win32":
        return None

    try:
        cmd = ["powershell", "-NoProfile", "-Command",
               "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'Virtual|Tunnel|Meta|wintun|VPN|Loopback|Hyper-V|VMware' } | Select-Object -ExpandProperty Name"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        adapters = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if adapters:
            # Prefer WLAN or Ethernet
            for a in adapters:
                if any(pref in a.lower() for pref in ["wlan", "wi-fi", "ethernet", "以太网"]):
                    return a
            return adapters[0]
    except Exception:
        pass
    return None


def run_speedtest(
    yaml_input,
    yaml_output=None,
    core_path=None,
    direct=True,
    interface_name=None,
    test_url="http://www.gstatic.com/generate_204",
    timeout_ms=3500,
    max_workers=16,
    retries=1,
    filter_alive=False,
    sort_by_delay=False,
    verbose=True
):
    """
    Test all proxies in yaml_input.
    Returns (alive_nodes, failed_nodes).
    """
    # Load input config
    if isinstance(yaml_input, (str, Path)):
        in_path = Path(yaml_input)
        if not in_path.exists():
            raise FileNotFoundError(f"Config file not found: {in_path}")
        with open(in_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    elif isinstance(yaml_input, dict):
        config_data = yaml_input
        in_path = None
    else:
        raise ValueError("yaml_input must be a file path or dict.")

    proxies = config_data.get("proxies", [])
    if not proxies:
        if verbose:
            print("No proxies found in configuration.")
        return [], []

    # Locate core
    core = find_mihomo_core(core_path)
    if not core:
        raise FileNotFoundError("Mihomo/Clash-Meta core executable not found. Please provide path via --core.")

    # Detect interface if direct requested
    if direct and not interface_name:
        interface_name = detect_physical_interface()

    # Allocate ports and temp dir
    api_port = find_available_port(19000, 20000)
    mixed_port = find_available_port(20001, 21000)
    secret = f"st_{random.randint(100000, 999999)}"

    temp_dir_obj = tempfile.TemporaryDirectory(prefix="proxy_st_")
    temp_dir = temp_dir_obj.name
    temp_cfg_path = os.path.join(temp_dir, "test_config.yaml")

    test_config = {
        "mixed-port": mixed_port,
        "external-controller": f"127.0.0.1:{api_port}",
        "secret": secret,
        "mode": "rule",
        "log-level": "silent",
        "ipv6": False,
        "dns": {
            "enable": True,
            "ipv6": False,
            "nameserver": ["223.5.5.5", "119.29.29.29"],
            "default-nameserver": ["223.5.5.5", "119.29.29.29"]
        },
        "proxies": proxies,
        "rules": ["MATCH,DIRECT"]
    }

    if direct and interface_name:
        test_config["interface-name"] = interface_name
        if verbose:
            print(f"[Direct Mode] Bound to physical network interface: {interface_name}")

    with open(temp_cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(test_config, f, allow_unicode=True, sort_keys=False)

    proc = subprocess.Popen(
        [core, "-d", temp_dir, "-f", temp_cfg_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if verbose:
        print(f"Started test core (PID: {proc.pid}) on API port {api_port}...")

    time.sleep(2.5)

    results = {}
    auth_header = {"Authorization": f"Bearer {secret}"}

    def test_single_node(p_name):
        encoded_name = urllib.parse.quote(p_name)
        api_url = f"http://127.0.0.1:{api_port}/proxies/{encoded_name}/delay?url={urllib.parse.quote(test_url, safe='')}&timeout={timeout_ms}"

        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(api_url, headers=auth_header)
                with urllib.request.urlopen(req, timeout=(timeout_ms / 1000.0) + 2) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    delay = resp_data.get("delay", 0)
                    if delay > 0:
                        return (p_name, True, delay)
            except Exception as ex:
                if attempt == retries:
                    err_msg = str(ex)
                    if "504" in err_msg or "timeout" in err_msg.lower():
                        err_msg = "Timeout"
                    return (p_name, False, err_msg)
            time.sleep(0.3)
        return (p_name, False, "Timeout")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(test_single_node, p["name"]): p["name"] for p in proxies}
            for future in as_completed(futures):
                name, ok, val = future.result()
                results[name] = (ok, val)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        temp_dir_obj.cleanup()

    alive_nodes = []
    failed_nodes = []

    for p in proxies:
        name = p["name"]
        ok, val = results.get(name, (False, "Untested"))
        if ok:
            alive_nodes.append((val, p))
        else:
            failed_nodes.append((name, val))

    if sort_by_delay:
        alive_nodes.sort(key=lambda x: x[0])

    if verbose:
        print("\n" + "=" * 45)
        print(f"Total Proxies Tested: {len(proxies)}")
        print(f"Alive / Reachable:    {len(alive_nodes)}")
        print(f"Failed / Timeout:     {len(failed_nodes)}")
        print("=" * 45)

        if alive_nodes:
            print("\nTop Low-Latency Nodes:")
            for delay, p in alive_nodes[:8]:
                print(f"  {delay:4d} ms  {p['name']} ({p.get('type')})")

        if failed_nodes:
            print(f"\nFailed Nodes Sample (Total {len(failed_nodes)}):")
            for name, reason in failed_nodes[:6]:
                print(f"  {name:25s} : {reason}")

    # Output / In-place update if requested
    if yaml_output or filter_alive:
        target_path = yaml_output if yaml_output else in_path
        if target_path:
            out_proxies = [p for _, p in alive_nodes] if filter_alive else [p for _, p in alive_nodes] + [p for p in proxies if any(p['name'] == f[0] for f in failed_nodes)]
            if sort_by_delay and not filter_alive:
                out_proxies = [p for _, p in alive_nodes] + [p for p in proxies if any(p['name'] == f[0] for f in failed_nodes)]
            elif sort_by_delay and filter_alive:
                out_proxies = [p for _, p in alive_nodes]

            out_names = set(p["name"] for p in out_proxies)
            alive_name_list = [p["name"] for _, p in alive_nodes]

            # Update proxy-groups
            if "proxy-groups" in config_data:
                for group in config_data["proxy-groups"]:
                    if "proxies" in group:
                        orig_g_proxies = group["proxies"]
                        if filter_alive:
                            # Keep non-proxy group keywords (DIRECT, REJECT, or other group names) and alive proxies
                            new_g_proxies = [item for item in orig_g_proxies if item in out_names or item in [g['name'] for g in config_data['proxy-groups']] or item in ('DIRECT', 'REJECT', 'COMPATIBLE', 'GLOBAL')]
                            if sort_by_delay and group.get("type") in ("url-test", "select", "fallback"):
                                # Optionally reorder proxies by latency in auto group
                                special_items = [i for i in new_g_proxies if i not in out_names]
                                proxy_items = [i for i in alive_name_list if i in new_g_proxies]
                                new_g_proxies = special_items + proxy_items
                            group["proxies"] = new_g_proxies

            config_data["proxies"] = out_proxies

            out_file = Path(target_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

            if verbose:
                print(f"\nSuccessfully written updated configuration to: {target_path}")

    return alive_nodes, failed_nodes


def main():
    parser = argparse.ArgumentParser(description="Direct Proxy Speedtest and Healthcheck for Clash/Mihomo YAML configs.")
    parser.add_argument("-i", "--input", required=True, help="Path to input Clash/Mihomo YAML file")
    parser.add_argument("-o", "--output", help="Path to output file (if omitted with --filter-alive, updates input in-place)")
    parser.add_argument("--core", help="Custom path to mihomo/clash-meta executable")
    parser.add_argument("--no-direct", dest="direct", action="store_false", default=True, help="Do not bind to physical interface (allow routing via system/TUN proxy)")
    parser.add_argument("--interface", help="Explicit physical interface name to bind (e.g. WLAN, Ethernet)")
    parser.add_argument("-u", "--test-url", default="http://www.gstatic.com/generate_204", help="Test latency URL")
    parser.add_argument("-t", "--timeout", type=int, default=3500, help="Test timeout in milliseconds (default: 3500)")
    parser.add_argument("-w", "--workers", type=int, default=16, help="Concurrent test threads (default: 16)")
    parser.add_argument("-r", "--retries", type=int, default=1, help="Retry attempts for failed nodes (default: 1)")
    parser.add_argument("--filter-alive", action="store_true", help="Remove dead/timeout nodes from proxies and proxy-groups")
    parser.add_argument("--sort", dest="sort_by_delay", action="store_true", help="Sort alive nodes by latency (lowest first)")

    args = parser.parse_args()

    run_speedtest(
        yaml_input=args.input,
        yaml_output=args.output,
        core_path=args.core,
        direct=args.direct,
        interface_name=args.interface,
        test_url=args.test_url,
        timeout_ms=args.timeout,
        max_workers=args.workers,
        retries=args.retries,
        filter_alive=args.filter_alive,
        sort_by_delay=args.sort_by_delay,
        verbose=True
    )


if __name__ == "__main__":
    main()
