# -*- coding: utf-8 -*-
"""
测活 -> 服务检测线 ∥ 测速线 -> 汇总交叉核对 的完整编排 (参考 subs-check 分段流水线)。
mihomo 主流水线 (probe_services.py) 与 sing-box 备用流水线 (probe_singbox.py) 共用本模块，流程与判据完全一致，
差异只在内核适配器如何为节点启动本地监听:
  1. 测活: 全部节点并发测活 (多目标多次，全部失败才判死)；本地直连不通的节点经最多 3 个不同服务器的已判活前置链式重试。
  2. 服务检测线 与 测速线 并行: 节点一判活即分别入队；同一节点不同时被两条线占用；
     受并行流量干扰且未达标的测速，留到服务检测全部结束、链路空闲时重测。
     需前置的落地节点按序最多备 3 个前置: 某个前置到该节点不通时换下一个继续服务检测与测速。
  3. 汇总交叉核对: 出口、前置重合、测速结论统一核对后才淘汰，再评选 Key、打标编号，由入口脚本导出配置。
同一套代码与判据在本地与 GitHub Actions 运行，--profile auto 按环境自动选择资源参数 (云端不做前置链式测活)。

内核适配器 (core.mihomo_runner.MihomoKernel / core.singbox_runner.SingboxKernel) 约定:
  label: 内核名称；node(row): 交给内核的节点配置；
  start(stack, entries, monitor, shard_size): entries 为 [(key, 节点配置, 前置节点配置或 None)]，
      返回 ({key: 本地监听端口}, {key: 失败原因})，监听存活到 stack 关闭。
"""
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack

from .ai_probe import probe_all_ai
from .egress_geo import flag_emoji, probe_egress, probe_geolocation
from .key_evaluator import is_front_capable, is_landing_role, pick_front_nodes, rank_front_candidates, select_key_nodes
from .liveness import MAX_CHAIN_FRONTS, check_alive, check_alive_via_fronts, pick_chain_fronts, rank_chain_fronts
from .media_probe import probe_all_media
from .mihomo_runner import direct_listener
from .pipeline import SERVICE, SPEED, DualLineScheduler, Job
from .renderer import check_template
from .run_profile import add_speed_arguments, apply_profile, validate_speed_options
from .shield_probe import probe_sites_browser, probe_sites_http, shield_passed
from .speed_probe import (DEFAULT_SUSTAINED_TARGETS, FRONT_FALLBACK_TIER, apply_speed_result, better_measurement,
                          describe_speed, measure_speed_and_stall, measure_with_retry, speed_options,
                          speed_verdict_text)
from .tagger import tag_and_rename_nodes
from .traffic_monitor import TrafficMonitor, assess_contention
from .youtube_probe import probe_youtube

CHECKPOINT_VERSION = 2
CHECKPOINT_INTERVAL = 5.0
# 第二轮直连复测的并发 (首轮高并发下 UDP 类节点可能被误伤，复测压低并发)
RECHECK_WORKERS = 4


def add_flow_arguments(parser):
    """两条流水线共用的流程参数 (输入输出与内核路径等入口相关参数由各脚本自行添加)。"""
    parser.add_argument("--report", "-r", help="保存测试详情的 JSON 报告文件路径")
    parser.add_argument("--template", "-t", help="自定义 Clash 母版模版路径 (默认使用内置 template.yaml)")
    parser.add_argument("--tests", default="all", help="指定测试维度: all, 或组合逗号分隔 ip,ai,youtube,shield,media,speed")
    parser.add_argument("--no-browser", action="store_true", help="轻量模式: 跳过 Playwright 浏览器实测 (跳过 YouTube 与浏览器免盾)")
    parser.add_argument("--iface", help="绑定物理网卡名称 (如 WLAN, 以太网)，防止被本地 TUN (如 Karing) 接管，不指定则自动探测")
    parser.add_argument("--direct-proxy",
                        help="跑机基线出口探测改走指定的直连代理 (如 http://127.0.0.1:24999)；默认经 mihomo 绑定物理网卡直连测得")
    parser.add_argument("--mihomo", help="显式指定 Mihomo 可执行文件路径 (跑机基线出口也经它探测)")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="单个临时内核实例承载的节点监听数 (默认: 64)；某节点配置被内核拒绝时自动二分隔离")
    parser.add_argument("--alive-workers", type=int, default=16, help="首轮测活并发数 (默认: 16)")
    parser.add_argument("--workers", type=int, default=4, help="服务检测线同时检测的节点数 (默认: 4)")
    parser.add_argument("--dry-run", action="store_true", help="干跑测试: 仅解析节点与模版，不发起真实网络连接")
    parser.add_argument("--start-index", type=int, default=0, help="从指定节点序号 (0-based) 开始测试")
    parser.add_argument("--checkpoint", help="断点续测状态 JSON 文件路径 (逐节点保存已完成结果，续测时跳过)")
    parser.add_argument("--resort", action="store_true",
                        help="仅在用户主动要求重排序时使用: 同地区按标签与信誉重排并从 1 重新编号 (默认保留原节点编号)")
    parser.add_argument("--merge-into", default=None,
                        help="合流目标配置路径 (Clash YAML / sing-box JSON): 测试完成后直接并入目标订阅底库")
    parser.add_argument("--insert", dest="insert_mode", action="store_true",
                        help="合流时的中间插入模式: 打破原有编号完全重排序并从 1 重新编号 (默认优先保留目标底库原节点及原有编号)")
    # 持续下载测速与 Key 遴选选项 (非主动技能: 默认不开启，仅在用户显式指定时触发)
    add_speed_arguments(parser)


