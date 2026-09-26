# -*- coding: utf-8 -*-
"""Clash / Mihomo 配置渲染模块: 以 template.yaml 为母版，注入节点并生成标准策略组与规则集 (同步自 freenode 规范)。"""
import os
import re
import json
from copy import deepcopy
import yaml

STREAMING_RULES = [
    "DOMAIN-SUFFIX,netflix.com,🎬 国际流媒体", "DOMAIN-SUFFIX,netflix.net,🎬 国际流媒体",
    "DOMAIN-SUFFIX,nflxso.net,🎬 国际流媒体", "DOMAIN-SUFFIX,nflxext.com,🎬 国际流媒体",
    "DOMAIN-SUFFIX,nflxvideo.net,🎬 国际流媒体", "DOMAIN-SUFFIX,nflximg.net,🎬 国际流媒体",
    "DOMAIN-SUFFIX,disneyplus.com,🎬 国际流媒体", "DOMAIN-SUFFIX,bamgrid.com,🎬 国际流媒体",
    "DOMAIN-SUFFIX,disney-plus.net,🎬 国际流媒体", "DOMAIN-SUFFIX,spotify.com,🎬 国际流媒体",
    "DOMAIN-SUFFIX,scdn.co,🎬 国际流媒体",
    "RULE-SET,Netflix,🎬 国际流媒体", "RULE-SET,DisneyPlus,🎬 国际流媒体", "RULE-SET,Spotify,🎬 国际流媒体",
    "RULE-SET,Amazon,🎬 国际流媒体", "RULE-SET,Hulu,🎬 国际流媒体", "RULE-SET,HBO,🎬 国际流媒体",
]


GENERATED_SECTIONS = ("proxies", "proxy-groups")
# 技能母版 (格式与 freenode/template.yaml 对齐，由用户手动维护)
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
BUNDLED_TEMPLATE = os.path.join(SKILL_ROOT, "templates", "template.yaml")
BUILTIN_POLICIES = frozenset({"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"})


class _NoAliasDumper(yaml.SafeDumper):
    """多个策略组共用同一节点列表时不输出 &id001 / *id001 锚点，逐组展开。"""

    def ignore_aliases(self, data):
        return True


def dump_yaml(data):
    return yaml.dump(data, Dumper=_NoAliasDumper, allow_unicode=True, sort_keys=False)


def resolve_template_path(template_path=None):
    """母版路径: 显式指定 (--template) 优先，否则用技能母版 templates/template.yaml。"""
    path = template_path or BUNDLED_TEMPLATE
    if not os.path.isfile(path):
        raise FileNotFoundError(f"未找到 Clash 模版文件: {path}")
    return path


def read_template_text(template_path=None):
    """读取母版原文 (兼容记事本保存的 UTF-8 BOM 与 CRLF)，返回 (路径, 原文, 解析结果)；语法错误带行列号报出。"""
    path = resolve_template_path(template_path)
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"母版 YAML 语法错误 ({path}):\n{e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"母版顶层必须是键值映射 ({path})")
    return path, text, data


def load_template(template_path=None):
    """加载母版模版 (默认技能母版 templates/template.yaml)。"""
    return read_template_text(template_path)[2]


def _split_rule(rule):
    """按顶层逗号切分规则，AND/OR/NOT 逻辑规则括号内的逗号不切。"""
    parts, depth, current = [], 0, ""
    for ch in rule:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    parts.append(current.strip())
    return parts


def template_problems(template, group_names, proxy_names=()):
    """母版引用检查: 规则指向的策略组/节点必须存在，RULE-SET 必须在 rule-providers 中定义。"""
    problems = []
    rules = template.get("rules")
    if not isinstance(rules, list) or not rules:
        return ["缺少 rules 列表"]
    providers = template.get("rule-providers") or {}
    if not isinstance(providers, dict):
        problems.append("rule-providers 必须是键值映射")
        providers = {}
    policies = BUILTIN_POLICIES | set(group_names) | set(proxy_names)
    for no, rule in enumerate(rules, 1):
        if not isinstance(rule, str):
            problems.append(f"rules 第 {no} 条不是字符串: {rule!r}")
            continue
        parts = _split_rule(rule)
        kind = parts[0].upper()
        if kind == "SUB-RULE":
            continue
        policy_at = 1 if kind == "MATCH" else 2
        policy = parts[policy_at] if len(parts) > policy_at else None
        if policy is None:
            problems.append(f"rules 第 {no} 条缺少策略: {rule}")
        elif policy not in policies:
            problems.append(f"rules 第 {no} 条指向不存在的策略组: {rule}")
        if kind == "RULE-SET" and parts[1] not in providers:
            problems.append(f"rules 第 {no} 条引用未定义的 rule-providers: {rule}")
    return problems


