#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proxy-service-probe 命令行入口 (主流水线，mihomo 内核):
对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登、过盾、流媒体、打标命名及配置渲染）。
支持单连接内存流式持续下载测速（按真实 YouTube 播放校准的稳态判定，稳态过低的节点删除）与 Key 优质前置跳板遴选（作为非主动技能，仅在显式指定时触发）。

流程 (与 sing-box 备用流水线 probe_singbox.py 共用 core.probe_flow，参考 subs-check 分段流水线):
  1. 测活: 全部节点并发测活 (多目标多次，全部失败才判死)；本地直连不通的节点经最多 3 个已判活前置链式重试。
  2. 服务检测线 与 测速线 并行: 节点一判活即分别入队；同一节点不同时被两条线占用；
     受并行流量干扰且未达标的测速，留到服务检测全部结束、链路空闲时重测；
     落地节点某个前置不通时换下一个前置继续服务检测与测速 (最多 3 个)。
  3. 汇总交叉核对: 出口、前置重合、测速结论统一核对后才淘汰，再评选 Key、打标编号与渲染。
同一套代码与判据在本地与 GitHub Actions 运行，--profile auto 按环境自动选择资源参数 (云端不做前置链式测活)。
具备端口黑名单避让与活跃物理网卡自动绑定机制，绝不破坏本地已有网络连接（适配 Karing / Sing-box / Mihomo / Xray）。
"""
import argparse
import io
import os
import sys
import time

from core.parsers import load_proxies
from core.mihomo_runner import MihomoKernel, find_mihomo_bin
from core.probe_flow import add_flow_arguments, dry_run, prepare_run, run_probe
from core.renderer import export_clash_yaml

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="代理节点服务能力测试与配置渲染工具 (proxy-service-probe)")
    parser.add_argument("--input", "-i", required=True,
                        help="输入节点源: 本地文件路径(.yaml/.json/.txt)、远程订阅URL或FoFa在线订阅检索(如 fofa:recommended, fofa:vless, fofa:hy2)")
    parser.add_argument("--output", "-o", help="输出渲染后的 Clash/Mihomo YAML 配置文件路径")
    add_flow_arguments(parser)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start_time = time.time()
    profile_name, profile = prepare_run(args, check_output=bool(args.output))

    print("[1/4] 加载并解析输入节点...")
    proxies = load_proxies(args.input)
    if not proxies:
        print("错误: 未从输入源解析到有效代理节点。")
        sys.exit(1)
    print(f"      成功解析到 {len(proxies)} 个候选节点")

    def export(results):
        # 导出 Clash 配置 (自动处理 Key 前置策略组与落地链式绑定)
        if args.output:
            out_file = export_clash_yaml([r["proxy"] for r in results], args.output, template_path=args.template)
            print(f"      已成功导出 Clash 配置文件: {out_file}")

    if args.dry_run:
        return dry_run(args, proxies, export)

    mihomo_bin = find_mihomo_bin(args.mihomo)
    if not mihomo_bin:
        print("错误: 未检测到 Mihomo 内核。请确认系统 PATH 或 _temp/mihomo.exe 存在，或通过 --mihomo 指定。")
        sys.exit(1)
    print(f"      使用 Mihomo 内核: {mihomo_bin}")
    return run_probe(args, profile_name, profile, MihomoKernel(mihomo_bin, args.iface), proxies, export,
                     mihomo_bin=mihomo_bin, started=start_time)


if __name__ == "__main__":
    ret = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(ret if isinstance(ret, int) else 0)