def print_summary_table(results, speed_tested=False):
    print("\n" + "=" * 123)
    speed_col_name = "稳态带宽" if speed_tested else "带宽"
    print(f"{'序号':<4} | {'最终命名':<32} | {'出口IP':<15} | {'延迟':<6} | {'信誉':<5} | {'AI':<4} | {'免盾':<4} | {'YT':<4} | {'流媒体':<6} | {speed_col_name:<12} | {'角色'}")
    print("-" * 123)
    for idx, r in enumerate(results, 1):
        name = r.get("final_name", r["proxy"].get("name", "unk"))
        if len(name) > 30:
            name = name[:28] + ".."
        ip = r.get("exit_ip") or "未知"
        delay = f"{r['delay']:.0f}ms" if r.get("delay") else "-"
        reputation = r.get("ip_reputation") or (r.get("ip_info") or {}).get("reputation") or {}
        score = str(reputation.get("score")) if reputation.get("score") is not None else "-"
        ai = "✓" if r.get("ai_supported") else "✗"
        shield = "✓" if r.get("shield_passed") else "✗"
        yt = "✓" if r.get("youtube_passed") else "✗"

        media_str = []
        md = r.get("media_details") or {}
        if md.get("nf"):
            media_str.append("NF")
        if md.get("dp"):
            media_str.append("D+")
        media = "+".join(media_str) if media_str else "-"

        if speed_tested and r.get("speed_result"):
            speed_text = f"{r.get('speed_mbps') or 0.0:.1f} Mbps"
        elif r.get("speed_kbs"):
            speed_text = f"{r.get('speed_kbs')} KB/s"
        else:
            speed_text = "-"

        role = ("Key跳板" if r.get("is_key") else "备用前置" if r.get("is_front_fallback") else
                "Fast" if r.get("is_fast") else "落地" if r.get("is_landing") else "直连")
        print(f"{idx:<4} | {name:<32} | {ip:<15} | {delay:<6} | {score:<5} | {ai:<4} | {shield:<4} | {yt:<4} | {media:<6} | {speed_text:<12} | {role}")
    print("=" * 123 + "\n")


def probe_runner_baseline(args, mihomo_bin):
    """
    跑机真实出口基线，用于识别"流量未经节点转发"的节点。
    指定 --direct-proxy 时以其为准；否则经 mihomo DIRECT 监听、绑定与节点测试相同的物理网卡测得。
    系统路由出口可能被本机客户端的 TUN/系统代理接管，等于本机正在使用的节点出口，只记录、不作基线，
    否则正在使用的节点会被误判为"出口与本机重合"而淘汰。
    """
    if args.direct_proxy:
        runner_ips = set(probe_egress({"http": args.direct_proxy, "https": args.direct_proxy})["observed_ips"])
        print(f"      跑机基线出口 (--direct-proxy): {sorted(runner_ips) or '未检测到'}")
    else:
        runner_ips = set()
        try:
            with direct_listener(args.iface, mihomo_bin) as port:
                url = f"http://127.0.0.1:{port}"
                runner_ips = set(probe_egress({"http": url, "https": url})["observed_ips"])
        except Exception as e:
            print(f"      [警告] 物理网卡直连基线探测失败: {e}")
        print(f"      物理网卡直连出口 (跑机基线): {sorted(runner_ips) or '未检测到'}")
        system_ips = set(probe_egress(None)["observed_ips"])
        if system_ips and system_ips != runner_ips:
            print(f"      系统路由出口: {sorted(system_ips)} —— 与物理直连不同，本机客户端正经 TUN/系统代理使用节点；"
                  f"该出口不作基线，正在使用的节点照常测试")
    if not runner_ips:
        print("      [警告] 未取得跑机基线，本轮不做\"出口与本机重合\"淘汰")
    return runner_ips


def test_dimensions(args):
    req_tests = set(t.strip().lower() for t in args.tests.split(","))
    do_all = "all" in req_tests
    test_speed = do_all or "speed" in req_tests or args.speed_test
    shield = do_all or "shield" in req_tests
    return {
        "ai": do_all or "ai" in req_tests,
        "media": do_all or "media" in req_tests,
        "shield": shield,
        "browser_shield": shield and not args.no_browser,
        "youtube": (do_all or "youtube" in req_tests) and not args.no_browser,
        # 未主动测速时由 3 秒防断流快检兜底；主动测速时完整测速已覆盖断流判定
        "stall": test_speed and not args.speed_test,
    }


def run_services(row, proxy_url, dims, runner_ips):
    """
    服务检测线的单节点任务：出口 -> (YouTube 实播 ∥ 属地/AI/流媒体/免盾)。
    两路互不依赖，并行执行 (单节点耗时由约 60 秒降到约 30 秒)。淘汰原因写入 row["service_drop"]，由汇总阶段统一处理。
    runner_ips: 返回跑机基线出口集合的函数 (基线在后台探测，首次调用时等待)。
    """
    node_proxies = {"http": proxy_url, "https": proxy_url}
    egress = probe_egress(node_proxies)
    exit_ip = egress["ipv4"]["ip"] or egress["ipv6"]["ip"]
    row["exit_ip"], row["egress"] = exit_ip, egress
    if not exit_ip:
        row["service_drop"] = ("未验证到公网出口" if row["path"] == "direct"
                               else f"经前置({row.get('front_node')})未验证到公网出口")
        return
    if exit_ip in runner_ips():
        row["service_drop"] = ("出口与本机物理直连出口重合(流量未经该节点转发)" if row["path"] == "direct"
                               else "出口与本机出口重合(流量未经该节点转发)")
        return

    if dims["stall"]:
        sp_res = measure_speed_and_stall(node_proxies)
        row.update(sp_res)
        if sp_res.get("eliminated_reason"):
            row["service_drop"] = sp_res["eliminated_reason"]
            return
    else:
        row.setdefault("speed_kbs", 0)
    # 注意: 测速线可能先于本任务完成，不能在此重置 is_fast 等测速字段 (Fast/Key 只由完整测速授予)

    browser = {}
    player = None
    if dims["youtube"]:
        def play():
            browser["youtube"] = probe_youtube(proxy_url, expected_ip=exit_ip)
        player = threading.Thread(target=play, daemon=True)
        player.start()
    try:
        # 共享属地证据链：显式 Google 地区、绑定出口的 GeoIP、前后出口复核
        row.update(probe_geolocation(node_proxies, egress=egress))
        if dims["ai"]:
            ai_res = probe_all_ai(node_proxies, google_region_info=row["google_region"])
            row["ai_supported"] = bool(ai_res["ai_supported"] and row["geo_decision"]["egress_stable"]
                                       and not row["geo_decision"]["is_pool"])
            row["ai_details"] = ai_res["details"]
            row["ai_observations"] = ai_res["observations"]
            row["ai_summary"] = ai_res.get("summary", {})
        else:
            row["ai_supported"], row["ai_details"] = False, {}
            row["ai_summary"] = {}
        if dims["media"]:
            media_res = probe_all_media(node_proxies)
            row["media_supported"] = media_res["media_supported"]
            row["media_details"] = media_res["details"]
        else:
            row["media_supported"], row["media_details"] = False, {}
        if dims["shield"]:
            http_shield = probe_sites_http(node_proxies)
            browser_res = probe_sites_browser(proxy_url) if dims["browser_shield"] else {}
            combined_shield = {k: browser_res.get(k) or v for k, v in http_shield.items()}
            row["shield_passed"] = shield_passed(combined_shield)
            row["shield_details"] = combined_shield
        else:
            row["shield_passed"], row["shield_details"] = False, {}
    finally:
        if player is not None:
            player.join()
    yt_res = browser.get("youtube") or ({"status": "unknown", "reason": "player_thread_failed"} if dims["youtube"] else {})
    row["youtube_passed"] = yt_res.get("status") == "passed"
    row["youtube_details"] = yt_res


