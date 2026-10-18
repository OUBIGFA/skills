# -*- coding: utf-8 -*-
"""
merge_myfree02_to_myfree.py
将 MyFree02.yaml 经过全量测试的合格节点合流并入 MyFree.yaml 底库。
规则：
1. 重复节点（按 clash_proxy_sig 连接指纹）100% 以 MyFree02.yaml 为准（覆盖/替换 MyFree.yaml 中的旧节点）。
2. 中间插入完全重排模式 (resort=True)：
   打破原编号界限，完全按地区 (CATEGORY_ORDER) 聚拢；
   直连在前，落地沉底；
   按能力位阶 (✨️ > 🏠 > ❇️ > Key > Fast > 专线/家宽 > _NF > _D+ > ♥️ > 信誉分) 严格重排；
   从 1 重新依次递增编号。
3. 自动同步更新 proxy-groups 并通过 Clash 母版渲染。
4. 写入前生成 MyFree.yaml.bak 备份。
"""
import argparse
from copy import deepcopy
import os
import sys

# 保证 scripts 路径可导入
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.merger import clash_proxy_sig
from core.parsers import load_proxies
from core.renderer import (
    build_proxy_groups,
    clean_proxy_dict,
    read_template_text,
    render_clash_yaml_text,
    sort_nodes_by_region_and_landing,
)


def merge_myfree02_to_myfree(base_path: str, source_path: str, apply: bool = True):
    base_abs = os.path.abspath(base_path)
    source_abs = os.path.abspath(source_path)

    if not os.path.isfile(base_abs):
        raise FileNotFoundError(f"底库文件不存在: {base_abs}")
    if not os.path.isfile(source_abs):
        raise FileNotFoundError(f"输入源文件不存在: {source_abs}")

    print(f"[*] 底库文件 (Target): {base_abs}")
    print(f"[*] 合流源文件 (Source): {source_abs}")

    # 1. 读取节点
    base_proxies = load_proxies(base_abs)
    source_proxies = load_proxies(source_abs)

    print(f"[*] 底库当前节点数: {len(base_proxies)}")
    print(f"[*] 待并入节点数: {len(source_proxies)}")

    # 2. 构建 source 身份指纹集合
    source_sig_map = {}
    for p in source_proxies:
        s = clash_proxy_sig(p)
        if s:
            source_sig_map[s] = p

    # 3. 统计冲突与去重（冲突时以 source_proxies 为准）
    conflicts = []
    kept_base = []
    for p in base_proxies:
        s = clash_proxy_sig(p)
        if s and s in source_sig_map:
            conflicts.append((p.get("name"), source_sig_map[s].get("name")))
        else:
            kept_base.append(p)

    print(f"[*] 冲突/重复节点数: {len(conflicts)} (全部以 MyFree02.yaml 为准替换)")
    for old_name, new_name in conflicts[:5]:
        print(f"    - 底库旧节点: {old_name}  -->  替换为新节点: {new_name}")
    if len(conflicts) > 5:
        print(f"    ... 等共 {len(conflicts)} 个冲突节点")

    # 4. 合并所有节点（源节点优先保留，加上底库未冲突节点）
    combined = list(source_proxies) + kept_base
    print(f"[*] 合并去重后总节点数: {len(combined)}")

    # 5. 全面重排与从 1 重新编号
    sorted_proxies = sort_nodes_by_region_and_landing(combined, resort=True)
    clean_proxies = [clean_proxy_dict(p) for p in sorted_proxies]
    front_fallback = [p.get("name") for p in sorted_proxies if p.get("_front_fallback")]

    # 6. 生成策略组
    new_groups = build_proxy_groups(clean_proxies, front_fallback=front_fallback)

    # 7. 读取原底库模板与数据
    _, text, base_data = read_template_text(base_abs)
    target_data = deepcopy(base_data)
    target_data["proxies"] = clean_proxies
    target_data["proxy-groups"] = new_groups

    out_yaml = render_clash_yaml_text(target_data, template_path=base_abs)

    if not apply:
        print("\n[!] 预览模式 (未指定 --apply)，未写入文件。")
        return {
            "base_count": len(base_proxies),
            "source_count": len(source_proxies),
            "conflicts": len(conflicts),
            "total_count": len(clean_proxies),
        }

    # 8. 备份与写入
    bak_path = base_abs + ".bak"
    with open(bak_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[✓] 已备份原底库至: {bak_path}")

    with open(base_abs, "w", encoding="utf-8") as f:
        f.write(out_yaml)
    print(f"[✓] 成功写回底库文件: {base_abs} (节点总数: {len(clean_proxies)})")

    # 9. 徽章统计
    badge_counts = {"✨️": 0, "🏠": 0, "❇️": 0, "Key": 0, "Fast": 0, "♥️": 0}
    for p in clean_proxies:
        n = p.get("name", "")
        if "✨️" in n or "✨" in n:
            badge_counts["✨️"] += 1
        if "🏠" in n:
            badge_counts["🏠"] += 1
        if "❇️" in n or "❇" in n:
            badge_counts["❇️"] += 1
        if "Key" in n:
            badge_counts["Key"] += 1
        if "Fast" in n:
            badge_counts["Fast"] += 1
        if "♥️" in n or "♥" in n:
            badge_counts["♥️"] += 1

    print("\n[合流后能力徽章统计]")
    for b, c in badge_counts.items():
        print(f"  {b}: {c}")

    return {
        "base_count": len(base_proxies),
        "source_count": len(source_proxies),
        "conflicts": len(conflicts),
        "total_count": len(clean_proxies),
        "badges": badge_counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge MyFree02.yaml into MyFree.yaml")
    parser.add_argument("--base", default=r"E:\_BIGFAFree\freeorg\MyFree.yaml", help="Path to MyFree.yaml")
    parser.add_argument("--source", default=r"E:\_BIGFAFree\freeorg\MyFree02.yaml", help="Path to MyFree02.yaml")
    parser.add_argument("--apply", action="store_true", help="Apply changes directly")
    args = parser.parse_args()

    merge_myfree02_to_myfree(args.base, args.source, apply=args.apply)
