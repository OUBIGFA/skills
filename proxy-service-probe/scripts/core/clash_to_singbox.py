# -*- coding: utf-8 -*-
"""
Clash / Mihomo 节点 → sing-box 1.14 标准出站 (outbound / endpoint) 转换器。

字段依据 sing-box stable 官方文档 (1.14.x)：
- WireGuard 自 1.11 起为 endpoint，旧 wireguard outbound 已于 1.13 移除，转换结果带 type=wireguard 放入 `endpoints`；
- hysteria2 的 server_ports 与 server_port 互斥，端口跳跃时只输出 server_ports；
- Reality 需要 uTLS，缺省指纹时补 chrome；ECH 配置转为 PEM 行数组；
- 旧式 domain_strategy 已迁移为 dial 字段 domain_resolver。
无法等价转换的节点抛出 UnsupportedProxy 并给出原因，绝不输出残缺节点冒充成功。
"""
import base64
import re

DEFAULT_DOMAIN_RESOLVER = "dns_direct"

SS_METHODS = {
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305",
    "none", "aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305", "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "aes-128-cfb",
    "aes-192-cfb", "aes-256-cfb", "rc4-md5", "chacha20-ietf", "xchacha20",
}
SS_METHOD_ALIASES = {"plain": "none", "dummy": "none", "chacha20-poly1305": "chacha20-ietf-poly1305"}
VMESS_SECURITY = {"auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-ctr"}
UTLS_FINGERPRINTS = {"chrome", "firefox", "edge", "safari", "360", "qq", "ios", "android", "random", "randomized"}
IP_VERSION_STRATEGY = {"ipv4": "ipv4_only", "ipv6": "ipv6_only",
                       "ipv4-prefer": "prefer_ipv4", "ipv6-prefer": "prefer_ipv6"}


class UnsupportedProxy(ValueError):
    """该节点无法等价转换为 sing-box 配置。"""


def _as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]


def _duration(value, unit="s"):
    """Clash 用数字（秒或毫秒）表示时长，sing-box 需要带单位的字符串。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return f"{int(value)}{unit}"
    text = str(value).strip()
    return f"{text}{unit}" if text.isdigit() else text


def _mbps(value):
    """解析 Clash 带宽写法（100 / "100" / "100 Mbps" / "1 Gbps" / "500 Kbps"）为整数 Mbps。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.match(r'^\s*([\d.]+)\s*([KMGkmg]?)(?:bps|b)?\s*$', str(value))
    if not m:
        raise UnsupportedProxy(f"无法解析带宽值: {value}")
    num, unit = float(m.group(1)), m.group(2).upper()
    factor = {"K": 1 / 1000, "M": 1, "G": 1000, "": 1}[unit]
    return max(1, int(num * factor))


def _server_ports(ports):
    """Clash `443,8000-9000` → sing-box ["443:443", "8000:9000"]。"""
    result = []
    for part in re.split(r'[,/]', str(ports)):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(\d+)(?:\s*[-:]\s*(\d+))?$', part)
        if not m:
            raise UnsupportedProxy(f"无法解析端口跳跃范围: {ports}")
        start, end = m.group(1), m.group(2) or m.group(1)
        result.append(f"{start}:{end}")
    return result


def _ech_pem(config):
    config = str(config).strip()
    if config.startswith("-----BEGIN"):
        return [line for line in config.splitlines() if line.strip()]
    return ["-----BEGIN ECH CONFIGS-----", config, "-----END ECH CONFIGS-----"]


