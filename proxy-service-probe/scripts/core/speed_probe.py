# -*- coding: utf-8 -*-
"""
测速模块:
1. 持续流式下载测速 (内存计数零落盘、单连接、RateMeter 逐秒采样、带宽上限保护、稳态判定)
2. 3 秒轻量防断流快速初测 (保留供默认模式使用)

准确性设计 (以真实 YouTube 播放校准):
- 跨境高延迟链路上新建连接爬升慢 (实测 10~20 秒才到稳态，与 YouTube "connection speed" 先低后稳一致)，
  因此不设固定预热，而是至少观测 10 秒、最多 20 秒，以"最后 6 秒"作为稳态窗口；
- 稳态速度 = 稳态窗口平均速度 (单秒按窗口中位数 2 倍封顶，削平孤立尖峰)；
  最低速度 = 稳态窗口内 2 秒滑动平均的最小值 (容忍 1 秒抖动，抓连续下滑)；
- 先突发后限速的节点：限速后的秒数进入稳态窗口，最低速度随之跌落而不达标；
- 单连接测量：YouTube 播放器按顺序拉分段，节点常按单连接限速，多连接聚合会虚高；
- 目标为 CDN 域名：经代理由节点侧解析，自动命中离出口最近的边缘；Google 下载 CDN 与 YouTube 同属 Google 边缘网络。
"""
import math
import statistics
import threading
import time

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# 持续测速目标: 依次尝试，仅在目标尚未返回有效载荷时换下一个 (已开始传输即以该目标定论，杜绝挑目标凑高速)
DEFAULT_SUSTAINED_TARGETS = [
    "https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg",  # ~280MB，支持 Range
    "https://speed.cloudflare.com/__down?bytes=50000000",  # 单次上限 < 100MB，忽略 Range
]

# 门槛 (按实测校准：YouTube 连接速度稳定在 15 Mbps 左右的节点可流畅播放 4K，应能入选 Key)
DEFAULT_MIN_STABLE_MBPS = 12.0   # Key / Fast：稳态速度下限 (新建连接测得，较播放器热连接留余量)
DEFAULT_MIN_FLOOR_MBPS = 6.0     # Key / Fast：稳态窗口内 2 秒滑动平均的最低值下限
DEFAULT_DROP_BELOW_MBPS = 6.0    # 稳态速度低于此值直接淘汰 (删除)
STEADY_WINDOW_SECONDS = 6        # 稳态窗口：观测的最后 N 秒
MIN_OBSERVE_SECONDS = 10         # 至少观测 N 秒才下结论 (排除只在开头突发的假高速)
DEFAULT_MAX_OBSERVE_SECONDS = 20  # 爬升慢的节点最多观测 N 秒
# 无 Key 时的备用前置档：未被淘汰 (稳态 >= 6 Mbps，约 1080p 流畅) 且最低速度不低于其一半
FRONT_FALLBACK_TIER = (DEFAULT_DROP_BELOW_MBPS, DEFAULT_DROP_BELOW_MBPS / 2)

# 3秒轻量防断流目标
SPEED_TEST_URLS = [
    ("https://speed.cloudflare.com/__down?bytes=10000000", {}),
    ("https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg", {"Range": "bytes=0-10485759"}),
]

DEFAULT_STALL_MIN_BYTES = 16 * 1024  # 默认 3 秒内累计下载不足 16KB 视为断流假死 (兼顾低速文字/AI节点)

PAYLOAD_TYPES = {
    "application/octet-stream", "binary/octet-stream",
    "application/x-apple-diskimage", "application/zip",
    "application/vnd.android.package-archive"
}


class RateMeter:
    """按秒切片的下载字节计量器 (按时间比例分摊到各秒)，并记录最长无进展时长。"""

    def __init__(self, started_at, warmup_seconds, duration_seconds):
        if warmup_seconds < 0 or duration_seconds <= 0:
            raise ValueError("invalid measurement duration")
        self.sample_start = started_at + warmup_seconds
        self.duration = float(duration_seconds)
        self.end = self.sample_start + self.duration
        self.buckets = [0.0] * math.ceil(self.duration)
        self.last_time = started_at
        self.total = 0
        self.last_progress = started_at
        self.max_stall = 0.0

    def record(self, when, total_bytes):
        if when < self.last_time or total_bytes < self.total:
            raise ValueError("measurement counters must be monotonic")
        delta = total_bytes - self.total
        elapsed = when - self.last_time
        if delta:
            self.last_progress = when
            if elapsed > 0:
                for index in range(len(self.buckets)):
                    left = max(self.last_time, self.sample_start + index)
                    right = min(when, self.sample_start + index + 1, self.end)
                    if right > left:
                        self.buckets[index] += delta * (right - left) / elapsed
            elif self.sample_start <= when < self.end:
                self.buckets[int(when - self.sample_start)] += delta
        elif when > self.sample_start:
            self.max_stall = max(self.max_stall, min(when, self.end) - max(self.last_progress, self.sample_start))
        self.last_time, self.total = when, total_bytes