def check_template(template_path=None):
    """测试开始前校验母版，问题一次性报出，避免跑完整轮测试才在导出时失败。返回实际使用的母版路径。"""
    path, _, template = read_template_text(template_path)
    # 用带 ✨️ 的示例节点把按需生成的「✨️ 综合全通」组也算进可用策略组
    groups = [g["name"] for g in build_proxy_groups([{"name": "✨️示例", "type": "direct"}])]
    problems = template_problems(template, groups)
    if problems:
        raise ValueError(f"母版校验未通过 ({path})，proxy-groups 由脚本生成，可用策略组: {'、'.join(groups)}\n  - "
                         + "\n  - ".join(problems))
    return path


def clean_proxy_dict(proxy):
    """清理内部私有字段（以 _ 开头），仅保留合法字段。"""
    clean = {}
    for k, v in proxy.items():
        if not k.startswith("_"):
            clean[k] = v
    return clean


def _is_landing(p):
    """判定是否为落地节点"""
    name = p.get("name") or p.get("tag") or ""
    if isinstance(p.get("_is_landing"), bool):
        return p["_is_landing"]
    if isinstance(p.get("is_landing"), bool):
        return p["is_landing"]
    if "_Lnd" in name or "_USAI" in name or "_家宽" in name:
        return True
    # 旧 detour 可能残留在 Key 直连节点上，不能借此将前置节点链回自身。
    if p.get("_is_key") is True or re.search(r'(?i)\bkey(?![a-z])', name):
        return False
    return bool(p.get("dialer-proxy") or p.get("detour"))


def _is_key(p):
    """判定是否为 Key 优质前置跳板节点 (直连强加密且测速达标)；落地节点即使带 Key 标记也不作前置，杜绝前置组自环。"""
    if _is_landing(p):
        return False
    name = p.get("name") or p.get("tag") or ""
    return p.get("_is_key") is True or "Key" in name


def renumber_node_tag(old_name, slot, is_hq=False):
    """根据目标编号重构节点名称（保留已有能力徽章、前缀与后缀）。"""
    flag_match = re.search(r'^([\U0001F1E6-\U0001F1FF]{2}|🏳️|\U0001F3F3\uFE0F?)\s*', old_name)
    flag = flag_match.group(0) if flag_match else ""
    rest = old_name[len(flag):]

    sparkle = bool("✨️" in rest or "✨" in rest)
    ai = bool("❇️" in rest or "❇" in rest)
    is_polluted = bool("_⚠️" in rest)
    hq = bool(is_hq and not is_polluted)
    key = bool(re.search(r'(?i)\bkey(?![a-z])', rest))
    fast = bool(re.search(r'(?i)\bfast(?![a-z])', rest))

    prefix = ""
    if sparkle:
        prefix += "✨️"
    if ai:
        prefix += "❇️"
    if hq:
        prefix += "♥️"
    if key:
        prefix += "Key"
    elif fast:
        prefix += "Fast"

    cleaned_rest = re.sub(r'^(?:[✨❇️♥️♥]️?|\s+|Key|Fast)+', '', rest, flags=re.I)
    m = re.search(r'^(.*?)_(\d+)(.*)$', cleaned_rest)
    if m:
        country = m.group(1)
        raw_suffix = m.group(3)
        clean_suffix = re.sub(r'(?:✨\uFE0F?|❇\uFE0F?|♥\uFE0F?|\bKey\b|\bFast\b)', '', raw_suffix, flags=re.I).strip()
        return f"{flag}{prefix}{country}_{slot}{clean_suffix}"

    m_old = re.search(r'^(.*?)_(\d+)(.*)$', old_name)
    if m_old:
        return f"{m_old.group(1)}_{slot}{m_old.group(3)}"
    return f"{old_name}_{slot}"


