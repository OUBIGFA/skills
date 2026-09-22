# -*- coding: utf-8 -*-
"""节点规范打标、命名与空号分配模块。"""
import re
from collections import defaultdict
from .egress_geo import CATEGORY_ORDER, country_name_zh, flag_emoji


class SlotAllocator:
    """跳过已认领节点的编号，从 1 开始依次分配最小空号。"""

    def __init__(self, surviving_indices=()):
        self.surviving = set(surviving_indices)
        self.next_new = 1

    def next_slot(self):
        while self.next_new in self.surviving:
            self.next_new += 1
        slot = self.next_new
        self.surviving.add(slot)
        self.next_new += 1
        return slot


def parse_existing_slot(name):
    """从节点名称中提取已有的数字序号。"""
    if not isinstance(name, str):
        return None
    # 匹配类似 _1_ 或 _1 结尾
    m = re.search(r'_(?:[A-Za-z]+_)?(\d+)(?:_|$)', name)
    if not m:
        m = re.search(r'_(\d+)', name)
    return int(m.group(1)) if m else None


def format_node_name(cc, slot, ai_supported=False, comprehensive_sparkle=False,
                     is_fast=False, is_landing=False, is_usai=False,
                     media_details=None, is_chromego=False):
    """
    构造符合规范的节点名称:
    [国旗] [❇️] [✨️] [Fast] [国家]_[编号][落地后缀][流媒体后缀][来源后缀]
    """
    flag = flag_emoji(cc)
    cname = country_name_zh(cc)

    # 1. 前置标识组合 (严格顺序: ❇️ -> ✨️ -> Fast)
    prefix_tags = ""
    if ai_supported:
        prefix_tags += "❇️"
    if comprehensive_sparkle:
        prefix_tags += "✨️"
    if is_fast:
        prefix_tags += "Fast"

    # 2. 基础名称与编号
    country_part = f"{prefix_tags}{cname}_{slot}"

    # 3. 后置后缀组合: 落地 (_USAI / _Lnd) -> 流媒体 (_NF / _D+) -> 来源
    lnd_suffix = ""
    if is_landing:
        lnd_suffix = "_USAI" if is_usai else "_Lnd"

    md = media_details or {}
    media_suffix = ""
    if md.get("nf"):
        media_suffix += "_NF"
    if md.get("dp"):
        media_suffix += "_D+"

    cg_suffix = "_ChromeGo" if is_chromego else ""

    return f"{flag} {country_part}{lnd_suffix}{media_suffix}{cg_suffix}"


def tag_and_rename_nodes(results):
    """
    对一批测试结果进行统一打标、分配空号并排序。
    每个 result 包含:
      proxy, cc, is_landing, ai_supported, youtube_passed, shield_passed,
      is_fast, media_details
    """
    # 1. 提取老节点编号并按国家认领 (同一个国家内每个编号只能被认领一次)
    claimed_slots = defaultdict(set)
    for r in results:
        p = r["proxy"]
        cc = r.get("cc") or "UNK"
        orig_slot = parse_existing_slot(p.get("_orig_name") or p.get("name", ""))
        if orig_slot and orig_slot > 0 and orig_slot not in claimed_slots[cc]:
            claimed_slots[cc].add(orig_slot)
            r["assigned_slot"] = orig_slot
        else:
            r["assigned_slot"] = None

    allocators = {cc: SlotAllocator(slots) for cc, slots in claimed_slots.items()}

    # 2. 为未认领编号的节点分配该国最小空号
    for r in results:
        cc = r.get("cc") or "UNK"
        if cc not in allocators:
            allocators[cc] = SlotAllocator()
        if r["assigned_slot"] is None:
            r["assigned_slot"] = allocators[cc].next_slot()

    # 3. 生成规范化名称并防止重名
    seen_names = set()
    for r in results:
        p = r["proxy"]
        cc = r.get("cc") or "UNK"
        slot = r["assigned_slot"]

        ai_sup = r.get("ai_supported", False)
        yt_pass = r.get("youtube_passed", False)
        cf_pass = r.get("shield_passed", False)
        # 综合全通: AI三大全通 + YouTube免登实播 + 目标网站免盾
        sparkle = bool(ai_sup and yt_pass and cf_pass)

        is_landing = r.get("is_landing", False) or "_Lnd" in p.get("name", "") or "_USAI" in p.get("name", "")
        is_usai = bool(is_landing and cc == "US" and ai_sup)

        is_cg = "_ChromeGo" in p.get("_orig_name", "") or "_ChromeGo" in p.get("name", "")

        new_name = format_node_name(
            cc=cc,
            slot=slot,
            ai_supported=ai_sup,
            comprehensive_sparkle=sparkle,
            is_fast=r.get("is_fast", False),
            is_landing=is_landing,
            is_usai=is_usai,
            media_details=r.get("media_details", {}),
            is_chromego=is_cg
        )

        # 杜绝任何同名碰撞
        if new_name in seen_names:
            extra_slot = allocators[cc].next_slot()
            new_name = format_node_name(
                cc=cc,
                slot=extra_slot,
                ai_supported=ai_sup,
                comprehensive_sparkle=sparkle,
                is_fast=r.get("is_fast", False),
                is_landing=is_landing,
                is_usai=is_usai,
                media_details=r.get("media_details", {}),
                is_chromego=is_cg
            )
            r["assigned_slot"] = extra_slot

        seen_names.add(new_name)
        p["name"] = new_name
        r["final_name"] = new_name
        r["slot"] = r["assigned_slot"]
        r["comprehensive_sparkle"] = sparkle
        r["is_usai"] = is_usai

    # 4. 排序 (按区域优先级 -> 国家码 -> Fast优先 -> AI全通优先 -> 综合徽章 -> 序号)
    def sort_key(row):
        cc = row.get("cc") or "UNK"
        order_info = CATEGORY_ORDER.get(cc, (7, 999, '未知'))
        region_rank = order_info[0]
        country_rank = order_info[1]
        fast_rank = 0 if row.get("is_fast") else 1
        ai_rank = 0 if row.get("ai_supported") else 1
        sparkle_rank = 0 if row.get("comprehensive_sparkle") else 1
        slot = row.get("slot", 9999)
        return (region_rank, country_rank, fast_rank, ai_rank, sparkle_rank, slot)

    results.sort(key=sort_key)
    return results