def validate_payload(status_code, headers):
    """校验响应状态与类型，确保是未压缩的二进制载荷。"""
    if status_code not in (200, 206):
        raise ValueError(f"unexpected HTTP response status {status_code}")
    content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in PAYLOAD_TYPES:
        # 部分 CDN 不带严格 content-type 或为 text/plain，宽容放行只要不是 html
        if "text/html" in content_type:
            raise ValueError(f"unexpected HTML content type: {content_type}")
    if (headers.get("content-encoding") or "identity").strip().lower() not in ("", "identity"):
        raise ValueError("compressed responses are not valid bandwidth samples")


class _StreamCounter:
    """后台读取线程与计量主线程之间的共享计数 (单写者，无需加锁)。"""

    def __init__(self):
        self.total = 0
        self.eof = False
        self.error = None
        self.stop = False


def _pump(response, counter, chunk_size, rate_limit_bps):
    """读取响应体并丢弃，只累计字节数；按带宽上限节流 (读慢即经 TCP 背压让发送端降速)。"""
    budget_start, budget_bytes = time.monotonic(), 0
    try:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if counter.stop:
                return
            counter.total += len(chunk)
            if not rate_limit_bps:
                continue
            budget_bytes += len(chunk)
            now = time.monotonic()
            lag = budget_bytes / rate_limit_bps - (now - budget_start)
            if lag > 0:
                time.sleep(lag)
            elif lag < -0.25:
                # 节点慢于上限时不积攒突发额度，避免之后以超过上限的速率补读
                budget_start, budget_bytes = now, 0
        counter.eof = True
    except Exception as error:
        if not counter.stop:
            counter.error = error


def default_criteria():
    return {
        "min_stable_mbps": DEFAULT_MIN_STABLE_MBPS,
        "min_floor_mbps": DEFAULT_MIN_FLOOR_MBPS,
        "drop_below_mbps": DEFAULT_DROP_BELOW_MBPS,
        "window_seconds": STEADY_WINDOW_SECONDS,
        "min_observe_seconds": MIN_OBSERVE_SECONDS,
        "max_observe_seconds": DEFAULT_MAX_OBSERVE_SECONDS,
    }


def steady_stats(rates, window=STEADY_WINDOW_SECONDS):
    """
    取逐秒速率的最后 window 秒：返回 (稳态平均速度, 2 秒滑动平均最低值)。
    单秒速率按窗口中位数的 2 倍封顶后计入，孤立尖峰 (突发缓存/测量抖动) 不能拉高稳态速度。
    """
    tail = rates[-window:]
    if not tail:
        return None, None
    cap = statistics.median(tail) * 2
    tail = [min(rate, cap) for rate in tail]
    moving = [(tail[i] + tail[i + 1]) / 2 for i in range(len(tail) - 1)] or tail
    return statistics.fmean(tail), min(moving)


def classify_steady(stable, floor, criteria):
    """qualified: 达到 Key/Fast 门槛；drop: 低于淘汰线；keep: 介于两者之间 (保留但不授标)。"""
    if stable is None:
        return "drop"
    if stable >= criteria["min_stable_mbps"] and floor >= criteria["min_floor_mbps"]:
        return "qualified"
    if criteria["drop_below_mbps"] and stable < criteria["drop_below_mbps"]:
        return "drop"
    return "keep"