def sort_nodes_by_region_and_landing(items, resort=False):
    """
    按国家/地区分组，并严格保持与 YAML 相同的排序规则：
    1. 同一国家/地区内的节点聚集在一起（按 CATEGORY_ORDER 标准地区位阶排列，未列出的地区排在已列出地区之后，
       中国排在所有国家/地区之后，未知垫底）。
    2. 同一国家/地区内，直连节点排在前面，落地节点 (_Lnd / _USAI) 排在该地区最后。
    3. 特殊边界保护：如果排在全节点第一个的国家/地区仅有 1 个节点且为落地节点，
       则将该国家/地区挪至下一个国家/地区之后，确保客户端启动的首选节点必定为可直连节点。
    4. resort=False（默认）：名称与编号原样保留，同组内按现有编号排位；
       resort=True（仅用户主动要求重排序时）：按能力标签与信誉重排，位置全部确定后从 1 重新编号。
    """
    if not items:
        return []

    from .egress_geo import CATEGORY_ORDER, valid_reputation_score

    def _get_name(item):
        if isinstance(item, dict):
            return item.get('final_name') or item.get('name') or item.get('tag') or ''
        return str(item)

    def _is_lnd(item):
        if isinstance(item, dict):
            if isinstance(item.get('is_landing'), bool):
                return item['is_landing']
            if isinstance(item.get('_is_landing'), bool):
                return item['_is_landing']
            if item.get('dialer-proxy') or item.get('detour'):
                return True
            proxy = item.get('proxy')
            if isinstance(proxy, dict) and (proxy.get('dialer-proxy') or proxy.get('detour')):
                return True
        name = _get_name(item)
        return ('_Lnd' in name) or ('_USAI' in name) or ('_家宽' in name)

    def _reputation(item):
        if not isinstance(item, dict):
            return {}
        return (item.get('ip_reputation') or item.get('_ip_reputation') or
                (item.get('proxy') or {}).get('_ip_reputation') or
                (item.get('raw_node') or {}).get('_ip_reputation') or {})

    def _is_hq(item, name):
        # 送中/受限地区污染节点不授予 ♥️，与打标层 format_node_name 保持一致
        if '_⚠️' in name:
            return False
        # 打标层已给出结论（含浏览器复测沿用已有 ♥️）时以其为准，排位与命名不再各算一套
        if isinstance(item, dict) and isinstance(item.get('is_high_quality'), bool):
            return item['is_high_quality']
        reputation = _reputation(item)
        score = valid_reputation_score(reputation.get('score'))
        if score is not None:
            return score >= 80 and reputation.get('status') == 'observed'
        return '♥' in name

    def _parse_cc(name):
        m = re.search(r'([\U0001F1E6-\U0001F1FF]{2})', name)
        if m:
            f = m.group(1)
            return chr(ord(f[0]) - 0x1F1E6 + ord('A')) + chr(ord(f[1]) - 0x1F1E6 + ord('A'))
        for cc, info in CATEGORY_ORDER.items():
            if info[2] in name:
                return cc
        return 'UNK'

    def _node_internal_key(item):
        name = _get_name(item)
        sparkle = 0 if ('✨' in name) else 1
        ai = 0 if ('❇️' in name or '❇' in name) else 1
        key = 0 if re.search(r'(?i)\bkey(?![a-z])', name) else 1
        fast = 0 if re.search(r'(?i)\bfast(?![a-z])', name) else 1
        is_polluted = 1 if ('_⚠️' in name) else 0
        reputation = _reputation(item)
        score = valid_reputation_score(reputation.get('score'))
        hq = 0 if _is_hq(item, name) else 1
        has_score = 0 if score is not None else 1
        reputation_rank = -score if score is not None and reputation.get('status') == 'observed' else 0
        nf = 0 if '_NF' in name else 1
        dp = 0 if '_D+' in name else 1
        m = re.search(r'_(\d+)', name)
        slot = int(m.group(1)) if m else 9999
        if not resort:
            return (slot, name)
        # 先按 ✨️ > ❇️ > Key > Fast > _NF > _D+ 硬分层；干净节点优于污染节点；
        # ♥️ 与信誉分只在上述标签完全相同的节点之间决定先后，不跨越标签层级
        return (sparkle, ai, key, fast, nf, dp, is_polluted, hq, has_score, reputation_rank, slot, name)

    country_buckets = {}
    country_order = []
    for it in items:
        cc = _parse_cc(_get_name(it))
        if cc not in country_buckets:
            country_buckets[cc] = []
            country_order.append(cc)
        country_buckets[cc].append(it)

    country_order.sort(key=lambda c: CATEGORY_ORDER.get(c, (7, 999, c))[:2])

    if len(country_order) >= 2:
        first_c = country_order[0]
        first_nodes = country_buckets[first_c]
        if len(first_nodes) == 1 and _is_lnd(first_nodes[0]) and country_order[1] not in ('CN', 'UNK'):
            # 首节点保护不能破坏“中国在所有已知国家/地区之后、未知垫底”的硬顺序。
            country_order = [country_order[1], first_c] + country_order[2:]

    _renumber_tag = renumber_node_tag

    sorted_items = []
    for c in country_order:
        c_nodes = country_buckets[c]
        directs = [n for n in c_nodes if not _is_lnd(n)]
        landings = [n for n in c_nodes if _is_lnd(n)]
        directs.sort(key=_node_internal_key)
        landings.sort(key=_node_internal_key)
        combined = directs + landings
        if not resort:
            sorted_items.extend(combined)
            continue

        # 定好位置再编号：每个国家/地区内的节点位置确定后，从 1 开始严格依次递增重新编号
        for slot_idx, item in enumerate(combined, start=1):
            old_name = _get_name(item)
            new_name = _renumber_tag(old_name, slot_idx, is_hq=_is_hq(item, old_name))

            if isinstance(item, dict):
                if "tag" in item:
                    item["tag"] = new_name
                if "name" in item:
                    item["name"] = new_name
                if "final_name" in item:
                    item["final_name"] = new_name
                if "proxy" in item and isinstance(item["proxy"], dict):
                    if "name" in item["proxy"]:
                        item["proxy"]["name"] = new_name
                    if "tag" in item["proxy"]:
                        item["proxy"]["tag"] = new_name
                if "raw_node" in item and isinstance(item["raw_node"], dict):
                    if "tag" in item["raw_node"]:
                        item["raw_node"]["tag"] = new_name
                    if "name" in item["raw_node"]:
                        item["raw_node"]["name"] = new_name
                if "slot" in item:
                    item["slot"] = slot_idx
                if "assigned_slot" in item:
                    item["assigned_slot"] = slot_idx
                sorted_items.append(item)
            elif isinstance(item, str):
                sorted_items.append(new_name)
            else:
                sorted_items.append(item)

    return sorted_items