def _tls(p, warnings, always=False):
    """按 Clash 字段构造 sing-box outbound TLS；未启用时返回 None。"""
    reality = p.get("reality-opts") or {}
    enabled = always or bool(p.get("tls")) or bool(reality)
    if not enabled:
        return None
    tls = {"enabled": True}
    server_name = p.get("servername") or p.get("sni")
    if server_name:
        tls["server_name"] = str(server_name)
    if p.get("disable-sni"):
        tls["disable_sni"] = True
    if p.get("skip-cert-verify"):
        tls["insecure"] = True
    alpn = _as_list(p.get("alpn"))
    if alpn:
        tls["alpn"] = alpn

    fingerprint = str(p.get("client-fingerprint") or "").strip().lower()
    if fingerprint:
        if fingerprint not in UTLS_FINGERPRINTS:
            warnings.append(f"uTLS 指纹 {fingerprint} 不受 sing-box 支持，改用 chrome")
            fingerprint = "chrome"
        tls["utls"] = {"enabled": True, "fingerprint": fingerprint}

    if reality:
        public_key = reality.get("public-key")
        if not public_key:
            raise UnsupportedProxy("reality-opts 缺少 public-key")
        tls["reality"] = {"enabled": True, "public_key": public_key}
        if reality.get("short-id"):
            tls["reality"]["short_id"] = str(reality["short-id"])
        # sing-box 的 Reality 客户端依赖 uTLS
        tls.setdefault("utls", {"enabled": True, "fingerprint": "chrome"})

    ech = p.get("ech-opts") or {}
    if ech.get("enable"):
        tls["ech"] = {"enabled": True}
        if ech.get("config"):
            tls["ech"]["config"] = _ech_pem(ech["config"])
        if ech.get("query-server-name"):
            tls["ech"]["query_server_name"] = ech["query-server-name"]

    if p.get("fingerprint"):
        warnings.append("Clash 证书指纹锁定 fingerprint 与 sing-box certificate_public_key_sha256 口径不同，未转换")
    if p.get("certificate") or p.get("private-key"):
        warnings.append("Clash 客户端证书 (mTLS) 未转换")
    return tls


def _transport(p):
    """vmess / vless / trojan 的 V2Ray 传输层。"""
    network = str(p.get("network") or "tcp").lower()
    if network == "tcp":
        return None
    if network == "ws":
        opts = p.get("ws-opts") or {}
        headers = {k: v for k, v in (opts.get("headers") or {}).items()}
        path = opts.get("path") or "/"
        if opts.get("v2ray-http-upgrade"):
            tr = {"type": "httpupgrade", "path": path}
            host = headers.pop("Host", None) or headers.pop("host", None)
            if host:
                tr["host"] = host
            if headers:
                tr["headers"] = headers
            return tr
        tr = {"type": "ws", "path": path}
        if headers:
            tr["headers"] = headers
        if opts.get("max-early-data"):
            tr["max_early_data"] = int(opts["max-early-data"])
            tr["early_data_header_name"] = opts.get("early-data-header-name") or "Sec-WebSocket-Protocol"
        return tr
    if network == "h2":
        opts = p.get("h2-opts") or {}
        tr = {"type": "http", "path": opts.get("path") or "/"}
        hosts = _as_list(opts.get("host"))
        if hosts:
            tr["host"] = hosts
        return tr
    if network == "http":
        opts = p.get("http-opts") or {}
        paths = _as_list(opts.get("path")) or ["/"]
        tr = {"type": "http", "path": paths[0]}
        if opts.get("method"):
            tr["method"] = opts["method"]
        headers = dict(opts.get("headers") or {})
        hosts = _as_list(headers.pop("Host", None) or headers.pop("host", None))
        if hosts:
            tr["host"] = hosts
        if headers:
            tr["headers"] = headers
        return tr
    if network == "grpc":
        opts = p.get("grpc-opts") or {}
        return {"type": "grpc", "service_name": opts.get("grpc-service-name") or ""}
    raise UnsupportedProxy(f"sing-box 不支持传输层 {network}")


def _multiplex(p):
    smux = p.get("smux") or {}
    if not smux.get("enabled"):
        return None
    mux = {"enabled": True, "protocol": smux.get("protocol") or "h2mux"}
    for src, dst in (("max-connections", "max_connections"), ("min-streams", "min_streams"),
                     ("max-streams", "max_streams")):
        if smux.get(src):
            mux[dst] = int(smux[src])
    if smux.get("padding"):
        mux["padding"] = True
    brutal = smux.get("brutal-opts") or {}
    if brutal.get("enabled"):
        mux["brutal"] = {"enabled": True, "up_mbps": _mbps(brutal.get("up")),
                         "down_mbps": _mbps(brutal.get("down"))}
    return mux


