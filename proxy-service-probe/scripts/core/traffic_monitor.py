# -*- coding: utf-8 -*-
"""
测试流量监测: 经各临时 mihomo 实例的 external-controller /traffic 逐秒汇总下行速率。

服务检测与测速并行时，服务检测 (尤其浏览器实播) 的突发下行会挤占本机宽带，把同时进行的测速测低。
所有测试流量都经本工具启动的 mihomo 转发，因此 "总下行 - 测速自身下行" 即同一秒的服务检测占用；
据此判断某次测速是否受干扰 (assess_contention)，受干扰且未达标的结论留到链路空闲时重测。
本机其他程序 (如正在使用的代理客户端) 的流量不经测试内核，不在统计范围内。
"""
import json
import math
import threading
import time

import requests

# 链路接近饱和：测速 + 服务检测下行达到估计容量的该比例
SATURATION_RATIO = 0.8
# 服务检测占用低于该值 (Mbps) 时不视为干扰
MIN_BACKGROUND_MBPS = 2.0
# 观测期内至少这么多秒受干扰才判定整次测速受干扰 (单秒抖动不算)
MIN_CONTENDED_SECONDS = 2


class TrafficMonitor:
    """
    汇总多个 mihomo 实例的逐秒下行字节。每个 /traffic 样本代表采样时刻之前 1 秒的平均速率，
    按时间比例摊入整数秒桶 (与测速逐秒分桶同一口径)。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets = {}      # int(monotonic 秒) -> 字节
        self._sources = 0       # 已接入且至少回传过一次样本的实例数
        self._stopped = False

    def add_sample(self, when, down_bytes_per_second):
        """记录一个样本：when 为采样时刻 (monotonic)，覆盖 (when-1, when] 这 1 秒。"""
        start = when - 1.0
        with self._lock:
            second = math.floor(start)
            while second < when:
                overlap = min(when, second + 1) - max(start, second)
                if overlap > 0:
                    self._buckets[second] = self._buckets.get(second, 0.0) + down_bytes_per_second * overlap
                second += 1

    def watch(self, controller_port, secret=None):
        """后台线程持续读取一个实例的 /traffic 流，实例退出后线程自然结束。"""
        thread = threading.Thread(target=self._follow, args=(controller_port, secret), daemon=True)
        thread.start()
        return thread

    def _follow(self, port, secret):
        headers = {"Authorization": f"Bearer {secret}"} if secret else {}
        session = requests.Session()
        session.trust_env = False
        counted = False
        try:
            with session.get(f"http://127.0.0.1:{port}/traffic", headers=headers, stream=True,
                             timeout=(3.0, 10.0)) as resp:
                if resp.status_code != 200:
                    return
                for line in resp.iter_lines():
                    if self._stopped:
                        return
                    if not line:
                        continue
                    try:
                        down = float(json.loads(line).get("down") or 0.0)
                    except (ValueError, AttributeError):
                        continue
                    if not counted:
                        with self._lock:
                            self._sources += 1
                        counted = True
                    self.add_sample(time.monotonic(), down)
        except requests.RequestException:
            return  # 实例关闭时连接被重置属正常结束
        finally:
            session.close()

    def stop(self):
        self._stopped = True

    @property
    def available(self):
        return self._sources > 0

    def total_mbps(self, start, end):
        """[start, end) 区间内全部测试流量的平均下行 (Mbps)；区间尚无数据时返回 None。"""
        if end <= start:
            return None
        with self._lock:
            total, covered = 0.0, False
            second = math.floor(start)
            while second < end:
                overlap = min(end, second + 1) - max(start, second)
                if second in self._buckets:
                    covered = True
                    total += self._buckets[second] * overlap
                second += 1
        return total * 8 / 1_000_000 / (end - start) if covered else None

    def capacity_mbps(self, floor=0.0):
        """本次运行观测到的最高 2 秒平均总下行，作为本机链路容量的保守估计 (只会偏低，从而多判干扰、多重测)。"""
        with self._lock:
            seconds = sorted(self._buckets)
            best = 0.0
            for second in seconds:
                pair = self._buckets[second] + self._buckets.get(second + 1, 0.0)
                best = max(best, pair / 2)
        return max(best * 8 / 1_000_000, floor)


def assess_contention(measured, monitor, capacity_floor=0.0, service_busy=None):
    """
    判断一次测速是否受并行服务检测干扰。返回 dict:
      contended: True/False；method: traffic (按流量判定) / activity (流量数据缺失时按服务检测是否在跑判定)；
      contended_seconds / background_mbps (观测期服务检测平均占用) / capacity_mbps。
    某秒受干扰：服务检测占用 >= MIN_BACKGROUND_MBPS 且 测速 + 占用 >= 估计容量 * SATURATION_RATIO。
    service_busy(start, end) 在缺少流量数据时回答该区间内是否有服务检测在跑 (保守起见视为受干扰)。
    """
    rates = measured.get("sample_mbps") or []
    started = measured.get("started_monotonic")
    if started is None or not rates:
        return {"contended": False, "method": "none"}
    capacity = monitor.capacity_mbps(capacity_floor) if monitor else capacity_floor
    contended, backgrounds, missing = 0, [], 0
    for index, rate in enumerate(rates):
        total = monitor.total_mbps(started + index, started + index + 1) if monitor else None
        if total is None:
            missing += 1
            continue
        background = max(0.0, total - rate)
        backgrounds.append(background)
        if background >= MIN_BACKGROUND_MBPS and rate + background >= capacity * SATURATION_RATIO:
            contended += 1
    if missing > len(rates) // 2:
        busy = bool(service_busy and service_busy(started, started + len(rates)))
        return {"contended": busy, "method": "activity", "capacity_mbps": round(capacity, 1)}
    return {
        "contended": contended >= MIN_CONTENDED_SECONDS,
        "method": "traffic",
        "contended_seconds": contended,
        "background_mbps": round(sum(backgrounds) / len(backgrounds), 2) if backgrounds else 0.0,
        "capacity_mbps": round(capacity, 1),
    }
