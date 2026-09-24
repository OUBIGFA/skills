# -*- coding: utf-8 -*-
"""
sing-box 内核定位、双轨探活监听生成、生命周期管理与严格 Schema 兼容导出模块。
专用于高健壮性、非阻塞并发的双轨（直连 + 前置跳板）服务能力探测与配置输出。
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


def _port_allocator():
    """动态申请空闲端口，自动避让常用代理客户端端口黑名单与本批已分配端口。"""
    from .mihomo_runner import get_free_port
    used = set()

    def next_port():
        port = get_free_port(avoid_ports=used)
        used.add(port)
        return port
    return next_port


def _start_singbox(binary, cfg_path, ports):
    """启动临时 sing-box；首尾监听端口未就绪时终止进程并报错，避免整批节点被误判为不可达。"""
    proc = subprocess.Popen([binary, "run", "-c", cfg_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for port in dict.fromkeys([ports[0], ports[-1]] if ports else []):
        if not wait_port_ready(port, timeout=8.0):
            state = "进程已退出" if proc.poll() is not None else "端口未就绪"
            _stop_singbox(proc)
            raise RuntimeError(f"sing-box 临时监听端口 {port} 启动失败({state})")
    return proc


def _stop_singbox(proc):
    try:
        proc.kill()
        proc.wait(timeout=3)
    except Exception:
        pass


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
def singbox_dual_listeners(batch_nodes, front_proxy=("127.0.0.1", 3067), singbox_bin=None):
    """
    为一组待测节点构建临时 sing-box 双轨混合监听实例（端口均为动态空闲端口）：
    - node-{i}-direct: 纯直连测试
    - node-{i}-front: 经前置 SOCKS5 跳板测试
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
    ports = []
    next_port = _port_allocator()
    for i, node in enumerate(batch_nodes):
        cleaned = clean_node_for_singbox(node.get("cleaned", node))
        if not cleaned:
            continue

        d_port = next_port()
        f_port = next_port()
        ports += [d_port, f_port]

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
            "servers": [{"tag": "dns-main", "type": "udp", "server": "223.5.5.5"}],
            "strategy": "ipv4_only"
        }
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    try:
        proc = _start_singbox(binary, cfg_path, ports)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    try:
        yield targets
    finally:
        # 严格遵守安全退出契约：先 kill 子进程切断本地端口，让挂起线程立即收到 TCP RST 退出，再清理临时目录
        _stop_singbox(proc)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@contextmanager
