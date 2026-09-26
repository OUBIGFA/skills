# -*- coding: utf-8 -*-
"""节点规范打标、命名与空号分配模块。"""
import re
from collections import defaultdict
from .egress_geo import country_name_zh, flag_emoji, valid_reputation_score
from .renderer import sort_nodes_by_region_and_landing


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
    """从节点名称中提取已有的数字序号，过滤 Key/Fast/AY 等干扰词。"""
    if not isinstance(name, str):
        return None
    # 去除国旗与前缀标签
    cleaned = re.sub(r'^(?:(?:[\U0001F1E6-\U0001F1FF]{2}|🏳️|\S+)\s*)', '', name.strip())
    cleaned = re.sub(r'^(?:[❇✨♥️♥]️?|\s+|Key|Fast)+', '', cleaned)
    m = re.search(r'_(?:[A-Za-z]+_)?(\d+)(?:_|$)', cleaned)
    if not m:
        m = re.search(r'_(\d+)', cleaned)
    return int(m.group(1)) if m else None


_FLAG_RE = re.compile(r'^([\U0001F1E6-\U0001F1FF]{2}|🏳️?)\s*')
_BADGES_RE = re.compile(r'^(?:[✨❇♥]️?|Key|Fast)*')
_CITY_SLOT_RE = re.compile(r'^(?:_([^_\d\s]+))?_(\d+)(?!\d)')


def parse_canonical_node(name):
    """
    解析本技能规范命名的原节点: [国旗] [徽章] 国家[_城市]_编号...
    国旗与国家名必须一致；返回 {cc, slot, city}，非规范名称（新节点）返回 None。
    """
    if not isinstance(name, str):
        return None
    text = name.strip()
    m = _FLAG_RE.match(text)
    if not m:
        return None
    flag = m.group(1)
    cc = 'UNK' if flag.startswith('🏳') else ''.join(chr(ord(c) - 127397) for c in flag)
    rest = text[m.end():]
    rest = rest[_BADGES_RE.match(rest).end():]
    cname = country_name_zh(cc)
    if not rest.startswith(cname):
        return None
    s = _CITY_SLOT_RE.match(rest[len(cname):])
    if not s or int(s.group(2)) <= 0:
        return None
    return {"cc": cc, "slot": int(s.group(2)), "city": s.group(1) or ""}


def format_node_name(cc, slot, ai_supported=False, comprehensive_sparkle=False,
                     is_high_quality=False, is_key=False, is_fast=False,
                     is_landing=False, is_usai=False, media_details=None,
                     is_chromego=False, poison_tag=None, city=""):
    """
    构造符合规范的节点名称:
    [国旗] [✨️] [❇️] [♥️] [Key/Fast] [国家][_城市]_[编号][落地后缀][流媒体后缀][来源后缀]
    """
    if poison_tag:
        ai_supported = comprehensive_sparkle = is_usai = is_high_quality = False
    flag = flag_emoji(cc)
    cname = country_name_zh(cc)

    # 1. 前置标识组合 (严格顺序: ✨️ -> ❇️ -> ♥️ -> Key/Fast)
    prefix_tags = ""
    if comprehensive_sparkle:
        prefix_tags += "✨️"
    if ai_supported:
        prefix_tags += "❇️"
    if is_high_quality:
        prefix_tags += "♥️"
    if is_key:
        prefix_tags += "Key"
    elif is_fast:
        prefix_tags += "Fast"

    # 2. 基础名称与编号
    country_part = f"{prefix_tags}{cname}{f'_{city}' if city else ''}_{slot}"

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

    return f"{flag} {country_part}{lnd_suffix}{media_suffix}{cg_suffix}{poison_tag or ''}"


def _orig_name(r):
    p = r.get("proxy") or {}
    return r.get("orig_name") or p.get("_orig_name") or p.get("name") or ""


