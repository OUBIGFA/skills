# -*- coding: utf-8 -*-
"""
测速模块:
1. 持续流式下载测速 (基于 curl、RateMeter 逐秒采样与带宽限速防网络拥塞，移植自 freenode 核心)
2. 目标快速轻量预检 (Range: bytes=0-1023)
3. 3 秒轻量防断流快速初测 (保留供默认模式使用)
"""
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# 默认测速目标 (首选 proof.ovh.us，备选 cloudflare 与 google)
DEFAULT_SUSTAINED_TARGETS = [
    "https://proof.ovh.us/files/100Mb.dat",
    "https://speed.cloudflare.com/__down?bytes=50000000",
    "https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg",
]

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
    """按秒切片的下载速率计量器，排除 TCP 慢启动并统计平均/中位数/P10与卡顿时长。"""

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

    def report(self, status, ended_at):
        measured = min(self.duration, max(0.0, ended_at - self.sample_start))
        complete = status == "complete" and measured >= self.duration - 1e-6
        if status == "complete" and not complete:
            status = "incomplete"
        rates, measured_bytes = [], 0.0
        for index, count in enumerate(self.buckets):
            width = min(1.0, measured - index)
            if width <= 0:
                break
            measured_bytes += count
            rates.append(count * 8 / width / 1_000_000)
        ordered = sorted(rates)
        return {
            "status": status,
            "complete": complete,
            "bytes_received": self.total,
            "measured_seconds": round(measured, 3),
            "mean_mbps": round(measured_bytes * 8 / measured / 1_000_000, 3) if measured > 0 else None,
            "median_mbps": round(statistics.median(rates), 3) if rates else None,
            "p10_mbps": round(ordered[math.floor((len(ordered) - 1) * 0.1)], 3) if ordered else None,
            "max_stall_seconds": round(max(0.0, self.max_stall), 3),
            "sample_mbps": [round(rate, 3) for rate in rates],
        }


def parse_response_headers(raw):
    """解析 HTTP 响应头字节流"""
    result = None
    for block in raw.replace(b"\r\n", b"\n").split(b"\n\n")[:-1]:
        lines = block.decode("iso-8859-1", errors="replace").splitlines()
        if not lines or not lines[0].startswith("HTTP/"):
            continue
        parts = lines[0].split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        result = {"status": int(parts[1])}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip().lower()] = value.strip()
    return result


def validate_payload(headers):
    """校验响应类型，确保非压缩有效载荷。"""
    if not headers or headers.get("status") not in (200, 206):
        raise ValueError("unexpected HTTP response status")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in PAYLOAD_TYPES:
        # 部分 CDN 不带严格 content-type 或为 text/plain，宽容放行只要不是 html
        if "text/html" in content_type:
            raise ValueError(f"unexpected HTML content type: {content_type}")
    if headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
        raise ValueError("compressed responses are not valid bandwidth samples")


def _stop_process(process):
    """确保子进程彻底退出，杜绝残留句柄或端口占用。"""
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=3)
            except Exception:
                pass


def precheck_target(url, proxy_url, timeout=3.0):
    """
    轻量快速预检: Range: bytes=0-1023，确认目标通过此节点连通后再执行完整下载测速，
    避免在断流/死节点上浪费完整观测时间窗。
    """
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    with requests.Session() as session:
        session.trust_env = False
        try:
            with session.get(
                url,
                proxies=proxies,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
                headers={"Range": "bytes=0-1023", "User-Agent": "proxy-speed-precheck/1"}
            ) as response:
                if response.status_code not in (200, 206):
                    return {"status": "invalid_response", "error": f"http_{response.status_code}", "http_status": response.status_code}
                chunk = next(response.iter_content(chunk_size=1024), b"")
                if not chunk:
                    return {"status": "short_response", "error": "empty_body", "http_status": response.status_code}
                return None
        except Exception as error:
            return {"status": "transfer_error", "error": f"precheck:{type(error).__name__}", "http_status": None}