def build_proxy_groups(proxies, front_fallback=None):
    """
    根据节点的能力和属性构造标准策略组结构 (严格同步 freenode 分组规则)。
    1. 🛡️ Front前置：仅允许 Key 优质前置节点进组，严禁落地节点充当前置跳板！
       无 Key 时优先使用 front_fallback (测速达到备用档、实际用于验证落地节点的前置)，再退守可用直连节点。
    2. ⚡ Fast自动选择：仅在 Key 优质前置跳板节点中执行 url-test 延迟选优。
    3. 落地节点：所有落地节点默认绑定 dialer-proxy: 🛡️ Front前置。
    """
    all_names = [(p.get("name") or p.get("tag")) for p in proxies if (p.get("name") or p.get("tag"))]
    landing = [(p.get("name") or p.get("tag")) for p in proxies if _is_landing(p)]
    directs = [(p.get("name") or p.get("tag")) for p in proxies if not _is_landing(p)]

    # 遴选 Key 前置跳板节点 (按评分排序，落地绝不进入)
    key_nodes = [p for p in proxies if _is_key(p)]
    key_nodes.sort(key=lambda item: -float(item.get("_key_score") or 0.0))
    keys = [(p.get("name") or p.get("tag")) for p in key_nodes]

    sparkle = [(p.get("name") or p.get("tag")) for p in proxies if ("✨️" in (p.get("name") or p.get("tag") or "") or "✨" in (p.get("name") or p.get("tag") or ""))]
    ai = [(p.get("name") or p.get("tag")) for p in proxies if "❇️" in (p.get("name") or p.get("tag") or "")]
    usai = [(p.get("name") or p.get("tag")) for p in proxies if "_USAI" in (p.get("name") or p.get("tag") or "")]
    us = [(p.get("name") or p.get("tag")) for p in proxies if re.search(r"🇺🇸|美国|USA|\bUS\b", (p.get("name") or p.get("tag") or ""))]
    nf = [(p.get("name") or p.get("tag")) for p in proxies if "_NF" in (p.get("name") or p.get("tag") or "")]
    dp = [(p.get("name") or p.get("tag")) for p in proxies if "_D+" in (p.get("name") or p.get("tag") or "")]

    def make_url_test(name, members, fallback, url="https://cp.cloudflare.com/generate_204", interval=45, tolerance=50, hidden=True):
        return {
            "name": name,
            "type": "url-test",
            "hidden": hidden,
            "url": url,
            "interval": interval,
            "tolerance": tolerance,
            "lazy": False,
            "proxies": members if members else fallback
        }

    front_group_name = "🛡️ Front前置"
    fast_group_name = "⚡ Fast自动选择"

    # 为落地节点绑定 dialer-proxy 指向前置策略组
    for p in proxies:
        if _is_landing(p):
            p["dialer-proxy"] = front_group_name
        else:
            p.pop("dialer-proxy", None)

    # 构造前置跳板池选项: 优先 Key 节点池；无 Key 时用备用前置 (排除落地)，再退守可用直连节点
    fallback = [name for name in (front_fallback or []) if name in directs]
    front_members = keys or fallback or directs
    front_proxies = [fast_group_name, "DIRECT"]
    if front_members:
        front_proxies.extend(front_members)

    # 核心入口与分流总开关代理列表
    node_select_proxies = []
    if sparkle:
        node_select_proxies.append("✨️ 综合全通")
    node_select_proxies.extend(["🚀 自动选择", "🔄 手动切换", "🔀 AI 服务", "🇺🇸 Google", "🎬 国际流媒体", "🔒️ 落地节点", "DIRECT"])

    # AI 策略组代理列表
    ai_service_proxies = []
    if sparkle:
        ai_service_proxies.append("✨️ 综合全通")
    ai_service_proxies.extend(["🇺🇸 Google", "✅ 解锁USAI", "✅ 解锁 AI", "🔄 手动切换"])

    groups = [
        # --- 前置跳板管理组 (仅包含 Key 前置与直连，落地节点绝不可作为前置跳板) ---
        {"name": front_group_name, "type": "select", "proxies": front_proxies},
        make_url_test(fast_group_name, front_members, ["DIRECT"]),

        # --- 核心入口与分流总开关 ---
        {"name": "🌏️ 节点选择", "type": "select", "proxies": node_select_proxies},
        make_url_test("🚀 自动选择", all_names, ["DIRECT"], hidden=False, tolerance=20),
        {"name": "🔄 手动切换", "type": "select", "proxies": all_names if all_names else ["DIRECT"]},
    ]

    # ✨️ 综合全通标杆策略组 (AI + YouTube + 4站免盾全部通过)
    if sparkle:
        groups.append(make_url_test("✨️ 综合全通", sparkle, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0, hidden=False))

    groups.extend([
        # --- AI 与 Google 专属策略组 ---
        {"name": "🔀 AI 服务", "type": "select", "proxies": ai_service_proxies},
        {"name": "🇺🇸 Google", "type": "select", "proxies": ["✅ 解锁USAI", "✅ 解锁 AI", "🇺🇸 美国节点", "🚀 自动选择", "🔄 手动切换"]},
        make_url_test("✅ 解锁 AI", ai, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0),
        make_url_test("✅ 解锁USAI", usai, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0),
        {"name": "🇺🇸 美国节点", "type": "select", "hidden": True, "proxies": us if us else ["🚀 自动选择"]},

        # --- 国际流媒体专属策略组 ---
        {"name": "🎬 国际流媒体", "type": "select", "proxies": ["🎥 奈飞解锁", "✨ 解锁Disney+", "🔄 手动切换", "DIRECT"]},
        make_url_test("🎥 奈飞解锁", nf, ["🔄 手动切换", "DIRECT"], url="https://www.netflix.com/title/81280792", interval=300, tolerance=100),
        make_url_test("✨ 解锁Disney+", dp, ["🔄 手动切换", "DIRECT"], url="https://www.disneyplus.com", interval=300, tolerance=100),

        # --- 落地节点专属组 ---
        {"name": "🔒️ 落地节点", "type": "select", "proxies": landing if landing else ["DIRECT"]},
        {"name": "⛔️ 拦截广告", "type": "select", "proxies": ["DIRECT", "REJECT"]},
        {"name": "↪️ 漏网之鱼", "type": "select", "proxies": ["🌏️ 节点选择", "DIRECT"]},
    ])

    return groups