def steady_verdict(rates, criteria):
    """
    按已定型的逐秒速率决定是否结束观测，返回 (结论, 原因) 或 None (继续观测)。
    - 观测满 min_observe 秒、稳态达标且稳态窗口内不在下滑 (后半段 >= 前半段 75%)：立即结束，qualified；
      正在下滑的节点 (慢慢限速型假高速) 继续观测，由下滑后的稳态决定；
    - 观测满 min_observe 秒、稳态低于淘汰线、最近 3 秒也明显偏低 (< 淘汰线 75%) 且不在爬升：结束，drop；
      仍在缓慢爬升或贴近淘汰线的节点一律观测到上限，避免误删；
    - 观测满 max_observe 秒：按稳态窗口给出最终结论。
    """
    count = len(rates)
    if count < max(criteria["min_observe_seconds"], criteria["window_seconds"]):
        return None
    stable, floor = steady_stats(rates, criteria["window_seconds"])
    verdict = classify_steady(stable, floor, criteria)
    if verdict == "qualified":
        tail = rates[-criteria["window_seconds"]:]
        half = len(tail) // 2
        if statistics.fmean(tail[-half:]) >= statistics.fmean(tail[:half]) * 0.75:
            return verdict, "稳态达标"
        if count >= criteria["max_observe_seconds"]:
            return verdict, "观测到上限"
        return None
    if verdict == "drop" and count >= 6:
        recent, previous = statistics.fmean(rates[-3:]), statistics.fmean(rates[-6:-3])
        hopeless = recent < criteria["drop_below_mbps"] * 0.75
        if hopeless and recent <= max(previous * 1.2, previous + 0.5):
            return verdict, "稳态明显低于淘汰线且未见爬升"
    if count >= criteria["max_observe_seconds"]:
        return verdict, "观测到上限"
    return None


def measure_download_sustained(
    url,
    proxy_url,
    *,
    rate_limit_mbps=40.0,
    criteria=None,
    max_bytes=None,
    deadline=None,
    poll_interval=0.1,
    read_timeout=5.0,
    chunk_size=16384,
):
    """
    经代理执行单连接流式 HTTP 下载测速，字节只在内存计数、不落盘。
    逐秒采样，按 steady_verdict 在 min_observe~max_observe 秒之间给出结论：
    返回的 verdict 为 qualified (Key/Fast 级) / keep (保留) / drop (淘汰)；中途断流按已测秒数判定，不会给 qualified。
    """
    criteria = {**default_criteria(), **(criteria or {})}
    max_observe = criteria["max_observe_seconds"]
    if not proxy_url or max_observe <= 0:
        raise ValueError("invalid download measurement options")
    rate_limit_bps = rate_limit_mbps * 125_000 if rate_limit_mbps and rate_limit_mbps > 0 else None
    if max_bytes is None:
        # 按上限估算整段传输量并留余量；无上限时不设字节上限，以观测上限与期限约束
        max_bytes = int(rate_limit_bps * (max_observe + 3)) if rate_limit_bps else math.inf

    requested = time.monotonic()
    deadline = min(deadline if deadline is not None else math.inf, requested + max_observe + 12)
    status, error, http_status, ttfb_ms = "transfer_error", None, None, None
    verdict, reason, decided_rates = None, None, None
    meter, counter = None, _StreamCounter()

    def settled_rates(now):
        seconds = min(math.floor(max(0.0, now - meter.sample_start)), len(meter.buckets))
        return [meter.buckets[i] * 8 / 1_000_000 for i in range(seconds)]

    session = requests.Session()
    session.trust_env = False  # 严防继承系统全局代理
    try:
        with session.get(
            url,
            proxies={"http": proxy_url, "https": proxy_url},
            stream=True,
            allow_redirects=True,
            timeout=(min(5.0, max(0.5, deadline - requested)), read_timeout),
            headers={"User-Agent": "proxy-probe-speed/2.0", "Accept-Encoding": "identity"},
        ) as response:
            http_status = response.status_code
            validate_payload(response.status_code, response.headers)
            started = time.monotonic()
            ttfb_ms = round((started - requested) * 1000, 1)
            meter = RateMeter(started, 0.0, max_observe)
            reader = threading.Thread(target=_pump, args=(response, counter, chunk_size, rate_limit_bps), daemon=True)
            reader.start()
            try:
                while True:
                    now = time.monotonic()
                    meter.record(now, counter.total)
                    if counter.error is not None:
                        status, error = "stalled", f"{type(counter.error).__name__}: {counter.error}"[:300]
                        break
                    if counter.total >= max_bytes:
                        status, error = "byte_limit", "reached byte budget"
                        break
                    if counter.eof:
                        status, error = "short_response", "target file ended"
                        break
                    rates_now = settled_rates(now)
                    decided = steady_verdict(rates_now, criteria)
                    if decided:
                        status = "complete"
                        verdict, reason = decided
                        decided_rates = rates_now
                        break
                    if now >= deadline:
                        status = "budget_exhausted"
                        break
                    time.sleep(poll_interval)
            finally:
                counter.stop = True
                response.close()
                reader.join(timeout=2)
    except ValueError as exc:
        status, error = "invalid_response", str(exc)
    except requests.RequestException as exc:
        status, error = "transfer_error", f"{type(exc).__name__}: {exc}"[:300]
    finally:
        session.close()

    finished = time.monotonic()
    if decided_rates is not None:
        rates = decided_rates  # 报告与结论使用同一组已定型样本
    else:
        rates = settled_rates(finished) if meter else []
        width = finished - meter.sample_start - len(rates) if meter else 0.0
        if meter and width >= 0.5 and len(rates) < len(meter.buckets):
            # 中途结束时计入最后不足 1 秒的片段，避免丢掉末尾的下滑/断流
            rates.append(meter.buckets[len(rates)] * 8 / 1_000_000 / width)
    stable, floor = steady_stats(rates, criteria["window_seconds"])
    if verdict is None:
        if status in ("short_response", "byte_limit") and len(rates) >= criteria["window_seconds"]:
            # 测速文件读完或达到字节预算时已有完整稳态窗口：按窗口正常判定
            status = "complete"
            verdict, reason = classify_steady(stable, floor, criteria), "测速文件读完"
        elif rates:
            # 中途断流/超时：只能判保留或淘汰，不授予 Key/Fast
            verdict = "drop" if classify_steady(stable, floor, criteria) == "drop" else "keep"
            reason = error or status
        else:
            verdict, reason = "drop", error or status

    return {
        "status": status,
        "complete": status == "complete",
        "verdict": verdict,
        "reason": reason,
        "error": error,
        "observed_seconds": len(rates),
        "stable_mbps": round(stable, 3) if stable is not None else None,
        "floor_mbps": round(floor, 3) if floor is not None else None,
        "peak_mbps": round(max(rates), 3) if rates else None,
        "mean_mbps": round(statistics.fmean(rates), 3) if rates else None,
        "sample_mbps": [round(rate, 3) for rate in rates],
        "max_stall_seconds": round(meter.max_stall, 3) if meter else None,
        "bytes_received": counter.total,
        "http_status": http_status,
        "ttfb_ms": ttfb_ms,
        "rate_limit_mbps": rate_limit_mbps,
        # 稳态窗口每 2 秒都接近上限，说明真实能力不低于上限
        "capped": bool(rate_limit_mbps and floor is not None and floor >= rate_limit_mbps * 0.9),
        "target": url,
        # 观测第 0 秒的起点 (monotonic)，用于把逐秒速率与并行测试的流量统计对齐；进程内有效，不作跨进程比较
        "started_monotonic": meter.sample_start if meter else None,
    }