class Checkpoint:
    """
    逐节点断点: 已完成全部阶段的节点结果按输入指纹保存，续测时直接复用，未完成的节点从测活重新开始。
    检查点记录所用内核，换内核 (mihomo / sing-box) 续测时不复用另一内核的结论。
    """

    def __init__(self, path, proxies, kernel="mihomo"):
        self.path = path
        self.kernel = kernel
        digest = hashlib.sha256()
        for p in proxies:
            digest.update(json.dumps([p.get("name"), p.get("server"), p.get("port"), p.get("type")],
                                     ensure_ascii=False).encode("utf-8"))
        self.fingerprint = digest.hexdigest()
        self.rows = {}
        self._lock = threading.Lock()
        self._last = 0.0

    def load(self):
        if not self.path or not os.path.isfile(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"      [警告] 读取检查点失败: {e}")
            return {}
        # 早期检查点不带 kernel 字段，均由 mihomo 流水线写出
        if (data.get("version") != CHECKPOINT_VERSION or data.get("fingerprint") != self.fingerprint
                or data.get("kernel", "mihomo") != self.kernel):
            print("      [提示] 检查点与本次输入、内核或版本不一致，忽略并从头测试")
            return {}
        self.rows = {int(k): v for k, v in (data.get("rows") or {}).items()}
        return dict(self.rows)

    def record(self, row, force=False):
        if not self.path:
            return
        with self._lock:
            if row is not None:
                self.rows[row["idx"]] = row
            now = time.monotonic()
            if not force and now - self._last < CHECKPOINT_INTERVAL:
                return
            self._last = now
            payload = {"version": CHECKPOINT_VERSION, "kernel": self.kernel, "fingerprint": self.fingerprint,
                       "rows": {str(k): v for k, v in self.rows.items()}}
            tmp = f"{self.path}.tmp"
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp, self.path)
            except (OSError, TypeError, ValueError) as e:
                print(f"      [警告] 写入检查点失败: {e}")


