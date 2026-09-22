# -*- coding: utf-8 -*-
"""
sing-box 内核定位、双轨探活监听生成、生命周期管理与严格 Schema 兼容导出模块。
专用于高健壮性、非阻塞并发的双轨（直连 + Karing/前置跳板）服务能力探测与配置输出。
"""
import os
import sys
import json
import time
import socket
import shutil
import tempfile
import subprocess
from copy import deepcopy
from contextlib import contextmanager

SUPPORTED_TYPES = {'vless', 'vmess', 'trojan', 'shadowsocks', 'hysteria2', 'tuic', 'http', 'socks', 'wireguard', 'hysteria'}
STRIP_OUTBOUND_FIELDS = {'domain_resolver', 'tls_fragment', 'detour'}
VALID_FINGERPRINTS = {'chrome', 'firefox', 'safari', 'ios', 'android', 'edge', '360', 'qq', 'random'}


def find_singbox_bin(custom_path=None):
    """寻找可用的 sing-box 可执行文件。"""
    if custom_path and os.path.isfile(custom_path):
        return os.path.abspath(custom_path)

    env_bin = os.environ.get("SINGBOX_BIN")
    if env_bin and os.path.isfile(env_bin):
        return os.path.abspath(env_bin)

    candidates = [
        r"E:\_BIGFAFree\_code\_Mywork\singbox sub\bin\sing-box.exe",
        os.path.join(os.getcwd(), "bin", "sing-box.exe"),
        os.path.join(os.getcwd(), "bin", "sing-box"),
        os.path.join(os.getcwd(), "_temp", "sing-box.exe"),
        os.path.join(os.getcwd(), "_temp", "sing-box"),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.abspath(cand)

    found = shutil.which("sing-box") or shutil.which("sing-box.exe")
    if found:
        return os.path.abspath(found)

    return None


def clean_node_for_singbox(node):
    """
    清洗待测节点，过滤掉 sing-box 1.10+ 不支持的协议或传输层，
    并剔除可能导致 FATAL 的快照定制字段（tls_tricks、fingerprint: custom 等）。
    """
    if not isinstance(node, dict):
        return None
    t = str(node.get("type", "")).lower()
    if t not in SUPPORTED_TYPES:
        return None

    tr = node.get("transport", {})
    if tr and isinstance(tr, dict) and tr.get("type") in ("xhttp", "splithttp"):
        return None

    clean = {k: v for k, v in node.items() if k not in STRIP_OUTBOUND_FIELDS}
    if 'tls' in clean and isinstance(clean['tls'], dict):
        clean['tls'] = deepcopy(clean['tls'])
        clean['tls'].pop('tls_tricks', None)
        utls = clean['tls'].get('utls')
        if isinstance(utls, dict) and utls.get('fingerprint'):
            fp = str(utls.get('fingerprint', '')).lower()
            if fp not in VALID_FINGERPRINTS:
                clean['tls']['utls']['fingerprint'] = 'chrome'
    return clean


def wait_port_ready(port, timeout=3.0):
    """等待本地端口开启监听"""
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.05)
    return False


