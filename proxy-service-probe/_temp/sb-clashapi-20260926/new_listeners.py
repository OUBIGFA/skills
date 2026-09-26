def _port_allocator():
    """动态申请空闲端口，自动避让常用代理客户端端口黑名单与本批已分配端口。"""
    used = set()

    def next_port():
        port = get_free_port(avoid_ports=used)
        used.add(port)
        return port
    return next_port


def apply_physical_relay(outbounds, relay):
    """
    本机 TUN 接管系统路由时，让节点出站 (含节点前置) 经绑定物理网卡的本地 SOCKS 中继出网。
    sing-box 1.14 在 Windows 上开着外部 TUN 时 bind_interface/default_interface 不生效 (实测连不通)，
    不经中继则测试流量会先经过本机客户端正在使用的节点，测速与属地都会失真。
    已有 detour 的落地节点经前置出网；回环地址上的出站无需中继。
    """
    if not relay:
        return outbounds
    for out in outbounds:
        if out.get("detour") or out.get("type") in ("direct", "wireguard"):
            continue
        if str(out.get("server", "")).startswith("127."):
            continue
        out["detour"] = "physical-relay"
    outbounds.append({"type": "socks", "tag": "physical-relay", "server": relay[0], "server_port": int(relay[1])})
    return outbounds


def _listener_config(entries, relay=None):
    """
    entries: [(key, 节点出站, 前置出站或 None)]。每个节点一个 127.0.0.1 mixed 入站，按入站路由到该节点；
    经前置的节点以 detour 链到前置，同一前置只加载一次。relay 见 apply_physical_relay。返回 (配置, {key: 端口})。
    """
    inbounds, outbounds, rules, ports, fronts = [], [], [], {}, {}
    next_port = _port_allocator()
    for idx, (key, node, front) in enumerate(entries):
        out = deepcopy(node)
        out["tag"] = f"node_{idx}"
        out.pop("detour", None)
        if front is not None:
            if id(front) not in fronts:
                anchor = deepcopy(front)
                anchor["tag"] = f"front_{len(fronts)}"
                anchor.pop("detour", None)
                fronts[id(front)] = anchor["tag"]
                outbounds.append(anchor)
            out["detour"] = fronts[id(front)]
        outbounds.append(out)
        ports[key] = next_port()
        inbounds.append({"type": "mixed", "tag": f"in_{idx}", "listen": "127.0.0.1", "listen_port": ports[key]})
        rules.append({"inbound": [f"in_{idx}"], "outbound": out["tag"]})
    apply_physical_relay(outbounds, relay)
    outbounds.append({"type": "direct", "tag": "direct-out"})
    config = {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "final": "direct-out"},
        "dns": {
            "servers": [{"tag": "dns-main", "type": "udp", "server": "223.5.5.5"}],
            "strategy": "ipv4_only"
        }
    }
    return config, ports


@contextmanager
def _run_singbox(binary, config, ports, monitor=None):
    """
    启动临时 sing-box 并等待端口就绪。给出 monitor (TrafficMonitor) 时开启仅本机可达、带随机密钥的
    Clash API，接入与 mihomo 相同的 /traffic 流量统计 (sing-box 官方构建含 with_clash_api)。
    """
    config = dict(config)
    controller = None
    if monitor is not None:
        controller = (get_free_port(avoid_ports=ports), secrets.token_hex(12))
        config["experimental"] = {"clash_api": {"external_controller": f"127.0.0.1:{controller[0]}",
                                                "secret": controller[1]}}
    with kernel_process("sing-box",
                        lambda tmp_dir, cfg_path: [binary, "run", "-D", tmp_dir, "--disable-color", "-c", cfg_path],
                        "config.json", json.dumps(config, ensure_ascii=False, indent=2), ports,
                        controller=controller, monitor=monitor):
        yield


def start_singbox_group(stack, entries, singbox_bin=None, relay=None, monitor=None, shard_size=64):
    """
    在 ExitStack 中为 entries 启动临时 sing-box 监听，存活到 stack 关闭为止 (供测活、服务检测、测速各阶段复用)。
    分片与被拒节点的二分隔离与 mihomo 相同 (见 start_isolated)。返回 ({key: 端口}, {key: 失败原因})。
    """
    binary = find_singbox_bin(singbox_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 sing-box 可执行文件，请确认安装或指定路径。")

    def launch_group(group):
        config, group_ports = _listener_config(group, relay)
        return _run_singbox(binary, config, list(group_ports.values()), monitor=monitor), group_ports

    return start_isolated(stack, entries, launch_group, shard_size)


class SingboxKernel:
    """core.probe_flow 的 sing-box 内核适配器：交给内核的节点配置为清洗后的 sing-box 出站 (proxy["_singbox_outbound"])。"""
    label = "sing-box"

    def __init__(self, binary, relay=None):
        self.binary = binary
        self.relay = relay

    @staticmethod
    def node(row):
        return row["proxy"]["_singbox_outbound"]

    def start(self, stack, entries, monitor=None, shard_size=64):
        return start_singbox_group(stack, entries, singbox_bin=self.binary, relay=self.relay, monitor=monitor,
                                   shard_size=shard_size)