def _base(p, sb_type, with_port=True):
    ob = {"type": sb_type, "tag": str(p.get("name") or f"{sb_type}_{p.get('server')}:{p.get('port')}"),
          "server": str(p["server"])}
    if with_port:
        ob["server_port"] = int(p["port"])
    return ob


def _dial_fields(p, ob):
    # dialer-proxy 原样保留为 detour，由导出层识别为落地节点并统一改接 🛡️ Front前置
    if p.get("dialer-proxy"):
        ob["detour"] = p["dialer-proxy"]
    if p.get("tfo"):
        ob["tcp_fast_open"] = True
    if p.get("mptcp"):
        ob["tcp_multi_path"] = True
    strategy = IP_VERSION_STRATEGY.get(str(p.get("ip-version") or "").lower())
    if strategy:
        ob["domain_resolver"] = {"server": DEFAULT_DOMAIN_RESOLVER, "strategy": strategy}
    if p.get("interface-name"):
        ob["bind_interface"] = p["interface-name"]
    if p.get("routing-mark"):
        ob["routing_mark"] = int(p["routing-mark"])
    return ob


def _tcp_only(p, ob):
    if p.get("udp") is False:
        ob["network"] = "tcp"


def _set(ob, key, value):
    if value not in (None, "", [], {}):
        ob[key] = value


def _ss(p, warnings):
    method = str(p.get("cipher") or "").lower()
    method = SS_METHOD_ALIASES.get(method, method)
    if method not in SS_METHODS:
        raise UnsupportedProxy(f"sing-box 不支持 Shadowsocks 加密方式 {p.get('cipher')}")
    ob = _base(p, "shadowsocks")
    ob["method"] = method
    ob["password"] = str(p.get("password") or "")
    plugin = str(p.get("plugin") or "").lower()
    opts = p.get("plugin-opts") or {}
    if plugin == "obfs":
        mode = opts.get("mode") or "http"
        plugin_opts = f"obfs={mode}"
        if opts.get("host"):
            plugin_opts += f";obfs-host={opts['host']}"
        ob["plugin"], ob["plugin_opts"] = "obfs-local", plugin_opts
    elif plugin == "v2ray-plugin":
        if (opts.get("mode") or "websocket") != "websocket":
            raise UnsupportedProxy(f"v2ray-plugin 仅支持 websocket 模式，当前为 {opts.get('mode')}")
        parts = ["mode=websocket"]
        if opts.get("tls"):
            parts.append("tls")
        if opts.get("host"):
            parts.append(f"host={opts['host']}")
        if opts.get("path"):
            parts.append(f"path={opts['path']}")
        if opts.get("mux"):
            parts.append("mux=1")
        ob["plugin"], ob["plugin_opts"] = "v2ray-plugin", ";".join(parts)
    elif plugin:
        raise UnsupportedProxy(f"sing-box 不支持 Shadowsocks 插件 {plugin}")
    if p.get("udp-over-tcp"):
        ob["udp_over_tcp"] = {"enabled": True, "version": int(p.get("udp-over-tcp-version") or 1)}
    _tcp_only(p, ob)
    _set(ob, "multiplex", _multiplex(p))
    return ob


def _vmess(p, warnings):
    security = str(p.get("cipher") or "auto").lower()
    if security not in VMESS_SECURITY:
        raise UnsupportedProxy(f"sing-box 不支持 VMess 加密方式 {p.get('cipher')}")
    ob = _base(p, "vmess")
    ob["uuid"] = str(p.get("uuid") or "")
    ob["security"] = security
    ob["alter_id"] = int(p.get("alterId") or p.get("alter-id") or 0)
    if p.get("global-padding"):
        ob["global_padding"] = True
    if p.get("authenticated-length"):
        ob["authenticated_length"] = True
    _packet_encoding(p, ob)
    _tcp_only(p, ob)
    _set(ob, "tls", _tls(p, warnings))
    _set(ob, "transport", _transport(p))
    _set(ob, "multiplex", _multiplex(p))
    return ob


def _packet_encoding(p, ob):
    encoding = p.get("packet-encoding")
    if not encoding and p.get("xudp"):
        encoding = "xudp"
    if encoding in ("xudp", "packetaddr"):
        ob["packet_encoding"] = encoding