@contextmanager
def singbox_dual_listeners(batch_nodes, front_proxy=("127.0.0.1", 3067),
                           singbox_bin=None, base_port=26000):
    """
    为一组待测节点构建临时 sing-box 双轨混合监听实例：
    - node-{i}-direct: 纯直连测试 (监听 127.0.0.1:base_port + 2*i)
    - node-{i}-front: 经前置 SOCKS5 跳板测试 (监听 127.0.0.1:base_port + 2*i + 1)
    """
    binary = find_singbox_bin(singbox_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 sing-box 可执行文件，请确认安装或指定路径。")

    if not batch_nodes:
        yield []
        return

    tmp_dir = tempfile.mkdtemp(prefix="sb_probe_batch_")
    cfg_path = os.path.join(tmp_dir, "config.json")

    inbounds = []
    rules = []
    outs = []

    # 1. 注入前置出站
    front_host, front_port = front_proxy[0], int(front_proxy[1])
    outs.append({
        "type": "socks",
        "tag": "front-anchor",
        "server": front_host,
        "server_port": front_port
    })

    targets = []
    for i, node in enumerate(batch_nodes):
        cleaned = clean_node_for_singbox(node.get("cleaned", node))
        if not cleaned:
            continue

        d_port = base_port + 2 * i
        f_port = base_port + 2 * i + 1

        # 直连出站
        cd = deepcopy(cleaned)
        cd['tag'] = f"node-{i}-direct"
        outs.append(cd)
        inbounds.append({
            "type": "mixed",
            "tag": f"in-{i}-d",
            "listen": "127.0.0.1",
            "listen_port": d_port
        })
        rules.append({"inbound": [f"in-{i}-d"], "outbound": f"node-{i}-direct"})

        # 前置跳板出站
        cf = deepcopy(cleaned)
        cf['tag'] = f"node-{i}-front"
        cf['detour'] = "front-anchor"
        outs.append(cf)
        inbounds.append({
            "type": "mixed",
            "tag": f"in-{i}-f",
            "listen": "127.0.0.1",
            "listen_port": f_port
        })
        rules.append({"inbound": [f"in-{i}-f"], "outbound": f"node-{i}-front"})

        targets.append({
            "index": i,
            "raw": node.get("raw", node),
            "cleaned": cleaned,
            "direct_proxies": {"http": f"http://127.0.0.1:{d_port}", "https": f"http://127.0.0.1:{d_port}"},
            "front_proxies": {"http": f"http://127.0.0.1:{f_port}", "https": f"http://127.0.0.1:{f_port}"}
        })

    outs.append({"type": "direct", "tag": "direct-out"})
    cfg = {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outs,
        "route": {"rules": rules, "final": "direct-out"},
        "dns": {
            "servers": [{"tag": "dns-main", "address": "223.5.5.5", "detour": "direct-out"}],
            "strategy": "ipv4_only"
        }
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # 启动进程
    proc = subprocess.Popen([binary, "run", "-c", cfg_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_port_ready(base_port, timeout=3.0)

    try:
        yield targets
    finally:
        # 严格遵守安全退出契约：先 kill 子进程切断本地端口，让挂起线程立即收到 TCP RST 退出，再清理临时目录
        try:
            proc.kill()
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


@contextmanager
def singbox_active_listeners(qualified_nodes, front_proxy=("127.0.0.1", 3067),
                            singbox_bin=None, base_port=27000):
    """
    为一组已确定路径（直连 or 落地经由 front_proxy）的合格节点建立单端口独享监听：
    - node-{i}: 监听 127.0.0.1:base_port + i
    方便 Playwright 浏览器或深度探针直接通过 127.0.0.1:base_port + i 访问。
    """
    binary = find_singbox_bin(singbox_bin)
    if not binary:
        raise RuntimeError("未检测到可用的 sing-box 可执行文件，请确认安装或指定路径。")

    if not qualified_nodes:
        yield []
        return

    tmp_dir = tempfile.mkdtemp(prefix="sb_active_batch_")
    cfg_path = os.path.join(tmp_dir, "config.json")

    inbounds = []
    rules = []
    outs = []

    front_host, front_port = front_proxy[0], int(front_proxy[1])
    outs.append({
        "type": "socks",
        "tag": "front-anchor",
        "server": front_host,
        "server_port": front_port
    })

    targets = []
    for i, r in enumerate(qualified_nodes):
        node = r.get("cleaned_node") or clean_node_for_singbox(r.get("raw_node", r.get("proxy", {})))
        if not node:
            continue

        port = base_port + i
        cn = deepcopy(node)
        cn["tag"] = f"node-{i}"
        if r.get("is_landing"):
            cn["detour"] = "front-anchor"
        else:
            cn.pop("detour", None)
        outs.append(cn)

        inbounds.append({
            "type": "mixed",
            "tag": f"in-{i}",
            "listen": "127.0.0.1",
            "listen_port": port
        })
        rules.append({"inbound": [f"in-{i}"], "outbound": f"node-{i}"})

        targets.append({
            "index": i,
            "result_ref": r,
            "port": port,
            "proxy_url": f"http://127.0.0.1:{port}"
        })

    outs.append({"type": "direct", "tag": "direct-out"})
    cfg = {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outs,
        "route": {"rules": rules, "final": "direct-out"},
        "dns": {
            "servers": [{"tag": "dns-main", "address": "223.5.5.5", "detour": "direct-out"}],
            "strategy": "ipv4_only"
        }
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    proc = subprocess.Popen([binary, "run", "-c", cfg_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_port_ready(base_port, timeout=3.0)

    try:
        yield targets
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def export_singbox_json(base_config, qualified_results, output_path,
                        front_proxy=("127.0.0.1", 3067), singbox_bin=None):
    """
    组装导出严格符合 sing-box 1.10+ 标准的 JSON 配置文件，
    自动挂载落地前置跳板、规范化出站引用并执行 sing-box check 验证。
    """
    final_outbounds = []
    has_landing = any(r.get('is_landing') for r in qualified_results)

    qualified_tags = []
    for r in qualified_results:
        node_obj = deepcopy(r.get('raw_node', r.get('proxy', {})))
        name = r.get('final_name') or node_obj.get('tag')
        node_obj['tag'] = name
        node_obj.pop('domain_resolver', None)
        node_obj.pop('tls_fragment', None)
        node_obj.pop('detour', None)

        final_outbounds.append(node_obj)
        qualified_tags.append(name)

    # 继承原模版的 selector、urltest、direct、block
    for ob in base_config.get('outbounds', []):
        t = ob.get('type')
        if t in ('urltest', 'selector'):
            ob_copy = deepcopy(ob)
            ob_copy['outbounds'] = list(qualified_tags)
            final_outbounds.append(ob_copy)
        elif t in ('direct', 'block', 'dns'):
            final_outbounds.append(deepcopy(ob))

    final_cfg = deepcopy(base_config)
    final_cfg['outbounds'] = final_outbounds

    # 清洗 1.10+ 不支持的 experimental.statistics
    if 'experimental' in final_cfg and isinstance(final_cfg['experimental'], dict):
        final_cfg['experimental'].pop('statistics', None)

    # 清洗老旧 DNS 语法的无效字段
    for s in final_cfg.get('dns', {}).get('servers', []):
        s.pop('domain_resolver', None)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_cfg, f, ensure_ascii=False, indent=2)

    # 校验
    binary = find_singbox_bin(singbox_bin)
    check_ok = False
    check_msg = ""
    if binary:
        chk = subprocess.run([binary, "check", "-c", output_path], capture_output=True, text=True)
        check_ok = (chk.returncode == 0)
        check_msg = chk.stdout or chk.stderr

    return {
        "output_path": output_path,
        "total_nodes": len(qualified_results),
        "has_landing": has_landing,
        "check_ok": check_ok,
        "check_msg": check_msg
    }