def tag_and_rename_nodes(results, resort=False):
    """
    对一批测试结果进行统一打标、分配空号并排序。
    每个 result 包含:
      proxy (或 sing-box 的 raw_node + orig_name), cc, is_landing, ai_supported,
      youtube_passed, shield_passed, is_key, is_fast, media_details
    编号规则:
      - 默认: 规范命名且属地未变的原节点保留原编号；新节点及属地变化的节点按国家从 1 补空号；
      - resort=True (用户主动要求重排序): 位置按标签与信誉全部确定后，从 1 重新编号。
    """
    # 1. 原节点按国家认领原编号 (属地变化即视为新节点；同一国家内每个编号只能被认领一次)
    claimed_slots = defaultdict(set)
    for r in results:
        cc = r.get("cc") or "UNK"
        canon = parse_canonical_node(_orig_name(r))
        r["assigned_slot"] = None
        if canon and canon["cc"] == cc and canon["slot"] not in claimed_slots[cc]:
            claimed_slots[cc].add(canon["slot"])
            r["assigned_slot"] = canon["slot"]
            r.setdefault("city", canon["city"])

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
        p = r.get("proxy") if isinstance(r.get("proxy"), dict) else {}
        pname = p.get("name", "")
        orig = _orig_name(r)
        cc = r.get("cc") or "UNK"
        slot = r["assigned_slot"]
        city = r.get("city") or ""

        poison_tag = (r.get("geo_decision") or {}).get("poison_tag")
        ai_sup = bool(r.get("ai_supported", False) and not poison_tag)
        r["ai_supported"] = ai_sup
        orig_has_sparkle = bool("✨️" in orig or "✨" in orig)
        orig_has_hq = bool("♥️" in orig or "♥" in orig)
        orig_has_key = bool(re.search(r'(?i)\bkey(?![a-z])', orig))
        orig_has_fast = bool(re.search(r'(?i)\bfast(?![a-z])', orig))
        orig_has_nf = bool("_NF" in orig)
        orig_has_dp = bool("_D+" in orig)

        # Groq 解锁状态: 独立作为 ✨️ 综合全通的硬性门槛
        if "ai_details" in r and r["ai_details"]:
            groq_pass = bool(r["ai_details"].get("groq", False))
        else:
            groq_pass = bool(ai_sup)

        yt_pass = r.get("youtube_passed", False)
        cf_pass = r.get("shield_passed", False)
        # 综合全通 ✨️: 必须同时满足 AI五大全通 + Groq解锁 + YouTube免登实播 + 四站免盾 (只有解锁Groq才能给✨️)
        if r.get("youtube_details") or r.get("shield_details"):
            sparkle = bool(ai_sup and groq_pass and yt_pass and cf_pass)
        elif "youtube_passed" in r and "shield_passed" in r and (yt_pass or cf_pass):
            sparkle = bool(ai_sup and groq_pass and yt_pass and cf_pass)
        else:
            sparkle = bool(ai_sup and groq_pass and orig_has_sparkle and not poison_tag)

        # 测速相关：实测以实测为准，未测速继承原 Key / Fast
        if r.get("speed_result") is not None or r.get("is_key") is True or r.get("is_fast") is True:
            is_key = bool(r.get("is_key", False) or p.get("_is_key", False))
            is_fast = bool((r.get("is_fast", False) or p.get("_is_fast", False)) and not is_key)
        else:
            is_key = bool(orig_has_key)
            is_fast = bool(orig_has_fast and not is_key)

        # 流水线已实测判定直连/落地时以实测为准，不让原名里的 _Lnd/_USAI 覆盖本轮结果
        if isinstance(r.get("is_landing"), bool):
            is_landing = r["is_landing"]
        else:
            is_landing = "_Lnd" in pname or "_USAI" in pname
        is_usai = bool(is_landing and cc == "US" and ai_sup)

        is_cg = "_ChromeGo" in orig or "_ChromeGo" in pname

        rep = r.get("ip_reputation") or p.get("_ip_reputation") or {}
        sc = valid_reputation_score(rep.get("score"))
        if r.get("is_high_quality") is True:
            is_hq = bool(not poison_tag)
        elif rep.get("status") == "observed" and sc is not None:
            is_hq = bool(sc >= 80 and not poison_tag)
        else:
            is_hq = bool(orig_has_hq and not poison_tag)

        # 流媒体：实测以实测为准，未测继承原 _NF / _D+
        if r.get("media_details"):
            media_details = r.get("media_details")
        else:
            media_details = {}
            if orig_has_nf:
                media_details["nf"] = True
            if orig_has_dp:
                media_details["dp"] = True

        new_name = format_node_name(
            cc=cc,
            slot=slot,
            ai_supported=ai_sup,
            comprehensive_sparkle=sparkle,
            is_high_quality=is_hq,
            is_key=is_key,
            is_fast=is_fast,
            is_landing=is_landing,
            is_usai=is_usai,
            media_details=media_details,
            is_chromego=is_cg,
            poison_tag=poison_tag,
            city=city
        )

        # 杜绝任何同名碰撞
        if new_name in seen_names:
            extra_slot = allocators[cc].next_slot()
            new_name = format_node_name(
                cc=cc,
                slot=extra_slot,
                ai_supported=ai_sup,
                comprehensive_sparkle=sparkle,
                is_high_quality=is_hq,
                is_key=is_key,
                is_fast=is_fast,
                is_landing=is_landing,
                is_usai=is_usai,
                media_details=media_details,
                is_chromego=is_cg,
                poison_tag=poison_tag,
                city=city
            )
            r["assigned_slot"] = extra_slot

        seen_names.add(new_name)
        if "proxy" in r:
            p["name"] = new_name
            p["_is_key"] = is_key
            p["_is_fast"] = is_fast
            p["_key_score"] = r.get("key_score", 0.0)
            p["_ip_reputation"] = r.get("ip_reputation")

        r["final_name"] = new_name
        r["slot"] = r["assigned_slot"]
        r["is_key"] = is_key
        r["is_fast"] = is_fast
        r["comprehensive_sparkle"] = sparkle
        r["is_high_quality"] = is_hq
        r["is_usai"] = is_usai

    # 4. 与导出共用同一排序规则：默认按编号排位；resort 时先定位置再从 1 重新编号
    results[:] = sort_nodes_by_region_and_landing(results, resort=resort)
    if resort:
        for row in results:
            canon = parse_canonical_node(row["final_name"])
            if canon:
                row["slot"] = row["assigned_slot"] = canon["slot"]
    return results