def _vless(p, warnings):
    encryption = str(p.get("encryption") or "").strip().lower()
    if encryption not in ("", "none"):
        raise UnsupportedProxy("sing-box 不支持 VLESS encryption（ML-KEM 等后量子加密）")
    ob = _base(p, "vless")
    ob["uuid"] = str(p.get("uuid") or "")
    flow = str(p.get("flow") or "").strip()
    if flow:
        if not flow.startswith("xtls-rprx-vision"):
            raise UnsupportedProxy(f"sing-box 仅支持 xtls-rprx-vision 流控，当前为 {flow}")
        ob["flow"] = "xtls-rprx-vision"
    _packet_encoding(p, ob)
    _tcp_only(p, ob)
    _set(ob, "tls", _tls(p, warnings))
    _set(ob, "transport", _transport(p))
    _set(ob, "multiplex", _multiplex(p))
    return ob


def _trojan(p, warnings):
    if (p.get("ss-opts") or {}).get("enabled"):
        raise UnsupportedProxy("sing-box 不支持 Trojan-Go 的 ss-opts 二次加密")
    ob = _base(p, "trojan")
    ob["password"] = str(p.get("password") or "")
    _tcp_only(p, ob)
    ob["tls"] = _tls(p, warnings, always=True)
    _set(ob, "transport", _transport(p))
    _set(ob, "multiplex", _multiplex(p))
    return ob


def _hop(p, ob):
    ports = p.get("ports") or p.get("mport")
    if ports:
        ob.pop("server_port", None)  # 1.14 文档：server_ports 与 server_port 互斥
        ob["server_ports"] = _server_ports(ports)
        _set(ob, "hop_interval", _duration(p.get("hop-interval")))


def _hysteria2(p, warnings):
    has_port_range = bool(p.get("ports") or p.get("mport"))
    ob = _base(p, "hysteria2", with_port=not has_port_range)
    _hop(p, ob)
    _set(ob, "up_mbps", _mbps(p.get("up")))
    _set(ob, "down_mbps", _mbps(p.get("down")))
    obfs = str(p.get("obfs") or "").lower()
    if obfs:
        if obfs not in ("salamander", "gecko"):
            raise UnsupportedProxy(f"sing-box 不支持 Hysteria2 混淆 {obfs}")
        ob["obfs"] = {"type": obfs, "password": str(p.get("obfs-password") or "")}
    ob["password"] = str(p.get("password") or p.get("auth") or "")
    _tcp_only(p, ob)
    ob["tls"] = _tls(p, warnings, always=True)
    return ob


def _hysteria(p, warnings):
    protocol = str(p.get("protocol") or "udp").lower()
    if protocol != "udp":
        raise UnsupportedProxy(f"sing-box 的 Hysteria 仅支持 udp 协议，当前为 {protocol}")
    has_port_range = bool(p.get("ports") or p.get("mport"))
    ob = _base(p, "hysteria", with_port=not has_port_range)
    _hop(p, ob)
    up, down = _mbps(p.get("up")), _mbps(p.get("down"))
    if not up or not down:
        raise UnsupportedProxy("Hysteria 缺少 up/down 带宽")
    ob["up_mbps"], ob["down_mbps"] = up, down
    _set(ob, "obfs", p.get("obfs"))
    auth_str = p.get("auth-str") or p.get("auth_str")
    if auth_str:
        ob["auth_str"] = str(auth_str)
    elif p.get("auth"):
        ob["auth"] = str(p["auth"])
    if p.get("disable-mtu-discovery") or p.get("disable_mtu_discovery"):
        ob["disable_path_mtu_discovery"] = True  # 旧 disable_mtu_discovery 已弃用
    _tcp_only(p, ob)
    ob["tls"] = _tls(p, warnings, always=True)
    return ob