def convert_clash_groups_to_singbox(groups):
    """
    将标准 Clash / Mihomo 策略组结构转换为 sing-box 1.14+ 现代 outbounds 策略组 (selector / urltest)。
    """
    sb_outbounds = []
    for g in groups:
        name = g.get("name", "")
        g_type = g.get("type", "select")
        proxies = g.get("proxies", [])

        # 映射 DIRECT -> direct；sing-box 1.11 起弃用 block 出站（拦截改用路由 action: reject），REJECT 不进组
        sb_proxies = ["direct" if p == "DIRECT" else p for p in proxies if p != "REJECT"]
        if not sb_proxies:
            sb_proxies = ["direct"]

        if g_type == "select":
            sb_outbounds.append({
                "type": "selector",
                "tag": name,
                "outbounds": sb_proxies,
                "default": sb_proxies[0] if sb_proxies else "direct"
            })
        elif g_type == "url-test":
            interval = g.get("interval", 60)
            if isinstance(interval, int):
                interval_str = f"{max(interval, 60)}s"
            else:
                interval_str = str(interval)

            sb_outbounds.append({
                "type": "urltest",
                "tag": name,
                "outbounds": sb_proxies if sb_proxies else ["direct"],
                "url": g.get("url", "https://cp.cloudflare.com/generate_204"),
                "interval": interval_str,
                "tolerance": g.get("tolerance", 50)
            })

    return sb_outbounds


