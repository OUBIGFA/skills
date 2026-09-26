# -*- coding: utf-8 -*-
"""
多订阅与配置合流核心引擎 (scripts/core/merger.py):
用于将经过全量测活测速与服务检测后的节点（或外部订阅）合流并入目标订阅配置 (Clash YAML / sing-box JSON)。

合流准则 (用户需求核心契约):
1. 默认合流模式 (优先保留目标订阅的原节点以及编号):
   - 目标订阅中原有节点及其编号 100% 优先保留不改变；
   - 自动按连接身份指纹执行去重，确保底库无重复节点；
   - 新加入的节点按国家从目标订阅已占用的空号之后或空隙中依次补最小空号 (SlotAllocator)；
   - 合并后根据标准规则重新排序 (地区聚拢，直连在前按编号升序，落地沉底)。
2. 中间插入模式 (--insert / --resort / --reorder-all):
   - 完全打破原有编号界限，所有节点按规则与综合能力全面重排；
   - 直连顺位遵循: ✨️ > ❇️ > Key > Fast > _NF > _D+ > 纯净优于污染 > ♥️ > 信誉分；
   - 落地节点统一置于各地区末尾；
   - 位置全部确定后，从 1 开始严格依次递增重新编号。
"""
from collections import defaultdict
from copy import deepcopy
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from .egress_geo import country_name_zh, flag_emoji
from .parsers import load_proxies
from .renderer import (
    build_proxy_groups,
    clean_proxy_dict,
    dump_yaml,
    load_template,
    read_template_text,
    render_clash_config,
    render_clash_yaml_text,
    renumber_node_tag,
    sort_nodes_by_region_and_landing,
)
from .tagger import SlotAllocator, parse_canonical_node, parse_existing_slot

# 确保脚本根目录在 sys.path 中以便导入 sort_nodes / common
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from sort_nodes import detect_cc
except ImportError:
    def detect_cc(tag: str, node: Any = None) -> Optional[str]:
        m = re.search(r'([\U0001F1E6-\U0001F1FF]{2})', tag)
        if m:
            f = m.group(1)
            return chr(ord(f[0]) - 0x1F1E6 + ord('A')) + chr(ord(f[1]) - 0x1F1E6 + ord('A'))
        return None

try:
    from common import sig as singbox_sig
    from common import remap_refs, strip_node_detours, validate_config, write_config, NODE_TYPES