def measure_node_speed(proxy_url, targets=None, **options):
    """
    依次尝试测速目标：目标在返回有效载荷前失败 (连不上/非二进制响应) 才换下一个；
    一旦开始传输即以该目标的结果定论，不因速度低而换目标重测。
    """
    attempts = []
    for url in targets or DEFAULT_SUSTAINED_TARGETS:
        measured = measure_download_sustained(url, proxy_url, **options)
        if measured["bytes_received"] > 0 or measured["status"] not in ("transfer_error", "invalid_response"):
            if attempts:
                measured["failed_targets"] = attempts
            return measured
        attempts.append({"target": url, "status": measured["status"], "error": measured["error"]})
    measured["failed_targets"] = attempts[:-1]
    return measured


def speed_qualified(measured, min_stable_mbps=DEFAULT_MIN_STABLE_MBPS, min_floor_mbps=DEFAULT_MIN_FLOOR_MBPS):
    """
    测速准入 (Key / Fast)：观测正常结束 (status=complete) 且稳态窗口满足
    稳态速度 >= min_stable_mbps、2 秒滑动平均最低值 >= min_floor_mbps。中途断流的测量不授予资格。
    """
    if not measured or measured.get("status") != "complete":
        return False
    stable, floor = measured.get("stable_mbps"), measured.get("floor_mbps")
    return stable is not None and floor is not None and stable >= min_stable_mbps and floor >= min_floor_mbps


def speed_drop_reason(measured):
    """测速结论为淘汰时返回淘汰原因，否则 None。"""
    if not measured or measured.get("verdict") != "drop":
        return None
    if measured.get("stable_mbps") is None:
        return f"测速失败，无法取得稳定速度({measured.get('reason') or measured.get('status')})"
    return f"稳态速度 {measured['stable_mbps']:.1f}Mbps 低于淘汰线({measured.get('reason')})"


def speed_options(args):
    """由 CLI 参数构造测速选项 (两条流水线共用同一套门槛与观测规则)。"""
    return {
        "rate_limit_mbps": args.rate_limit_mbps,
        "criteria": {
            **default_criteria(),
            "min_stable_mbps": args.min_speed_mbps,
            "min_floor_mbps": args.min_floor_mbps,
            "drop_below_mbps": args.drop_below_mbps,
            "max_observe_seconds": args.speed_duration,
        },
    }


