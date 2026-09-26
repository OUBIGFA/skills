#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sing-box 备用流水线 (probe_singbox.py)：以 sing-box 内核执行与主流水线 probe_services.py (mihomo 内核) 完全相同的
流程与判据 (共用 core.probe_flow)，用于 sing-box 内核兼容性验证，结束时同时导出 sing-box JSON 与 Clash/Mihomo YAML。
  1. 并发测活: 全部节点并发测活；本地直连不通的节点经最多 3 个已判活前置链式重试。
  2. 服务检测线 (并发 --workers，默认 4) ∥ 测速线 (本地串行) 交错并行: 节点一判活即同时进入两条线；
     落地节点某个前置不通时换下一个前置继续服务检测与测速 (最多 3 个)。
  3. 汇总交叉核对后统一淘汰、评选 Key、打标命名，导出双份配置。
Windows 下 sing-box 节点出站统一经绑定物理网卡的 mihomo 直连中继出网，与 mihomo 流水线绑定物理网卡同一路径
(sing-box 1.14 在 Windows 外部 TUN 下绑网卡不生效)。
"""
import argparse
import json
import os
import sys
import time
from contextlib import ExitStack

from core.mihomo_runner import detect_physical_interface, direct_listener, find_mihomo_bin
from core.parsers import parse_singbox_outbound
from core.probe_flow import add_flow_arguments, dry_run, prepare_run, run_probe
from core.renderer import export_clash_yaml
from core.singbox_runner import SingboxKernel, clean_node_for_singbox, export_singbox_json, find_singbox_bin
# 命名与编号规则与 Mihomo 流水线共用 core.tagger，此处导出 format_node_name 保持脚本接口不变
from core.tagger import format_node_name  # noqa: F401

if sys.platform == "win32":
    try:
        # 原地重设编码 (不另包一层，与 probe_services 同进程导入时不会关闭对方的输出流)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

NON_NODE_TYPES = ("urltest", "direct", "block", "dns", "selector")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="sing-box 内核节点服务能力测试与双份配置导出工具 (probe_singbox.py，备用流水线)")
    parser.add_argument("--input", "-i", required=True, help="输入 sing-box JSON 配置文件路径")
    parser.add_argument("--output", "-o", required=True,
                        help="输出 sing-box JSON 配置文件路径 (同时导出 Clash/Mihomo YAML；给 .yaml 路径时 JSON 写到同名 .json)")
    parser.add_argument("--yaml-output", "-y", help="显式指定 Clash/Mihomo YAML 输出路径 (默认与 -o 同名的 .yaml)")
    parser.add_argument("--singbox-bin", help="显式指定 sing-box 可执行文件路径")
    add_flow_arguments(parser)
    return parser.parse_args(argv)


def load_singbox_nodes(path):
    """
    读取 sing-box 配置中的代理出站，转为 Clash 视图节点 (角色、前置资格与 YAML 导出按其判定，原 detour 视为已声明落地)；
    清洗后的 sing-box 出站存于 _singbox_outbound，交给内核测试并用于 JSON 导出。
    返回 (原配置, Clash 视图节点列表, 无法测试的 [(tag, 原因)])。
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        config = json.load(f)
    proxies, skipped = [], []
    for outbound in config.get("outbounds", []):
        if outbound.get("type") in NON_NODE_TYPES:
            continue
        node = clean_node_for_singbox(outbound)
        proxy = parse_singbox_outbound(outbound) if node else None
        if not proxy:
            skipped.append((outbound.get("tag"), "sing-box 流水线不支持的协议或传输层" if node is None
                            else "无法转换为 Clash 节点"))
            continue
        proxy["_orig_name"] = proxy["name"]
        proxy["_singbox_outbound"] = node
        proxies.append(proxy)
    return config, proxies, skipped


def output_paths(args):
    """(sing-box JSON 路径, Clash/Mihomo YAML 路径)：-o 给 .yaml/.yml 时 JSON 写到同名 .json。"""
    base, ext = os.path.splitext(args.output)
    if ext.lower() in (".yaml", ".yml"):
        return base + ".json", args.yaml_output or args.output
    return args.output, args.yaml_output or base + ".yaml"