def _rule_target(target):
    """Clash 规则目标 → sing-box 1.14 路由目标：REJECT 用 action: reject 取代已弃用的 block 出站。"""
    if target == "REJECT":
        return {"action": "reject"}
    return {"outbound": "direct" if target == "DIRECT" else target}


def build_singbox_rules_from_template(template_path=None):
    """
    从 template.yaml 提取全部进程分流、国内外域名、AI、Google、流媒体与广告拦截规则，
    压缩合并为符合 sing-box 1.14+ 规范的高性能内存路由规则。
    """
    template = load_template(template_path)
    rules = template.get("rules", [])

    base_rules = [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
        {"clash_mode": "Direct", "outbound": "direct"},
        {"clash_mode": "Global", "outbound": "🌏️ 节点选择"},
        {"ip_is_private": True, "outbound": "direct"}
    ]

    sb_rules = []
    for r in rules:
        parts = [p.strip() for p in r.split(",")]
        if not parts or not parts[0]:
            continue
        rtype = parts[0]
        if rtype == "PROCESS-NAME" and len(parts) >= 3:
            sb_rules.append({"process_name": [parts[1]], **_rule_target(parts[2])})
        elif rtype == "DOMAIN-SUFFIX" and len(parts) >= 3:
            sb_rules.append({"domain_suffix": [parts[1]], **_rule_target(parts[2])})
        elif rtype == "DOMAIN-KEYWORD" and len(parts) >= 3:
            sb_rules.append({"domain_keyword": [parts[1]], **_rule_target(parts[2])})
        elif rtype == "DOMAIN" and len(parts) >= 3:
            sb_rules.append({"domain": [parts[1]], **_rule_target(parts[2])})
        elif rtype == "GEOSITE" and len(parts) >= 3:
            if parts[1] in ("geolocation-cn", "cn"):
                sb_rules.append({"rule_set": ["geosite-cn"], "outbound": "direct"})
        elif rtype == "GEOIP" and len(parts) >= 3:
            if parts[1] in ("CN", "cn"):
                sb_rules.append({"rule_set": ["geoip-cn"], "outbound": "direct"})

    # 合并相邻同类同目标（同出站或同为 reject 动作）的规则
    optimized = []
    for r in sb_rules:
        key = [k for k in r if k not in ("outbound", "action")][0]
        if (
            optimized
            and key in optimized[-1]
            and len(optimized[-1]) == len(r)
            and optimized[-1].get("outbound") == r.get("outbound")
            and optimized[-1].get("action") == r.get("action")
            and isinstance(optimized[-1][key], list)
            and isinstance(r[key], list)
        ):
            optimized[-1][key].extend(r[key])
        else:
            optimized.append(deepcopy(r))

    return base_rules + optimized