def measure_download_sustained(
    url,
    proxy_url,
    work_dir,
    *,
    duration_seconds=5.0,
    warmup_seconds=1.0,
    max_bytes=35 * 1024 * 1024,
    deadline=None,
    curl_bin=None,
    poll_interval=0.1,
    rate_limit_mbps=10.0
):
    """
    执行一段受约束的流式 HTTP 下载测速。
    使用 curl 子进程，实时读取临时文件增量，杜绝内存占用；
    严格支持 --limit-rate，防止跑满本地家宽影响其他应用。
    """
    if not proxy_url or max_bytes <= 0 or duration_seconds <= 0 or warmup_seconds < 0:
        raise ValueError("invalid download measurement options")

    curl_bin = curl_bin or shutil.which("curl")
    if not curl_bin:
        raise ValueError("curl is not installed")

    directory = Path(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    payload_file = directory / "payload.bin"
    header_file = directory / "headers.txt"
    error_file = directory / "curl.log"

    started = time.monotonic()
    deadline = min(deadline if deadline is not None else math.inf, started + warmup_seconds + duration_seconds + 8)

    # 隔离环境变量，严防继承系统全局代理
    environment = {
        k: v for k, v in os.environ.items()
        if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }

    meter = None
    total = 0
    status = "budget_exhausted"
    error = None
    metadata = None

    for path in (payload_file, header_file, error_file):
        path.write_bytes(b"")

    remaining = max(0.1, deadline - time.monotonic())
    command = [
        curl_bin, "--fail", "--location", "--max-redirs", "3", "--silent", "--show-error",
        "--suppress-connect-headers", "--proxy", proxy_url, "--noproxy", "",
        "--connect-timeout", str(min(5, int(remaining))), "--max-time", str(int(remaining)),
        "--speed-limit", "1", "--speed-time", "3", "--header", "Accept-Encoding: identity",
        "--user-agent", "proxy-probe-speed/1.0", "--output", str(payload_file),
        "--dump-header", str(header_file)
    ]

    if rate_limit_mbps is not None and rate_limit_mbps > 0:
        # 1 Mbps = 125,000 bytes/sec
        command.extend(["--limit-rate", str(int(rate_limit_mbps * 125000))])

    command.extend(["--url", url])

    with error_file.open("wb") as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, env=environment)
        try:
            while True:
                now = time.monotonic()
                size = payload_file.stat().st_size if payload_file.exists() else 0

                if size > 0 and metadata is None and header_file.exists():
                    try:
                        with header_file.open("rb") as src:
                            candidate = parse_response_headers(src.read(65536))
                        if candidate and candidate.get("status") not in range(100, 200) and candidate.get("status") not in range(300, 400):
                            metadata = candidate
                            validate_payload(candidate)
                    except ValueError as exc:
                        status, error = "invalid_response", str(exc)
                        break

                if size > 0 and metadata and meter is None:
                    meter = RateMeter(now, warmup_seconds, duration_seconds)

                if meter:
                    meter.record(now, size)

                return_code = process.poll()
                if return_code is not None and return_code != 0:
                    status = "transfer_error"
                    break
                if size >= max_bytes:
                    status = "byte_limit"
                    break
                if meter and now >= meter.end:
                    status = "complete"
                    break
                if now >= deadline:
                    break
                if return_code is not None:
                    break

                stop_at = min(deadline, meter.end if meter else deadline)
                time.sleep(min(poll_interval, max(0.01, stop_at - now)))
        finally:
            _stop_process(process)

    final_size = payload_file.stat().st_size if payload_file.exists() else 0
    total = final_size
    if status == "transfer_error":
        error = error_file.read_text(encoding="utf-8", errors="replace")[-300:].strip() if error_file.exists() else "curl error"
    elif status == "budget_exhausted" and time.monotonic() < deadline:
        if not final_size or metadata is None:
            status, error = "invalid_response", "no verified payload received"
        else:
            status, error = "short_response", "ended before observation window"

    finished = time.monotonic()
    meter = meter or RateMeter(finished, warmup_seconds, duration_seconds)
    report = meter.report(status, finished)

    if metadata is None and header_file.exists():
        with header_file.open("rb") as src:
            metadata = parse_response_headers(src.read(65536))

    report.update({
        "bytes_received": total,
        "http_status": metadata.get("status") if metadata else None,
        "error": error,
        "rate_limit_mbps": rate_limit_mbps,
        "target": url
    })

    # 清理临时下载载荷文件以节省磁盘
    try:
        if payload_file.exists():
            payload_file.unlink()
    except Exception:
        pass

    return report


def speed_qualified(measured, min_median_mbps=5.0, min_p10_mbps=3.0, max_stall_seconds=1.0):
    """
    测速通过准入评判:
    1. 测速状态为 complete；
    2. 中位数速率 median_mbps >= min_median_mbps (默认 5.0 Mbps)；
    3. P10 速率底线 >= min_p10_mbps (默认 3.0 Mbps)；
    4. 最大卡顿停滞时间 <= max_stall_seconds (默认 1.0 秒)。
    """
    if not measured or not measured.get("complete") or measured.get("status") != "complete":
        return False
    median = measured.get("median_mbps")
    p10 = measured.get("p10_mbps")
    stall = measured.get("max_stall_seconds", 0.0)

    if median is None or median < min_median_mbps:
        return False
    if p10 is None or p10 < min_p10_mbps:
        return False
    if stall is not None and stall > max_stall_seconds:
        return False
    return True


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
