# -*- coding: utf-8 -*-
"""
订阅源与节点长效性过滤模块 (sub_filter.py):
识别并淘汰含「试用」「体验」「临时」「限时」「短期」「一次性」「日抛/周抛」「已过期」等
不能长期使用的订阅源与单个节点。
"""
import base64
import re
import time
import urllib.parse
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


# 试用 / 短期 / 不可长期使用特征匹配表 (按优先级排列)
_NON_LONG_TERM_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"试用"), "含试用字样"),
    (
        re.compile(
            r"(?:免费|限时|短期|新手|新人|注册|白嫖|游客)\s*体验"
            r"|体验\s*(?:版|套餐|节点|订阅|线路|流量|用户|卡|专享|期|服|账号)"
            r"|(?<!极速)(?<!丝滑)(?<!游戏)(?<!优质)(?<!流畅)(?<!良好)(?<!最佳)(?<!完美)(?<!极致)(?<!沉浸)(?<!视觉)(?<!用户)体验"
        ),
        "含体验/试用字样",
    ),
    (re.compile(r"临时"), "含临时字样"),
    (re.compile(r"限时"), "含限时字样"),
    (re.compile(r"短期"), "含短期字样"),
    (re.compile(r"短效"), "含短效字样"),
    (re.compile(r"一次性"), "含一次性字样"),
    (re.compile(r"(?:小时|日|周|天|次)抛"), "含日抛/周抛等短效字样"),
    (
        re.compile(
            r"非长期|不能长期|无法长期|不保证长期|随时失效|随时关闭|即将下线|即将停用|即将关闭|即将失效"
            r"|已过期|已到期|已失效|即将过期|即将到期"
        ),
        "含非长期/失效/过期字样",
    ),
    (re.compile(r"(?:仅限|有效期|剩余|限用|可用)\s*\d+\s*(?:分钟|小时|天|日|周)"), "含限时有效期字样"),
    (re.compile(r"\d+\s*(?:分钟|小时|天|日)\s*(?:有效|过期|到期|失效|试用|体验|内可用)"), "含限时有效期字样"),
    (re.compile(r"(?:今日|当日|今天|明天|本周)\s*(?:有效|失效|过期|到期)"), "含短期有效字样"),
    (re.compile(r"(?:新手|新人|新用户)\s*(?:专享|福利|免费|赠送|节点|订阅|套餐)"), "含新人/新用户试用字样"),
    (
        re.compile(
            r"(?<![a-z])(?:free[-_\s]?)?trial(?:[-_\s]?(?:node|sub|plan|user|pack|key|vip))?(?![a-z])",
            re.IGNORECASE,
        ),
        "含 trial 字样",
    ),
    (
        re.compile(
            r"(?<![a-z])temporary(?![a-z])|(?<![a-z])temp(?=[-_.\s\d/]|$)",
            re.IGNORECASE,
        ),
        "含 temporary/temp 字样",
    ),
    (
        re.compile(
            r"(?<![a-z])(?:short[-_\s]?term|short[-_\s]?lived|time[-_\s]?limited|limited[-_\s]?time"
            r"|disposable|ephemeral|one[-_\s]?time|onetime|expired|expiring)(?![a-z])",
            re.IGNORECASE,
        ),
        "含短期/一次性/过期英文字样",
    ),
    (
        re.compile(
            r"(?<![a-z])(?:\d+\s*(?:min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)"
            r"\s*(?:only|trial|limit|limited|valid|left|remaining)"
            r"|(?:valid|only|trial)\s*(?:for\s*)?\d+\s*(?:min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days))(?![a-z])",
            re.IGNORECASE,
        ),
        "含限时英文有效期字样",
    ),
)

# 节点名称中明确表示「整份订阅/套餐」属于试用或已失效的公告节点特征
_SUB_LEVEL_NOTICE_PATTERN = re.compile(
    r"(?:试用|体验|临时|限时|短期|一次性)\s*(?:套餐|订阅|计划|账号|专线|版|服务)"
    r"|(?:免费|限时)\s*(?:试用|体验)\s*(?:套餐|订阅|计划|账号|专线|版|服务|$)"
    r"|已过期|已到期|已失效"
    r"|(?<![a-z])(?:free[-_\s]?trial[-_\s]?(?:plan|sub)|trial[-_\s]?(?:plan|sub)|expired)(?![a-z])",
    re.IGNORECASE,
)


def _unquote_safe(text: str) -> str:
    if "%" in text:
        try:
            return urllib.parse.unquote(text)
        except Exception:
            return text
    return text


def match_non_long_term_reason(text: Optional[str]) -> Optional[str]:
    """若文本包含试用、临时、限时、短期、一次性、已过期等不可长期使用特征，返回原因，否则返回 None。"""
    if not text or not isinstance(text, str):
        return None
    candidates = [text]
    unquoted = _unquote_safe(text)
    if unquoted != text:
        candidates.append(unquoted)
    for cand in candidates:
        for pattern, reason in _NON_LONG_TERM_PATTERNS:
            if pattern.search(cand):
                return reason
    return None


def _decode_profile_title(value: str) -> str:
    val = (value or "").strip()
    if val.lower().startswith("base64:"):
        b64 = val[7:].strip()
        try:
            pad = "=" * ((4 - len(b64) % 4) % 4)
            return base64.b64decode(b64 + pad).decode("utf-8", errors="replace")
        except Exception:
            return val
    return val


