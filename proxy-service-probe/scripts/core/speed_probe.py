# -*- coding: utf-8 -*-
"""快速吞吐与防断流检测模块: 3 秒流式下载窗口与断流假死淘汰。"""
import time
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

SPEED_TEST_URLS = [
    ("https://speed.cloudflare.com/__down?bytes=10000000", {}),
    ("https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg", {"Range": "bytes=0-10485759"}),
]

DEFAULT_STALL_MIN_BYTES = 16 * 1024  # 默认 3 秒内累计下载不足 16KB 视为断流假死 (兼顾低速文字/AI节点)


def measure_speed_and_stall(proxies, window_sec=3.0, timeout=(3.0, 5.0), stall_min_bytes=None):
    """
    持续流式下载一个固定时间窗，返回 (KB/s, 累计字节, 是否断流, 淘汰原因)。
    任一测速目标可通即采纳。
    """
    if stall_min_bytes is None:
        stall_min_bytes = DEFAULT_STALL_MIN_BYTES

    best_speed = 0.0
    best_bytes = 0
    session = requests.Session()
    session.trust_env = False

    for url, headers in SPEED_TEST_URLS:
        try:
            req_headers = {"User-Agent": UA, **headers}
            t0 = time.time()
            total = 0
            with session.get(url, proxies=proxies, timeout=timeout, headers=req_headers, stream=True) as resp:
                if resp.status_code not in (200, 206):
                    continue
                for chunk in resp.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if time.time() - t0 >= window_sec or total >= 8 * 1024 * 1024:
                        break
            duration = max(time.time() - t0, 0.1)
            kbs = round(total / duration / 1024, 1)
            if total > best_bytes:
                best_bytes = total
                best_speed = kbs
            if total >= stall_min_bytes:
                break
        except Exception:
            continue

    session.close()

    is_dead = best_bytes == 0
    is_stalled = 0 < best_bytes < stall_min_bytes

    eliminated_reason = None
    if is_dead:
        eliminated_reason = "无法连通外网"
    elif is_stalled:
        eliminated_reason = "断流假死"

    return {
        "speed_kbs": best_speed,
        "total_bytes": best_bytes,
        "is_dead": is_dead,
        "is_stalled": is_stalled,
        "eliminated_reason": eliminated_reason
    }