def _tuic(p, warnings):
    if p.get("token") and not p.get("uuid"):
        raise UnsupportedProxy("sing-box 仅支持 TUIC v5，不支持 v4 token 认证")
    ob = _base(p, "tuic")
    ob["uuid"] = str(p.get("uuid") or "")
    ob["password"] = str(p.get("password") or "")
    _set(ob, "congestion_control", p.get("congestion-controller"))
    _set(ob, "udp_relay_mode", p.get("udp-relay-mode"))
    if p.get("udp-over-stream"):
        ob["udp_over_stream"] = True
    if p.get("reduce-rtt"):
        ob["zero_rtt_handshake"] = True
    _set(ob, "heartbeat", _duration(p.get("heartbeat-interval"), unit="ms"))
    _tcp_only(p, ob)
    ob["tls"] = _tls(p, warnings, always=True)
    return ob


def _anytls(p, warnings):
    ob = _base(p, "anytls")
    ob["password"] = str(p.get("password") or "")
    _set(ob, "idle_session_check_interval", _duration(p.get("idle-session-check-interval")))
    _set(ob, "idle_session_timeout", _duration(p.get("idle-session-timeout")))
    if p.get("min-idle-session") is not None:
        ob["min_idle_session"] = int(p["min-idle-session"])
    ob["tls"] = _tls(p, warnings, always=True)
    return ob


def _socks(p, warnings):
    if p.get("tls"):
        raise UnsupportedProxy("sing-box 的 SOCKS 出站不支持 TLS")
    ob = _base(p, "socks")
    ob["version"] = "5"
    _set(ob, "username", p.get("username"))
    _set(ob, "password", p.get("password"))
    _tcp_only(p, ob)
    return ob


def _http(p, warnings):
    ob = _base(p, "http")
    _set(ob, "username", p.get("username"))
    _set(ob, "password", p.get("password"))
    _set(ob, "headers", p.get("headers"))
    _set(ob, "tls", _tls(p, warnings))
    return ob


def _ssh(p, warnings):
    ob = _base(p, "ssh")
    _set(ob, "user", p.get("username"))
    _set(ob, "password", p.get("password"))
    key = p.get("private-key")
    if key:
        ob["private_key" if str(key).lstrip().startswith("-----BEGIN") else "private_key_path"] = str(key)
    _set(ob, "private_key_passphrase", p.get("private-key-passphrase"))
    _set(ob, "host_key", _as_list(p.get("host-key")))
    _set(ob, "host_key_algorithms", _as_list(p.get("host-key-algorithms")))
    return ob


def _reserved(value):
    if value in (None, "", []):
        return None
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value]
    text = str(value).strip()
    if re.match(r'^\d+\s*,\s*\d+\s*,\s*\d+$', text):
        return [int(v) for v in text.split(",")]
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4))
    except Exception:
        raise UnsupportedProxy(f"无法解析 WireGuard reserved: {value}")
    if len(raw) != 3:
        raise UnsupportedProxy(f"WireGuard reserved 必须为 3 字节: {value}")
    return list(raw)


def _cidr(addr, v6=False):
    addr = str(addr).strip()
    return addr if "/" in addr else f"{addr}/{128 if v6 else 32}"


def _wg_peer(src, fallback):
    peer = {"address": str(src.get("server") or fallback.get("server")),
            "port": int(src.get("port") or fallback.get("port")),
            "public_key": src.get("public-key") or fallback.get("public-key")}
    if not peer["public_key"]:
        raise UnsupportedProxy("WireGuard 缺少 public-key")
    _set(peer, "pre_shared_key", src.get("pre-shared-key") or fallback.get("pre-shared-key"))
    peer["allowed_ips"] = _as_list(src.get("allowed-ips") or fallback.get("allowed-ips")) or ["0.0.0.0/0", "::/0"]
    keepalive = src.get("persistent-keepalive") or fallback.get("persistent-keepalive")
    if keepalive:
        peer["persistent_keepalive_interval"] = int(keepalive)
    _set(peer, "reserved", _reserved(src.get("reserved") or fallback.get("reserved")))
    return peer


def _wireguard(p, warnings):
    if p.get("amnezia-wg-option"):
        raise UnsupportedProxy("sing-box 不支持 AmneziaWG 参数")
    if not p.get("private-key"):
        raise UnsupportedProxy("WireGuard 缺少 private-key")
    address = []
    if p.get("ip"):
        address.append(_cidr(p["ip"]))
    if p.get("ipv6"):
        address.append(_cidr(p["ipv6"], v6=True))
    if not address:
        raise UnsupportedProxy("WireGuard 缺少本地地址 ip/ipv6")
    ep = {"type": "wireguard", "tag": str(p.get("name") or f"wireguard_{p.get('server')}"),
          "address": address, "private_key": p["private-key"]}
    if p.get("mtu"):
        ep["mtu"] = int(p["mtu"])
    peers = p.get("peers") or [{}]
    ep["peers"] = [_wg_peer(peer, p) for peer in peers]
    return _dial_fields(p, ep)


