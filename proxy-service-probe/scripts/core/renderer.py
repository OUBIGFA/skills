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


def load_template(template_path=None):
    """加载母版模版，默认采用技能内置的 template.yaml。"""
    if not template_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        template_path = os.path.join(base_dir, "templates", "template.yaml")

    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"未找到 Clash 模版文件: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    return bool(p.get("_is_landing") or p.get("is_landing") or "_Lnd" in name or "_USAI" in name or p.get("dialer-proxy") or p.get("detour"))


def _is_key(p):
    """判定是否为 Key 优质前置跳板节点 (直连强加密且测速达标)"""
    if p.get("_is_key") is True:
        return True
    name = p.get("name") or p.get("tag") or ""
    return "Key" in name and not _is_landing(p)


def sort_nodes_by_region_and_landing(items):
    """
    按国家/地区分组，并严格保持与 YAML 相同的排序规则：
    1. 同一国家/地区内的节点聚集在一起（按 CATEGORY_ORDER 标准地区位阶排列）。
    2. 同一国家/地区内，直连节点排在前面，落地节点 (_Lnd / _USAI) 排在该地区最后。
    3. 特殊边界保护：如果排在全节点第一个的国家/地区仅有 1 个节点且为落地节点，
       则将该国家/地区挪至下一个国家/地区之后，确保客户端启动的首选节点必定为可直连节点。
    """
    if not items:
        return []

    from .egress_geo import CATEGORY_ORDER

    def _get_name(item):
        if isinstance(item, dict):
            return item.get('final_name') or item.get('name') or item.get('tag') or ''
        return str(item)

    def _is_lnd(item):
        if isinstance(item, dict):
            if item.get('is_landing') is True or item.get('_is_landing') is True:
                return True
            if item.get('dialer-proxy') or item.get('detour'):
                return True
        name = _get_name(item)
        return ('_Lnd' in name) or ('_USAI' in name) or ('_家宽' in name)

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
        sparkle = 0 if '✨' in name else 1
        ai = 0 if '❇️' in name else 1
        key = 0 if ('Key' in name or 'key' in name) else 1
        fast = 0 if 'Fast' in name else 1
        nf = 0 if '_NF' in name else 1
        dp = 0 if '_D+' in name else 1
        m = re.search(r'_(\d+)', name)
        slot = int(m.group(1)) if m else 9999
        return (sparkle, ai, key, fast, nf, dp, slot, name)

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
        if len(first_nodes) == 1 and _is_lnd(first_nodes[0]):
            country_order = [country_order[1], first_c] + country_order[2:]

    def _renumber_tag(old_name, slot):
        m = re.search(r'^(.*?)_(\d+)(.*)$', old_name)
        if m:
            return f"{m.group(1)}_{slot}{m.group(3)}"
        return f"{old_name}_{slot}"

    sorted_items = []
    for c in country_order:
        c_nodes = country_buckets[c]
        directs = [n for n in c_nodes if not _is_lnd(n)]
        landings = [n for n in c_nodes if _is_lnd(n)]
        directs.sort(key=_node_internal_key)
        landings.sort(key=_node_internal_key)
        combined = directs + landings

        # 定好位置再编号：每个国家/地区内的节点位置确定后，从 1 开始严格依次递增重新编号
        for slot_idx, item in enumerate(combined, start=1):
            old_name = _get_name(item)
            new_name = _renumber_tag(old_name, slot_idx)

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


def build_proxy_groups(proxies):
    """
    根据节点的能力和属性构造标准策略组结构 (严格同步 freenode 分组规则)。
    1. 🛡️ Front前置：仅允许 Key 优质前置节点进组，严禁落地节点充当前置跳板！
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

    # 构造前置跳板池选项: 优先 Key 节点池；若本批次无 Key 节点则退守可用直连节点
    front_members = keys if keys else directs
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

        # 映射 DIRECT -> direct, REJECT -> block
        sb_proxies = []
        for p in proxies:
            if p == "DIRECT":
                sb_proxies.append("direct")
            elif p == "REJECT":
                sb_proxies.append("block")
            else:
                sb_proxies.append(p)

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
            target = "direct" if parts[2] == "DIRECT" else parts[2]
            sb_rules.append({"process_name": [parts[1]], "outbound": target})
        elif rtype == "DOMAIN-SUFFIX" and len(parts) >= 3:
            target = "direct" if parts[2] == "DIRECT" else ("block" if parts[2] == "REJECT" else parts[2])
            sb_rules.append({"domain_suffix": [parts[1]], "outbound": target})
        elif rtype == "DOMAIN-KEYWORD" and len(parts) >= 3:
            target = "direct" if parts[2] == "DIRECT" else ("block" if parts[2] == "REJECT" else parts[2])
            sb_rules.append({"domain_keyword": [parts[1]], "outbound": target})
        elif rtype == "DOMAIN" and len(parts) >= 3:
            target = "direct" if parts[2] == "DIRECT" else ("block" if parts[2] == "REJECT" else parts[2])
            sb_rules.append({"domain": [parts[1]], "outbound": target})
        elif rtype == "GEOSITE" and len(parts) >= 3:
            if parts[1] in ("geolocation-cn", "cn"):
                sb_rules.append({"rule_set": ["geosite-cn"], "outbound": "direct"})
        elif rtype == "GEOIP" and len(parts) >= 3:
            if parts[1] in ("CN", "cn"):
                sb_rules.append({"rule_set": ["geoip-cn"], "outbound": "direct"})

    # 合并相邻同类同目标的规则
    optimized = []
    for r in sb_rules:
        key = [k for k in r if k != "outbound"][0]
        outbound = r["outbound"]
        if (
            optimized
            and key in optimized[-1]
            and optimized[-1].get("outbound") == outbound
            and isinstance(optimized[-1][key], list)
            and isinstance(r[key], list)
        ):
            optimized[-1][key].extend(r[key])
        else:
            optimized.append(deepcopy(r))

    return base_rules + optimized


def inject_streaming_rules(rules):
    """注入流媒体专属分流规则。"""
    has_streaming = any("🎬 国际流媒体" in r for r in rules)
    if has_streaming:
        return rules

    final_rules = []
    inserted = False
    for r in rules:
        if not inserted and ("TikTok" in r or "YouTube" in r or "OpenAI" in r):
            final_rules.extend(STREAMING_RULES)
            inserted = True
        final_rules.append(r)

    if not inserted:
        final_rules.extend(STREAMING_RULES)

    return final_rules


def render_clash_config(proxies, template_path=None):
    """根据测试后的节点与母版生成最终完整的 Clash / Mihomo 配置字典。"""
    sorted_proxies = sort_nodes_by_region_and_landing(proxies)
    template = load_template(template_path)
    clean_proxies = [clean_proxy_dict(p) for p in sorted_proxies]
    groups = build_proxy_groups(clean_proxies)

    config = deepcopy(template)
    config["proxies"] = clean_proxies
    config["proxy-groups"] = groups
    config["rules"] = inject_streaming_rules(template.get("rules", []))

    return config


def export_clash_yaml(proxies, output_path, template_path=None):
    """导出最终配置到指定 YAML 文件。"""
    cfg = render_clash_config(proxies, template_path=template_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return output_path


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
        if t in ("selector", "urltest", "direct", "block", "dns", "socks"):
            continue
        p = parse_singbox_outbound(ob)
        if p:
            clash_proxies.append(p)

    return export_clash_yaml(clash_proxies, output_yaml_path, template_path=template_path)