def inject_streaming_rules(rules, providers=None):
    """
    母版没有 🎬 国际流媒体 分流时补上: 插在首条 TikTok/YouTube/OpenAI 规则前，没有则插在 MATCH 兜底前。
    RULE-SET 规则只补母版 rule-providers 中已定义的，避免导出引用不存在规则集、客户端加载失败的配置。
    """
    if any("🎬 国际流媒体" in r for r in rules):
        return rules
    providers = providers or {}
    streaming = [r for r in STREAMING_RULES if not r.startswith("RULE-SET,") or r.split(",")[1] in providers]
    at = next((i for i, r in enumerate(rules) if "TikTok" in r or "YouTube" in r or "OpenAI" in r),
              next((i for i, r in enumerate(rules) if r.split(",")[0].strip().upper() == "MATCH"), len(rules)))
    return rules[:at] + streaming + rules[at:]


def render_clash_config(proxies, template_path=None):
    """根据测试后的节点与母版生成最终完整的 Clash / Mihomo 配置字典。"""
    sorted_proxies = sort_nodes_by_region_and_landing(proxies)
    template = load_template(template_path)
    clean_proxies = [clean_proxy_dict(p) for p in sorted_proxies]
    front_fallback = [p.get("name") for p in sorted_proxies if p.get("_front_fallback")]
    groups = build_proxy_groups(clean_proxies, front_fallback=front_fallback)

    config = deepcopy(template)
    config["proxies"] = clean_proxies
    config["proxy-groups"] = groups
    config["rules"] = inject_streaming_rules(template.get("rules", []), template.get("rule-providers"))

    return config


TOP_LEVEL_KEY = re.compile(r"^([^\s#-][^:#]*?)[ \t]*:(?:[ \t]|$)")
RULE_ITEM = re.compile(r"^(\s*)- ")


def _top_level_block(lines, key):
    """母版原文中顶层键 key 的行区间 [start, end): 键行及其缩进/列表续行；段尾空行与注释留给后面的段落。"""
    starts = [i for i, line in enumerate(lines)
              if (m := TOP_LEVEL_KEY.match(line)) and m.group(1).strip("'\"") == key]
    if not starts:
        return None
    if len(starts) > 1:
        raise ValueError(f"母版中顶层键 {key} 出现了 {len(starts)} 次")
    start = end = starts[0]
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.startswith("#"):
            continue
        if line[0] not in " \t-":
            break
        end = i
    return start, end + 1


def _insert_rules_text(lines, template_rules, rules):
    """规则与母版相同则原样返回；母版规则中被插入一段连续规则 (补流媒体分流) 时在原文对应位置插入；否则返回 None。"""
    if rules == template_rules:
        return list(lines)
    n = len(rules) - len(template_rules)
    k = next((i for i, (a, b) in enumerate(zip(template_rules, rules)) if a != b), len(template_rules))
    block = _top_level_block(lines, "rules")
    if n <= 0 or block is None or rules[:k] != template_rules[:k] or rules[k + n:] != template_rules[k:]:
        return None
    items = [i for i in range(*block) if RULE_ITEM.match(lines[i])]
    if len(items) != len(template_rules):
        return None  # 规则写法 (如跨行条目) 无法与解析结果逐行对应
    indent = RULE_ITEM.match(lines[items[0]]).group(1) if items else ""
    inserted = [indent + row + "\n" for row in dump_yaml(rules[k:k + n]).splitlines()]
    at = items[k] if k < len(items) else block[1]
    return lines[:at] + inserted + lines[at:]