def export_outputs(args, config, results):
    """同时导出 sing-box JSON 与 Clash/Mihomo YAML (同一批节点、同一母版规则)。"""
    sb_path, yaml_path = output_paths(args)
    exported = export_singbox_json(config, [{**r, "raw_node": r["proxy"]["_singbox_outbound"]} for r in results],
                                   sb_path, singbox_bin=args.singbox_bin, template_path=args.template)
    print(f"      [1/2] sing-box JSON 导出成功: {sb_path} (节点数: {exported['total_nodes']})")
    if exported["check_ok"]:
        print("            sing-box 内核校验: [通过] 100% 格式无误！")
    else:
        print(f"            sing-box 内核校验提示: {exported['check_msg']}")
    export_clash_yaml([r["proxy"] for r in results], yaml_path, template_path=args.template)
    print(f"      [2/2] Clash/Mihomo YAML 导出成功: {yaml_path} (节点数: {len(results)} | 策略组及规则基于母版)")


def start_physical_relay(stack, args, mihomo_bin):
    """
    sing-box 节点出站 (含前置) 统一经绑定物理网卡的 mihomo DIRECT 中继出网，与 mihomo 流水线 interface-name
    绑定物理网卡同一路径。本机开着 TUN (如 Karing) 时不绑网卡的流量会被 TUN 接管，而 sing-box 1.14 在 Windows
    外部 TUN 下 bind_interface 不生效；TUN 客户端又常把出口回显站点分流直连，按出口 IP 比较判断 TUN 并不可靠。
    无法确定物理网卡 (如 Linux 云端 Runner) 时不启用，与 mihomo 不绑网卡一致。返回中继地址或 None。
    """
    iface = args.iface or detect_physical_interface()
    if not iface:
        return None
    try:
        port = stack.enter_context(direct_listener(iface, mihomo_bin))
    except Exception as e:
        raise RuntimeError(f"无法启动物理网卡 {iface} 的直连中继: {e}；拒绝改走可能被 TUN 接管的路径") from e
    print(f"      sing-box 节点出站经物理网卡 {iface} 的直连中继出网 (与 mihomo 流水线绑定物理网卡一致，不经本机 TUN)")
    return ("127.0.0.1", port)


def main(argv=None):
    args = parse_args(argv)
    start_time = time.time()
    print("=" * 80)
    print(">>> sing-box 备用流水线：与主流水线 probe_services.py 相同的 测活 → 服务检测线 ∥ 测速线 → 汇总核对 流程")
    print("=" * 80)
    profile_name, profile = prepare_run(args, check_output=True)

    print("[1/4] 加载并解析 sing-box 输入节点...")
    if not os.path.isfile(args.input):
        print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)
    config, proxies, skipped = load_singbox_nodes(args.input)
    if skipped:
        print(f"      跳过 {len(skipped)} 个本流水线无法测试的节点: "
              + "、".join(f"{tag}({reason})" for tag, reason in skipped))
    if not proxies:
        print("错误: 输入配置中没有可测试的代理节点。")
        sys.exit(1)
    print(f"      成功解析到 {len(proxies)} 个候选节点")

    def export(results):
        export_outputs(args, config, results)

    if args.dry_run:
        return dry_run(args, proxies, export)

    singbox_bin = find_singbox_bin(args.singbox_bin)
    if not singbox_bin:
        print("错误: 未检测到 sing-box 内核。请确认 <skill>/core/sing-box(.exe) 或 PATH 中存在，或通过 --singbox-bin 指定。")
        sys.exit(1)
    mihomo_bin = find_mihomo_bin(args.mihomo)
    print(f"      使用 sing-box 内核: {singbox_bin}")
    if not mihomo_bin:
        print("      [警告] 未检测到 Mihomo 内核：跑机基线出口与物理直连中继不可用 (可用 --mihomo 指定)")
    with ExitStack() as stack:
        try:
            relay = start_physical_relay(stack, args, mihomo_bin)
        except RuntimeError as error:
            print(f"错误: {error}")
            return 2
        return run_probe(args, profile_name, profile, SingboxKernel(singbox_bin, relay), proxies, export,
                         mihomo_bin=mihomo_bin, started=start_time)


if __name__ == "__main__":
    ret = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(ret if isinstance(ret, int) else 0)