class ProbeRun:
    """一次完整运行的状态与各阶段编排。"""

    def __init__(self, args, profile_name, kernel, proxies, mihomo_bin=None):
        self.args = args
        self.profile_name = profile_name
        self.kernel = kernel
        self.mihomo_bin = mihomo_bin
        self.dims = test_dimensions(args)
        self.speed_opts = speed_options(args)
        self.speed_targets = [args.speed_target] if args.speed_target else DEFAULT_SUSTAINED_TARGETS
        self.t0 = time.monotonic()
        self._print_lock = threading.Lock()
        self.monitor = TrafficMonitor()
        self.checkpoint = Checkpoint(args.checkpoint, proxies, kernel.label)
        # 链式前置只用于本地：云端 Runner 在海外，直连不通即视为不可用
        self.chain_enabled = profile_name == "local" and not args.no_landing_probe
        self.rows = [{"idx": i, "proxy": p, "orig_name": p.get("name")} for i, p in enumerate(proxies)]
        self.ports = {}         # 直连监听: 节点序号 -> 端口
        self.chain_ports = {}   # 经前置监听: (节点序号, 前置序号) -> 端口，测活、服务检测与测速共用
        self.timeline = {}
        self.landing_speed_fronts = []
        self.sched = None
        self._baseline = None

    # ---- 基础设施 ----
    def log(self, message):
        with self._print_lock:
            print(f"[{time.monotonic() - self.t0:6.1f}s] {message}")

    def mark(self, name):
        self.timeline[name] = round(time.monotonic() - self.t0, 1)

    def runner_ips(self):
        return self._baseline.result()

    def assess(self, measured):
        return assess_contention(measured, self.monitor, capacity_floor=self.args.rate_limit_mbps,
                                 service_busy=self.sched.service_busy)

    def node_label(self, row):
        return row["proxy"].get("name")

    def front_label(self, front_idx):
        return self.rows[front_idx]["proxy"].get("name")

    def row_done(self, row):
        """所有适用阶段都有结论 (用于断点保存)。"""
        if not row.get("liveness_done"):
            return False
        if not row.get("alive"):
            return True
        if not row.get("service_done"):
            return False
        return (not self.args.speed_test or bool(row.get("speed_final") or row.get("speed_skipped")
                                                 or row.get("service_drop")))

    def finished(self, row):
        if self.row_done(row):
            self.checkpoint.record(row)

    # ---- 本地监听 (内核适配器) ----
    def start_group(self, stack, entries):
        """entries: [(key, 行, 前置行或 None)]，节点配置由内核适配器给出。返回 ({key: 端口}, {key: 失败原因})。"""
        node = self.kernel.node
        return self.kernel.start(stack, [(key, node(row), None if front is None else node(front))
                                         for key, row, front in entries],
                                 monitor=self.monitor, shard_size=self.args.batch_size)

    def start_chains(self, stack, pairs):
        """为 (节点行, 前置行) 组合启动经前置的监听，已有的组合直接复用；返回 {(节点序号, 前置序号): 失败原因}。"""
        missing = [((row["idx"], front["idx"]), row, front) for row, front in pairs
                   if (row["idx"], front["idx"]) not in self.chain_ports]
        if not missing:
            return {}
        ports, failed = self.start_group(stack, missing)
        self.chain_ports.update(ports)
        return failed

    def port_of(self, row, front_idx=None):
        return self.ports[row["idx"]] if front_idx is None else self.chain_ports[(row["idx"], front_idx)]

    # ---- 两条线的任务 ----
    def resources(self, row, front_idx=None):
        keys = {("node", row["idx"])}
        if front_idx is not None:
            keys.add(("node", front_idx))
        return keys

    def service_job(self, row):
        front_idx = row.get("front_idx")
        proxy_url = f"http://127.0.0.1:{self.port_of(row, front_idx)}"

        def run():
            if row["path"] == "direct" and row.get("speed_final") and row.get("speed_drop"):
                # 测速已给出最终淘汰结论的直连节点无需再做服务检测
                row["services_skipped"] = "测速已判淘汰"
                row["service_done"] = True
                self.finished(row)
                return
            started = time.monotonic()
            try:
                run_services(row, proxy_url, self.dims, self.runner_ips)
            except Exception as e:
                row["service_drop"] = f"服务检测异常:{type(e).__name__}: {e}"
            row["service_seconds"] = round(row.get("service_seconds", 0.0) + time.monotonic() - started, 1)
            if self.switch_service_front(row):
                return
            row["service_done"] = True
            if row.get("service_drop"):
                self.log(f"[服务✗] {self.node_label(row)}: {row['service_drop']}")
            else:
                ai_sum = row.get("ai_summary") or {}
                core_passed = ai_sum.get("passed", 5 if row.get("ai_supported") else 0)
                core_total = ai_sum.get("total", 5)
                failed_core = ai_sum.get("failed_services", [])
                abbr_map = {"openai": "OAI", "claude": "Cla", "gemini": "Gem", "huggingface": "HF", "grok": "Grok", "groq": "Groq"}
                if row.get("ai_supported"):
                    ai_text = f"AI: {core_total}/{core_total}✓"
                elif failed_core:
                    failed_abbr = ",".join(abbr_map.get(s, s[:3].title()) for s in failed_core[:2])
                    ai_text = f"AI: {core_passed}/{core_total}✗({failed_abbr})"
                else:
                    ai_text = f"AI: {'✓' if row.get('ai_supported') else '✗'}"
                self.log(f"[服务✓] {flag_emoji(row.get('cc'))} {self.node_label(row)} | IP: {row.get('exit_ip')} | "
                         f"{ai_text} | YT: {'✓' if row.get('youtube_passed') else '✗'} | "
                         f"盾: {'✓' if row.get('shield_passed') else '✗'} | {row['service_seconds']}s")
            self.finished(row)
        return Job(run, self.resources(row, front_idx), tag=row["path"], name=self.node_label(row))

    def switch_service_front(self, row):
        """
        经前置未验证到公网出口 (该前置到此节点不通) 时换下一个备用前置重做服务检测；已换返回 True。
        备用前置为测活时未判不通的其余前置，连同首个前置合计最多 MAX_CHAIN_FRONTS 个。
        """
        if row["path"] != "front" or row.get("exit_ip") or row.get("egress") is None:
            return False
        backups = [f for f in row.get("front_backups") or [] if (row["idx"], f) in self.chain_ports]
        if not backups:
            return False
        tried = row["front_node"]
        row.setdefault("front_attempts", []).append(
            {"stage": "service", "front": tried, "reason": row.pop("service_drop", None)})
        row.pop("egress")
        row.pop("exit_ip", None)
        row.update(front_idx=backups[0], front_node=self.front_label(backups[0]), front_backups=backups[1:])
        self.log(f"[服务~] {self.node_label(row)}: 经前置 {tried} 未验证到公网出口，换前置 {row['front_node']} 重测")
        self.sched.add(SERVICE, self.service_job(row))
        return True

    def speed_job(self, row, front_idx=None, quiet=False):
        criteria = self.speed_opts["criteria"]
        proxy_url = f"http://127.0.0.1:{self.port_of(row, front_idx)}"

        def run():
            if row.get("service_drop"):
                row["speed_skipped"] = "服务检测已判淘汰"
                self.finished(row)
                return
            measured, deferred = measure_with_retry(proxy_url, self.speed_opts, self.speed_targets,
                                                    assess=self.assess)
            if quiet:
                measured = better_measurement(row.pop("speed_pending"), measured)
            elif deferred:
                row["speed_pending"] = measured
                contention = measured.get("contention") or {}
                self.log(f"[测速~] {self.node_label(row)}: {describe_speed(measured)} | 受并行检测流量干扰"
                         f" (服务检测占用均值 {contention.get('background_mbps', '?')}Mbps)，链路空闲后重测")
                self.sched.add(SPEED, self.speed_job(row, front_idx, quiet=True))
                return
            if (front_idx is not None and measured.get("stable_mbps") is None
                    and self.switch_speed_front(row, front_idx, measured)):
                return
            apply_speed_result(row, measured, criteria)
            row["speed_final"] = True
            via = ""
            if front_idx is not None:
                row.update(speed_front_idx=front_idx, speed_front_node=self.front_label(front_idx))
                via = f" (经前置 {row['speed_front_node']})"
            self.log(f"[测速] {self.node_label(row)}{via}: {speed_verdict_text(row)} | {describe_speed(measured)}")
            self.finished(row)
        return Job(run, self.resources(row, front_idx), quiet=quiet,
                   tag="landing" if front_idx is not None else "direct", name=self.node_label(row))

    def switch_speed_front(self, row, front_idx, measured):
        """
        经该前置取不到任何测速样本 (前置到此节点不通) 时换下一个备选前置重测；已换返回 True。
        取不到样本的前置记入 speed_unreachable_fronts，全部备选前置都不通时由汇总阶段据此判定。
        """
        row.setdefault("speed_unreachable_fronts", []).append(front_idx)
        row.setdefault("front_attempts", []).append(
            {"stage": "speed", "front": self.front_label(front_idx), "reason": describe_speed(measured)})
        queue = row.get("speed_front_queue") or []
        if not queue:
            return False
        row["speed_front_queue"] = queue[1:]
        self.log(f"[测速~] {self.node_label(row)}: 经前置 {self.front_label(front_idx)} 取不到测速样本，"
                 f"换前置 {self.front_label(queue[0])} 重测")
        self.sched.add(SPEED, self.speed_job(row, queue[0]))
        return True

    def enqueue(self, row):
        # 先让测速线看见任务，再放行服务任务，避免工作线程抢先占满所有节点、让测速线空等。
        if self.args.speed_test and row["path"] == "direct":
            self.sched.add(SPEED, self.speed_job(row))
        self.sched.add(SERVICE, self.service_job(row))

    # ---- 阶段 1: 测活 ----
    def run_liveness(self, stack, pending):
        ports, failed = self.start_group(stack, [(row["idx"], row, None) for row in pending])
        self.ports.update(ports)
        for idx, reason in failed.items():
            row = self.rows[idx]
            row.update(alive=False, liveness_done=True, eliminated_reason=reason)
            self.log(f"[测活✗] {self.node_label(row)}: {reason}")
            self.finished(row)
        testable = [row for row in pending if row["idx"] in ports]
        self.log(f"首轮测活: {len(testable)} 个节点 (并发 {self.args.alive_workers}，每节点最多 3 次、轮换 3 个端点，全部失败才判不通)...")
        dead = []
        with ThreadPoolExecutor(max_workers=max(1, self.args.alive_workers)) as pool:
            futures = {pool.submit(self.probe_direct, ports[row["idx"]]): row for row in testable}
            for future in as_completed(futures):
                row = futures[future]
                row["liveness"] = future.result()
                if row["liveness"]["alive"]:
                    self.conclude_direct(row)
                else:
                    dead.append(row)
        self.mark("direct_liveness_done")
        return dead

    @staticmethod
    def probe_direct(port):
        try:
            return check_alive(f"http://127.0.0.1:{port}")
        except Exception as e:
            return {"alive": False, "latency_ms": None, "attempts": [], "error": f"{type(e).__name__}: {e}"}

    def conclude_direct(self, row, note=""):
        row.update(alive=True, liveness_done=True, path="direct", delay=row["liveness"]["latency_ms"],
                   is_landing=is_landing_role(row["proxy"]))
        self.log(f"[测活✓] {self.node_label(row)}: 直连 {row['delay']:.0f}ms{note}")
        self.enqueue(row)

    def run_second_round(self, stack, dead):
        """
        首轮直连不通的节点做第二轮 (首轮高并发下 UDP 类节点可能被误伤):
        - 低并发直连复测，复测通过按直连处理；
        - 同时 (仅本地) 经最多 3 个不同服务器的已判活前置链式测活，任一前置测通即可判为需前置的落地节点。
        输入已声明为落地 (dialer-proxy/_Lnd/_USAI) 的节点经前置测通即放行，不等直连复测；
        其余节点两路都有结论后再定: 直连复测通过优先，其次经前置，两路都不通才判不可达。
        """
        if not dead:
            return
        plans = {row["idx"]: [] for row in dead}
        if self.chain_enabled:
            alive_direct = [r for r in self.rows if r.get("alive") and r.get("path") == "direct"
                            and not r.get("is_landing") and r.get("liveness")]
            pairs = []
            for row in dead:
                fronts = rank_chain_fronts(alive_direct, row["proxy"])
                plans[row["idx"]] = [f["idx"] for f in fronts]
                pairs += [(row, f) for f in fronts]
            self.start_chains(stack, pairs)
        self.log(f"第二轮测活: {len(dead)} 个首轮直连不通的节点，低并发直连复测"
                 + (f"，同时经最多 {MAX_CHAIN_FRONTS} 个不同服务器的已判活前置链式测活..." if self.chain_enabled else
                    " (云端 Runner 不做前置链式测活)..." if self.profile_name != "local" else
                    " (已用 --no-landing-probe 关闭前置链式测活)..."))

        def via_fronts(row):
            port_by_front = {f: self.chain_ports[(row["idx"], f)] for f in plans[row["idx"]]
                             if (row["idx"], f) in self.chain_ports}
            return check_alive_via_fronts(port_by_front)

        state = {row["idx"]: {} for row in dead}
        with ThreadPoolExecutor(max_workers=RECHECK_WORKERS) as recheck_pool, \
                ThreadPoolExecutor(max_workers=max(1, self.args.alive_workers)) as chain_pool:
            futures = {recheck_pool.submit(self.probe_direct, self.ports[row["idx"]]): (row, "direct") for row in dead}
            if self.chain_enabled:
                futures.update({chain_pool.submit(via_fronts, row): (row, "chain") for row in dead})
            for future in as_completed(futures):
                row, kind = futures[future]
                seen = state[row["idx"]]
                seen[kind] = future.result()
                if not row.get("liveness_done"):
                    self.conclude_second_round(row, seen, plans[row["idx"]])
        self.mark("second_round_done")

    def conclude_second_round(self, row, seen, plan):
        recheck, chain = seen.get("direct"), seen.get("chain")
        if recheck is not None and recheck["alive"]:
            recheck["first_round"] = row["liveness"]
            row["liveness"] = recheck
            self.conclude_direct(row, note=" (首轮未通，低并发复测通过)")
            return
        best = chain[0] if chain else None
        declared_landing = is_landing_role(row["proxy"])
        if best is not None and (declared_landing or recheck is not None):
            self.conclude_front(row, best, chain[1], plan)
            return
        chain_pending = self.chain_enabled and chain is None
        if recheck is None or chain_pending:
            return  # 另一路尚未出结论
        row["liveness"]["recheck"] = recheck
        if chain is not None:
            row["chain_liveness"] = {self.front_label(f): res for f, res in chain[1].items()}
        tried = "、".join(self.front_label(f) for f in plan)
        reason = (f"两轮直连与经前置({tried})均不可达" if tried else
                  "两轮直连均不可达" + ("，且无可用前置" if self.chain_enabled else
                                     " (云端 Runner 不做前置链式测活)" if self.profile_name != "local" else
                                     " (已关闭前置链式测活)"))
        row.update(alive=False, liveness_done=True, eliminated_reason=reason)
        self.log(f"[测活✗] {self.node_label(row)}: {reason}")
        self.finished(row)

    def conclude_front(self, row, best, per_front, plan):
        row["chain_liveness"] = {self.front_label(f): res for f, res in per_front.items()}
        # 测通的前置先用；其余未判不通的前置 (含测活尚未出结论的) 依序备用
        row["front_backups"] = [f for f in plan if f != best and (per_front.get(f) or {}).get("alive") is not False]
        row.update(alive=True, liveness_done=True, path="front", is_landing=True, front_idx=best,
                   front_node=self.front_label(best), delay=per_front[best]["latency_ms"])
        self.log(f"[测活✓] {self.node_label(row)}: 直连不通，经前置 {row['front_node']} 测通 {row['delay']:.0f}ms (落地)")
        self.sched.add(SERVICE, self.service_job(row))

    # ---- 落地节点测速 ----
    def schedule_landing_speed(self, stack):
        """
        直连测速 (含受干扰后的空闲重测) 结束后给落地节点测速。备选前置按 Key 候选 -> 备用前置档依评分排列，
        每个落地节点最多备 3 个不同服务器的前置 (走 UDP 的节点优先声明支持 UDP 的前置)，
        某个前置取不到测速样本 (到该节点不通) 时换下一个。
        """
        landing = [r for r in self.rows if r.get("alive") and r.get("path") == "front" and not r.get("speed_final")]
        if not landing:
            return
        self.sched.wait_until(lambda s: s.pending(SPEED, lambda job: job.tag == "direct") == 0)
        candidates = [r for r in self.rows if r.get("path") == "direct" and r.get("speed_final")
                      and not r.get("is_landing") and is_front_capable(r["proxy"])
                      and not r.get("service_drop") and not r.get("speed_drop")]
        # 测速可能先于服务线取得出口；没有出口证据不能选前置，也不能提前误报“无合格前置”。
        self.sched.wait_until(lambda s: all(r.get("exit_ip") or r.get("service_done") for r in candidates)
                              or s.pending(SERVICE, lambda job: job.tag == "direct") == 0)
        candidates = [r for r in candidates if not r.get("service_drop")]
        ranked, kinds = [], {}
        for kind, tier in (("Key 候选", (self.args.min_speed_mbps, self.args.min_floor_mbps)),
                           ("备用前置", FRONT_FALLBACK_TIER)):
            for _, _, front in rank_front_candidates(candidates, *tier):
                if front["idx"] not in kinds:
                    kinds[front["idx"]] = kind
                    ranked.append(front)
        if not ranked:
            for row in landing:
                row["speed_skipped"] = "无测速达标的可前置节点，无法为落地节点测速"
                self.log(f"[测速-] {self.node_label(row)}: {row['speed_skipped']}")
                self.finished(row)
            return
        plans = {row["idx"]: pick_chain_fronts(ranked, row["proxy"]) for row in landing}
        failed = self.start_chains(stack, [(row, front) for row in landing for front in plans[row["idx"]]])
        used = {front["idx"] for plan in plans.values() for front in plan}
        self.landing_speed_fronts = [{"idx": f["idx"], "name": f["proxy"].get("name"), "kind": kinds[f["idx"]]}
                                     for f in ranked if f["idx"] in used]
        self.log(f"落地节点测速: {len(landing)} 个，每个节点按序最多备 {MAX_CHAIN_FRONTS} 个前置 (取不到样本时换下一个): "
                 + "、".join(f"[{f['kind']}] {f['name']}" for f in self.landing_speed_fronts))
        for row in landing:
            plan = [front["idx"] for front in plans[row["idx"]]]
            queue = [f for f in plan if (row["idx"], f) in self.chain_ports]
            if not queue:
                reasons = [failed[(row["idx"], f)] for f in plan if (row["idx"], f) in failed]
                row["speed_skipped"] = reasons[0] if reasons else "前置链路启动失败，无法为落地节点测速"
                self.log(f"[测速-] {self.node_label(row)}: {row['speed_skipped']}")
                self.finished(row)
                continue
            row["speed_front_queue"] = queue[1:]
            self.sched.add(SPEED, self.speed_job(row, front_idx=queue[0]))

    # ---- 主流程 ----
    def execute(self):
        args = self.args
        restored = self.checkpoint.load()
        for idx, saved in restored.items():
            if 0 <= idx < len(self.rows) and saved.get("orig_name") == self.rows[idx]["orig_name"]:
                saved["proxy"] = self.rows[idx]["proxy"]
                self.rows[idx] = saved
        pending = [r for r in self.rows[args.start_index:] if not r.get("liveness_done")
                   or (r.get("alive") and not self.row_done(r))]
        for row in pending:
            for key in list(row):
                if key not in ("idx", "proxy", "orig_name"):
                    del row[key]
        if restored:
            self.log(f"[断点] 复用已完成节点 {sum(1 for r in self.rows if self.row_done(r))} 个，待测 {len(pending)} 个")

        speed_workers = args.speed_concurrency if args.speed_test else 0
        self.sched = DualLineScheduler(max(1, args.workers), speed_workers,
                                       on_error=lambda line, job: self.log(f"[任务异常] {job.name} ({line}): {job.error}"))
        with ExitStack() as stack, ThreadPoolExecutor(max_workers=1) as baseline_pool:
            stack.callback(self.monitor.stop)
            self._baseline = baseline_pool.submit(probe_runner_baseline, args, self.mihomo_bin)
            self.sched.open_producer(SERVICE, SPEED)
            self.sched.start()
            try:
                dead = self.run_liveness(stack, pending) if pending else []
                self.run_second_round(stack, dead)
            finally:
                self.sched.close_producer(SERVICE)
            try:
                if args.speed_test:
                    self.schedule_landing_speed(stack)
            finally:
                self.sched.close_producer(SPEED)
            self.sched.join()
            self.mark("lines_done")
            self.runner_ips()
        self.checkpoint.record(None, force=True)

    # ---- 阶段 3: 汇总交叉核对 ----
    def aggregate(self):
        args = self.args
        results, eliminated = [], []

        def drop(row, reason):
            row["eliminated_reason"] = reason
            eliminated.append(row)

        runner_ips = self.runner_ips()
        for row in self.rows[args.start_index:]:
            if not row.get("alive"):
                drop(row, row.get("eliminated_reason") or "未测活")
                continue
            if not self.row_done(row):
                drop(row, "检测任务未完成，不能作为合格节点导出 (详见运行日志)")
                continue
            if row.get("service_drop"):
                drop(row, row["service_drop"])
                continue
            if row.get("path") == "front":
                front = self.rows[row["front_idx"]]
                blocked = runner_ips | set((front.get("egress") or {}).get("observed_ips") or []) | {front.get("exit_ip")}
                if row.get("exit_ip") in blocked:
                    drop(row, "出口与前置节点或本机出口重合(流量未经该节点转发)")
                    continue
            elif args.speed_test and row.get("speed_drop"):
                drop(row, row["speed_drop"])
                continue
            row.pop("eliminated_reason", None)
            results.append(row)

        if args.speed_test and results:
            measured_rows = [r for r in results if r.get("speed_result") and r.get("path") == "direct"]
            fast_count = sum(1 for r in measured_rows if r.get("is_fast"))
            print(f"\n[汇总] 保留的直连节点测速达标 {fast_count}/{len(measured_rows)}，执行 Key 优质前置跳板节点评选与配额分配...")
            if measured_rows and not fast_count and self.profile_name == "local":
                best = max((r["speed_result"].get("stable_mbps") or 0.0) for r in measured_rows)
                print(f"      [提示] 无节点达到 {args.min_speed_mbps}Mbps 门槛 (最高稳态 {best}Mbps)。"
                      f"若本机宽带下行低于 {args.rate_limit_mbps}Mbps，结果受本地线路限制。")
            chosen_keys = select_key_nodes(results, max_keys=10, per_country_cap=3,
                                           min_stable_mbps=args.min_speed_mbps, min_floor_mbps=args.min_floor_mbps)
            print(f"      成功评选出 {len(chosen_keys)} 个 Key 优质前置跳板节点")
            # 落地节点的速度受前置限制：只有经最终入选 Key 的前置测得的结论才据以淘汰；
            # 所有备选前置都取不到样本时，按其中入选 Key 的前置判定 (经这些 Key 都连不上，配置中的前置组也带不动它)
            for row in [r for r in results if r.get("path") == "front" and r.get("speed_drop")]:
                sampled = (row.get("speed_result") or {}).get("stable_mbps") is not None
                judged = ([row["speed_front_idx"]] if sampled else
                          row.get("speed_unreachable_fronts") or [row["speed_front_idx"]])
                keys = [self.front_label(f) for f in judged if self.rows[f].get("is_key")]
                if not keys:
                    row["speed_note"] = ("经非 Key 前置测速，速度受前置限制，只记录不淘汰" if sampled else
                                         f"经 {len(judged)} 个前置均取不到测速样本，前置均未入选 Key，只记录不淘汰")
                    continue
                results.remove(row)
                drop(row, row["speed_drop"] if sampled else
                     f"经前置({'、'.join(self.front_label(f) for f in judged)})均取不到测速样本 "
                     f"(其中已入选 Key: {'、'.join(keys)})")

        if any(r.get("path") == "front" for r in results):
            directs = [r for r in results if r.get("path") == "direct"]
            if args.speed_test:
                fronts, kind = pick_front_nodes(directs, FRONT_FALLBACK_TIER)
            else:
                fronts, kind = [r for r in directs if not r.get("is_landing") and is_front_capable(r["proxy"])], None
            front_ids = {r["idx"] for r in fronts}
            for row in [r for r in results if r.get("path") == "front"]:
                # 最终前置池必须包含至少一条本轮真正验证过的链路；不能把已淘汰的测试前置偷偷换成未验证的 HTTP/DIRECT。
                verified = {row["front_idx"]}
                if (row.get("speed_result") or {}).get("stable_mbps") is not None:
                    verified.add(row.get("speed_front_idx"))
                if not verified & front_ids:
                    results.remove(row)
                    drop(row, "无已验证且保留的合格前置，无法导出可用落地链路")
            if kind == "fallback" and any(r.get("path") == "front" for r in results):
                for r in fronts:
                    r["is_front_fallback"] = True
                    r["proxy"]["_front_fallback"] = True
        return results, eliminated


