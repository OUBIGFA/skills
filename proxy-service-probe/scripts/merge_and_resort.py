# -*- coding: utf-8 -*-
"""
合并并重排序工具 (merge_and_resort.py):
将 MyFree02.yaml 合并到已测活的 freeorgOP.yaml 中，
规则：
1. 重复节点以 MyFree02.yaml 为准（覆盖/替换 freeorgOP 中的旧节点，保留 MyFree02 的测速结果与 Key/Fast 等最新标签）；
2. 唯独存在于 freeorgOP 中的合格节点予以保留；
3. 全面重排序并重新连续编号（resort=True，层级：✨️ > 🏠 > ❇️ > Key > Fast > 专线/家宽 > _NF > _D+ > ♥️）；
4. 重新渲染导出完整的 Clash/Mihomo YAML 配置文件。
"""
import os
import sys
from copy import deepcopy

# 确保核心模块路径可用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.merger import clash_proxy_sig
from core.parsers import load_proxies
from core.renderer import export_clash_yaml, sort_nodes_by_region_and_landing


def merge_and_resort(base_path: str, add_path: str, output_path: str, template_path: str = None):
    print(f"[*] 读取基础节点池: {base_path}")
    base_proxies = load_proxies(base_path)
    print(f"    基础节点数: {len(base_proxies)}")

    print(f"[*] 读取并入节点池 (权威源): {add_path}")
    add_proxies = load_proxies(add_path)
    print(f"    待并入权威节点数: {len(add_proxies)}")

    # 1. 以 add_proxies (MyFree02) 建立指纹索引
    add_by_sig = {}
    add_sigs_order = []
    for p in add_proxies:
        sig = clash_proxy_sig(p)
        if sig:
            if sig not in add_by_sig:
                add_by_sig[sig] = p
                add_sigs_order.append(sig)
            else:
                # 自身内部去重
                pass
        else:
            # 没有指纹的兜底用名称
            name = p.get("name", "")
            add_by_sig[name] = p
            add_sigs_order.append(name)

    # 2. 检查 base_proxies 与 add_proxies 的重合情况
    duplicates = []
    unique_base = []
    for p in base_proxies:
        sig = clash_proxy_sig(p) or p.get("name", "")
        if sig in add_by_sig:
            duplicates.append((p.get("name"), add_by_sig[sig].get("name")))
        else:
            unique_base.append(p)

    print(f"[*] 重合节点检测: 发现 {len(duplicates)} 个重复节点，已按要求以 {os.path.basename(add_path)} 为准（淘汰基础池旧版本）:")
    for b_name, a_name in duplicates[:10]:
        print(f"    - 底库旧节点: {b_name} -> 替换为权威节点: {a_name}")
    if len(duplicates) > 10:
        print(f"    ... 以及其余 {len(duplicates) - 10} 个重复节点")

    print(f"[*] 保留底库独有存活节点: {len(unique_base)} 个")
    print(f"[*] 保留权威节点 (MyFree02): {len(add_sigs_order)} 个")

    # 3. 合并：MyFree02 全部节点 + base 独有存活节点
    combined = [deepcopy(add_by_sig[s]) for s in add_sigs_order] + [deepcopy(p) for p in unique_base]
    print(f"[*] 合并后总候选节点数: {len(combined)}")

    # 4. 全量重排序并重编号 (resort=True)
    print(f"[*] 执行全量重排序 (先按 ✨️ > 🏠 > ❇️ > Key > Fast > 专线/家宽 顺位定位置，再从 1 递增重新编号)...")
    sorted_proxies = sort_nodes_by_region_and_landing(combined, resort=True)

    # 5. 渲染导出
    print(f"[*] 渲染并导出到目标配置文件: {output_path}...")
    out_file = export_clash_yaml(sorted_proxies, output_path, template_path=template_path)
    print(f"[✓] 导出成功! 最终包含 {len(sorted_proxies)} 个规范化节点。")

    return {
        "base_count": len(base_proxies),
        "add_count": len(add_proxies),
        "duplicate_count": len(duplicates),
        "unique_base_count": len(unique_base),
        "total_count": len(sorted_proxies),
        "output_file": out_file,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="合并并重排序 Clash 代理配置")
    parser.add_argument("--base", required=True, help="基础配置文件路径 (如 freeorgOP_probed.yaml)")
    parser.add_argument("--add", required=True, help="待并入的高优配置文件路径 (如 MyFree02.yaml)")
    parser.add_argument("--output", "-o", required=True, help="输出最终配置文件路径")
    parser.add_argument("--template", help="可选母版路径")
    args = parser.parse_args()

    merge_and_resort(args.base, args.add, args.output, template_path=args.template)
