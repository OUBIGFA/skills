# -*- coding: utf-8 -*-
"""Mihomo 内核定位、临时监听生成与生命周期管理 (包含多客户端防冲突与物理网卡防 TUN 劫持)。"""
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy

import yaml

# 常见代理客户端默认端口黑名单 (杜绝与本地正在运行的 Karing, Sing-box, Clash/Mihomo, Xray 产生端口冲突)
BLACKLIST_PORTS = frozenset({
    53, 1053, 2080, 2081, 3067, 5353, 7890, 7891, 7892, 7893, 7894, 7895, 9090, 10808, 10809, 24999
})

SKILL_CORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core")


def find_mihomo_bin(custom_path=None):
    """寻找可用的 Mihomo 可执行文件。"""
    if custom_path and os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
        return os.path.abspath(custom_path)

    env_bin = os.environ.get("MIHOMO_BIN")
    if env_bin and os.path.isfile(env_bin):
        return os.path.abspath(env_bin)

    # 优先检查工作目录或上级目录的 _temp/mihomo.exe 或 _temp/mihomo
    candidates = [
        os.path.join(os.getcwd(), "_temp", "mihomo.exe"),
        os.path.join(os.getcwd(), "_temp", "mihomo"),
        os.path.join(os.path.dirname(os.getcwd()), "_temp", "mihomo.exe"),
        os.path.join(os.path.dirname(os.getcwd()), "_temp", "mihomo"),
        # 技能自带内核: Windows 用 core/mihomo.exe，Linux (如 GitHub Actions) 用 core/mihomo
        os.path.join(SKILL_CORE_DIR, "mihomo.exe" if sys.platform == "win32" else "mihomo"),
    ]
    for cand in candidates:
        if os.path.isfile(cand) and (sys.platform == "win32" or os.access(cand, os.X_OK)):
            return os.path.abspath(cand)

    # 环境变量 PATH 中查找
    found = shutil.which("mihomo") or shutil.which("mihomo.exe")
    if found:
        return os.path.abspath(found)

    return None


def get_free_port(avoid_ports=None):
    """获取一个未被占用的本地 TCP 端口，自动避开常用客户端默认端口与已分配端口。"""
    avoid = set(avoid_ports or ()) | BLACKLIST_PORTS
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = s.getsockname()[1]
            if port not in avoid:
                return port
    return port


def detect_physical_interface():
    """
    自动检测当前联网的物理网卡名称 (例如 WLAN 或 以太网)。
    避开 Karing、Sing-box、Clash 等客户端创建的虚拟 TUN 网卡。
    """
    env_iface = os.environ.get("FREENODE_TEST_INTERFACE") or os.environ.get("PROXY_PROBE_INTERFACE")
    if env_iface:
        return env_iface.strip()

    if sys.platform != "win32":
        return None

    try:
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty Name"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                name = line.strip()
                if not name:
                    continue
                # 排除 TUN / 虚拟网卡特征
                if not re.search(r'TUN|Virtual|TAP|Sing-box|Karing|Clash|Tailscale|VPN|Loopback|vEthernet', name, re.IGNORECASE):
                    return name
    except Exception:
        pass

    return None