def _extract_raw_header_hints(raw_text: str) -> List[str]:
    """提取订阅正文头部前 15 行中的顶层注释或订阅标题字段，遇到节点列表即停止，避免误判单个节点名。"""
    hints: List[str] = []
    if not raw_text or not isinstance(raw_text, str):
        return hints
    lines = raw_text.splitlines()
    non_empty = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        non_empty += 1
        if non_empty > 15:
            break
        lower = stripped.lower()
        if lower.startswith(("proxies:", "proxy-groups:", "rules:", "\"outbounds\"", "outbounds:")):
            break
        if stripped.startswith("#"):
            hints.append(stripped.lstrip("#").strip())
        elif not line[0].isspace() and lower.startswith(("title:", "remarks:", "profile-title:")):
            hints.append(stripped.split(":", 1)[1].strip().strip("\"'"))
    return hints


def get_node_non_long_term_reason(node: Dict[str, Any]) -> Optional[str]:
    """检查单个节点是否含有试用/临时/限时/短期等不可长期使用特征。"""
    if not isinstance(node, dict):
        return None
    seen = set()
    for key in ("_orig_name", "name", "tag"):
        val = node.get(key)
        if isinstance(val, str):
            val = val.strip()
            if val and val not in seen:
                seen.add(val)
                reason = match_non_long_term_reason(val)
                if reason:
                    return reason
    return None


def check_subscription_non_long_term(
    *,
    url: str = "",
    filename: str = "",
    headers: Optional[Mapping[str, str]] = None,
    raw_text: str = "",
    nodes: Optional[Sequence[Dict[str, Any]]] = None,
    extra_texts: Optional[Sequence[str]] = None,
    now_ts: Optional[float] = None,
) -> Optional[str]:
    """
    判断订阅源本身是否属于试用、临时、短期或已过期等不可长期使用的订阅源。
    若是，返回淘汰原因；否则返回 None。
    """
    if url:
        reason = match_non_long_term_reason(url)
        if reason:
            return f"订阅地址{reason}"

    if filename:
        reason = match_non_long_term_reason(filename)
        if reason:
            return f"订阅文件名{reason}"

    if extra_texts:
        for txt in extra_texts:
            reason = match_non_long_term_reason(txt)
            if reason:
                return f"订阅描述{reason}"

    if headers and isinstance(headers, Mapping):
        lower_headers = {str(k).lower(): str(v) for k, v in headers.items() if v is not None}
        cd = lower_headers.get("content-disposition", "")
        if cd:
            reason = match_non_long_term_reason(cd)
            if reason:
                return f"响应头 Content-Disposition {reason}"

        pt = lower_headers.get("profile-title", "")
        if pt:
            decoded_pt = _decode_profile_title(pt)
            reason = match_non_long_term_reason(decoded_pt)
            if reason:
                return f"响应头 Profile-Title {reason}"

        userinfo = lower_headers.get("subscription-userinfo", "")
        if userinfo:
            m = re.search(r"expire\s*=\s*(\d+)", userinfo, re.IGNORECASE)
            if m:
                expire_ts = int(m.group(1))
                ref_now = time.time() if now_ts is None else now_ts
                if 0 < expire_ts < ref_now:
                    return "响应头 subscription-userinfo 显示订阅已过期"

    if raw_text:
        for hint in _extract_raw_header_hints(raw_text):
            reason = match_non_long_term_reason(hint)
            if reason:
                return f"订阅头部说明{reason}"

    if nodes:
        matched_count = 0
        for n in nodes:
            if not isinstance(n, dict):
                continue
            for key in ("_orig_name", "name", "tag"):
                val = n.get(key)
                if isinstance(val, str) and val.strip():
                    if _SUB_LEVEL_NOTICE_PATTERN.search(val):
                        return f"订阅内含套餐/状态提示「{val.strip()}」"
                    break
            if get_node_non_long_term_reason(n):
                matched_count += 1

        total = len(nodes)
        if total > 0 and (matched_count == total or (total >= 2 and matched_count * 2 >= total)):
            return f"订阅内过半节点 ({matched_count}/{total}) 为试用/短期节点"

    return None


def filter_non_long_term_nodes(
    nodes: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """过滤节点列表中的试用/临时/限时/短期等不可长期使用节点，返回 (保留列表, [(淘汰节点, 原因), ...])。"""
    kept: List[Dict[str, Any]] = []
    dropped: List[Tuple[Dict[str, Any], str]] = []
    for node in nodes:
        reason = get_node_non_long_term_reason(node)
        if reason:
            dropped.append((node, reason))
        else:
            kept.append(node)
    return kept, dropped


def filter_subscription_batch(
    nodes: List[Dict[str, Any]],
    source_label: str,
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """
    对单个订阅源解析出的节点批次执行统一防污染过滤：
    1. 节点数超过 limit (如 300) 时整源淘汰；
    2. 订阅内含套餐/状态公告或过半节点为试用/短期节点时整源淘汰；
    3. 剔除剩余节点中含试用/短期特征的单个节点。
    """
    if not nodes:
        return []
    if limit > 0 and len(nodes) > limit:
        print(f"      [跳过超量源] {source_label} 节点数 ({len(nodes)}) 超过上限 ({limit})，丢弃以防低质公开聚合源干扰")
        return []
    nodes_sub_reason = check_subscription_non_long_term(nodes=nodes)
    if nodes_sub_reason:
        print(f"      [跳过试用/短期源] {source_label} ({nodes_sub_reason})，整源淘汰")
        return []
    kept, dropped = filter_non_long_term_nodes(nodes)
    if dropped:
        print(f"      [淘汰试用/短期节点] {source_label} 剔除 {len(dropped)}/{len(nodes)} 个不可长期使用节点")
    return kept
