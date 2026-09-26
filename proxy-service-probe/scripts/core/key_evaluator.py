# -*- coding: utf-8 -*-
"""
Key (优质前置跳板) 节点判定、评分与优选模块 (移植自 freenode 核心)。

核心准入原则:
1. 严禁 HTTP/HTTPS 与 SOCKS 协议作为 Key 前置跳板 (无加密易被干扰，且 CONNECT 无法中转非标端口落地节点)。
2. 落地节点 (_Lnd, _USAI, dialer-proxy) 绝不可作为前置跳板。
3. 必须具备可核实的真实代理出网出口，绝不可与本地跑机基线出口重合。
4. 必须通过完整持续下载测速 (默认: 稳态速度 >= 12 Mbps 且 2 秒滑动最低 >= 6 Mbps)。
5. 亚太核心地区 (HK/TW/JP/SG/KR) 优先，TLS-TCP 强加密协议优先。
"""
import math

from .speed_probe import DEFAULT_MIN_FLOOR_MBPS, DEFAULT_MIN_STABLE_MBPS, speed_qualified

# 严禁作为前置跳板的协议 (无法胜任落地中转)
KEY_DISALLOWED_PROTOCOLS = frozenset({"http", "https", "socks", "socks5"})

ASIA_CORE = frozenset({"HK", "TW", "JP", "SG", "KR"})

PROTOCOL_CLASS_SCORE = {
    "tls-tcp": 10,     # vless/vmess/trojan + TLS/Reality/gRPC, anytls
    "self-enc": 6,     # ss/shadowsocks, 无 TLS 的 vmess
    "udp": 3,          # hysteria2 / tuic
    "cdn-plain": 4,    # 无 TLS 的 vless ws
}


def is_key_protocol_allowed(proxy):
    """判定节点协议是否具备作为前置跳板的资格。"""
    if not isinstance(proxy, dict):
        return False
    proto = (proxy.get("type") or "").strip().lower()
    if proto in KEY_DISALLOWED_PROTOCOLS:
        return False
    # vless 未开 TLS 时仅允许 ws/grpc/http 等传输层
    if proto == "vless" and not proxy.get("tls") and not proxy.get("reality-opts"):
        network = (proxy.get("network") or "").lower()
        return network in ("ws", "grpc", "http")
    return True


def protocol_class(proxy):
    """计算协议类别"""
    t = (proxy.get("type") or "").lower()
    if t in ("hysteria2", "hysteria", "tuic"):
        return "udp"
    if t in ("ss", "shadowsocks"):
        return "self-enc"
    if t == "vmess":
        return "tls-tcp" if (proxy.get("tls") or proxy.get("reality-opts")) else "self-enc"
    if t == "vless":
        return "tls-tcp" if (proxy.get("tls") or proxy.get("reality-opts")) else "cdn-plain"
    return "tls-tcp"


def is_landing_role(proxy):
    """判断节点是否为落地角色"""
    if not isinstance(proxy, dict):
        return False
    name = proxy.get("name", "")
    return bool(
        proxy.get("_is_landing") or
        "_Lnd" in name or
        "_USAI" in name or
        "_家宽" in name or
        proxy.get("dialer-proxy")
    )


def evaluate_key_node(proxy, speed_result=None, egress_result=None, delay=None,
                      min_stable_mbps=DEFAULT_MIN_STABLE_MBPS, min_floor_mbps=DEFAULT_MIN_FLOOR_MBPS, is_landing=False):
    """
    对单个节点进行 Key 前置跳板资格判定与综合打分。
    is_landing: 流水线实测的落地角色 (直连不通、经前置才连通)；这类节点名称与配置里未必带落地标记，同样不能作前置。
    返回: (eligible: bool, score: float, reason: str)
    """
    if is_landing or is_landing_role(proxy):
        return False, 0.0, "落地节点不能作为前置跳板"

    proto = (proxy.get("type") or "").strip().lower()
    if not is_key_protocol_allowed(proxy):
        return False, 0.0, f"{proto.upper()}协议不支持作前置跳板"

    # 出口核验
    if egress_result:
        if egress_result.get("runner_ip_match"):
            return False, 0.0, "代理出口与跑机基线重合"
        if not egress_result.get("exit_ip") and not egress_result.get("observed_ips"):
            return False, 0.0, "代理出网未确认"

    # 测速硬门槛
    speed_mbps = 0.0
    if speed_result is not None:
        if not speed_qualified(speed_result, min_stable_mbps, min_floor_mbps):
            return False, 0.0, f"测速未达标(稳态 {speed_result.get('stable_mbps')}Mbps)"
        speed_mbps = float(speed_result.get("stable_mbps") or 0.0)
    else:
        # 未开启测速时不支持评选为 Key (必须有实测带宽证据)
        return False, 0.0, "缺少下载测速达标证据"

    # 综合质量评分 (满分约 50)
    score = 0.0

    # 1. 协议类别分 (3 ~ 10 分)
    p_class = protocol_class(proxy)
    score += PROTOCOL_CLASS_SCORE.get(p_class, 5)

    # 2. 亚太核心地区加分 (HK/TW/JP/SG/KR 优先)
    cc = proxy.get("_country_code") or ((egress_result.get("cc") or egress_result.get("country")) if egress_result else "")
    if cc in ASIA_CORE:
        score += 8.0

    # 3. 带宽速率对数分 (按超出合格门槛的倍数计分，0 ~ 15 分)
    if speed_mbps > 0:
        rate_ratio = speed_mbps / min_stable_mbps
        score += 15.0 * min(1.0, math.log10(rate_ratio + 1) / math.log10(20.0))

    # 4. 延迟加分 (0 ~ 10 分)
    if delay is not None and delay > 0:
        # 延迟低于 100ms 满分，350ms 以上 0 分
        score += 10.0 * max(0.0, min(1.0, 1.0 - (delay - 50.0) / 300.0))

    score = round(score, 1)
    return True, score, "ok"


