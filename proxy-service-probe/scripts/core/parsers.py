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
    if not server or not port:
        return None

    p = {"name": name, "type": o_type, "server": server, "port": int(port), "udp": True}

    if o_type == "vless":
        p["uuid"] = outbound.get("uuid")
        if outbound.get("flow"):
            p["flow"] = outbound.get("flow")
        tls = outbound.get("tls", {})
        if tls.get("enabled"):
            p["tls"] = True
            p["servername"] = tls.get("server_name")
            reality = tls.get("reality", {})
            if reality.get("enabled"):
                p["reality-opts"] = {"public-key": reality.get("public_key"), "short-id": reality.get("short_id")}
            utls = tls.get("utls", {})
            if utls.get("enabled"):
                p["client-fingerprint"] = normalize_fingerprint(utls.get("fingerprint"))
        transport = outbound.get("transport", {})
        tr_type = transport.get("type")
        if tr_type == "ws":
            p["network"] = "ws"
            p["ws-opts"] = {"path": transport.get("path", "/")}
            if transport.get("headers"):
                p["ws-opts"]["headers"] = transport.get("headers")
        elif tr_type == "grpc":
            p["network"] = "grpc"
            p["grpc-opts"] = {"grpc-service-name": transport.get("service_name")}
        return p

    if o_type == "vmess":
        p["uuid"] = outbound.get("uuid")
        p["alterId"] = outbound.get("alter_id", 0)
        p["cipher"] = outbound.get("security", "auto")
        tls = outbound.get("tls", {})
        if tls.get("enabled"):
            p["tls"] = True
            p["servername"] = tls.get("server_name")
        transport = outbound.get("transport", {})
        if transport.get("type") == "ws":
            p["network"] = "ws"
            p["ws-opts"] = {"path": transport.get("path", "/")}
        return p

    if o_type == "shadowsocks":
        p["type"] = "ss"
        p["cipher"] = outbound.get("method")
        p["password"] = outbound.get("password")
        return p

    if o_type == "trojan":
        p["password"] = outbound.get("password")
        tls = outbound.get("tls", {})
        if tls.get("enabled"):
            p["sni"] = tls.get("server_name")
        return p

    if o_type == "hysteria2":
        p["password"] = outbound.get("password")
        tls = outbound.get("tls", {})
        if tls.get("enabled"):
            p["sni"] = tls.get("server_name")
        return p

    if o_type in ("http", "socks"):
        p["type"] = "http" if o_type == "http" else "socks5"
        if outbound.get("username"):
            p["username"] = outbound.get("username")
        if outbound.get("password"):
            p["password"] = outbound.get("password")
        return p

    return None


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
        if source.startswith("http://") or source.startswith("https://"):
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
                if isinstance(item, dict) and item.get("server") and item.get("port"):
                    p = deepcopy(item)
                    p.setdefault("_orig_name", p.get("name", ""))
                    proxies.append(p)
            if proxies:
                return proxies
        elif isinstance(data, list) and all(isinstance(x, dict) and "server" in x for x in data):
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