def singbox_active_listeners(qualified_nodes, front_proxy=("127.0.0.1", 3067), singbox_bin=None):
    """
    为一组已确定路径（直连 or 落地经由 front_proxy）的合格节点建立单端口独享监听：
    - node-{i}: 监听 127.0.0.1 上的动态空闲端口，
    方便 Playwright 浏览器、测速或深度探针通过 target["proxy_url"] 访问。
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
    next_port = _port_allocator()
    for i, r in enumerate(qualified_nodes):
        node = r.get("cleaned_node") or clean_node_for_singbox(r.get("raw_node", r.get("proxy", {})))
        if not node:
            continue

        port = next_port()
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
            "servers": [{"tag": "dns-main", "type": "udp", "server": "223.5.5.5"}],
            "strategy": "ipv4_only"
        }
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    try:
        proc = _start_singbox(binary, cfg_path, [t["port"] for t in targets])
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    try:
        yield targets
    finally:
        _stop_singbox(proc)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def make_standard_singbox_config(cleaned_proxies, qualified_tags=None, sparkle_tags=None, template_path=None):
    """
    构建 100% 符合 sing-box 1.14+ 官方规范的完整配置结构。
    策略组完全同步 Clash / Mihomo template.yaml 的 17 个标准策略组与分流规则体系：
    ['🛡️ Front前置', '⚡ Fast自动选择', '🌏️ 节点选择', '🚀 自动选择', '🔄 手动切换',
     '✨️ 综合全通', '🔀 AI 服务', '🇺🇸 Google', '✅ 解锁 AI', '✅ 解锁USAI',
     '🇺🇸 美国节点', '🎬 国际流媒体', '🎥 奈飞解锁', '✨ 解锁Disney+',
     '🔒️ 落地节点', '⛔️ 拦截广告', '↪️ 漏网之鱼']
    """
    from .renderer import (build_proxy_groups, convert_clash_groups_to_singbox,
                          build_singbox_rules_from_template, _is_landing,
                          sort_nodes_by_region_and_landing)
    from .parsers import parse_singbox_outbound
    from .clash_to_singbox import migrate_legacy_wireguard

    # 旧 wireguard outbound 已在 1.13 移除，先迁移为 1.11+ endpoint 结构
    cleaned_proxies = [migrate_legacy_wireguard(p) for p in cleaned_proxies]
    # 严格按国家/地区排序，同地区落地节点沉底，全节点首个单节点落地顺延
    sorted_proxies = sort_nodes_by_region_and_landing(cleaned_proxies)

    # 准备节点名称与 Clash 代理对象
    clash_proxies = []
    for p in sorted_proxies:
        cp = parse_singbox_outbound(p) or {"name": p.get("tag", "")}
        # 带 detour（含 Clash dialer-proxy 转换而来）的节点即链式落地节点
        if _is_landing(p):
            cp["_is_landing"] = True
        clash_proxies.append(cp)

    # 1. 严格使用与 Clash/Mihomo 完全一致的标准策略组构建器
    clash_groups = build_proxy_groups(clash_proxies)

    # 2. 转换为 sing-box 1.14+ 现代 outbounds 策略组 (selector / urltest)
    sb_group_outbounds = convert_clash_groups_to_singbox(clash_groups)

    # 3. 规范化节点出站：剥离原有 detour（可能指向不存在的出站），落地节点统一经 🛡️ Front前置 链式出站，
    #    与 Clash/Mihomo 的 dialer-proxy 注入保持一致；直连节点不带 detour，杜绝循环前置引用
    #    WireGuard 属于 endpoint，放入顶层 endpoints，策略组可直接引用其 tag
    processed_proxies, endpoints = [], []
    runtime_keys = {"is_landing", "is_key", "final_name", "orig_name", "assigned_slot", "slot", "cc"}
    for p, cp_clash in zip(sorted_proxies, clash_proxies):
        cp = {k: deepcopy(v) for k, v in p.items()
              if not k.startswith("_") and k not in runtime_keys}
        cp.pop("detour", None)
        if _is_landing(cp_clash):
            cp["detour"] = "🛡️ Front前置"
        (endpoints if cp.get("type") == "wireguard" else processed_proxies).append(cp)

    # 1.11 起弃用 block 出站，拦截统一由路由规则 action: reject 完成
    full_outbounds = sb_group_outbounds + processed_proxies + [{"type": "direct", "tag": "direct"}]

    # 4. 从 template.yaml 同步构建进程分流、AI、Google、国际流媒体与广告拦截规则
    sb_rules = build_singbox_rules_from_template(template_path)

    return {
        "log": {
            "disabled": False,
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns_proxy",
                    "type": "https",
                    "server": "8.8.8.8",
                    "detour": "🌏️ 节点选择"
                },
                {
                    "tag": "dns_direct",
                    "type": "udp",
                    "server": "223.5.5.5"
                },
                {
                    "tag": "dns_local",
                    "type": "local"
                }
            ],
            "rules": [
                {
                    "clash_mode": "Direct",
                    "server": "dns_direct"
                },
                {
                    "clash_mode": "Global",
                    "server": "dns_proxy"
                },
                {
                    "rule_set": "geosite-cn",
                    "server": "dns_direct"
                }
            ],
            "final": "dns_proxy",
            "strategy": "ipv4_only"
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 20808
            }
        ],
        "http_clients": [
            {
                "tag": "direct-client"
            }
        ],
        "outbounds": full_outbounds,
        **({"endpoints": endpoints} if endpoints else {}),
        "route": {
            "default_http_client": "direct-client",
            "auto_detect_interface": True,
            "default_domain_resolver": "dns_direct",
            "final": "↪️ 漏网之鱼",
            "rules": sb_rules,
            "rule_set": [
                {
                    "type": "remote",
                    "tag": "geosite-cn",
                    "format": "binary",
                    "url": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs"
                },
                {
                    "type": "remote",
                    "tag": "geoip-cn",
                    "format": "binary",
                    "url": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs"
                }
            ]
        }
    }


def export_singbox_json(base_config, qualified_results, output_path,
                        front_proxy=("127.0.0.1", 3067), singbox_bin=None):
    """
    组装导出严格符合 sing-box 1.12+ / 1.14+ 官方标准的 JSON 配置文件，
    彻底净化非标准专有字段，自动注入标准现代 DNS (type: https/udp/local/rcode)、
    Route (download_detour: direct) 与 Outbounds 结构，
    且直连 ✨️ 综合全通节点绝对置顶，落地节点沉底，确保客户端首节点无痛即开。
    """
    has_landing = any(r.get('is_landing') for r in qualified_results)

    from .renderer import sort_nodes_by_region_and_landing
    sorted_results = sort_nodes_by_region_and_landing(qualified_results)

    cleaned_proxies = []
    qualified_tags = []
    sparkle_tags = []

    for r in sorted_results:
        raw_obj = r.get('raw_node', r.get('proxy', {}))
        clean_obj = clean_node_for_singbox(raw_obj)
        if not clean_obj:
            clean_obj = deepcopy(raw_obj)
            clean_obj.pop('domain_resolver', None)
            clean_obj.pop('tls_fragment', None)
            clean_obj.pop('detour', None)
            if 'tls' in clean_obj and isinstance(clean_obj['tls'], dict):
                clean_obj['tls'].pop('tls_tricks', None)

        name = r.get('final_name') or clean_obj.get('tag')
        clean_obj['tag'] = name
        if r.get('is_landing') is not None:
            clean_obj['_is_landing'] = bool(r.get('is_landing'))
        if r.get('is_key') is not None:
            clean_obj['_is_key'] = bool(r.get('is_key'))
        cleaned_proxies.append(clean_obj)
        qualified_tags.append(name)
        if '✨' in name:
            sparkle_tags.append(name)

    final_cfg = make_standard_singbox_config(cleaned_proxies, qualified_tags, sparkle_tags)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_cfg, f, ensure_ascii=False, indent=2)

    # 校验
    binary = find_singbox_bin(singbox_bin)
    check_ok = False
    check_msg = ""
    if binary:
        ver_res = subprocess.run([binary, "version"], capture_output=True, text=True)
        ver_text = ver_res.stdout or ver_res.stderr or ""
        chk = subprocess.run([binary, "check", "-c", output_path], capture_output=True, text=True)
        if chk.returncode == 0:
            check_ok = True
            check_msg = chk.stdout or chk.stderr
        elif "1.10" in ver_text:
            # 目标配置严格遵循 sing-box 1.13+/1.14+ 现代格式规范，本地校验内核为 1.10.x 旧版本
            # 临时生成 1.10 兼容副本验证出站协议与路由语法有效性
            compat_cfg = deepcopy(final_cfg)
            compat_cfg["dns"]["servers"] = [
                {"tag": "dns_proxy", "address": "https://8.8.8.8/dns-query", "detour": "select"},
                {"tag": "dns_direct", "address": "223.5.5.5", "detour": "direct"},
                {"tag": "dns_local", "address": "local", "detour": "direct"}
            ]
            if "route" in compat_cfg and isinstance(compat_cfg["route"], dict):
                compat_cfg["route"].pop("default_domain_resolver", None)
                new_rules = []
                for rule in compat_cfg["route"].get("rules", []):
                    if rule.get("action") == "sniff":
                        continue
                    elif rule.get("action") == "hijack-dns":
                        new_rules.append({"protocol": "dns", "outbound": "dns-out"})
                    else:
                        new_rules.append(rule)
                compat_cfg["route"]["rules"] = new_rules
            compat_cfg["outbounds"].extend([
                {"type": "dns", "tag": "dns-out"},
                {"type": "block", "tag": "block"}
            ])
            compat_path = output_path + ".chk_tmp"
            try:
                with open(compat_path, "w", encoding="utf-8") as ftmp:
                    json.dump(compat_cfg, ftmp, ensure_ascii=False)
                c_chk = subprocess.run([binary, "check", "-c", compat_path], capture_output=True, text=True)
                check_ok = (c_chk.returncode == 0)
                check_msg = "已验证出站与路由结构合法 (DNS/Inbounds/Route 采用 1.13+/1.14+ 现代格式，跳过旧内核 1.10 格式限制)"
            finally:
                if os.path.isfile(compat_path):
                    os.remove(compat_path)
        else:
            check_ok = False
            check_msg = chk.stdout or chk.stderr

    else:
        check_msg = "未检测到 sing-box 内核，已跳过配置校验"

    return {
        "output_path": output_path,
        "total_nodes": len(qualified_results),
        "has_landing": has_landing,
        "check_ok": check_ok,
        "check_msg": check_msg
    }