def report_row(r):
    return {
        "orig_name": r.get("orig_name"),
        "final_name": r.get("final_name"),
        "cc": r.get("cc"),
        "google_region": r.get("google_region"),
        "geo_decision": r.get("geo_decision"),
        "egress": r.get("egress"),
        "egress_after": r.get("egress_after"),
        "exit_ip": r.get("exit_ip"),
        "path": r.get("path"),
        "is_landing": r.get("is_landing"),
        "front_node": r.get("front_node"),
        "speed_front_node": r.get("speed_front_node"),
        "front_attempts": r.get("front_attempts"),
        "liveness": r.get("liveness"),
        "chain_liveness": r.get("chain_liveness"),
        "delay": r.get("delay"),
        "is_front_fallback": r.get("is_front_fallback", False),
        "alive": r.get("alive", False),
        "service_done": r.get("service_done", False),
        "services_skipped": r.get("services_skipped"),
        "speed_final": r.get("speed_final", False),
        "ip_info_by_ip": r.get("ip_info_by_ip"),
        "ip_reputation": r.get("ip_reputation"),
        "is_key": r.get("is_key", False),
        "is_fast": r.get("is_fast", False),
        "key_score": r.get("key_score"),
        "speed_mbps": r.get("speed_mbps"),
        "speed_kbs": r.get("speed_kbs"),
        "speed_result": r.get("speed_result"),
        "speed_note": r.get("speed_note") or r.get("speed_skipped"),
        "key_reason": r.get("key_reason"),
        "service_seconds": r.get("service_seconds"),
        "ai_supported": r.get("ai_supported"),
        "ai_details": r.get("ai_details"),
        "ai_observations": r.get("ai_observations"),
        "ai_summary": r.get("ai_summary"),
        "youtube_passed": r.get("youtube_passed"),
        "youtube_details": r.get("youtube_details"),
        "shield_passed": r.get("shield_passed"),
        "shield_details": r.get("shield_details"),
        "media_details": r.get("media_details"),
        "ip_info": r.get("ip_info")
    }


