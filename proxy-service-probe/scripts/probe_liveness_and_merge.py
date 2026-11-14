# -*- coding: utf-8 -*-
"""
probe_liveness_and_merge.py

专用于执行"只测活"模式并合流重排序的工具：
1. 分别加载 MyFree.yaml 与 freeorgOP.yaml 中的全部节点；
2. 基于连接指纹 (clash_proxy_sig) 统计并去重，重合节点优选能力位阶更高/标签更全的版本；
3. 执行纯粹测活流程 (严格不进行 AI、YouTube、免盾、持续测速等重型服务测试)：
   - 第一轮：全量候选节点直连并发测活 (samples=10，轮换 Google/Cloudflare/Apple 探针，丢包≥50% 淘汰，起始5次失败熔断)；
   - 第二轮：
     * 普通直连失败节点先执行低并发直连复测，快速捞回偶发丢包节点；
     * 声明为落地的节点 (_Lnd / dialer-proxy) 与复测仍不通的节点，经已判活优质直连跳板执行链式测活 (每节点择优 2 个前置)；
4. 筛出全部存活节点 (alive=True)；
5. 执行全量重排序与重编号 (resort=True，位阶：✨️ > 🏠 > ❇️ > Key > Fast > 专线/家宽 > _NF > _D+ > ♥️)；
6. 自动注入/更新 dialer-proxy，渲染 17 大策略组并安全写入目标 freeorgOP.yaml (写入前自动创建 .bak 备份)。
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from copy import deepcopy
import io
import os
import shutil
import sys
import time

# 确保控制台 UTF-8 输出
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.key_evaluator import is_front_capable, is_landing_role
from core.liveness import (
    DEFAULT_LOSS_SAMPLES,
    DEFAULT_MAX_LOSS_RATE,
    check_alive,
    check_alive_via_fronts,
    rank_chain_fronts,
)
from core.merger import clash_proxy_sig
from core.mihomo_runner import MihomoKernel, detect_physical_interface, find_mihomo_bin
from core.parsers import load_proxies
from core.renderer import (
    clean_proxy_dict,
    export_clash_yaml,
    sort_nodes_by_region_and_landing,
)


def node_badge_rank(name: str) -> int:
    """计算节点徽章/能力综合位阶得分，越高表示能力越强/信息越丰富。"""
    score = 0
    if "✨️" in name or "✨" in name:
        score += 1000000
    if "🏠" in name:
        score += 500000
    if "❇️" in name or "❇" in name:
        score += 200000
    if "Key" in name:
        score += 100000
    if "Fast" in name:
        score += 50000
    if "IPLC" in name or "专线" in name:
        score += 20000
    if "_ISP" in name:
        score += 10000
    if "_NF" in name:
        score += 5000
    if "_D+" in name:
        score += 2000
    if "♥️" in name or "❤️" in name:
        score += 1000
    # 纯净度加分：无污染标记优先
    if "_⚠️" not in name:
        score += 100
    return score


def probe_liveness_only(proxies, kernel: MihomoKernel, alive_workers=20, loss_samples=10, max_loss_rate=50.0, batch_size=64):
    """纯测活核心流程，不执行任何重型探测。"""
    total = len(proxies)
    print(f"\n[2/4] 开始节点测活流水线 (共 {total} 个候选节点，采样 {loss_samples} 次探针，丢包≥{max_loss_rate:.0f}%淘汰)...")

    rows = []
    for idx, p in enumerate(proxies):
        is_lnd = is_landing_role(p) or bool("_Lnd" in p.get("name", ""))
        rows.append({
            "idx": idx,
            "proxy": p,
            "orig_name": p.get("name", f"node_{idx}"),
            "is_declared_landing": is_lnd,
            "alive": False,
            "path": "direct",
            "is_landing": is_lnd,
            "delay": None,
            "loss_rate": 100.0,
            "eliminated_reason": None,
        })

    liveness_opts = {
        "samples": loss_samples,
        "max_loss_rate": max_loss_rate,
    }

    with ExitStack() as stack:
        # 1. 启动直连端口监听
        entries = [(r["idx"], r["proxy"], None) for r in rows]
        print(f"      正在为 {len(entries)} 个节点启动本地直连监听 (分片大小: {batch_size})...")
        ports, failed = kernel.start(stack, entries, shard_size=batch_size)

        for idx, reason in failed.items():
            rows[idx]["eliminated_reason"] = f"内核启动失败: {reason}"
            print(f"      [测活✗] {rows[idx]['orig_name']}: {rows[idx]['eliminated_reason']}")

        testable = [r for r in rows if r["idx"] in ports]
        print(f"      第 1 轮：直连并发测活 ({len(testable)} 节点，并发 {alive_workers})...")

        dead = []
        alive_direct_count = 0

        with ThreadPoolExecutor(max_workers=max(1, alive_workers)) as pool:
            futures = {
                pool.submit(check_alive, f"http://127.0.0.1:{ports[r['idx']]}", **liveness_opts): r
                for r in testable
            }
            for fut in as_completed(futures):
                r = futures[fut]
                try:
                    res = fut.result()
                except Exception as ex:
                    res = {"alive": False, "latency_ms": None, "loss_rate": 100.0, "reason": str(ex)}

                r["liveness"] = res
                if res.get("alive"):
                    r["alive"] = True
                    r["delay"] = res.get("latency_ms")
                    r["loss_rate"] = res.get("loss_rate", 0.0)
                    r["path"] = "direct"
                    r["is_landing"] = r["is_declared_landing"]
                    alive_direct_count += 1
                    loss_text = f" (丢包: {r['loss_rate']:.0f}%)" if r["loss_rate"] > 0 else ""
                    print(f"      [测活✓] {r['orig_name']}: 直连 {r['delay']:.0f}ms{loss_text}")
                else:
                    dead.append(r)

        print(f"      第 1 轮完成: 直连通达 {alive_direct_count} 个，未达标/待复测 {len(dead)} 个")

        # 2. 第二轮：直连复测 + 链式前置测活
        if dead:
            # 2.1 对非落地声明的直连失败节点先执行一轮低并发复测
            direct_recheck_candidates = [r for r in dead if not r["is_declared_landing"] and r["idx"] in ports]
            if direct_recheck_candidates:
                print(f"      第 2 轮(a)：低并发直连复测 ({len(direct_recheck_candidates)} 个节点)...")
                with ThreadPoolExecutor(max_workers=8) as recheck_pool:
                    rfuts = {
                        recheck_pool.submit(check_alive, f"http://127.0.0.1:{ports[r['idx']]}", **liveness_opts): r
                        for r in direct_recheck_candidates
                    }
                    for fut in as_completed(rfuts):
                        r = rfuts[fut]
                        try:
                            d_res = fut.result()
                        except Exception as ex:
                            d_res = {"alive": False, "loss_rate": 100.0, "reason": str(ex)}
                        if d_res.get("alive"):
                            r["alive"] = True
                            r["delay"] = d_res.get("latency_ms")
                            r["loss_rate"] = d_res.get("loss_rate", 0.0)
                            r["path"] = "direct"
                            r["is_landing"] = False
                            loss_text = f" (丢包: {r['loss_rate']:.0f}%)" if r["loss_rate"] > 0 else ""
                            print(f"      [测活✓] {r['orig_name']}: 直连复测通过 {r['delay']:.0f}ms{loss_text}")

            # 2.2 依然未通的节点 + 所有声明为落地的节点，进行前置链式测活
            need_chain = [r for r in dead if not r["alive"]]
            alive_direct_fronts = [
                r for r in rows
                if r.get("alive") and r.get("path") == "direct" and not r.get("is_landing") and is_front_capable(r["proxy"])
            ]

            if need_chain and alive_direct_fronts:
                print(f"      第 2 轮(b)：经已判活前置进行链式测活 ({len(need_chain)} 个节点，可用前置跳板: {len(alive_direct_fronts)} 个)...")
                plans = {}
                chain_pairs = []
                for r in need_chain:
                    fronts = rank_chain_fronts(alive_direct_fronts, r["proxy"], limit=2)
                    plans[r["idx"]] = fronts
                    for f in fronts:
                        chain_pairs.append(((r["idx"], f["idx"]), r["proxy"], f["proxy"]))

                chain_ports, chain_failed = {}, {}
                if chain_pairs:
                    print(f"      正在启动链式代理链路 (共 {len(chain_pairs)} 条链路，分片大小: {batch_size})...")
                    chain_ports, chain_failed = kernel.start(stack, chain_pairs, shard_size=batch_size)

                def test_chain(r):
                    fronts = plans.get(r["idx"], [])
                    port_by_front = {
                        f["idx"]: chain_ports[(r["idx"], f["idx"])]
                        for f in fronts
                        if (r["idx"], f["idx"]) in chain_ports
                    }
                    if not port_by_front:
                        return None, {}
                    return check_alive_via_fronts(port_by_front, **liveness_opts)

                with ThreadPoolExecutor(max_workers=max(1, alive_workers)) as chain_pool:
                    chain_futs = {
                        chain_pool.submit(test_chain, r): r
                        for r in need_chain
                        if plans.get(r["idx"])
                    }
                    for fut in as_completed(chain_futs):
                        r = chain_futs[fut]
                        idx = r["idx"]
                        try:
                            c_best, c_details = fut.result()
                        except Exception:
                            c_best, c_details = None, {}

                        if c_best is not None:
                            best_live = c_details[c_best]
                            front_name = next((f["orig_name"] for f in plans.get(idx, []) if f["idx"] == c_best), str(c_best))
                            r["alive"] = True
                            r["delay"] = best_live.get("latency_ms")
                            r["loss_rate"] = best_live.get("loss_rate", 0.0)
                            r["path"] = "front"
                            r["is_landing"] = True
                            r["front_node"] = front_name
                            loss_text = f" (丢包: {r['loss_rate']:.0f}%)" if r["loss_rate"] > 0 else ""
                            print(f"      [测活✓] {r['orig_name']}: 经前置 {front_name} 测通 {r['delay']:.0f}ms{loss_text} (落地)")
                        else:
                            reason = (r.get("liveness") or {}).get("reason") or "直连与前置链路均未通达"
                            r["alive"] = False
                            r["eliminated_reason"] = reason
                            print(f"      [测活✗] {r['orig_name']}: {reason}")
            else:
                for r in need_chain:
                    reason = (r.get("liveness") or {}).get("reason") or "两轮直连均未达标"
                    r["alive"] = False
                    r["eliminated_reason"] = reason
                    print(f"      [测活✗] {r['orig_name']}: {reason}")

    alive_rows = [r for r in rows if r["alive"]]
    dead_rows = [r for r in rows if not r["alive"]]

    for r in alive_rows:
        p = r["proxy"]
        p["is_landing"] = r["is_landing"]
        p["_is_landing"] = r["is_landing"]
        p["path"] = r["path"]

    print(f"\n[测活完成] 总节点: {total} | 存活: {len(alive_rows)} | 淘汰: {len(dead_rows)}")
    return alive_rows, dead_rows


def merge_and_resort_liveness(myfree_path: str, freeorg_path: str, output_path: str):
    start_time = time.time()
    print("=" * 100)
    print(f"[*] 代理节点纯测活与合流重排序流水线")
    print(f"[*] 输入 1 (MyFree):    {myfree_path}")
    print(f"[*] 输入 2 (freeorgOP): {freeorg_path}")
    print(f"[*] 输出目标:           {output_path}")
    print("=" * 100)

    # 1. 加载节点
    print("\n[1/4] 加载配置文件...")
    myfree_nodes = load_proxies(myfree_path)
    freeorg_nodes = load_proxies(freeorg_path)
    print(f"      MyFree 节点数:    {len(myfree_nodes)}")
    print(f"      freeorgOP 节点数: {len(freeorg_nodes)}")

    # 2. 建立指纹并去重聚合
    sig_to_candidates = defaultdict(list)
    for p in myfree_nodes:
        s = clash_proxy_sig(p)
        if s:
            sig_to_candidates[s].append(("MyFree", p))
        else:
            sig_to_candidates[p.get("name", "")].append(("MyFree", p))

    for p in freeorg_nodes:
        s = clash_proxy_sig(p)
        if s:
            sig_to_candidates[s].append(("freeorgOP", p))
        else:
            sig_to_candidates[p.get("name", "")].append(("freeorgOP", p))

    unique_candidates = []
    conflict_count = 0
    for sig, items in sig_to_candidates.items():
        if len(items) == 1:
            src, p = items[0]
            unique_candidates.append(deepcopy(p))
        else:
            conflict_count += 1
            # 存在重合，按徽章/能力位阶打分择优
            scored = []
            for src, p in items:
                sc = node_badge_rank(p.get("name", ""))
                # 若得分完全一致，优先保留 freeorgOP (底库基准)
                tie_breaker = 1 if src == "freeorgOP" else 0
                scored.append((sc, tie_breaker, p, src))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            chosen_p = deepcopy(scored[0][2])
            unique_candidates.append(chosen_p)

    print(f"      两库重合节点: {conflict_count} 个 (已按能力顺位与底库基准择优选取)")
    print(f"      去重后待测活总候选节点数: {len(unique_candidates)}")

    # 3. 执行纯测活
    bin_path = find_mihomo_bin()
    if not bin_path:
        raise RuntimeError("未找到 Mihomo 内核，请确认 core/mihomo.exe 存在。")
    iface = detect_physical_interface()
    print(f"      使用 Mihomo 内核: {bin_path}")
    print(f"      绑定物理网卡 (避让 TUN): {iface or '自动回退'}")

    kernel = MihomoKernel(bin_path, iface)
    alive_rows, dead_rows = probe_liveness_only(unique_candidates, kernel)

    if not alive_rows:
        print("[!] 严重警告: 无任何存活节点，不修改目标文件。")
        return False

    surviving_proxies = [r["proxy"] for r in alive_rows]

    # 4. 全量重排序与从 1 递增重新编号
    print(f"\n[3/4] 执行全量规范化重排序与从 1 重新编号 (resort=True)...")
    print(f"      遵循顺位：✨️ > 🏠 > ❇️ > Key > Fast > 专线/家宽 > _NF > _D+ > ♥️，落地沉底")
    sorted_proxies = sort_nodes_by_region_and_landing(surviving_proxies, resort=True)
    clean_proxies = [clean_proxy_dict(p) for p in sorted_proxies]

    # 5. 渲染导出并安全备份
    print(f"\n[4/4] 渲染并导出至目标配置: {output_path}...")
    output_abs = os.path.abspath(output_path)
    if os.path.isfile(output_abs):
        bak_file = output_abs + ".bak"
        shutil.copy2(output_abs, bak_file)
        print(f"      已安全备份原目标配置: {bak_file}")

    # 以目标配置 freeorgOP.yaml 为母版模版渲染 (保留其原有注释与头部配置)
    template_to_use = freeorg_path if os.path.isfile(freeorg_path) else None
    out_file = export_clash_yaml(clean_proxies, output_abs, template_path=template_to_use)

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 100)
    print(f"[✓] 任务圆满完成! 耗时: {elapsed} 秒")
    print(f"[✓] 初始节点池: MyFree ({len(myfree_nodes)}) + freeorgOP ({len(freeorg_nodes)}) = 去重前 {len(myfree_nodes)+len(freeorg_nodes)} 个")
    print(f"[✓] 独立连接指纹: {len(unique_candidates)} 个 (淘汰失效/死节点: {len(dead_rows)} 个)")
    print(f"[✓] 最终合格存活并规范重排节点数: {len(clean_proxies)} 个")
    print(f"[✓] 配置文件已更新: {out_file}")
    print("=" * 100)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MyFree 与 freeorgOP 节点纯测活、合流与重排序")
    parser.add_argument("--myfree", default=r"E:\_BIGFAFree\freeorg\MyFree.yaml", help="MyFree.yaml 路径")
    parser.add_argument("--freeorg", default=r"E:\_BIGFAFree\freeorg\freeorgOP.yaml", help="freeorgOP.yaml 路径")
    parser.add_argument("--output", "-o", default=r"E:\_BIGFAFree\freeorg\freeorgOP.yaml", help="输出路径")
    args = parser.parse_args()

    success = merge_and_resort_liveness(args.myfree, args.freeorg, args.output)
    sys.exit(0 if success else 1)