def render_clash_yaml_text(cfg, template_path=None):
    """
    在母版原文上只替换 proxies / proxy-groups 两段为生成内容，其余注释、空行与排版逐字保留。
    母版里这两段写成 `[]` 占位、留有旧节点或被删掉都可以 (删掉时插到 rules 之前)；需补流媒体规则时按原位置插行。
    结果必须解析回与目标配置完全一致；做不到逐行保留时整体输出并提示，不静默丢格式。
    """
    path, text, template = read_template_text(template_path)
    problems = template_problems(cfg, [g["name"] for g in cfg.get("proxy-groups", [])],
                                 [p["name"] for p in cfg.get("proxies", [])])
    if problems:
        raise ValueError(f"渲染结果引用检查未通过 (母版 {path}):\n  - " + "\n  - ".join(problems))
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    fixed = GENERATED_SECTIONS + ("rules",)
    same = {k: v for k, v in cfg.items() if k not in fixed} == {k: v for k, v in template.items() if k not in fixed}
    out_lines = _insert_rules_text(lines, template.get("rules") or [], cfg.get("rules") or []) if same else None
    if out_lines is not None:
        missing = []
        for key in GENERATED_SECTIONS:
            block = _top_level_block(out_lines, key)
            generated = dump_yaml({key: cfg[key]}).splitlines(keepends=True)
            if block is None:
                missing += generated
            else:
                out_lines[block[0]:block[1]] = generated
        if missing:
            rules_block = _top_level_block(out_lines, "rules")
            at = rules_block[0] if rules_block else len(out_lines)
            out_lines[at:at] = missing + ["\n"]
        out = "".join(out_lines)
        if yaml.safe_load(out) == cfg:
            return out
    print(f"      [提示] 母版 {path} 的写法无法逐行保留，已整体输出配置，母版注释与空行未保留")
    out = dump_yaml(cfg)
    if yaml.safe_load(out) != cfg:
        raise ValueError("渲染后的配置与目标配置不一致")
    return out


def export_clash_yaml(proxies, output_path, template_path=None):
    """导出最终配置到指定 YAML 文件 (保留母版注释与空行)。"""
    cfg = render_clash_config(proxies, template_path=template_path)
    content = render_clash_yaml_text(cfg, template_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def _singbox_wireguard_endpoint_to_clash(endpoint):
    """把 sing-box wireguard endpoint 转回 Clash WireGuard 节点；缺关键字段时返回 None。"""
    if not isinstance(endpoint, dict) or endpoint.get("type") != "wireguard":
        return None
    peers = endpoint.get("peers") or []
    peer = peers[0] if peers and isinstance(peers[0], dict) else {}
    if not peer.get("address") or not peer.get("port") or not peer.get("public_key"):
        return None
    addresses = endpoint.get("address") or []
    if not addresses or not endpoint.get("private_key"):
        return None
    p = {
        "name": endpoint.get("tag") or "wireguard",
        "type": "wireguard",
        "server": peer["address"],
        "port": int(peer["port"]),
        "ip": str(addresses[0]).split("/", 1)[0],
        "private-key": endpoint["private_key"],
        "public-key": peer["public_key"],
        "allowed-ips": peer.get("allowed_ips") or ["0.0.0.0/0", "::/0"],
    }
    if len(addresses) > 1:
        p["ipv6"] = str(addresses[1]).split("/", 1)[0]
    if endpoint.get("mtu"):
        p["mtu"] = int(endpoint["mtu"])
    if peer.get("persistent_keepalive_interval"):
        p["persistent-keepalive"] = int(peer["persistent_keepalive_interval"])
    if peer.get("pre_shared_key"):
        p["pre-shared-key"] = peer["pre_shared_key"]
    if peer.get("reserved") is not None:
        p["reserved"] = peer["reserved"]
    if endpoint.get("detour"):
        p["dialer-proxy"] = endpoint["detour"]
    return p


def convert_singbox_to_clash_yaml(singbox_input, output_yaml_path, template_path=None, front_proxy=("127.0.0.1", 3067)):
    """
    将 sing-box JSON 配置文件直接转换为标准的 Clash / Mihomo YAML 配置文件。
    输入可为 JSON 路径或已被解析的 dict 对象。
    """
    from .parsers import parse_singbox_outbound

    if isinstance(singbox_input, str):
        with open(singbox_input, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    elif isinstance(singbox_input, dict):
        cfg = singbox_input
    else:
        raise TypeError("singbox_input 必须是文件路径字符串或 dict 对象")

    outbounds = cfg.get("outbounds", [])
    clash_proxies = []

    for ob in outbounds:
        t = ob.get("type", "").lower()
        if t in ("selector", "urltest", "direct", "block", "dns"):
            continue
        p = parse_singbox_outbound(ob)
        if not p:
            raise ValueError(f"sing-box 节点 {ob.get('tag', '<未命名>')}（{t}）无法转换为 Clash 节点")
        clash_proxies.append(p)

    for endpoint in cfg.get("endpoints", []):
        p = _singbox_wireguard_endpoint_to_clash(endpoint)
        if not p:
            raise ValueError(f"sing-box endpoint {endpoint.get('tag', '<未命名>')} 无法转换为 Clash 节点")
        clash_proxies.append(p)

    return export_clash_yaml(clash_proxies, output_yaml_path, template_path=template_path)