except ImportError:
    NODE_TYPES = {
        'hysteria', 'hysteria2', 'tuic', 'http', 'shadowsocks', 'shadowsocksr',
        'trojan', 'vmess', 'vless', 'wireguard', 'socks', 'ssh', 'shadowtls',
        'anytls', 'mieru',
    }
    def singbox_sig(o: Dict[str, Any]) -> str:
        ident = {k: v for k, v in o.items() if k not in {'tag', 'detour', 'domain_resolver'}}
        if 'server' in ident:
            ident['server'] = str(ident['server']).lower().rstrip('.')
        return json.dumps(ident, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def clash_proxy_sig(p: Dict[str, Any]) -> str:
    """生成 Clash 代理节点的连接身份指纹（协议、服务器、端口、密钥/密码、网络方式、路径、SNI、Reality Public Key 等）。"""
    if not isinstance(p, dict):
        return ""
    proto = str(p.get("type", "")).strip().lower()
    server = str(p.get("server", "")).strip().lower().rstrip(".")
    port = str(p.get("port", "")).strip()
    secret = str(p.get("uuid") or p.get("password") or "").strip()
    net = str(p.get("network", "")).strip().lower()

    path = ""
    if "ws-opts" in p and isinstance(p["ws-opts"], dict):
        path = str(p["ws-opts"].get("path", "")).strip()
    elif "path" in p:
        path = str(p.get("path", "")).strip()

    sni = str(p.get("servername") or p.get("sni") or "").strip().lower()

    pbk = ""
    if "reality-opts" in p and isinstance(p["reality-opts"], dict):
        pbk = str(p["reality-opts"].get("public-key", "")).strip()

    return f"{proto}:{server}:{port}:{secret}:{net}:{path}:{sni}:{pbk}"


def extract_claimed_slots(proxies: List[Dict[str, Any]]) -> Dict[str, Set[int]]:
    """提取现有节点列表中已按国家占用的编号集合。"""
    claimed: Dict[str, Set[int]] = defaultdict(set)
    for p in proxies:
        name = p.get("name") or p.get("tag") or ""
        canon = parse_canonical_node(name)
        if canon and canon.get("slot"):
            claimed[canon["cc"]].add(canon["slot"])
            continue

        cc = detect_cc(name, p) or "UNK"
        slot = parse_existing_slot(name)
        if slot and slot > 0:
            claimed[cc].add(slot)
    return claimed


def merge_clash_proxies(base_proxies: List[Dict[str, Any]],
                        new_proxies: List[Dict[str, Any]],
                        insert_mode: bool = False,
                        dedup: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    合流新旧 Clash 代理节点。
    - insert_mode=False (默认): 优先保留 base_proxies 的原节点及原有编号，新节点按国家在空缺/后续分配空号；
    - insert_mode=True: 中间插入模式，打破原编号完全按能力与规则重排序并从 1 重新连续编号。
    返回: (合并排序后的 proxies 列表, 统计报告字典)
    """
    seen_sigs = {}
    for p in base_proxies:
        s = clash_proxy_sig(p)
        if s:
            seen_sigs[s] = p.get("name")

    skipped = []
    added = []

    for p in new_proxies:
        s = clash_proxy_sig(p)
        if dedup and s and s in seen_sigs:
            skipped.append((p.get("name"), seen_sigs[s]))
            continue
        if s:
            seen_sigs[s] = p.get("name")
        added.append(deepcopy(p))

    stats = {
        "base_count": len(base_proxies),
        "new_input_count": len(new_proxies),
        "added_count": len(added),
        "skipped_count": len(skipped),
        "insert_mode": insert_mode,
        "skipped": skipped
    }

    if not insert_mode:
        # === 默认模式：优先保留目标订阅的原节点以及编号 ===
        claimed_slots = extract_claimed_slots(base_proxies)
        allocators = {cc: SlotAllocator(slots) for cc, slots in claimed_slots.items()}

        seen_names = set(p.get("name") for p in base_proxies if p.get("name"))

        for p in added:
            orig_name = p.get("name") or p.get("tag") or ""
            canon = parse_canonical_node(orig_name)
            cc = canon["cc"] if canon else (detect_cc(orig_name, p) or p.get("_cc") or "UNK")
            if cc not in allocators:
                allocators[cc] = SlotAllocator()

            # 分配最小空号
            slot = allocators[cc].next_slot()
            new_name = renumber_node_tag(orig_name, slot)
            while new_name in seen_names:
                slot = allocators[cc].next_slot()
                new_name = renumber_node_tag(orig_name, slot)

            seen_names.add(new_name)
            p["name"] = new_name
            if "tag" in p:
                p["tag"] = new_name
            p["slot"] = slot
            p["assigned_slot"] = slot

        # 合并并使用标准规则排位（resort=False 保留已有编号）
        combined = list(base_proxies) + added
        sorted_proxies = sort_nodes_by_region_and_landing(combined, resort=False)
    else:
        # === 中间插入模式：完全按规则与能力重排序和重编号 ===
        combined = list(base_proxies) + added
        sorted_proxies = sort_nodes_by_region_and_landing(combined, resort=True)

    stats["total_count"] = len(sorted_proxies)
    return sorted_proxies, stats


def merge_into_clash_config(base_path: str,
                            additions: List[Dict[str, Any]],
                            output_path: Optional[str] = None,
                            insert_mode: bool = False,
                            dedup: bool = True,
                            template_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    将新增代理节点并入目标 Clash YAML 文件中，并自动刷新策略组。
    若 output_path 为空，则就地更新目标文件（自动备份 .bak）。
    """
    if not os.path.isfile(base_path):
        raise FileNotFoundError(f"目标底库文件不存在: {base_path}")

    # 读取底库配置原文与数据
    _, text, base_data = read_template_text(base_path)
    base_proxies = base_data.get("proxies") or []

    # 执行节点合并与排位编号
    merged_proxies, stats = merge_clash_proxies(base_proxies, additions,
                                                insert_mode=insert_mode, dedup=dedup)

    clean_proxies = [clean_proxy_dict(p) for p in merged_proxies]
    front_fallback = [p.get("name") for p in merged_proxies if p.get("_front_fallback")]
    new_groups = build_proxy_groups(clean_proxies, front_fallback=front_fallback)

    # 注入并渲染
    target_data = deepcopy(base_data)
    target_data["proxies"] = clean_proxies
    target_data["proxy-groups"] = new_groups

    dest_path = os.path.abspath(output_path or base_path)

    # 如果是就地更新，生成备份
    backup_path = None
    if dest_path == os.path.abspath(base_path):
        backup_path = dest_path + ".bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(text)

    # 渲染 YAML
    out_yaml = render_clash_yaml_text(target_data, template_path=base_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(out_yaml)

    stats["backup_path"] = backup_path
    stats["dest_path"] = dest_path
    return dest_path, stats


def merge_into_target_file(target_path: str,
                           new_nodes_or_file: Any,
                           output_path: Optional[str] = None,
                           insert_mode: bool = False,
                           dedup: bool = True,
                           template_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    通用合流入口：根据目标文件类型 (Clash YAML / sing-box JSON) 自动分流并入。
    支持输入节点列表或文件路径。
    """
    target_abs = os.path.abspath(target_path)
    if not os.path.isfile(target_abs):
        raise FileNotFoundError(f"目标文件不存在: {target_path}")

    # 解析新增节点
    if isinstance(new_nodes_or_file, str) and os.path.isfile(new_nodes_or_file):
        additions = load_proxies(new_nodes_or_file)
    elif isinstance(new_nodes_or_file, list):
        additions = new_nodes_or_file
    else:
        raise ValueError("new_nodes_or_file 必须是节点列表或现有文件路径")

    # 检测目标格式
    with open(target_abs, "r", encoding="utf-8-sig") as f:
        head_sample = f.read(512).strip()

    is_json = target_abs.endswith(".json") or head_sample.startswith("{")

    if not is_json:
        # Clash YAML 格式
        return merge_into_clash_config(
            base_path=target_abs,
            additions=additions,
            output_path=output_path,
            insert_mode=insert_mode,
            dedup=dedup,
            template_path=template_path
        )
    else:
        # sing-box JSON 格式
        from merge_configs import load_nodes, merge_config_data
        base_data, base_nodes = load_nodes(target_abs)

        # 把待并入的 additions 转换为 sing-box 节点
        from core.clash_to_singbox import convert_clash_proxies
        converted = convert_clash_proxies(additions)
        sb_additions = converted.get("nodes", [])

        # 调用原有 merge_config_data 或扩展模式
        # 当 insert_mode 时 do_sort=True, do_rename=True
        res = merge_config_data(
            base_data, [sb_additions],
            dedup=dedup,
            dedup_base=True,
            strip_detour=True,
            do_sort=insert_mode,
            do_rename=insert_mode
        )

        dest_path = os.path.abspath(output_path or target_abs)
        changed, backup = write_config(dest_path, base_data, backup=True, style_from=target_abs)
        stats = {
            "base_count": len(base_nodes),
            "new_input_count": len(additions),
            "added_count": len(res.get("added", [])),
            "skipped_count": len(res.get("skipped", [])),
            "total_count": len([o for o in base_data.get("outbounds", []) if o.get("type") in NODE_TYPES]),
            "insert_mode": insert_mode,
            "backup_path": backup,
            "dest_path": dest_path
        }
        return dest_path, stats
