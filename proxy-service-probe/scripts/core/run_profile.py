# -*- coding: utf-8 -*-
"""
运行环境 Profile: 同一套测试与判据，只按运行位置调整资源参数。

- local: 家宽/办公网络。测速严格串行 (节点间不抢本机带宽)，带宽上限 40 Mbps (高于 Key 门槛，又不长时间占满家宽)。
- ci:    GitHub Actions 等云端 Runner。带宽充裕，测速 2 路并发缩短耗时，带宽上限 50 Mbps。

两种 Profile 的门槛、观测窗与评选规则完全一致；差异只影响耗时与对本机网络的占用。
云端测得的是"节点出口到 CDN"的能力，不包含国内家宽到节点这一段线路，报告中以 vantage 字段区分。
"""
import os

from .speed_probe import (DEFAULT_DROP_BELOW_MBPS, DEFAULT_MAX_OBSERVE_SECONDS, DEFAULT_MIN_FLOOR_MBPS,
                          DEFAULT_MIN_STABLE_MBPS, MIN_OBSERVE_SECONDS)

PROFILES = {
    "local": {"rate_limit_mbps": 40.0, "speed_concurrency": 1, "vantage": "本机网络 -> 节点 -> CDN"},
    "ci": {"rate_limit_mbps": 50.0, "speed_concurrency": 2, "vantage": "云端机房 -> 节点 -> CDN"},
}


def detect_profile(environ=None):
    """GitHub Actions 或通用 CI 环境 (CI=true) 返回 ci，否则返回 local。"""
    environ = os.environ if environ is None else environ
    if str(environ.get("GITHUB_ACTIONS", "")).lower() == "true" or str(environ.get("CI", "")).lower() == "true":
        return "ci"
    return "local"


def apply_profile(args, environ=None):
    """
    解析 args.profile (auto/local/ci) 并为未显式指定的参数 (值为 None) 填入 Profile 默认值。
    返回 (profile_name, profile_settings)。
    """
    name = args.profile if args.profile in PROFILES else detect_profile(environ)
    settings = PROFILES[name]
    for key in ("rate_limit_mbps", "speed_concurrency"):
        if getattr(args, key, None) is None:
            setattr(args, key, settings[key])
    args.profile = name
    return name, settings


MAX_RATE_LIMIT_MBPS = 100.0  # Google 测速文件约 280MB，最长 20 秒观测须在上限速率下读不完文件


def add_speed_arguments(parser):
    """两条流水线共用的测速参数。"""
    parser.add_argument("--speed-test", action="store_true",
                        help="主动开启完整下载测速 (非主动技能，仅在显式要求时执行)")
    parser.add_argument("--profile", choices=["auto", "local", "ci"], default="auto",
                        help="运行环境: auto 按 GITHUB_ACTIONS/CI 环境变量自动识别 (默认)，local 本地，ci 云端 Runner")
    parser.add_argument("--rate-limit-mbps", type=float, default=None,
                        help=f"测速带宽上限 (Mbps；默认 local 40 / ci 50，须不低于 Key 门槛且不超过 {MAX_RATE_LIMIT_MBPS:.0f})")
    parser.add_argument("--speed-concurrency", type=int, default=None,
                        help="同时测速的节点数 (默认 local 1 严格串行 / ci 2)")
    parser.add_argument("--speed-duration", type=float, default=DEFAULT_MAX_OBSERVE_SECONDS,
                        help=f"单节点最长观测秒数 (至少观测 {MIN_OBSERVE_SECONDS} 秒；默认 {DEFAULT_MAX_OBSERVE_SECONDS})")
    parser.add_argument("--min-speed-mbps", type=float, default=DEFAULT_MIN_STABLE_MBPS,
                        help=f"Key/Fast 稳态速度门槛 (最后 6 秒平均，Mbps；默认 {DEFAULT_MIN_STABLE_MBPS})")
    parser.add_argument("--min-floor-mbps", type=float, default=DEFAULT_MIN_FLOOR_MBPS,
                        help=f"Key/Fast 稳态窗口内 2 秒滑动平均最低值门槛 (Mbps；默认 {DEFAULT_MIN_FLOOR_MBPS})")
    parser.add_argument("--drop-below-mbps", type=float, default=DEFAULT_DROP_BELOW_MBPS,
                        help=f"稳态速度低于此值直接淘汰 (Mbps；默认 {DEFAULT_DROP_BELOW_MBPS}，0 表示不按速度淘汰)")
    parser.add_argument("--speed-target", default=None,
                        help="只用指定 URL 测速 (默认依次尝试 Google 下载 CDN、Cloudflare)")
    parser.add_argument("--no-landing-probe", action="store_true",
                        help="不对直连不可达的节点经前置 (Key 或备用前置) 重测")


def validate_speed_options(args):
    """带宽上限必须落在可判定区间：低于门槛永远测不出达标，过高会在观测窗内读完测速文件而判为未完成。"""
    if not args.rate_limit_mbps or args.rate_limit_mbps < args.min_speed_mbps:
        return (f"--rate-limit-mbps {args.rate_limit_mbps} 低于合格门槛 --min-speed-mbps {args.min_speed_mbps}，"
                f"无法判定达标；请调高上限")
    if args.rate_limit_mbps > MAX_RATE_LIMIT_MBPS:
        return f"--rate-limit-mbps 不能超过 {MAX_RATE_LIMIT_MBPS} (超出测速文件容量)"
    if args.speed_concurrency < 1:
        return "--speed-concurrency 必须 >= 1"
    if args.speed_duration < MIN_OBSERVE_SECONDS:
        return f"--speed-duration 不能小于 {MIN_OBSERVE_SECONDS} 秒 (爬升慢的节点需要足够观测时间)"
    if args.drop_below_mbps and args.drop_below_mbps > args.min_speed_mbps:
        return "--drop-below-mbps 不能高于 --min-speed-mbps"
    return None
