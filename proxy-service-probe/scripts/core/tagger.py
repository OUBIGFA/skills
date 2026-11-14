# -*- coding: utf-8 -*-
"""节点规范打标、命名与空号分配模块。"""
import re
from collections import defaultdict
from .egress_geo import country_name_zh, flag_emoji, valid_reputation_score, is_ip_region_inconsistent, is_google_recognized_us
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
    # 去除国旗与前缀标签 (包含美国节点专属的 Free 前缀)
    cleaned = re.sub(r'^(?:(?:[\U0001F1E6-\U0001F1FF]{2}|🏳️|\S+)\s*)', '', name.strip())
    cleaned = re.sub(r'^(?:[❇✨♥️♥🏠]️?|\s+|Key|Fast|Free)+', '', cleaned)
    m = re.search(r'_(?:[A-Za-z]+_)?(\d+)(?:_|$)', cleaned)
    if not m:
        m = re.search(r'_(\d+)', cleaned)
    return int(m.group(1)) if m else None


_FLAG_RE = re.compile(r'^([\U0001F1E6-\U0001F1FF]{2}|🏳️?)\s*')
_BADGES_RE = re.compile(r'^(?:[✨❇♥🏠]️?|Key|Fast|Free)*')
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
                     is_landing=False, is_usai=False, is_goai=False, is_gui=False, media_details=None,
                     is_chromego=False, poison_tag=None, city="", is_iplc=False,
                     is_residential=False, has_res_suffix=False):
    """
    构造符合规范的节点名称:
    [国旗] [✨️] [🏠 / ♥️] [❇️] [Key/Fast] [国家][_城市]_[编号][IPLC/ISP后缀][落地后缀][流媒体后缀][来源后缀][污染标记]
    """
    effective_goai = bool(is_goai or is_gui)
    raw_poison = str(poison_tag or "")
    has_warp = "[⚡WARP]" in raw_poison
    geo_poison = raw_poison.replace("[⚡WARP]", "")
    if geo_poison:
        ai_supported = comprehensive_sparkle = is_usai = effective_goai = is_high_quality = is_residential = has_res_suffix = False
    if has_warp:
        comprehensive_sparkle = is_high_quality = is_residential = has_res_suffix = False
    flag = flag_emoji(cc)
    cname = country_name_zh(cc)

    # 1. 前置标识组合 (严格顺序: ✨️ -> 🏠 / ♥️ -> ❇️ -> Key/Fast)
    prefix_tags = ""
    if comprehensive_sparkle:
        prefix_tags += "✨️"
    # 规则升级：前置徽章顺序严格遵循: ✨️ > 🏠 > ❇️ > Key > Fast
    # 符合 ♥️ 标准的家宽节点获得 🏠（🏠 与 ♥️ 互斥，家宽获得 🏠 即代表符合高纯净度，避免两者并存，更简洁）
    if is_residential:
        prefix_tags += "🏠"
    elif is_high_quality:
        prefix_tags += "♥️"
    if ai_supported:
        prefix_tags += "❇️"
    if is_key:
        # 准则升级：只有带有 USAI 后缀的美国节点才改成 Free 前缀，其他符合 key 标准的美国节点继续用 Key 前缀
        prefix_tags += "Free" if (cc == "US" and is_usai) else "Key"
    elif is_fast:
        prefix_tags += "Fast"

    # 2. 基础名称与编号
    country_part = f"{prefix_tags}{cname}{f'_{city}' if city else ''}_{slot}"

    # 3. 后置后缀组合: 线路后缀 (IPLC / ISP) -> 落地 (_USAI / _GOAI / _Lnd) -> 流媒体 (_NF / _D+) -> 来源 (_ChromeGo) -> 污染标记
    # 规则：又是家宽又是专线的则只保留专线 (_IPLC)；低分家宽加上英文缩写 _ISP 后缀（不出现中文）
    if is_iplc:
        line_suffix = "_IPLC"
    elif has_res_suffix:
        line_suffix = "_ISP"
    else:
        line_suffix = ""

    lnd_suffix = ""
    if is_landing:
        lnd_suffix = "_USAI" if is_usai else ("_GOAI" if effective_goai else "_Lnd")
    elif is_usai:
        lnd_suffix = "_USAI"
    elif effective_goai:
        lnd_suffix = "_GOAI"

    md = media_details or {}
    media_suffix = ""
    if md.get("nf"):
        media_suffix += "_NF"
    if md.get("dp"):
        media_suffix += "_D+"

    cg_suffix = "_ChromeGo" if is_chromego else ""

    return f"{flag} {country_part}{line_suffix}{lnd_suffix}{media_suffix}{cg_suffix}{poison_tag or ''}"


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

    # 2. 为未认领编号的节点分配该国最小空号 (统一认定节点优先于地区不一致节点分配较小空号)
    unassigned = [r for r in results if r["assigned_slot"] is None]
    unassigned.sort(key=lambda r: (1 if is_ip_region_inconsistent(r) else 0, r.get("_orig_idx", 9999)))
    for r in unassigned:
        cc = r.get("cc") or "UNK"
        if cc not in allocators:
            allocators[cc] = SlotAllocator()
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
        orig_has_ai = bool("❇️" in orig or "❇" in orig or "❇️" in pname or "❇" in pname)
        if r.get("ai_supported") is not None:
            ai_sup = bool(r.get("ai_supported", False) and not poison_tag)
        elif p.get("_ai_supported") is not None:
            ai_sup = bool(p["_ai_supported"] and not poison_tag)
        else:
            ai_sup = bool(orig_has_ai and not poison_tag)
        r["ai_supported"] = ai_sup
        orig_has_sparkle = bool("✨️" in orig or "✨" in orig or "✨️" in pname or "✨" in pname)
        orig_has_hq = bool("♥️" in orig or "♥" in orig)
        is_us_node = (cc == "US" or bool(re.search(r'🇺🇸|美国|USA|\bUS\b', orig)) or bool(re.search(r'🇺🇸|美国|USA|\bUS\b', pname)))
        orig_has_key = bool(re.search(r'(?i)\bkey(?![a-z])', orig) or (is_us_node and re.search(r'(?i)\bfree(?![a-z])', orig)))
        orig_has_fast = bool(re.search(r'(?i)\bfast(?![a-z])', orig))
        orig_has_nf = bool("_NF" in orig)
        orig_has_dp = bool("_D+" in orig)

        # Groq 解锁状态: 独立作为 ✨️ 综合全通的硬性门槛
        if "ai_details" in r and r["ai_details"]:
            groq_pass = bool(r["ai_details"].get("groq", False))
        elif p.get("_groq_passed") is not None:
            groq_pass = bool(p["_groq_passed"])
        else:
            groq_pass = bool(ai_sup)

        if "youtube_passed" in r and r["youtube_passed"] is not None:
            yt_pass = bool(r["youtube_passed"])
        elif p.get("_youtube_passed") is not None:
            yt_pass = bool(p["_youtube_passed"])
        else:
            yt_pass = None

        shield_det = r.get("shield_details") or p.get("_shield_details") or {}
        waf_eval = shield_det.get("waf_evaluation") or {}
        waf_score = shield_det.get("waf_shield_score", waf_eval.get("waf_shield_score"))

        # WARP 套壳识别并附加 [⚡WARP] 污染标记（保留 AI 标记，仅剥夺 ✨️ / 🏠 / ♥️ / _ISP）
        is_warp = bool(
            r.get("is_warp")
            or p.get("_is_warp")
            or shield_det.get("is_warp_wrapped")
            or waf_eval.get("is_warp_wrapped")
            or "[⚡WARP]" in orig
            or "[⚡WARP]" in pname
        )
        geo_poison_tag = poison_tag
        if is_warp and "[⚡WARP]" not in (poison_tag or ""):
            poison_tag = f"{poison_tag or ''}[⚡WARP]"

        # 检查 OpenAI 算力降智：若命中重度降智惩罚，剥夺 ❇️ AI 徽章
        openai_p = waf_eval.get("probes", {}).get("openai_sentinel", {})
        if openai_p.get("degraded") is True and openai_p.get("level") == "DEGRADED_HEAVY":
            if r.get("ai_supported") is not None:
                ai_sup = False
                r["ai_supported"] = False

        if "shield_passed" in r and r["shield_passed"] is not None:
            cf_pass = bool(r["shield_passed"])
        elif shield_det.get("sparkle_badge") is True or (waf_score is not None and waf_score >= 85):
            cf_pass = True
        elif p.get("_shield_passed") is not None:
            cf_pass = bool(p["_shield_passed"])
        elif r.get("shield_details") and isinstance(r["shield_details"], dict):
            from .shield_probe import shield_passed
            cf_pass = shield_passed(r["shield_details"])
        else:
            cf_pass = None

        # 若存在 HTTP v3 WAF 评分且无浏览器全通证据，✨️ 必须满足 sparkle_badge 或 waf_score >= 85
        has_browser_shield = any(
            isinstance(shield_det.get(k), dict) and "status" in shield_det[k]
            for k in ("cloudflare", "chatgpt", "anthropic", "gemini", "claude")
        )
        if waf_score is not None and not has_browser_shield:
            waf_sparkle_ok = bool(shield_det.get("sparkle_badge") is True or waf_score >= 85)
        else:
            waf_sparkle_ok = True

        # 综合全通 ✨️: 必须同时满足 AI五大全通 + Groq解锁 + YouTube免登实播 + 免盾达成
        # 且丢包率必须健康 (< 20%)，严重丢包/高抖动节点不授予 ✨️ 徽章
        liveness_info = r.get("liveness") or {}
        loss_val = r.get("loss_rate") if r.get("loss_rate") is not None else liveness_info.get("loss_rate")
        loss_ok = bool(loss_val is None or loss_val < 20.0)

        if yt_pass is not None and cf_pass is not None:
            sparkle = bool(ai_sup and groq_pass and yt_pass and cf_pass and waf_sparkle_ok and loss_ok and not is_warp)
        elif yt_pass is None and cf_pass is not None:
            sparkle = bool(ai_sup and groq_pass and (orig_has_sparkle or shield_det.get("sparkle_badge")) and cf_pass and waf_sparkle_ok and loss_ok and not is_warp)
        elif r.get("youtube_details") or r.get("shield_details"):
            sparkle = bool(ai_sup and groq_pass and (yt_pass is True) and (cf_pass is True) and waf_sparkle_ok and loss_ok and not is_warp)
        else:
            sparkle = bool(ai_sup and groq_pass and orig_has_sparkle and not poison_tag and loss_ok and not is_warp)

        # 测速相关：实测以实测为准，未测速继承原 Key / Fast
        if r.get("speed_result") is not None or r.get("is_key") is True or r.get("is_fast") is True:
            is_key = bool(r.get("is_key", False) or p.get("_is_key", False))
            is_fast = bool((r.get("is_fast", False) or p.get("_is_fast", False)) and not is_key)
        else:
            is_key = bool(orig_has_key)
            is_fast = bool(orig_has_fast and not is_key)

        # 流水线已实测判定直连/落地时以实测为准，不让原名里的 _Lnd/_USAI/_GOAI/_GUI 覆盖本轮结果
        orig_has_usai = bool("_USAI" in orig or "_USAI" in pname or r.get("is_usai"))
        orig_has_goai = bool("_GOAI" in orig or "_GOAI" in pname or "_GUI" in orig or "_GUI" in pname or r.get("is_goai") or r.get("is_gui"))
        if isinstance(r.get("is_landing"), bool):
            is_landing = r["is_landing"]
        elif r.get("path") == "direct":
            is_landing = False
        elif r.get("path") == "front":
            is_landing = True
        else:
            is_landing = bool("_Lnd" in pname or ((orig_has_usai or orig_has_goai) and p.get("dialer-proxy")))

        # 检查 IP 属地是否统一认定
        is_geo_inconsistent = is_ip_region_inconsistent(r)

        # USAI 与 GOAI 判定规则:
        # 准则：
        # 1. 属地统一认定的美国 AI 节点 -> 正常授予 _USAI；
        # 2. 属地判定存在不一致、但由谷歌认定为美国 IP 且具备 AI 能力的节点（不论多数决归属到哪个国家，如墨西哥、印尼等） -> 授予 _GOAI 后缀；
        # 3. 属地不一致且非谷歌认定的节点，或不具备 AI 能力的节点 -> 严禁授予 _GOAI，亦不得授予 _USAI。
        google_is_us = bool(is_google_recognized_us(r) or (orig_has_goai and not r.get("geo_decision")))
        if not is_geo_inconsistent:
            is_usai = bool(cc == "US" and ai_sup)
            is_goai = False
        else:
            is_usai = False
            is_goai = bool(google_is_us and ai_sup)
        is_gui = is_goai

        is_cg = "_ChromeGo" in orig or "_ChromeGo" in pname

        rep = r.get("ip_reputation") or p.get("_ip_reputation") or {}
        sc = valid_reputation_score(rep.get("score"))
        has_cf_mitigated = bool(
            shield_det.get("any_cf_mitigated")
            or waf_eval.get("any_cf_mitigated")
            or any(p_item.get("cf_mitigated") for p_item in (waf_eval.get("probes") or {}).values())
            or any(
                isinstance(v, dict) and (v.get("cf_mitigated") or v.get("reason") == "cf_mitigated_header")
                for v in shield_det.values()
            )
            or r.get("any_cf_mitigated")
            or p.get("_any_cf_mitigated")
            or r.get("cf_mitigated")
            or p.get("_cf_mitigated")
        )
        r["any_cf_mitigated"] = has_cf_mitigated

        # ♥️ 高信誉/纯净 IP 判定: 信誉分 >= 80 且无任何 cf-mitigated 硬拦截且无污染标记
        if r.get("is_high_quality") is True:
            is_hq = bool(not poison_tag and not has_cf_mitigated)
        elif rep.get("status") == "observed" and sc is not None:
            is_hq = bool(sc >= 80 and not poison_tag and not has_cf_mitigated)
        else:
            is_hq = bool(orig_has_hq and not poison_tag and not has_cf_mitigated)

        # 流媒体：实测以实测为准，未测继承原 _NF / _D+
        if r.get("media_details"):
            media_details = r.get("media_details")
        else:
            media_details = {}
            if orig_has_nf:
                media_details["nf"] = True
            if orig_has_dp:
                media_details["dp"] = True

        raw = r.get("raw_node") if isinstance(r.get("raw_node"), dict) else {}
        raw_name = raw.get("tag") or raw.get("name") or raw.get("_orig_name") or ""

        # IPLC 专线识别：测试节点中有 IPLC/专线 标识的保留 IPLC 后缀，排在所有后缀第一位
        is_iplc = bool(
            r.get("is_iplc")
            or p.get("_is_iplc")
            or raw.get("_is_iplc")
            or re.search(r'(?i)iplc|专线', orig)
            or re.search(r'(?i)iplc|专线', pname)
            or re.search(r'(?i)iplc|专线', raw_name)
            or re.search(r'(?i)iplc|专线', r.get("name") or "")
            or re.search(r'(?i)iplc|专线', r.get("tag") or "")
        )
        r["is_iplc"] = is_iplc

        # 家宽 / 双ISP 真实检测识别：严禁盲信上游节点自标名称（家宽/双ISP/住宅/residential），仅信任真实网络层检测或已有规范标记
        ip_info = r.get("ip_info") or p.get("_ip_info") or {}
        ip_flags = dict(ip_info.get("flags") or {})
        asn_cand = ip_info.get("asn")
        isp_cand = ip_info.get("isp") or ""
        ptr_cand = ip_info.get("ptr")
        isp_text = f"{isp_cand} {asn_cand or ''}".lower()
        for entry in (r.get("ip_info_by_ip") or {}).values():
            if isinstance(entry, dict):
                flags = entry.get("flags") or {}
                if flags.get("residential") is True:
                    ip_flags["residential"] = True
                if flags.get("datacenter") is True:
                    ip_flags["datacenter"] = True
                elif flags.get("datacenter") is False and "datacenter" not in ip_flags:
                    ip_flags["datacenter"] = False
                if not asn_cand and entry.get("asn"):
                    asn_cand = entry.get("asn")
                if not isp_cand and entry.get("isp"):
                    isp_cand = entry.get("isp")
                if not ptr_cand and entry.get("ptr"):
                    ptr_cand = entry.get("ptr")
                isp_text += f" {entry.get('isp', '')} {entry.get('asn', '')}".lower()

        is_known_res_isp = any(k in isp_text for k in [
            'hinet', 'chunghwa', 'hkt', 'pccw', 'hkbn', 'home broadband',
            'broadband', 'telecom', 'turing', 'comcast', 'at&t', 'spectrum',
            'charter', 'verizon', 'bigleaf', 'residential'
        ])

        canon_node = (
            parse_canonical_node(orig)
            or parse_canonical_node(pname)
            or parse_canonical_node(raw_name)
        )
        canon_has_home = bool(canon_node and ("🏠" in orig or "🏠" in pname or "🏠" in raw_name))
        canon_has_isp = bool(
            canon_node and (
                re.search(r'(?:^|_)ISP(?=_|\[|$)', orig)
                or re.search(r'(?:^|_)ISP(?=_|\[|$)', pname)
                or re.search(r'(?:^|_)ISP(?=_|\[|$)', raw_name)
            )
        )
        explicit_res = bool(
            r.get("is_residential")
            or p.get("is_residential")
            or p.get("_is_residential")
            or raw.get("is_residential")
            or raw.get("_is_residential")
        )
        explicit_isp = bool(
            r.get("has_res_suffix")
            or p.get("has_res_suffix")
            or p.get("_has_res_suffix")
            or raw.get("has_res_suffix")
            or raw.get("_has_res_suffix")
        )

        is_res_cand = bool(
            ip_flags.get("residential") is True
            or (is_known_res_isp and ip_flags.get("datacenter") is False)
            or explicit_res
            or canon_has_home
        )

        # 核心准则升级：四级家宽形态精准仲裁
        # Level 1: 原生民用住宅宽带 -> 综合信誉分 >= 80 授予 🏠，< 80 降级为 _ISP
        # Level 2: 商用/机房双 ISP -> 严禁 🏠，统一打标为 _ISP 后缀
        # Level 3: 住宅代理池 -> 剥离 🏠 与 ♥️ 资格
        # Level 4: 数据中心/机房 -> 普通机房节点，不带家宽相关标记
        res_level = (
            r.get("residential_level")
            or ip_info.get("residential_level")
            or rep.get("residential_level")
            or (rep.get("details") or {}).get("residential_level")
        )
        if not res_level and (asn_cand or isp_cand or ptr_cand or ip_flags):
            from .residential_judge import classify_residential
            judged = classify_residential(
                ip=str(r.get("egress_ip") or ip_info.get("ip") or ""),
                ptr=ptr_cand,
                asn_raw=asn_cand,
                isp_name=isp_cand,
                scamalytics=(rep.get("details") or {}).get("scamalytics"),
                ipinfo_flags=ip_flags
            )
            res_level = judged.get("level")

        if is_warp or geo_poison_tag:
            is_res_hq = False
            has_res_suf = False
            is_hq = False
        elif res_level == "Level 1: True Residential":
            is_res_hq = bool(is_hq)
            has_res_suf = bool(not is_res_hq and not is_iplc)
        elif res_level == "Level 2: Commercial Dual-ISP":
            is_res_hq = False  # 严禁授予 🏠
            has_res_suf = bool(not is_iplc)  # 统一授予 _ISP
        elif res_level == "Level 3: Residential Proxy":
            is_res_hq = False
            has_res_suf = False
            is_hq = False  # 剥离 ♥️ 纯净资格
        elif res_level == "Level 4: Datacenter":
            is_res_hq = False
            has_res_suf = False
        else:
            # 仅针对显式标记或既有规范节点（canon_node）的后备推断，绝不采信上游原始节点名自标家宽
            if rep.get("status") == "observed" or "is_high_quality" in r or "ip_reputation" in r:
                is_res_hq = bool(is_res_cand and is_hq)
            else:
                is_res_hq = bool(is_res_cand and (is_hq or explicit_res or canon_has_home))
            has_res_suf = bool(((is_res_cand and not is_res_hq) or explicit_isp or canon_has_isp) and not is_iplc)

        r["is_residential"] = is_res_hq
        r["has_res_suffix"] = has_res_suf
        r["is_res_candidate"] = is_res_cand or bool(res_level in ("Level 1: True Residential", "Level 2: Commercial Dual-ISP"))

        # 清除残留于城市/自定义段的原节点家宽名称（不再保留如 HiNet家宽, 双ISP家宽, Seller双ISP 等中缀）
        if city:
            city = re.sub(r'(?i)(?:^|_)?(?:hinet|hkt|tokala|seller|blurpath|bigleaf|blackmesa|proxy[-_]?cheap|iproyal)*(?:双isp|家宽|住宅|residential)+(?=_|$)?', '', city).strip('_')
            city = re.sub(r'(?i)(?:^|_)?(?:hinet|hkt|tokala|seller|blurpath|bigleaf|blackmesa|proxy[-_]?cheap|iproyal)(?=_|$)', '', city).strip('_')

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
            is_goai=is_goai,
            is_gui=is_goai,
            media_details=media_details,
            is_chromego=is_cg,
            poison_tag=poison_tag,
            city=city,
            is_iplc=is_iplc,
            is_residential=is_res_hq,
            has_res_suffix=has_res_suf
        )

        # 杜绝任何同名碰撞
        while new_name in seen_names:
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
                is_goai=is_goai,
                is_gui=is_goai,
                media_details=media_details,
                is_chromego=is_cg,
                poison_tag=poison_tag,
                city=city,
                is_iplc=is_iplc,
                is_residential=is_res_hq,
                has_res_suffix=has_res_suf
            )
            r["assigned_slot"] = extra_slot
        seen_names.add(new_name)

        is_geo_inconsistent = is_ip_region_inconsistent(r)
        if "proxy" in r:
            p["name"] = new_name
            p["_is_key"] = is_key
            p["_is_fast"] = is_fast
            p["_is_iplc"] = is_iplc
            p["_is_residential"] = is_res_hq
            p["_has_res_suffix"] = has_res_suf
            p["_is_geo_inconsistent"] = is_geo_inconsistent
            p["_is_usai"] = is_usai
            p["_is_goai"] = is_goai
            p["_is_gui"] = is_goai
            if r.get("geo_decision"):
                p["_geo_decision"] = r["geo_decision"]
            p["_key_score"] = r.get("key_score", 0.0)
            p["_ip_reputation"] = r.get("ip_reputation")
            p["_is_landing"] = is_landing
            p["is_landing"] = is_landing
            if not is_landing:
                p.pop("dialer-proxy", None)
        if "raw_node" in r and isinstance(r["raw_node"], dict):
            r["raw_node"]["_is_iplc"] = is_iplc
            r["raw_node"]["_is_residential"] = is_res_hq
            r["raw_node"]["_has_res_suffix"] = has_res_suf
            r["raw_node"]["_is_landing"] = is_landing
            r["raw_node"]["_is_geo_inconsistent"] = is_geo_inconsistent
            r["raw_node"]["_is_usai"] = is_usai
            r["raw_node"]["_is_goai"] = is_goai
            r["raw_node"]["_is_gui"] = is_goai
            if r.get("geo_decision"):
                r["raw_node"]["_geo_decision"] = r["geo_decision"]
            if not is_landing:
                r["raw_node"].pop("dialer-proxy", None)

        r["final_name"] = new_name
        r["slot"] = r["assigned_slot"]
        r["is_geo_inconsistent"] = is_geo_inconsistent
        r["is_usai"] = is_usai
        r["is_goai"] = is_goai
        r["is_gui"] = is_goai
        r["is_key"] = is_key
        r["is_fast"] = is_fast
        r["is_iplc"] = is_iplc
        r["is_residential"] = is_res_hq
        r["has_res_suffix"] = has_res_suf
        r["comprehensive_sparkle"] = sparkle
        r["is_high_quality"] = is_hq
        r["is_usai"] = is_usai
        r["is_landing"] = is_landing

    # 4. 与导出共用同一排序规则：默认按编号排位；resort 时先定位置再从 1 重新编号
    results[:] = sort_nodes_by_region_and_landing(results, resort=resort)
    if resort:
        for row in results:
            canon = parse_canonical_node(row["final_name"])
            if canon:
                row["slot"] = row["assigned_slot"] = canon["slot"]
    return results
