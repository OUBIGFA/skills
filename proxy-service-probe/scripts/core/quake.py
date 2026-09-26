# -*- coding: utf-8 -*-
"""
360 Quake 空间测绘订阅搜索模块:
实现基于 360 Quake (https://quake.360.net) 引擎的代理订阅源检索与目标提取。
支持通过 fofa_config.json 中的 quake_key 凭证或 QUAKE_KEY 环境变量进行鉴权。
"""
import copy
import json
import os
from typing import Dict, List, Optional, Any

import requests
import urllib3

urllib3.disable_warnings()

QUAKE_API_URL = "https://quake.360.net/api/v3/search/quake_service"
QUAKE_USER_INFO_URL = "https://quake.360.net/api/v3/user/info"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# 360 Quake 订阅检索语法体系
PRESET_QUAKE_QUERIES = {
    # 推荐主力：工业级反代 + 动态订阅/计费头特征 (高活性无死节点)
    "recommended": 'status_code: 200 AND NOT response: "<html" AND (response: "nginx" OR response: "caddy" OR response: "cloudflare" OR response: "openresty") AND (response: "subscription-userinfo" OR (response: "upload=" AND response: "download=")) AND response: "proxies:"',
    # 方案二：动态计费特征断言 (标准商业面板)
    "billing": 'status_code: 200 AND NOT response: "<html" AND response: "upload=" AND response: "download=" AND response: "total=" AND response: "proxies:"',
    # 方案三：用户原版综合型参考语法 (多协议正文断言)
    "comprehensive": 'status_code: 200 AND NOT response: "<html" AND (response: "proxies:" OR response: "\\"outbounds\\":" OR response: "dm1lc3M6" OR response: "c3M6Ly" OR response: "dHJvamFuOi")',
    # 方案四：VLESS / Reality 节点专项订阅
    "vless": 'status_code: 200 AND NOT response: "<html" AND response: "proxies:" AND response: "vless"',
    # 方案五：Hysteria 2 极速节点专项订阅
    "hy2": 'status_code: 200 AND NOT response: "<html" AND response: "hysteria2" AND response: "server"',
    # 方案六：通用 subscription-userinfo 动态流量池
    "sub_userinfo": 'status_code: 200 AND response: "subscription-userinfo"'
}

DEFAULT_QUAKE_PRESET = "recommended"


def resolve_quake_query(query_or_preset: Optional[str], default_query: Optional[str] = None) -> str:
    """根据输入的预设别名或自定义语法解析实际执行的 360 Quake 查询语句。"""
    if not query_or_preset:
        return default_query or PRESET_QUAKE_QUERIES[DEFAULT_QUAKE_PRESET]
    q = query_or_preset.strip()
    return PRESET_QUAKE_QUERIES.get(q.lower(), q)


def _post_quake_request(url: str, headers: Dict[str, str], payload: Dict[str, Any],
                        proxy_url: Optional[str] = None, timeout: int = 15) -> Optional[requests.Response]:
    """发送 HTTP POST 请求到 Quake API，支持本地代理与直连双通道降级。"""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    if proxies:
        try:
            r = requests.post(url, headers=headers, json=payload, proxies=proxies, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
        except Exception:
            pass

    # 直连尝试
    try:
        session = requests.Session()
        session.trust_env = False
        r = session.post(url, headers=headers, json=payload, timeout=timeout, verify=False)
        return r
    except Exception:
        return None


def search_quake_targets(query: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
                         page: int = 1, page_size: int = 80) -> List[str]:
    """
    使用 360 Quake 空间测绘 API (POST /api/v3/search/quake_service) 检索目标订阅源。
    返回目标 URL 列表（去重）。若未配置 quake_key 或请求异常，安全返回空列表，不抛出异常阻断整体流程。
    """
    cfg = config or {}
    quake_key = (
        cfg.get("quake_key")
        or os.environ.get("QUAKE_KEY")
        or os.environ.get("QUAKE_TOKEN")
        or ""
    ).strip()

    if not quake_key:
        print("[Quake] 提示: 未配置 quake_key，跳过 Quake 空间检索")
        return []

    actual_query = resolve_quake_query(query, cfg.get("quake_default_query"))
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or 12)

    headers = {
        "X-QuakeToken": quake_key,
        "Content-Type": "application/json",
        "User-Agent": DEFAULT_UA
    }

    start_index = max(0, (page - 1) * page_size)
    payload = {
        "query": actual_query,
        "start": start_index,
        "size": min(page_size, 100),
        "ignore_cache": False
    }

    resp = _post_quake_request(QUAKE_API_URL, headers=headers, payload=payload,
                               proxy_url=proxy, timeout=timeout)
    if not resp or resp.status_code != 200:
        code_str = f"状态码: {resp.status_code}" if resp else "网络不可达"
        print(f"[Quake] 警告: 请求 API 失败 ({code_str})")
        return []

    try:
        res_json = resp.json()
    except Exception as e:
        print(f"[Quake] 警告: 解析返回 JSON 异常: {e}")
        return []

    if res_json.get("code") != 0:
        msg = res_json.get("message") or "未知错误"
        print(f"[Quake] API 提示: {msg}")
        return []

    data_items = res_json.get("data", [])
    total_count = res_json.get("meta", {}).get("pagination", {}).get("total", len(data_items))
    print(f"      [Quake] 检索成功，匹配到 {total_count} 条资产，本批获取 {len(data_items)} 条")

    targets: List[str] = []
    for item in data_items:
        if not isinstance(item, dict):
            continue

        ip = item.get("ip")
        port = item.get("port")
        hostname = item.get("hostname")
        service = item.get("service") or {}
        service_name = str(service.get("name", "")).lower()
        http_info = service.get("http") or {}

        # 优先读取明确的 url 字段
        explicit_url = http_info.get("url") or item.get("url")
        if explicit_url and isinstance(explicit_url, str) and explicit_url.startswith(("http://", "https://")):
            clean_url = explicit_url.strip()
            if clean_url not in targets:
                targets.append(clean_url)
            continue

        host = http_info.get("host") or hostname or ip
        if not host or not port:
            continue

        is_ssl = "ssl" in service_name or "https" in service_name or str(port) in ("443", "8443") or "tls" in service_name
        scheme = "https" if is_ssl else "http"

        if (scheme == "http" and str(port) == "80") or (scheme == "https" and str(port) == "443"):
            t = f"{scheme}://{host}"
        else:
            t = f"{scheme}://{host}:{port}"

        if t not in targets:
            targets.append(t)

    return targets
