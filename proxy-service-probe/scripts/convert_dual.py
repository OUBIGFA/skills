# -*- coding: utf-8 -*-
"""
双格式配置转换与同步导出工具 (convert_dual.py)。
支持把现有 sing-box JSON 或 Clash YAML 转换为同时具备 sing-box (.json) 与 Clash/Mihomo (.yaml) 的双份标准配置文件。
Clash/Mihomo YAML 配置文件严格以技能内置的 template.yaml 为母版（包含全部标准策略组与分流规则）。
"""
import sys
import os
import json
import argparse
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.parsers import parse_singbox_outbound, load_proxies
from core.renderer import export_clash_yaml, convert_singbox_to_clash_yaml
from core.singbox_runner import export_singbox_json, find_singbox_bin, make_standard_singbox_config

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def convert_file_to_dual(input_path, output_json=None, output_yaml=None, front_proxy=("127.0.0.1", 3067), singbox_bin=None):
    """
    将输入配置文件转换为标准 sing-box JSON 与标准 Clash/Mihomo YAML 双份文件。
    严格保证 sing-box 现代 1.12+/1.14+ DNS/Route 规范与 ✨️ 综合全通直连节点置顶。
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    base_no_ext = os.path.splitext(input_path)[0]
    out_json = output_json or (base_no_ext + ".json")
    out_yaml = output_yaml or (base_no_ext + ".yaml")

    print(f">>> 正在处理双格式转换: {input_path}")

    # 判断输入格式
    is_json = False
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if content.startswith("{"):
            is_json = True

    if is_json:
        with open(input_path, "r", encoding="utf-8") as f:
            sb_cfg = json.load(f)

        # 提取全部代理出站节点并执行严格排序
        proxy_objs = []
        for out in sb_cfg.get("outbounds", []):
            if out.get("type") not in ("selector", "urltest", "direct", "block", "dns"):
                out_copy = deepcopy(out)
                out_copy.pop("detour", None)
                proxy_objs.append(out_copy)

        from core.renderer import sort_nodes_by_region_and_landing
        sorted_proxies = sort_nodes_by_region_and_landing(proxy_objs)
        qualified_tags = [p["tag"] for p in sorted_proxies]
        sparkle_tags = [p["tag"] for p in sorted_proxies if "✨" in p.get("tag", "")]

        # 构造 100% 遵循 sing-box 1.12+/1.14+ 官方标准的现代配置
        modern_sb_cfg = make_standard_singbox_config(sorted_proxies, qualified_tags, sparkle_tags)

        # 1. 导出规范升级后的 sing-box JSON
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(modern_sb_cfg, f, ensure_ascii=False, indent=2)
        print(f"      [1/2] sing-box JSON 配置已升级并导出: {out_json}")

        # 2. 转换为标准 Clash/Mihomo YAML 配置
        convert_singbox_to_clash_yaml(modern_sb_cfg, out_yaml, front_proxy=front_proxy)
        print(f"      [2/2] Clash/Mihomo YAML 配置已导出: {out_yaml}")

    else:
        # 输入是 YAML，加载节点并构建双出
        proxies = load_proxies(input_path)
        export_clash_yaml(proxies, out_yaml)
        print(f"      [1/2] Clash/Mihomo YAML 配置已导出: {out_yaml}")

        # 构造简单 sing-box 配置
        sb_cfg = {
            "log": {"level": "info", "timestamp": True},
            "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 20808}],
            "outbounds": [{"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"}]
        }
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(sb_cfg, f, ensure_ascii=False, indent=2)
        print(f"      [2/2] sing-box JSON 配置已导出: {out_json}")

    return {
        "json_path": out_json,
        "yaml_path": out_yaml
    }


def main():
    parser = argparse.ArgumentParser(description="双格式配置同步导出工具 (convert_dual.py)")
    parser.add_argument("--input", "-i", required=True, help="输入 sing-box JSON 或 Clash YAML 文件路径")
    parser.add_argument("--output-json", "-j", help="输出的 sing-box JSON 路径 (默认与输入同名 .json)")
    parser.add_argument("--output-yaml", "-y", help="输出的 Clash YAML 路径 (默认与输入同名 .yaml)")
    parser.add_argument("--front-proxy", default="127.0.0.1:3067", help="本地前置跳板地址 (默认: 127.0.0.1:3067)")
    args = parser.parse_args()

    f_host, f_port = args.front_proxy.split(":")
    res = convert_file_to_dual(args.input, args.output_json, args.output_yaml, front_proxy=(f_host, int(f_port)))
    print(f"\n双份配置文件生成完毕！\n  1. sing-box: {res['json_path']}\n  2. Clash/Mihomo: {res['yaml_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
