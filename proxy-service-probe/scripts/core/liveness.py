# -*- coding: utf-8 -*-
"""
节点测活: 在服务检测与测速之前，把能连通的节点 (直连或经前置链式) 准确筛出来。

参考开源实现并取其稳健做法:
- mihomo / Clash 系客户端的 URL 延迟测试与 subs-check 测活: 经节点请求 generate_204 类连通性端点，2xx 即通;
- clash-speedtest: 同一节点连发多次请求，全部失败 (100% 丢包) 才判不可用，偶发失败不误杀;
- subs-check 流水线: 测活只做轻量连通，节点一旦判活立即进入后续服务检测与测速，不等整批。

在此之上为避免误杀:
- 轮换 3 个不同运营方的端点 (Google / Cloudflare / Apple)，单一站点被节点屏蔽或抖动不影响判定;
- 超时按跨境高延迟与多跳握手放宽 (直连 8s、链式 10s)，失败之间短暂间隔再试;
- 直连全部失败的节点 (仅本地) 经多个不同服务器的已判活前置并行重试，任一前置测通即判为需前置的落地候选;
  未判不通的其余前置留作该节点服务检测的备用 (某前置到该节点不通时换下一个，合计最多 3 个)。
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .key_evaluator import is_front_capable

LIVENESS_TARGETS = (
    "https://www.gstatic.com/generate_204",
    "https://cp.cloudflare.com/generate_204",
    "https://captive.apple.com/hotspot-detect.html",
)
DIRECT_TIMEOUT = 3.5
CHAIN_TIMEOUT = 5.0
DEFAULT_LOSS_SAMPLES = 10
DEFAULT_ATTEMPTS = DEFAULT_LOSS_SAMPLES  # 向后兼容别名
DEFAULT_MAX_LOSS_RATE = 50.0  # 硬淘汰阈值: >= 50% 丢包判定为不可用直接淘汰
DEFAULT_KEY_MAX_LOSS_RATE = 20.0  # Key跳板门槛: >= 20% 丢包剥离前置资格
RETRY_PAUSE = 0.05
FAST_FAIL_CONSECUTIVE = 5
MAX_CHAIN_FRONTS = 3
# 这些协议承载在 UDP 上，经前置链式时前置必须能转发 UDP
UDP_TRANSPORT_TYPES = frozenset({"hysteria", "hysteria2", "tuic", "wireguard"})

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def check_alive(proxy_url, targets=LIVENESS_TARGETS, samples=DEFAULT_LOSS_SAMPLES,
                timeout=DIRECT_TIMEOUT, pause=RETRY_PAUSE,
                max_loss_rate=DEFAULT_MAX_LOSS_RATE,
                fast_fail_consecutive=FAST_FAIL_CONSECUTIVE,
                attempts=None):
    """
    经本地监听对连通性端点发起 samples 次轻量请求 (轮换 targets)，测定最小延迟、平均延迟、抖动与丢包率。
    - 快速熔断 (Fast-Fail): 从起始连续失败达到 fast_fail_consecutive 次 (如连续 5 次且 0 次成功)，
      立即提前熔断退出，避免死节点空耗等待时间。
    - 丢包淘汰: 丢包率 >= max_loss_rate (默认 50%) 判定为 alive=False，直接在测活阶段淘汰。
    - 指标返回: {"alive", "latency_ms", "avg_latency_ms", "jitter_ms", "loss_rate",
                 "loss_count", "total_samples", "attempts", "reason"}。
    兼容性: 若传入旧参数 attempts，当 samples 未改变时以 attempts 为准。
    """
    if attempts is not None and (samples == DEFAULT_LOSS_SAMPLES or samples is None):
        samples = attempts
    total_target_count = max(1, samples)
    fast_fail_limit = min(fast_fail_consecutive, total_target_count)

    proxies = {"http": proxy_url, "https": proxy_url}
    records, latencies = [], []
    session = requests.Session()
    session.trust_env = False

    consecutive_fails = 0
    try:
        for index in range(total_target_count):
            target = targets[index % len(targets)]
            started = time.monotonic()
            try:
                resp = session.get(target, proxies=proxies, timeout=(timeout, timeout),
                                   allow_redirects=False, headers={"User-Agent": UA})
                _ = resp.content  # 读完响应体，连接放回池中
                elapsed = round((time.monotonic() - started) * 1000, 1)
                if 200 <= resp.status_code < 300:
                    records.append({"target": target, "ok": True, "ms": elapsed})
                    latencies.append(elapsed)
                    consecutive_fails = 0
                else:
                    records.append({"target": target, "ok": False, "error": f"http_{resp.status_code}"})
                    consecutive_fails += 1
            except requests.RequestException as exc:
                records.append({"target": target, "ok": False, "error": type(exc).__name__})
                consecutive_fails += 1

            # 快速熔断: 起始连续失败达到阈值且尚未有任何成功，判定为死节点/无法穿透，提前退出
            if len(latencies) == 0 and consecutive_fails >= fast_fail_limit:
                break

            if index + 1 < total_target_count and pause > 0:
                time.sleep(pause)
    finally:
        session.close()

    total_probes = len(records)
    loss_count = total_probes - len(latencies)
    loss_rate = round((loss_count / total_probes) * 100.0, 1) if total_probes > 0 else 100.0

    min_latency = min(latencies) if latencies else None
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    jitter = round(max(latencies) - min(latencies), 1) if len(latencies) > 1 else (0.0 if latencies else None)

    if not latencies:
        alive = False
        reason = "连通性检测全部失败(100%丢包)"
    elif loss_rate >= max_loss_rate:
        alive = False
        reason = f"丢包率过高({loss_rate:.0f}% >= {max_loss_rate:.0f}%)"
    else:
        alive = True
        reason = "ok"

    return {
        "alive": alive,
        "latency_ms": min_latency,
        "avg_latency_ms": avg_latency,
        "jitter_ms": jitter,
        "loss_rate": loss_rate,
        "loss_count": loss_count,
        "total_samples": total_probes,
        "attempts": records,
        "reason": reason
    }


def uses_udp_transport(proxy):
    return (proxy.get("type") or "").strip().lower() in UDP_TRANSPORT_TYPES


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
    """为直连不通的节点挑选测活用前置: 已直连判活的节点按丢包率升序、测活延迟升序，其余规则见 pick_chain_fronts。"""
    by_quality = sorted(alive_rows,
                        key=lambda r: (
                            (r.get("liveness") or {}).get("loss_rate", 0.0),
                            (r.get("liveness") or {}).get("latency_ms") or 1e9
                        ))
    return pick_chain_fronts(by_quality, landing_proxy, limit)


def check_alive_via_fronts(port_by_front, **options):
    """
    同一节点经多个前置的监听端口并行测活。port_by_front: {前置标识: 端口}。
    任一前置测通即返回 (不等其余前置耗尽重试)；全部失败才判不通。
    返回 (测通的前置标识或 None, {前置标识: 已完成的测活结果})。
    """
    if not port_by_front:
        return None, {}
    options.setdefault("timeout", CHAIN_TIMEOUT)
    pool = ThreadPoolExecutor(max_workers=len(port_by_front))
    try:
        futures = {pool.submit(check_alive, f"http://127.0.0.1:{port}", **options): key
                   for key, port in port_by_front.items()}
        results = {}
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()
            if results[key]["alive"]:
                return key, results
        return None, results
    finally:
        pool.shutdown(wait=False)
