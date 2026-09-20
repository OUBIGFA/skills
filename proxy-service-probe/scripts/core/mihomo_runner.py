# -*- coding: utf-8 -*-
"""Mihomo 内核定位、临时监听生成与生命周期管理。"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy

import yaml


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
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.abspath(cand)

    # 环境变量 PATH 中查找
    found = shutil.which("mihomo") or shutil.which("mihomo.exe")
    if found:
        return os.path.abspath(found)

    return None


def get_free_port():
    """获取一个未被占用的本地 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def wait_port_open(port, timeout=8.0):
    """等待本地端口开始接受 TCP 连接。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
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
    iface: 绑定的物理网卡（如 WLAN / 以太网），用于绕开本地 TUN 接管。
    mihomo_bin: 指定的内核可执行文件路径。

    yields: [(port, proxy, extra...), ...]
    """
    binary = find_mihomo_bin(mihomo_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 Mihomo 内核，请确认系统 PATH 或 _temp/mihomo.exe 存在。")

    if not items:
        yield []
        return

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

    tmp_dir = tempfile.mkdtemp(prefix="mihomo_probe_")
    cfg_path = os.path.join(tmp_dir, "config.yaml")

    # 分配端口与构造监听器
    targets = []
    listeners = []
    proxies_to_load = []

    # 规范化名称防冲突
    front_name = "🛡️_Front_Anchor"
    if is_landing and anchor_front:
        front_proxy = deepcopy(anchor_front)
        front_proxy["name"] = front_name
        front_proxy.pop("dialer-proxy", None)
        proxies_to_load.append(front_proxy)

    for idx, (proxy, rest) in enumerate(normalized):
        port = get_free_port()
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

    # 生成配置
    config_dict = {
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
        "proxies": proxies_to_load,
        "rules": ["MATCH,DIRECT"]
    }

    if iface:
        config_dict["interface-name"] = iface

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f, allow_unicode=True)

    proc = None
    try:
        proc = subprocess.Popen(
            [binary, "-d", tmp_dir, "-f", cfg_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # 检验首尾端口是否就绪
        test_ports = [targets[0][0]]
        if len(targets) > 1:
            test_ports.append(targets[-1][0])

        for p in test_ports:
            if not wait_port_open(p, timeout=12.0):
                raise TimeoutError(f"Mihomo 临时监听端口 {p} 启动超时")

        yield targets

    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
