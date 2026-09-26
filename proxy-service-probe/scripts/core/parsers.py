# -*- coding: utf-8 -*-
"""多格式节点解析模块: 支持 Clash YAML, sing-box JSON, 节点分享链接及 Base64 订阅。"""
import base64
import json
import os
import re
import urllib.parse
from copy import deepcopy

import requests
import yaml

VALID_FINGERPRINTS = {"chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def safe_b64decode(s):
    s = s.strip()
    s += '=' * (-len(s) % 4)
    try:
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except Exception:
        try:
            return base64.urlsafe_b64decode(s).decode('utf-8', errors='ignore')
        except Exception:
            return None


def normalize_fingerprint(fp):
    fp = str(fp or "").strip().lower()
    return fp if fp in VALID_FINGERPRINTS else "chrome"


def parse_node_uri(uri):
    """解析单条代理节点分享链接为 Clash 节点字典。"""
    uri = uri.strip()
    if not uri or '://' not in uri:
        return None
    try:
        # 1. VMess
        if uri.startswith('vmess://'):
            dec = safe_b64decode(uri[8:])
            if not dec:
                return None
            data = json.loads(dec)
            p = {
                'name': data.get('ps') or f"vmess_{data.get('add')}:{data.get('port')}",
                'type': 'vmess',
                'server': data.get('add'),
                'port': int(data.get('port', 443)),
                'uuid': data.get('id'),
                'alterId': int(data.get('aid', 0)),
                'cipher': data.get('scy', 'auto'),
                'udp': True,
            }
            if data.get('tls') == 'tls':
                p['tls'] = True
                if data.get('sni'):
                    p['servername'] = data['sni']
            net = data.get('net')
            if net == 'ws':
                p['network'] = 'ws'
                p['ws-opts'] = {'path': data.get('path', '/')}
                if data.get('host'):
                    p['ws-opts']['headers'] = {'Host': data['host']}
            elif net in ('grpc', 'gun'):
                p['network'] = 'grpc'
                p['grpc-opts'] = {'grpc-service-name': data.get('path', '')}
            return p

        # 2. VLESS
        if uri.startswith('vless://'):
            u = urllib.parse.urlparse(uri)
            query = urllib.parse.parse_qs(u.query)
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"vless_{u.hostname}:{u.port}"
            p = {
                'name': name,
                'type': 'vless',
                'server': u.hostname,
                'port': int(u.port or 443),
                'uuid': u.username,
                'udp': True,
            }
            sec = query.get('security', [''])[0]
            if sec in ('tls', 'reality'):
                p['tls'] = True
                p['client-fingerprint'] = normalize_fingerprint(query.get('fp', ['chrome'])[0])
                if query.get('sni'):
                    p['servername'] = query['sni'][0]
                if query.get('flow'):
                    p['flow'] = query['flow'][0]
                if sec == 'reality':
                    p['reality-opts'] = {
                        'public-key': query.get('pbk', [''])[0],
                        'short-id': query.get('sid', [''])[0]
                    }
            net = query.get('type', ['tcp'])[0]
            if net == 'ws':
                p['network'] = 'ws'
                p['ws-opts'] = {'path': query.get('path', ['/'])[0]}
                if query.get('host'):
                    p['ws-opts']['headers'] = {'Host': query['host'][0]}
            elif net == 'grpc':
                p['network'] = 'grpc'
                p['grpc-opts'] = {'grpc-service-name': query.get('serviceName', [''])[0]}
            return p

        # 3. Trojan
        if uri.startswith('trojan://'):
            u = urllib.parse.urlparse(uri)
            query = urllib.parse.parse_qs(u.query)
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"trojan_{u.hostname}:{u.port}"
            p = {
                'name': name,
                'type': 'trojan',
                'server': u.hostname,
                'port': int(u.port or 443),
                'password': u.username,
                'udp': True,
            }
            sni = query.get('sni', [''])[0] or query.get('peer', [''])[0]
            if sni:
                p['sni'] = sni
            if query.get('allowInsecure', [''])[0] in ('1', 'true'):
                p['skip-cert-verify'] = True
            net = query.get('type', ['tcp'])[0]
            if net == 'ws':
                p['network'] = 'ws'
                p['ws-opts'] = {'path': query.get('path', ['/'])[0]}
                if query.get('host'):
                    p['ws-opts']['headers'] = {'Host': query['host'][0]}
            elif net == 'grpc':
                p['network'] = 'grpc'
                p['grpc-opts'] = {'grpc-service-name': query.get('serviceName', [''])[0]}
            return p

        # 4. Shadowsocks (SS)
        if uri.startswith('ss://'):
            u = urllib.parse.urlparse(uri)
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"ss_{u.hostname}:{u.port}"
            user_info = u.netloc.split('@')[0] if '@' in u.netloc else u.username
            host_port = u.netloc.split('@')[1] if '@' in u.netloc else ''
            if not host_port and u.hostname:
                host_port = f"{u.hostname}:{u.port or 8388}"
            if ':' in user_info and not safe_b64decode(user_info):
                cipher, password = user_info.split(':', 1)
            else:
                decoded = safe_b64decode(user_info)
                if decoded and ':' in decoded:
                    cipher, password = decoded.split(':', 1)
                else:
                    return None
            host, port = host_port.split(':', 1)
            return {
                'name': name,
                'type': 'ss',
                'server': host,
                'port': int(port),
                'cipher': cipher,
                'password': password,
                'udp': True
            }

        # 5. Hysteria2 (hy2)
        if uri.startswith('hysteria2://') or uri.startswith('hy2://'):
            u = urllib.parse.urlparse(uri)
            query = urllib.parse.parse_qs(u.query)
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"hy2_{u.hostname}:{u.port}"
            p = {
                'name': name,
                'type': 'hysteria2',
                'server': u.hostname,
                'port': int(u.port or 443),
                'password': u.username,
                'udp': True,
            }
            if query.get('sni'):
                p['sni'] = query['sni'][0]
            if query.get('insecure', [''])[0] in ('1', 'true'):
                p['skip-cert-verify'] = True
            if query.get('obfs'):
                p['obfs'] = query['obfs'][0]
                if query.get('obfs-password'):
                    p['obfs-password'] = query['obfs-password'][0]
            return p

        # 6. TUIC
        if uri.startswith('tuic://'):
            u = urllib.parse.urlparse(uri)
            query = urllib.parse.parse_qs(u.query)
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"tuic_{u.hostname}:{u.port}"
            p = {
                'name': name,
                'type': 'tuic',
                'server': u.hostname,
                'port': int(u.port or 443),
                'uuid': u.username,
                'password': u.password or '',
                'udp': True,
            }
            if query.get('sni'):
                p['sni'] = query['sni'][0]
            if query.get('congestion_control'):
                p['congestion-controller'] = query['congestion_control'][0]
            return p

        # 7. HTTP / Socks5
        if uri.startswith('http://') or uri.startswith('https://') or uri.startswith('socks5://') or uri.startswith('socks://'):
            u = urllib.parse.urlparse(uri)
            is_http = uri.startswith('http://') or uri.startswith('https://')
            name = urllib.parse.unquote(u.fragment) if u.fragment else f"{'http' if is_http else 'socks5'}_{u.hostname}:{u.port}"
            p = {
                'name': name,
                'type': 'http' if is_http else 'socks5',
                'server': u.hostname,
                'port': int(u.port or (80 if uri.startswith('http://') else 443 if uri.startswith('https://') else 1080)),
            }
            if u.username:
                p['username'] = u.username
            if u.password:
                p['password'] = u.password
            if uri.startswith('https://'):
                p['tls'] = True
            return p

    except Exception:
        return None
    return None


def _as_list(value):
    """sing-box 的可列表字段 (alpn、h2 host 等) 可写成单个字符串；Clash/Mihomo 要求列表。"""
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _header_strings(headers):
    """
    sing-box 的 HTTP 头值可为字符串或字符串列表，Clash/Mihomo 只接受字符串 (列表会让整份配置加载失败)：
    列表取首个值，空列表的头丢弃。
    """
    flat = {}
    for key, value in (headers or {}).items():
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = value[0]
        flat[key] = str(value)
    return flat


def _copy_singbox_tls(outbound, proxy, use_sni=False):
    tls = outbound.get("tls") or {}
    if not tls.get("enabled"):
        return
    proxy["tls"] = True
    if tls.get("server_name"):
        proxy["sni" if use_sni else "servername"] = tls["server_name"]
    if tls.get("insecure"):
        proxy["skip-cert-verify"] = True
    if tls.get("alpn"):
        proxy["alpn"] = _as_list(tls["alpn"])
    utls = tls.get("utls") or {}
    if utls.get("enabled"):
        proxy["client-fingerprint"] = normalize_fingerprint(utls.get("fingerprint"))
    reality = tls.get("reality") or {}
    if reality.get("enabled"):
        proxy["reality-opts"] = {
            "public-key": reality.get("public_key", ""),
            "short-id": reality.get("short_id", "")
        }


def _copy_singbox_transport(outbound, proxy):
    transport = outbound.get("transport") or {}
    tr_type = transport.get("type")
    if tr_type == "ws":
        proxy["network"] = "ws"
        opts = {"path": transport.get("path", "/")}
        headers = _header_strings(transport.get("headers"))
        if headers:
            opts["headers"] = headers
        if transport.get("max_early_data"):
            opts["max-early-data"] = transport["max_early_data"]
            if transport.get("early_data_header_name"):
                opts["early-data-header-name"] = transport["early_data_header_name"]
        proxy["ws-opts"] = opts
    elif tr_type == "httpupgrade":
        proxy["network"] = "ws"
        opts = {"path": transport.get("path", "/"), "v2ray-http-upgrade": True}
        headers = _header_strings(transport.get("headers"))
        if transport.get("host"):
            headers["Host"] = transport["host"]
        if headers:
            opts["headers"] = headers
        proxy["ws-opts"] = opts
    elif tr_type == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {"grpc-service-name": transport.get("service_name", "")}
    elif tr_type == "http":
        proxy["network"] = "h2"
        opts = {"path": transport.get("path", "/")}
        if transport.get("host"):
            opts["host"] = _as_list(transport["host"])
        proxy["h2-opts"] = opts


def _copy_singbox_dial(outbound, proxy):
    if outbound.get("detour"):
        proxy["dialer-proxy"] = outbound["detour"]
    if outbound.get("tcp_fast_open"):
        proxy["tfo"] = True
    if outbound.get("tcp_multi_path"):
        proxy["mptcp"] = True
    if outbound.get("bind_interface"):
        proxy["interface-name"] = outbound["bind_interface"]
    resolver = outbound.get("domain_resolver") or {}
    strategy = resolver.get("strategy") if isinstance(resolver, dict) else None
    reverse = {"ipv4_only": "ipv4", "ipv6_only": "ipv6",
               "prefer_ipv4": "ipv4-prefer", "prefer_ipv6": "ipv6-prefer"}
    if strategy in reverse:
        proxy["ip-version"] = reverse[strategy]


def parse_singbox_outbound(outbound):
    """把单个 sing-box outbound 转换为 Clash 节点字典。"""
    if not isinstance(outbound, dict):
        return None
    o_type = outbound.get("type", "").lower()
    if o_type in ("direct", "block", "dns", "selector", "urltest"):
        return None
    name = outbound.get("tag") or f"{o_type}_{outbound.get('server')}:{outbound.get('server_port')}"
    server = outbound.get("server")
    port = outbound.get("server_port")
    has_port_range = o_type in ("hysteria", "hysteria2") and outbound.get("server_ports")
    if not server or (not port and not has_port_range):
        return None

    p = {"name": name, "type": o_type, "server": server, "udp": True}
    if port:
        p["port"] = int(port)
    if has_port_range:
        ranges = []
        for value in outbound["server_ports"]:
            value = str(value)
            ranges.append(value.replace(":", "-", 1) if ":" in value and value.split(":", 1)[0] != value.split(":", 1)[1] else value.split(":", 1)[0])
        p["ports"] = ",".join(ranges)
    _copy_singbox_dial(outbound, p)

    if o_type == "vless":
        p["uuid"] = outbound.get("uuid")
        if outbound.get("flow"):
            p["flow"] = outbound.get("flow")
        _copy_singbox_tls(outbound, p)
        _copy_singbox_transport(outbound, p)
        return p

    if o_type == "vmess":
        p["uuid"] = outbound.get("uuid")
        p["alterId"] = outbound.get("alter_id", 0)
        p["cipher"] = outbound.get("security", "auto")
        _copy_singbox_tls(outbound, p)
        _copy_singbox_transport(outbound, p)
        return p

    if o_type == "shadowsocks":
        p["type"] = "ss"
        p["cipher"] = outbound.get("method")
        p["password"] = outbound.get("password")
        return p

    if o_type == "trojan":
        p["password"] = outbound.get("password")
        _copy_singbox_tls(outbound, p, use_sni=True)
        _copy_singbox_transport(outbound, p)
        return p

    if o_type == "hysteria2":
        p["password"] = outbound.get("password")
        if outbound.get("up_mbps") is not None:
            p["up"] = outbound["up_mbps"]
        if outbound.get("down_mbps") is not None:
            p["down"] = outbound["down_mbps"]
        if outbound.get("obfs"):
            p["obfs"] = outbound["obfs"].get("type") if isinstance(outbound["obfs"], dict) else outbound["obfs"]
            if isinstance(outbound["obfs"], dict) and outbound["obfs"].get("password"):
                p["obfs-password"] = outbound["obfs"]["password"]
        _copy_singbox_tls(outbound, p, use_sni=True)
        return p

    if o_type == "hysteria":
        if outbound.get("up_mbps") is not None:
            p["up"] = outbound["up_mbps"]
        if outbound.get("down_mbps") is not None:
            p["down"] = outbound["down_mbps"]
        if outbound.get("auth_str"):
            p["auth-str"] = outbound["auth_str"]
        elif outbound.get("auth"):
            p["auth"] = outbound["auth"]
        _copy_singbox_tls(outbound, p, use_sni=True)
        return p

    if o_type == "tuic":
        p["uuid"] = outbound.get("uuid")
        p["password"] = outbound.get("password")
        if outbound.get("congestion_control"):
            p["congestion-controller"] = outbound["congestion_control"]
        if outbound.get("udp_relay_mode"):
            p["udp-relay-mode"] = outbound["udp_relay_mode"]
        if outbound.get("udp_over_stream"):
            p["udp-over-stream"] = True
        if outbound.get("zero_rtt_handshake"):
            p["reduce-rtt"] = True
        _copy_singbox_tls(outbound, p, use_sni=True)
        return p

    if o_type == "anytls":
        p["type"] = "anytls"
        p["password"] = outbound.get("password")
        _copy_singbox_tls(outbound, p)
        return p

    if o_type == "ssh":
        p["type"] = "ssh"
        p["username"] = outbound.get("user")
        p["password"] = outbound.get("password")
        if outbound.get("private_key"):
            p["private-key"] = outbound["private_key"]
        if outbound.get("private_key_path"):
            p["private-key"] = outbound["private_key_path"]
        return p

    if o_type in ("http", "socks"):
        p["type"] = "http" if o_type == "http" else "socks5"
        if outbound.get("username"):
            p["username"] = outbound.get("username")
        if outbound.get("password"):
            p["password"] = outbound.get("password")
        headers = _header_strings(outbound.get("headers"))
        if headers:
            p["headers"] = headers
        _copy_singbox_tls(outbound, p)
        return p

    return None


def _proxy_has_server_port(item):
    if not isinstance(item, dict) or not item.get("server"):
        return False
    if item.get("port"):
        return True
    return str(item.get("type", "")).lower() in ("hysteria", "hysteria2") and bool(item.get("ports") or item.get("mport"))


def load_proxies(source):
    """
    统一加载节点，输入 source 可以是:
    - 本地文件路径 (.yaml, .yml, .json, .txt)
    - 远程订阅 URL (http://, https://)
    - 内存原始文本/列表
    """
    text = ""
    if isinstance(source, list):
        return [deepcopy(p) for p in source if isinstance(p, dict) and "server" in p]

    if isinstance(source, str):
        source = source.strip()
        s_lower = source.lower()
        if (s_lower in ("fofa", "quake", "spatial") or
                s_lower.startswith(("fofa:", "quake:", "spatial:"))):
            from core.fofa import search_and_fetch_proxies
            if s_lower.startswith("quake:"):
                engine = "quake"
                query_or_preset = source[6:].strip() or None
            elif s_lower.startswith("fofa:"):
                engine = "fofa"
                query_or_preset = source[5:].strip() or None
            elif s_lower.startswith("spatial:"):
                engine = "all"
                query_or_preset = source[8:].strip() or None
            else:
                engine = "all"
                query_or_preset = None
            proxies, _ = search_and_fetch_proxies(query_or_preset=query_or_preset, engine=engine)
            return proxies
        elif source.startswith("http://") or source.startswith("https://"):
            resp = requests.get(source, headers={"User-Agent": UA}, timeout=25)
            resp.raise_for_status()
            text = resp.text
        elif os.path.isfile(source):
            with open(source, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = source

    if not text:
        return []

    proxies = []

    # 1. 尝试解析为 Clash YAML
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and "proxies" in data and isinstance(data["proxies"], list):
            for item in data["proxies"]:
                if isinstance(item, dict) and _proxy_has_server_port(item):
                    p = deepcopy(item)
                    p.setdefault("_orig_name", p.get("name", ""))
                    proxies.append(p)
            if proxies:
                return proxies
        elif isinstance(data, list) and all(_proxy_has_server_port(x) for x in data):
            for item in data:
                p = deepcopy(item)
                p.setdefault("_orig_name", p.get("name", ""))
                proxies.append(p)
            if proxies:
                return proxies
    except Exception:
        pass

    # 2. 尝试解析为 sing-box JSON
    try:
        jdata = json.loads(text)
        if isinstance(jdata, dict) and "outbounds" in jdata:
            for ob in jdata["outbounds"]:
                cp = parse_singbox_outbound(ob)
                if cp:
                    cp.setdefault("_orig_name", cp.get("name", ""))
                    proxies.append(cp)
            if proxies:
                return proxies
    except Exception:
        pass

    # 3. 尝试 Base64 解码并按行提取
    decoded = safe_b64decode(text)
    candidate_lines = (decoded if decoded else text).splitlines()

    for line in candidate_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        node = parse_node_uri(line)
        if node:
            node.setdefault("_orig_name", node.get("name", ""))
            proxies.append(node)

    # 去除重名后缀并赋名
    seen_names = {}
    for p in proxies:
        raw_name = p.get("name") or f"{p.get('type')}_{p.get('server')}:{p.get('port')}"
        if raw_name in seen_names:
            seen_names[raw_name] += 1
            p["name"] = f"{raw_name}_{seen_names[raw_name]}"
        else:
            seen_names[raw_name] = 1
            p["name"] = raw_name

    return proxies
