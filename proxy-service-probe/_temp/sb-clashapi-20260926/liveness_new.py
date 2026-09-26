def pick_chain_fronts(ranked_rows, landing_proxy, limit=MAX_CHAIN_FRONTS):
    """
    从已按偏好排好序的行中为需前置的节点取最多 limit 个前置: 协议可作前置、非落地，同一服务器只取一个
    (避免多个前置其实是同一台机器)；被测节点走 UDP 时把声明支持 UDP 的前置提前 (其余保持原偏好顺序)。
    """
    needs_udp = uses_udp_transport(landing_proxy)
    ordered = sorted((r for r in ranked_rows if is_front_capable(r["proxy"])),
                     key=lambda r: needs_udp and not r["proxy"].get("udp"))
    chosen, servers = [], set()
    for row in ordered:
        server = (row["proxy"].get("server"), row["proxy"].get("port"))
        if server in servers:
            continue
        servers.add(server)
        chosen.append(row)
        if len(chosen) >= limit:
            break
    return chosen


def rank_chain_fronts(alive_rows, landing_proxy, limit=MAX_CHAIN_FRONTS):
    """为直连不通的节点挑选测活用前置: 已直连判活的节点按测活延迟升序，其余规则见 pick_chain_fronts。"""
    by_latency = sorted(alive_rows, key=lambda r: r["liveness"]["latency_ms"] or 1e9)
    return pick_chain_fronts(by_latency, landing_proxy, limit)