def write_report(path, run, profile, results, eliminated, total, start_time):
    args = run.args
    report_data = {
        "timestamp": time.time(),
        "kernel": run.kernel.label,
        "test_dimensions": {"ip": True, **run.dims, "speed": args.speed_test},
        "pipeline": {"alive_workers": args.alive_workers, "service_workers": args.workers,
                     "speed_workers": args.speed_concurrency if args.speed_test else 0,
                     "max_chain_fronts": MAX_CHAIN_FRONTS, "chain_enabled": run.chain_enabled},
        "speed_test_enabled": args.speed_test,
        "speed_profile": {
            "profile": run.profile_name,
            "vantage": profile["vantage"],
            "targets": run.speed_targets,
            "concurrency": args.speed_concurrency,
            **run.speed_opts,
        } if args.speed_test else None,
        "timeline_seconds": {**run.timeline, "total": round(time.time() - start_time, 1)},
        "total_candidates": total,
        "qualified_count": len(results),
        "eliminated_count": len(eliminated),
        "key_count": sum(1 for r in results if r.get("is_key")),
        "landing_speed_fronts": [
            {
                "kind": front["kind"],
                "orig_name": front["name"],
                "final_name": run.rows[front["idx"]].get("final_name"),
                "is_key": run.rows[front["idx"]].get("is_key", False),
                "speed_result": run.rows[front["idx"]].get("speed_result"),
            } for front in run.landing_speed_fronts
        ],
        "results": [report_row(r) for r in results],
        "eliminated": [{**report_row(e), "name": e["proxy"].get("name"), "reason": e.get("eliminated_reason")}
                       for e in eliminated]
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"      已保存详细测试报告: {path}")