CONVERTERS = {
    "ss": _ss, "vmess": _vmess, "vless": _vless, "trojan": _trojan,
    "hysteria2": _hysteria2, "hysteria": _hysteria, "tuic": _tuic, "anytls": _anytls,
    "socks5": _socks, "http": _http, "ssh": _ssh, "wireguard": _wireguard,
}


def clash_to_singbox(proxy, warnings=None):
    """把单个 Clash 节点转换为 sing-box 出站；WireGuard 返回 type=wireguard 的 endpoint。"""
    warnings = [] if warnings is None else warnings
    if not isinstance(proxy, dict):
        raise UnsupportedProxy("节点不是字典")
    ptype = str(proxy.get("type") or "").lower()
    converter = CONVERTERS.get(ptype)
    if not converter:
        raise UnsupportedProxy(f"sing-box 不支持协议 {ptype or '(空)'}")
    if not proxy.get("server"):
        raise UnsupportedProxy("缺少 server")
    if ptype not in ("wireguard", "hysteria", "hysteria2") and not proxy.get("port"):
        raise UnsupportedProxy("缺少 port")
    if ptype in ("hysteria", "hysteria2") and not proxy.get("port") and not (proxy.get("ports") or proxy.get("mport")):
        raise UnsupportedProxy("Hysteria 缺少 port 或 ports")
    try:
        ob = converter(proxy, warnings)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, UnsupportedProxy):
            raise
        raise UnsupportedProxy(f"字段格式无效: {exc}") from exc
    return ob if ptype == "wireguard" else _dial_fields(proxy, ob)


def convert_clash_proxies(proxies):
    """批量转换。返回 {"nodes": [...], "skipped": [(name, reason)], "warnings": [(name, msg)]}。"""
    nodes, skipped, warnings = [], [], []
    seen = set()
    for proxy in proxies:
        name = (proxy or {}).get("name") if isinstance(proxy, dict) else None
        node_warnings = []
        try:
            node = clash_to_singbox(proxy, node_warnings)
        except UnsupportedProxy as exc:
            skipped.append((name, str(exc)))
            continue
        if node["tag"] in seen:
            skipped.append((name, "节点名称重复"))
            continue
        seen.add(node["tag"])
        nodes.append(node)
        warnings.extend((name, msg) for msg in node_warnings)
    return {"nodes": nodes, "skipped": skipped, "warnings": warnings}


def migrate_legacy_wireguard(outbound):
    """sing-box 旧 wireguard outbound（1.13 已移除）→ 1.11+ wireguard endpoint；其余节点原样返回。"""
    if not isinstance(outbound, dict) or outbound.get("type") != "wireguard" or "address" in outbound:
        return outbound
    ep = {"type": "wireguard", "tag": outbound.get("tag"),
          "address": _as_list(outbound.get("local_address")),
          "private_key": outbound.get("private_key")}
    _set(ep, "mtu", outbound.get("mtu"))
    legacy_peers = outbound.get("peers") or [outbound]
    peers = []
    for src in legacy_peers:
        peer = {"address": src.get("server") or outbound.get("server"),
                "port": src.get("server_port") or outbound.get("server_port"),
                "public_key": src.get("public_key") or src.get("peer_public_key") or outbound.get("peer_public_key"),
                "allowed_ips": _as_list(src.get("allowed_ips")) or ["0.0.0.0/0", "::/0"]}
        _set(peer, "pre_shared_key", src.get("pre_shared_key"))
        _set(peer, "reserved", src.get("reserved") or outbound.get("reserved"))
        peers.append(peer)
    ep["peers"] = peers
    for key in ("detour", "domain_resolver", "bind_interface", "routing_mark"):
        _set(ep, key, outbound.get(key))
    return ep