def wait_port_open(port, timeout=8.0, proc=None):
    """等待本地端口开始接受 TCP 连接；给出 proc 时进程提前退出 (如配置被拒) 立即返回 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False


@contextmanager
def node_listeners(items, anchor_front=None, is_landing=False, iface=None, mihomo_bin=None):
    """
    为一组节点启动临时 Mihomo 混合监听。
    items: 可以是 proxy 字典列表，或 (proxy, extra) 元组列表。
    anchor_front: 落地节点使用的固定前置跳板节点字典。
    is_landing: 是否是落地链式测试。
    iface: 绑定的物理网卡（如 WLAN / 以太网），若未指定则尝试自动探测，用于绕开本地 TUN 接管。
    mihomo_bin: 指定的内核可执行文件路径。

    yields: [(port, proxy, extra...), ...]
    """
    binary = find_mihomo_bin(mihomo_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 Mihomo 内核，请确认系统 PATH 或 _temp/mihomo.exe 存在。")

    if not items:
        yield []
        return

    # 若未显式指定网卡，则尝试自动探测物理网卡以防 TUN 劫持
    effective_iface = iface or detect_physical_interface()

    # 解析元素
    normalized = []
    for item in items:
        if isinstance(item, tuple):
            proxy = item[0]
            rest = item[1:]
        else:
            proxy = item
            rest = ()
        normalized.append((proxy, rest))

    # 分配端口与构造监听器
    targets = []
    listeners = []
    proxies_to_load = []
    used_ports = set()

    # 规范化名称防冲突
    front_name = "🛡️_Front_Anchor"
    if is_landing and anchor_front:
        front_proxy = deepcopy(anchor_front)
        front_proxy["name"] = front_name
        front_proxy.pop("dialer-proxy", None)
        proxies_to_load.append(front_proxy)

    for idx, (proxy, rest) in enumerate(normalized):
        port = get_free_port(avoid_ports=used_ports)
        used_ports.add(port)
        proxy_copy = deepcopy(proxy)
        unique_name = f"node_{idx}_{proxy_copy.get('name', 'unnamed')}"
        proxy_copy["name"] = unique_name

        if is_landing and anchor_front:
            proxy_copy["dialer-proxy"] = front_name
        else:
            proxy_copy.pop("dialer-proxy", None)

        proxies_to_load.append(proxy_copy)
        listeners.append({
            "name": f"mixed_{idx}",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": port,
            "proxy": unique_name
        })
        targets.append((port, proxy, *rest))

    ports = [targets[0][0]] + ([targets[-1][0]] if len(targets) > 1 else [])
    with _run_mihomo(binary, _mihomo_config(listeners, proxies_to_load, effective_iface), ports):
        yield targets


def _mihomo_config(listeners, proxies, iface):
    """临时实例配置: 强制关闭 TUN、仅监听 127.0.0.1；指定网卡时所有出站 (含 DIRECT) 绑定该网卡以绕开本机 TUN。"""
    config = {
        "port": 0,
        "socks-port": 0,
        "mode": "rule",
        "log-level": "warning",
        "allow-lan": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "tun": {"enable": False},
        "dns": {
            "enable": True,
            "listen": "127.0.0.1:0",
            "enhanced-mode": "fake-ip",
            "nameserver": ["https://223.5.5.5/dns-query", "https://1.1.1.1/dns-query"],
            "default-nameserver": ["223.5.5.5", "119.29.29.29"]
        },
        "listeners": listeners,
        "proxies": proxies,
        "rules": ["MATCH,DIRECT"]
    }
    if iface:
        config["interface-name"] = iface
    return config


class MihomoStartError(RuntimeError):
    """临时 mihomo 未能启动 (多为某个节点配置被内核拒绝)，message 带内核日志末尾。"""


def _log_tail(path, limit=300):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
    except OSError:
        return ""
    errors = [line for line in lines if "level=error" in line or "level=fatal" in line]
    return (errors or lines)[-1][-limit:] if (errors or lines) else ""


@contextmanager
def _run_mihomo(binary, config, ports, monitor=None):
    """
    写入配置并启动临时 mihomo，等待端口就绪；退出时先终止进程再删临时目录。
    给出 monitor (TrafficMonitor) 时开启仅本机可达、带随机密钥的 external-controller，并接入 /traffic 流量统计。
    """
    config = dict(config)
    controller = None
    if monitor is not None:
        controller = (get_free_port(avoid_ports=ports), secrets.token_hex(12))
        config["external-controller"] = f"127.0.0.1:{controller[0]}"
        config["secret"] = controller[1]
    tmp_dir = tempfile.mkdtemp(prefix="mihomo_probe_")
    cfg_path = os.path.join(tmp_dir, "config.yaml")
    log_path = os.path.join(tmp_dir, "mihomo.log")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True)

    proc = None
    log_file = open(log_path, "wb")
    try:
        proc = subprocess.Popen(
            [binary, "-d", tmp_dir, "-f", cfg_path],
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        for p in list(ports) + ([controller[0]] if controller else []):
            if not wait_port_open(p, timeout=12.0, proc=proc):
                detail = _log_tail(log_path)
                if proc.poll() is not None:
                    raise MihomoStartError(f"Mihomo 启动失败: {detail or f'退出码 {proc.returncode}'}")
                raise TimeoutError(f"Mihomo 临时监听端口 {p} 启动超时 {detail}".strip())
        if controller:
            monitor.watch(*controller)
        yield
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        log_file.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _listener_config(entries, iface):
    """
    entries: [(key, proxy, front)]，front 为 None 表示直连，否则为该节点经过的前置节点字典 (dialer-proxy 链)。
    每个节点一个 mixed 监听；同一前置只加载一次。返回 (配置, {key: 端口})。
    """
    proxies, listeners, ports, fronts = [], [], {}, {}
    used = set()
    for idx, (key, proxy, front) in enumerate(entries):
        node = deepcopy(proxy)
        node["name"] = f"node_{idx}"
        node.pop("dialer-proxy", None)
        if front is not None:
            front_id = id(front)
            if front_id not in fronts:
                front_copy = deepcopy(front)
                front_copy["name"] = f"front_{len(fronts)}"
                front_copy.pop("dialer-proxy", None)
                fronts[front_id] = front_copy["name"]
                proxies.append(front_copy)
            node["dialer-proxy"] = fronts[front_id]
        proxies.append(node)
        port = get_free_port(avoid_ports=used)
        used.add(port)
        ports[key] = port
        listeners.append({"name": f"mixed_{idx}", "type": "mixed", "listen": "127.0.0.1", "port": port,
                          "proxy": node["name"]})
    return _mihomo_config(listeners, proxies, iface), ports


def start_node_group(stack, entries, iface=None, mihomo_bin=None, monitor=None, shard_size=64):
    """
    在 ExitStack 中为 entries 启动临时 mihomo 监听，存活到 stack 关闭为止 (供测活、服务检测、测速各阶段复用)。
    每个实例最多承载 shard_size 个节点；某个节点配置被内核拒绝时整组二分重试，只把真正无法加载的节点单独剔除，
    不连累同组其他节点。返回 ({key: 端口}, {key: 失败原因})。
    """
    binary = find_mihomo_bin(mihomo_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 Mihomo 内核，请确认系统 PATH 或 _temp/mihomo.exe 存在。")
    effective_iface = iface or detect_physical_interface()
    ports, failed = {}, {}

    def launch(group):
        if not group:
            return
        config, group_ports = _listener_config(group, effective_iface)
        try:
            stack.enter_context(_run_mihomo(binary, config, list(group_ports.values()), monitor=monitor))
            ports.update(group_ports)
        except (MihomoStartError, TimeoutError) as error:
            if len(group) == 1:
                failed[group[0][0]] = f"内核无法加载该节点配置: {error}"
                return
            middle = len(group) // 2
            launch(group[:middle])
            launch(group[middle:])

    entries = list(entries)
    size = max(1, shard_size)
    for start in range(0, len(entries), size):
        launch(entries[start:start + size])
    return ports, failed


@contextmanager
def direct_listener(iface=None, mihomo_bin=None):
    """
    启动只走 DIRECT 的临时监听，出站与节点测试绑定同一物理网卡 (未指定时自动探测)。
    经它测得的是本机真实的物理直连出口：即使本机客户端开着 TUN/系统代理并正在使用某个节点，
    也不会把该节点的出口误当成本机出口。yields 监听端口。
    """
    binary = find_mihomo_bin(mihomo_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 Mihomo 内核，请确认系统 PATH 或 _temp/mihomo.exe 存在。")
    port = get_free_port()
    listeners = [{"name": "direct_baseline", "type": "mixed", "listen": "127.0.0.1", "port": port, "proxy": "DIRECT"}]
    with _run_mihomo(binary, _mihomo_config(listeners, [], iface or detect_physical_interface()), [port]):
        yield port