def prepare_run(args, check_output=True):
    """解析运行 Profile、校验测速参数与 (需导出时) 母版，出错直接退出；返回 (profile_name, profile)。"""
    profile_name, profile = apply_profile(args)
    option_error = validate_speed_options(args) if args.speed_test else None
    if option_error:
        print(f"错误: {option_error}")
        sys.exit(2)
    if check_output:
        try:
            print(f"[0/4] Clash 母版校验通过: {check_template(args.template)}")
        except (OSError, ValueError) as e:
            print(f"错误: {e}")
            sys.exit(2)
    return profile_name, profile


def dry_run(args, proxies, export):
    """干跑: 不发起真实网络连接，按模拟结论打标命名并交给 export 导出，用于检查解析、命名与母版渲染。"""
    print("[Dry-run] 干跑模式: 跳过真实网络连接，直接执行命名与模版渲染...")
    mock_results = []
    has_key = False
    for idx, p in enumerate(proxies):
        is_lnd = is_landing_role(p)
        is_key_node = bool(args.speed_test and not is_lnd and not has_key)
        if is_key_node:
            has_key = True
        is_fast_node = bool(args.speed_test and not is_key_node and idx < 3)
        mock_results.append({
            "proxy": p,
            "cc": "US" if idx % 2 == 0 else "JP",
            "is_landing": is_lnd,
            "ai_supported": True,
            "youtube_passed": not args.no_browser,
            "shield_passed": not args.no_browser,
            "is_key": is_key_node,
            "is_fast": is_fast_node,
            "key_score": 38.5 if is_key_node else 0.0,
            "speed_mbps": 12.5 if (is_key_node or is_fast_node) else 2.1,
            "media_details": {"nf": True, "dp": True}
        })
    tag_and_rename_nodes(mock_results, resort=args.resort)
    print_summary_table(mock_results, speed_tested=args.speed_test)
    export(mock_results)
    return 0