def measure_with_retry(proxy_url, options, targets=None, assess=None):
    """
    单节点完整测速：结论贴近门槛或没有样本时用新连接重测一次，取较好结论 (每次独立做稳态与防突发判定)。
    assess(measured) 给出时判断每次测量是否受并行测试流量干扰 (返回含 contended 的 dict，写入 measured["contention"])：
    受干扰且未达标的测量不做立即重测，返回 deferred=True，交由调用方在链路空闲时重测。
    返回 (measured, deferred)。
    """
    criteria = options["criteria"]

    def attempt():
        try:
            measured = measure_node_speed(proxy_url, targets, **options)
        except Exception as error:
            measured = {"status": "error", "complete": False, "verdict": "drop", "stable_mbps": None,
                        "reason": f"{type(error).__name__}: {error}", "error": f"{type(error).__name__}: {error}"}
        if assess is not None:
            measured["contention"] = assess(measured)
        return measured

    def disturbed(measured):
        return measured.get("verdict") != "qualified" and bool((measured.get("contention") or {}).get("contended"))

    measured = attempt()
    if disturbed(measured):
        return measured, True
    if needs_retry(measured, criteria):
        second = attempt()
        first_summary, second_summary = _attempt_summary(measured), _attempt_summary(second)
        measured = max((measured, second), key=_verdict_rank)
        measured["attempts"] = [first_summary, second_summary]
        if disturbed(measured):
            return measured, True
    return measured, False


def better_measurement(previous, current):
    """链路空闲时的重测与此前受干扰的测量取较好结论 (干扰只会测低，不会测高)，并保留两次摘要。"""
    best = max((previous, current), key=_verdict_rank)
    best = dict(best)
    best["quiet_retest"] = {"previous": _attempt_summary(previous), "retest": _attempt_summary(current)}
    return best


def apply_speed_result(row, measured, criteria):
    """把测量结论写回 row：speed_result / speed_mbps (稳态速度) / is_fast (Key/Fast 级) / speed_drop (淘汰原因或 None)。"""
    row["speed_result"] = measured
    row["speed_mbps"] = measured.get("stable_mbps") or 0.0
    row["speed_kbs"] = round(row["speed_mbps"] * 1_000_000 / 8 / 1024, 1)
    row["is_fast"] = speed_qualified(measured, criteria["min_stable_mbps"], criteria["min_floor_mbps"])
    row["speed_drop"] = speed_drop_reason(measured)


VERDICT_ORDER = {"drop": 0, "keep": 1, "qualified": 2}


def needs_retry(measured, criteria):
    """单次测量波动大 (同一节点实测稳态 6~16 Mbps)：结论贴近门槛或没有样本时重测一次。"""
    stable, verdict = measured.get("stable_mbps"), measured.get("verdict")
    if stable is None:
        return True
    if verdict == "drop":
        return stable >= criteria["drop_below_mbps"] * 0.6
    if verdict == "keep":
        return stable >= criteria["min_stable_mbps"] * 0.8
    return False


def _verdict_rank(measured):
    return VERDICT_ORDER.get(measured.get("verdict"), 0), measured.get("stable_mbps") or 0.0


def _attempt_summary(measured):
    summary = {key: measured.get(key) for key in
               ("verdict", "status", "stable_mbps", "floor_mbps", "observed_seconds", "reason", "target")}
    if measured.get("contention"):
        summary["contention"] = measured["contention"]
    return summary


def speed_verdict_text(row):
    """进度输出用的测速结论。"""
    if row.get("is_fast"):
        return "✓ Key/Fast 级"
    return "✗ 淘汰" if row.get("speed_drop") else "○ 保留"


def describe_speed(measured):
    """单行测速摘要，用于进度输出。"""
    if not measured:
        return "未测速"
    if measured.get("stable_mbps") is None:
        return f"无有效样本 [{measured.get('status')}: {measured.get('reason') or measured.get('error')}]"
    text = (f"稳态 {measured['stable_mbps']}Mbps / 最低 {measured.get('floor_mbps')}Mbps / "
            f"峰值 {measured.get('peak_mbps')}Mbps / {measured.get('observed_seconds')}s")
    if measured.get("capped"):
        text += " (已达上限)"
    if measured.get("status") != "complete":
        text += f" [{measured.get('status')}: {measured.get('error')}]"
    if measured.get("quiet_retest"):
        text += " (链路空闲时重测)"
    return text


def measure_speed_and_stall(proxies, window_sec=3.0, timeout=(3.0, 5.0), stall_min_bytes=None):
    """
    【非测速模式轻量防断流初检】
    持续流式下载一个 3 秒固定窗口，返回 (KB/s, 累计字节, 是否断流, 淘汰原因)。
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
