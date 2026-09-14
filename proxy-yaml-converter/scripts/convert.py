#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proxy YAML Converter: Convert sing-box JSON configurations into standard Clash / Clash Meta YAML format.
"""

import argparse
import json
import re
import sys
from pathlib import Path
import yaml


def normalize_speed(val):
    if not val:
        return None
    val_str = str(val).strip()
    m = re.match(r"^(\d+)\s*([kKmMgGtT]?[bB])?(?:[pP/sS]+)?$", val_str)
    if m:
        num, unit = m.groups()
        unit_prefix = unit[0].upper() if unit and unit[0].lower() in "kmgt" else "M"
        return f"{num} {unit_prefix}bps"
    return val_str


def extract_node_to_clash(ob, keep_anytls=True):
    ob_type = ob.get("type")
    tag = ob.get("tag")

    if not tag or ob_type in ("direct", "block", "dns", "urltest", "selector"):
        return None

    if ob_type == "shadowsocks":
        p = {
            "name": tag,
            "type": "ss",
            "server": ob["server"],
            "port": ob["server_port"],
            "cipher": ob["method"],
            "password": str(ob["password"]),
            "udp": True,
        }
        if ob.get("udp_over_tcp", {}).get("enabled"):
            p["uot"] = True
        return p

    elif ob_type == "socks":
        p = {
            "name": tag,
            "type": "socks5",
            "server": ob["server"],
            "port": ob["server_port"],
            "udp": True,
        }
        if ob.get("username"):
            p["username"] = str(ob["username"])
        if ob.get("password"):
            p["password"] = str(ob["password"])
        return p

    elif ob_type == "http":
        p = {
            "name": tag,
            "type": "http",
            "server": ob["server"],
            "port": ob["server_port"],
        }
        if ob.get("username") and ob["username"] != "null":
            p["username"] = str(ob["username"])
        if ob.get("password") and ob["password"] != "null":
            p["password"] = str(ob["password"])
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            p["tls"] = True
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
        return p

    elif ob_type == "trojan":
        p = {
            "name": tag,
            "type": "trojan",
            "server": ob["server"],
            "port": ob["server_port"],
            "password": str(ob["password"]),
            "udp": True,
        }
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
            fp = tls.get("utls", {}).get("fingerprint")
            if fp and fp != "custom":
                p["client-fingerprint"] = fp

        tr = ob.get("transport", {})
        if tr:
            tr_type = tr.get("type")
            if tr_type == "ws":
                p["network"] = "ws"
                ws_opts = {}
                if "path" in tr:
                    ws_opts["path"] = tr["path"]
                headers = {}
                if "headers" in tr:
                    for k, v in tr["headers"].items():
                        headers[k] = v[0] if isinstance(v, list) and v else str(v)
                if headers:
                    ws_opts["headers"] = headers
                if ws_opts:
                    p["ws-opts"] = ws_opts
            elif tr_type == "grpc":
                p["network"] = "grpc"
                if "service_name" in tr:
                    p["grpc-opts"] = {"grpc-service-name": tr["service_name"]}
        return p

    elif ob_type == "tuic":
        p = {
            "name": tag,
            "type": "tuic",
            "server": ob["server"],
            "port": ob["server_port"],
            "uuid": ob["uuid"],
            "password": str(ob["password"]),
            "congestion-controller": ob.get("congestion_control", "bbr"),
            "udp": True,
        }
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
        return p

    elif ob_type == "vmess":
        p = {
            "name": tag,
            "type": "vmess",
            "server": ob["server"],
            "port": ob["server_port"],
            "uuid": ob["uuid"],
            "alterId": ob.get("alter_id", 0),
            "cipher": ob.get("security", "auto"),
            "udp": True,
        }
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            p["tls"] = True
            if "server_name" in tls:
                p["servername"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            fp = tls.get("utls", {}).get("fingerprint")
            if fp and fp != "custom":
                p["client-fingerprint"] = fp

        tr = ob.get("transport", {})
        if tr:
            tr_type = tr.get("type")
            if tr_type == "ws":
                p["network"] = "ws"
                ws_opts = {}
                if "path" in tr:
                    ws_opts["path"] = tr["path"]
                headers = {}
                if "headers" in tr:
                    for k, v in tr["headers"].items():
                        headers[k] = v[0] if isinstance(v, list) and v else str(v)
                if headers:
                    ws_opts["headers"] = headers
                if ws_opts:
                    p["ws-opts"] = ws_opts
            elif tr_type == "grpc":
                p["network"] = "grpc"
                if "service_name" in tr:
                    p["grpc-opts"] = {"grpc-service-name": tr["service_name"]}
        return p

    elif ob_type == "hysteria2":
        p = {
            "name": tag,
            "type": "hysteria2",
            "server": ob["server"],
            "port": ob["server_port"],
            "password": str(ob["password"]),
        }
        if "up_mbps" in ob:
            p["up"] = f"{ob['up_mbps']} Mbps"
        elif "up" in ob:
            up = normalize_speed(ob["up"])
            if up:
                p["up"] = up
        if "down_mbps" in ob:
            p["down"] = f"{ob['down_mbps']} Mbps"
        elif "down" in ob:
            down = normalize_speed(ob["down"])
            if down:
                p["down"] = down
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
        obfs = ob.get("obfs", {})
        if obfs.get("type"):
            p["obfs"] = obfs["type"]
            if "password" in obfs:
                p["obfs-password"] = str(obfs["password"])
        return p

    elif ob_type == "vless":
        p = {
            "name": tag,
            "type": "vless",
            "server": ob["server"],
            "port": ob["server_port"],
            "uuid": ob["uuid"],
            "udp": True,
        }
        if ob.get("flow"):
            p["flow"] = ob["flow"]

        tls = ob.get("tls", {})
        if tls.get("enabled"):
            p["tls"] = True
            if "server_name" in tls:
                p["servername"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
            fp = tls.get("utls", {}).get("fingerprint")
            if fp and fp != "custom":
                p["client-fingerprint"] = fp

            reality = tls.get("reality", {})
            if reality.get("enabled"):
                reality_opts = {}
                if "public_key" in reality:
                    reality_opts["public-key"] = reality["public_key"]
                if "short_id" in reality:
                    reality_opts["short-id"] = reality["short_id"]
                p["reality-opts"] = reality_opts

        tr = ob.get("transport", {})
        if tr:
            tr_type = tr.get("type")
            if tr_type == "ws":
                p["network"] = "ws"
                ws_opts = {}
                if "path" in tr:
                    ws_opts["path"] = tr["path"]
                headers = {}
                if "headers" in tr:
                    for k, v in tr["headers"].items():
                        headers[k] = v[0] if isinstance(v, list) and v else str(v)
                if headers:
                    ws_opts["headers"] = headers
                if ws_opts:
                    p["ws-opts"] = ws_opts
            elif tr_type == "grpc":
                p["network"] = "grpc"
                if "service_name" in tr:
                    p["grpc-opts"] = {"grpc-service-name": tr["service_name"]}
            elif tr_type == "xhttp":
                p["network"] = "xhttp"
                xhttp_opts = {}
                if "mode" in tr:
                    xhttp_opts["mode"] = tr["mode"]
                if "path" in tr:
                    xhttp_opts["path"] = tr["path"]
                headers = {}
                if "host" in tr:
                    headers["Host"] = tr["host"]
                if headers:
                    xhttp_opts["headers"] = headers
                if xhttp_opts:
                    p["xhttp-opts"] = xhttp_opts
        return p

    elif ob_type == "anytls":
        if not keep_anytls:
            return None
        p = {
            "name": tag,
            "type": "anytls",
            "server": ob["server"],
            "port": ob["server_port"],
            "password": str(ob["password"]),
            "udp": True,
        }
        tls = ob.get("tls", {})
        if tls.get("enabled"):
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
                p["servername"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
            fp = tls.get("utls", {}).get("fingerprint")
            if fp and fp != "custom":
                p["client-fingerprint"] = fp
        return p

    elif ob_type == "hysteria":
        p = {
            "name": tag,
            "type": "hysteria",
            "server": ob["server"],
            "port": ob["server_port"],
        }
        auth = ob.get("auth_str") or ob.get("auth-str") or (str(ob["auth"]) if "auth" in ob else None)
        if auth:
            p["auth_str"] = auth
        if "up_mbps" in ob:
            p["up"] = f"{ob['up_mbps']} Mbps"
        elif "up" in ob:
            up = normalize_speed(ob["up"])
            if up:
                p["up"] = up
        if "down_mbps" in ob:
            p["down"] = f"{ob['down_mbps']} Mbps"
        elif "down" in ob:
            down = normalize_speed(ob["down"])
            if down:
                p["down"] = down

        tls = ob.get("tls", {})
        if tls.get("enabled"):
            if "server_name" in tls:
                p["sni"] = tls["server_name"]
            if "insecure" in tls:
                p["skip-cert-verify"] = tls["insecure"]
            if "alpn" in tls:
                p["alpn"] = tls["alpn"]
        return p

    elif ob_type == "shadowsocksr":
        p = {
            "name": tag,
            "type": "ssr",
            "server": ob["server"],
            "port": ob["server_port"],
            "cipher": ob.get("method", "none"),
            "password": str(ob.get("password", "")),
            "obfs": ob.get("obfs", "plain"),
            "protocol": ob.get("protocol", "origin"),
            "udp": True,
        }
        if "obfs_param" in ob:
            p["obfs-param"] = str(ob["obfs_param"])
        elif "obfs-param" in ob:
            p["obfs-param"] = str(ob["obfs-param"])

        if "protocol_param" in ob:
            p["protocol-param"] = str(ob["protocol_param"])
        elif "protocol-param" in ob:
            p["protocol-param"] = str(ob["protocol-param"])

        return p

    return None


def convert_config(input_path, output_path=None, keep_anytls=True, select_group="节点选择", auto_group="自动选择", test_url="http://www.gstatic.com/generate_204"):
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Input file not found: {in_file}")

    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        outbounds = data.get("outbounds", [])
    elif isinstance(data, list):
        outbounds = data
    else:
        raise ValueError("Invalid sing-box configuration format: expected object or list.")

    proxies = []
    seen_names = set()

    for ob in outbounds:
        p = extract_node_to_clash(ob, keep_anytls=keep_anytls)
        if p:
            name = p["name"]
            original_name = name
            suffix = 1
            while name in seen_names:
                name = f"{original_name}_{suffix}"
                suffix += 1
            p["name"] = name
            seen_names.add(name)
            proxies.append(p)

    proxy_names = [p["name"] for p in proxies]

    clash_config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": select_group,
                "type": "select",
                "proxies": [auto_group] + proxy_names
            },
            {
                "name": auto_group,
                "type": "url-test",
                "url": test_url,
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names
            }
        ],
        "rules": [
            "GEOIP,LAN,DIRECT",
            "GEOIP,CN,DIRECT",
            f"MATCH,{select_group}"
        ]
    }

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return clash_config, len(proxies)


def main():
    parser = argparse.ArgumentParser(description="Convert sing-box JSON config to Clash/Mihomo YAML format.")
    parser.add_argument("-i", "--input", required=True, help="Path to input sing-box JSON file")
    parser.add_argument("-o", "--output", required=True, help="Path to output Clash YAML file")
    parser.add_argument("--no-anytls", dest="keep_anytls", action="store_false", default=True, help="Exclude anytls nodes")
    parser.add_argument("--select-group", default="节点选择", help="Main selector proxy group name")
    parser.add_argument("--auto-group", default="自动选择", help="Auto latency test proxy group name")
    parser.add_argument("--test-url", default="http://www.gstatic.com/generate_204", help="Health check URL")
    parser.add_argument("--speedtest", action="store_true", help="Perform latency healthcheck after conversion")
    parser.add_argument("--filter-alive", action="store_true", help="Filter out dead nodes when --speedtest is enabled")
    parser.add_argument("--sort", dest="sort_by_delay", action="store_true", help="Sort alive nodes by latency")
    parser.add_argument("--no-direct", dest="direct", action="store_false", default=True, help="Do not force bind physical interface in speedtest")

    args = parser.parse_args()
    clash_cfg, count = convert_config(
        args.input,
        args.output,
        keep_anytls=args.keep_anytls,
        select_group=args.select_group,
        auto_group=args.auto_group,
        test_url=args.test_url
    )
    print(f"Successfully converted {count} proxies to {args.output}")

    if args.speedtest:
        try:
            from speedtest import run_speedtest
            print("\nStarting post-conversion speedtest...")
            run_speedtest(
                yaml_input=args.output,
                yaml_output=args.output,
                direct=args.direct,
                test_url=args.test_url,
                filter_alive=args.filter_alive,
                sort_by_delay=args.sort_by_delay,
                verbose=True
            )
        except Exception as e:
            print(f"Speedtest error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