def run_probe(args, profile_name, profile, kernel, proxies, export, mihomo_bin=None, started=None):
    """
    对 proxies (Clash 视图节点，角色与前置资格按其判定) 执行完整流程；汇总后打标命名、写报告，
    再交给 export(results) 按入口脚本的格式导出配置。返回进程退出码 (全部淘汰时直接以 1 退出)。
    """
    start_time = started or time.time()
    run = ProbeRun(args, profile_name, kernel, proxies, mihomo_bin)
    dims = run.dims
    print(f"[2/4] 测试维度与流程 ({kernel.label} 内核):")
    print(f"      AI解锁: {'✓' if dims['ai'] else '✗'} | 流媒体: {'✓' if dims['media'] else '✗'} | "
          f"免盾: {'✓' if dims['shield'] else '✗'} (浏览器:{'✓' if dims['browser_shield'] else '✗'}) | "
          f"YT免登实播: {'✓' if dims['youtube'] else '✗'}")
    if args.speed_test:
        print(f"      【测速模式】已主动激活完整下载测速 [Profile: {profile_name} | {profile['vantage']}]")
        print(f"      单连接、观测 10~{args.speed_duration:.0f}s 取最后 6 秒稳态：Key/Fast 稳态≥{args.min_speed_mbps}Mbps 且最低≥"
              f"{args.min_floor_mbps}Mbps，稳态<{args.drop_below_mbps}Mbps 淘汰；上限 {args.rate_limit_mbps}Mbps、"
              f"并发 {args.speed_concurrency}")
    else:
        print("      【测速模式】未激活 (默认非主动: 执行 3秒/<16KB 防断流轻量快检)")
    print(f"      测活 → 服务检测线 (并发 {args.workers})" + (f" ∥ 测速线 (并发 {args.speed_concurrency})" if args.speed_test else "")
          + " → 汇总核对；前置链式测活: "
          + (f"开启 (本地，落地节点最多备 {MAX_CHAIN_FRONTS} 个前置)" if run.chain_enabled else "关闭"))

    print("[3/4] 测活、服务检测与测速 (跑机基线出口在后台同时探测)...")
    run.execute()

    print("\n[4/4] 汇总交叉核对，执行淘汰、Key 评选、规范化打标、命名与配置渲染...")
    results, eliminated = run.aggregate()
    for e in eliminated:
        print(f"      [淘汰] {e['proxy'].get('name')}: {e['eliminated_reason']}")
    if results:
        tag_and_rename_nodes(results, resort=args.resort)
        print_summary_table(results, speed_tested=args.speed_test)
    else:
        print("警告: 本轮所有节点均未通过服务测试或已被淘汰，不导出配置。")
    if args.report:
        write_report(args.report, run, profile, results, eliminated, len(proxies), start_time)
    if not results:
        return 1
    export(results)

    if getattr(args, "merge_into", None) and results:
        from .merger import merge_into_target_file
        print(f"\n[*] 正在将 {len(results)} 个合格节点合流并入目标底库: {args.merge_into}...")
        try:
            dest, m_stats = merge_into_target_file(
                target_path=args.merge_into,
                new_nodes_or_file=[r["proxy"] for r in results],
                insert_mode=bool(getattr(args, "insert_mode", False) or args.resort),
                template_path=args.template
            )
            mode_str = "【中间插入模式 (完全重排重编号)】" if (getattr(args, "insert_mode", False) or args.resort) else "【默认合流模式 (优先保留底库原节点及编号，新节点补空号)】"
            print(f"      合流模式: {mode_str}")
            print(f"      底库原节点: {m_stats['base_count']} 个，新增: {m_stats['added_count']} 个，去重跳过: {m_stats['skipped_count']} 个，合并后总节点数: {m_stats['total_count']} 个")
            backup_msg = f" (原文件已备份: {os.path.basename(m_stats['backup_path'])})" if m_stats.get('backup_path') else ""
            print(f"      [✓] 目标底库已成功更新: {dest}{backup_msg}")
        except Exception as err:
            print(f"      [!] 合流并入底库失败: {err}")

    elapsed = round(time.time() - start_time, 1)
    timeline = ", ".join(f"{k}={v}s" for k, v in run.timeline.items())
    print(f"\n全部处理完毕，耗时 {elapsed} 秒 ({timeline})，合格节点: {len(results)}/{len(proxies)} "
          f"(其中 Key: {sum(1 for r in results if r.get('is_key'))} 个)。")
    return 0