def select_key_nodes(results, max_keys=10, per_country_cap=3, min_stable_mbps=DEFAULT_MIN_STABLE_MBPS,
                     min_floor_mbps=DEFAULT_MIN_FLOOR_MBPS):
    """
    从一组检测结果中优选 Key 节点，并根据国家配额进行分配。
    results 列表中每个 dict 应包含:
      - proxy: 节点字典
      - speed_result: 持续测速结果
      - egress_result: 出口检测结果
      - delay: 握手延迟
    """
    candidates = []
    for r in results:
        p = r["proxy"]
        eligible, score, reason = evaluate_key_node(
            proxy=p,
            speed_result=r.get("speed_result"),
            egress_result=r.get("egress_result") or r,
            delay=r.get("delay"),
            min_stable_mbps=min_stable_mbps,
            min_floor_mbps=min_floor_mbps,
            is_landing=bool(r.get("is_landing"))
        )
        r["is_key"] = False
        p["_is_key"] = False
        p.pop("_key_score", None)
        r["key_score"] = score
        r["key_reason"] = reason
        if eligible:
            candidates.append(r)

    # 优选排序: 评分降序 -> 测速中位数降序 -> 延迟升序
    candidates.sort(
        key=lambda item: (
            -float(item.get("key_score") or 0.0),
            -float((item.get("speed_result") or {}).get("stable_mbps") or 0.0),
            float(item.get("delay") or 9999.0)
        )
    )

    chosen = []
    country_counts = {}
    for r in candidates:
        if len(chosen) >= max_keys:
            r["key_reason"] = "总量配额已满"
            continue
        cc = r.get("cc") or r["proxy"].get("_country_code") or "UNK"
        if country_counts.get(cc, 0) >= per_country_cap:
            r["key_reason"] = f"国家 {cc} 配额已满"
            continue
        country_counts[cc] = country_counts.get(cc, 0) + 1
        r["is_key"] = True
        p = r["proxy"]
        p["_is_key"] = True
        p["_key_score"] = r["key_score"]
        chosen.append(r)

    return chosen


def is_front_capable(proxy):
    """协议与角色上可以充当前置跳板 (不看测速)，用于决定是否需要为其判出备用前置档。"""
    return not is_landing_role(proxy) and is_key_protocol_allowed(proxy)


def rank_front_candidates(results, min_stable_mbps, min_floor_mbps):
    """按 Key 评分规则给达到指定测速档的可前置节点排序 (只读，不改动 results)；返回 [(评分, 稳态速度, row)] 降序。"""
    ranked = []
    for r in results:
        eligible, score, _ = evaluate_key_node(
            proxy=r["proxy"], speed_result=r.get("speed_result"), egress_result=r.get("egress_result") or r,
            delay=r.get("delay"), min_stable_mbps=min_stable_mbps, min_floor_mbps=min_floor_mbps,
            is_landing=bool(r.get("is_landing")))
        if eligible:
            ranked.append((score, float((r.get("speed_result") or {}).get("stable_mbps") or 0.0), r))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return ranked


def pick_front_nodes(results, fallback_tier, max_count=10):
    """
    为"直连不可达、需经前置"的节点挑选测试前置与配置前置池。
    优先已评出的 Key (按评分)；没有 Key 时，从达到备用档 (fallback_tier=(稳态, 最低)，约 1080p 流畅) 且
    具备前置资格的直连节点中按同一评分规则取前 max_count 个。
    返回 (前置行列表, "key" | "fallback" | None)，列表首个即测试用前置。
    """
    keys = [r for r in results if r.get("is_key")]
    if keys:
        keys.sort(key=lambda item: -float(item.get("key_score") or 0.0))
        return keys, "key"

    ranked = rank_front_candidates(results, *fallback_tier)
    if not ranked:
        return [], None
    return [r for _, _, r in ranked[:max_count]], "fallback"
