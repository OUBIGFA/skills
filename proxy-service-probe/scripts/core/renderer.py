# -*- coding: utf-8 -*-
"""Clash / Mihomo 配置渲染模块: 以 template.yaml 为母版，注入节点并生成标准策略组与规则集。"""
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


def build_proxy_groups(proxies):
    """根据节点的能力和属性构造标准策略组结构。"""
    all_names = [p["name"] for p in proxies]
    landing = [p["name"] for p in proxies if "_Lnd" in p.get("name", "") or "_USAI" in p.get("name", "")]
    directs = [p["name"] for p in proxies if "_Lnd" not in p.get("name", "") and "_USAI" not in p.get("name", "")]
    sparkle = [p["name"] for p in proxies if ("✨️" in p.get("name", "") or "✨" in p.get("name", ""))]
    ai = [p["name"] for p in proxies if "❇️" in p.get("name", "")]
    usai = [p["name"] for p in proxies if "_USAI" in p.get("name", "")]
    us = [p["name"] for p in proxies if re.search(r"🇺🇸|美国|USA|\bUS\b", p.get("name", ""))]
    nf = [p["name"] for p in proxies if "_NF" in p.get("name", "")]
    dp = [p["name"] for p in proxies if "_D+" in p.get("name", "")]

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

    # 为落地节点绑定 dialer-proxy
    for p in proxies:
        is_lnd = "_Lnd" in p.get("name", "") or "_USAI" in p.get("name", "")
        if is_lnd:
            p["dialer-proxy"] = front_group_name
        else:
            p.pop("dialer-proxy", None)

    # 构造前置跳板池选项
    front_proxies = [fast_group_name, "DIRECT"]
    if directs:
        front_proxies.extend(directs)

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
        # 前置跳板管理组 (允许直连非落地节点及本地 Karing 端口作为前置跳板)
        {"name": front_group_name, "type": "select", "proxies": front_proxies},
        make_url_test(fast_group_name, directs, ["DIRECT"]),

        # 核心入口与分流总开关
        {"name": "🌏️ 节点选择", "type": "select", "proxies": node_select_proxies},
        make_url_test("🚀 自动选择", all_names, ["DIRECT"], hidden=False, tolerance=20),
        {"name": "🔄 手动切换", "type": "select", "proxies": all_names if all_names else ["DIRECT"]},
    ]

    # ✨️ 综合全通标杆策略组 (AI + YouTube + 4站免盾全部通过)
    if sparkle:
        groups.append(make_url_test("✨️ 综合全通", sparkle, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0, hidden=False))

    groups.extend([
        # AI 与 Google 策略组
        {"name": "🔀 AI 服务", "type": "select", "proxies": ai_service_proxies},
        {"name": "🇺🇸 Google", "type": "select", "proxies": ["✅ 解锁USAI", "✅ 解锁 AI", "🇺🇸 美国节点", "🚀 自动选择", "🔄 手动切换"]},
        make_url_test("✅ 解锁 AI", ai, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0),
        make_url_test("✅ 解锁USAI", usai, ["🚀 自动选择"], url="https://www.google.com/generate_204", interval=60, tolerance=0),
        {"name": "🇺🇸 美国节点", "type": "select", "hidden": True, "proxies": us if us else ["🚀 自动选择"]},

        # 国际流媒体策略组
        {"name": "🎬 国际流媒体", "type": "select", "proxies": ["🎥 奈飞解锁", "✨ 解锁Disney+", "🔄 手动切换", "DIRECT"]},
        make_url_test("🎥 奈飞解锁", nf, ["🔄 手动切换", "DIRECT"], url="https://www.netflix.com/title/81280792", interval=300, tolerance=100),
        make_url_test("✨ 解锁Disney+", dp, ["🔄 手动切换", "DIRECT"], url="https://www.disneyplus.com", interval=300, tolerance=100),

        # 落地专属组
        {"name": "🔒️ 落地节点", "type": "select", "proxies": landing if landing else ["DIRECT"]},
        {"name": "⛔️ 拦截广告", "type": "select", "proxies": ["DIRECT", "REJECT"]},
        {"name": "↪️ 漏网之鱼", "type": "select", "proxies": ["🌏️ 节点选择", "DIRECT"]},
    ])

    return groups


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
    template = load_template(template_path)
    clean_proxies = [clean_proxy_dict(p) for p in proxies]
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
