# -*- coding: utf-8 -*-
"""
GitHub Gist 代理订阅搜索与节点提取模块 (core.gist)
实现基于 GitHub Gist 的代理订阅主动检索与节点抓取能力。
支持以独立 JSON 配置文件 (gist_config.json) 维护参数，
采用方案 B (GitHub Fastly CDN Raw 直链免控拉取)，零风控、免 Token 频率限制，
默认抓取 20 条最新有效目标，并严格过滤单源超过 200 节点的公开垃圾源。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3

urllib3.disable_warnings()

from core.fofa import deduplicate_and_sort_proxies
from core.parsers import load_proxies

# Gist 搜索预设语法库
PRESET_GIST_QUERIES = {
    # 推荐主力（默认）：双源并进（最新 Clash YAML + 商用机场直连订阅），自动聚合取最新
    "recommended": ["filename:yaml proxies", 'filename:txt "subscribe?token="'],
    # 机场直链订阅：单独挖掘包含商用面板 subscribe?token= 的订阅直链文件 (高价值金矿)
    "subs": 'filename:txt "subscribe?token="',
    # Clash/Mihomo 专项配置
    "clash": "filename:yaml proxies",
    # sing-box 出站配置 (包含 vless, reality 等)
    "singbox": 'filename:json "outbounds" "vless"',
    # Hysteria 2 极速专线节点配置
    "hy2": 'filename:yaml "hysteria2"',
    # Base64 订阅源文件
    "base64": 'filename:txt "vmess://" OR "vless://"',
    # 综合多格式搜索
    "comprehensive": 'filename:yaml OR filename:json "proxies:" OR "outbounds"'
}

DEFAULT_GIST_PRESET = "recommended"
DEFAULT_TARGETS = 20
DEFAULT_MAX_AGE_HOURS = 48
DEFAULT_MAX_NODES_PER_SUB = 200
DEFAULT_TIMEOUT = 12

GIST_SEARCH_BASE_URL = "https://gist.github.com/search"
GIST_BASE_URL = "https://gist.github.com"
GIST_RAW_BASE_URL = "https://gist.githubusercontent.com"

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
SUBSCRIPTION_UA = "ClashforWindows/0.20.39"


def get_default_gist_config_path() -> str:
    """获取技能根目录下的 gist_config.json 默认绝对路径。"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    return os.path.join(skill_root, "gist_config.json")


def load_gist_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 Gist 配置文件。
    优先读取传入的 config_path，未指定则读取技能主目录下的 gist_config.json。
    同时支持系统环境变量覆盖，若未配置代理则尝试复用 fofa_config.json 中的代理设置。
    """
    path = config_path or get_default_gist_config_path()
    config: Dict[str, Any] = {
        "max_age_hours": DEFAULT_MAX_AGE_HOURS,
        "default_targets": DEFAULT_TARGETS,
        "max_nodes_per_subscription": DEFAULT_MAX_NODES_PER_SUB,
        "proxy": "",
        "timeout": DEFAULT_TIMEOUT,
        "default_query": PRESET_GIST_QUERIES[DEFAULT_GIST_PRESET]
    }

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                if isinstance(user_cfg, dict):
                    config.update(user_cfg)
        except Exception as e:
            print(f"      [Gist Config] 读取配置文件警告: {e}")

    # 若 Gist 未显式配置代理，尝试共享 fofa_config.json 中的代理
    if not config.get("proxy"):
        skill_root = os.path.dirname(os.path.abspath(path))
        fofa_cfg_path = os.path.join(skill_root, "fofa_config.json")
        if os.path.exists(fofa_cfg_path):
            try:
                with open(fofa_cfg_path, "r", encoding="utf-8") as f:
                    fc = json.load(f)
                    if fc.get("proxy"):
                        config["proxy"] = fc["proxy"]
            except Exception:
                pass

    # 环境变量覆盖
    env_proxy = os.environ.get("GIST_PROXY")
    if env_proxy:
        config["proxy"] = env_proxy

    env_max_age = os.environ.get("GIST_MAX_AGE_HOURS")
    if env_max_age:
        try:
            config["max_age_hours"] = float(env_max_age)
        except ValueError:
            pass

    env_targets = os.environ.get("GIST_DEFAULT_TARGETS")
    if env_targets:
        try:
            config["default_targets"] = int(env_targets)
        except ValueError:
            pass

    env_max_nodes = os.environ.get("GIST_MAX_NODES_PER_SUB")
    if env_max_nodes:
        try:
            config["max_nodes_per_subscription"] = int(env_max_nodes)
        except ValueError:
            pass

    env_timeout = os.environ.get("GIST_TIMEOUT")
    if env_timeout:
        try:
            config["timeout"] = int(env_timeout)
        except ValueError:
            pass

    return config


def resolve_gist_query(query_or_preset: Optional[str] = None, fallback: Optional[Any] = None) -> Any:
    """解析 Gist 查询语法或预设名称。"""
    if not query_or_preset:
        return fallback if fallback is not None else PRESET_GIST_QUERIES[DEFAULT_GIST_PRESET]
    q_clean = query_or_preset.strip()
    return PRESET_GIST_QUERIES.get(q_clean, q_clean)


def parse_iso_datetime(dt_str: str) -> Optional[datetime]:
    """解析 ISO 8601 时间戳字符串为 UTC datetime 对象。"""
    if not dt_str:
        return None
    dt_str = dt_str.strip()
    # 替换尾部 Z 为 +00:00 以便 fromisoformat 解析
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_within_max_age(datetime_str: str, max_age_hours: float, now_utc: Optional[datetime] = None) -> bool:
    """检查时间戳是否在指定的 max_age_hours 小时窗口内。"""
    dt = parse_iso_datetime(datetime_str)
    if not dt:
        return True  # 无法解析时宽容放行
    ref_now = now_utc or datetime.now(timezone.utc)
    age_seconds = (ref_now - dt).total_seconds()
    if age_seconds < 0:
        return True  # 未来微小时钟漂移放行
    return age_seconds <= (max_age_hours * 3600)


def _make_http_request(url: str, headers: Optional[Dict[str, str]] = None,
                       proxy_url: Optional[str] = None, timeout: int = 12) -> Optional[requests.Response]:
    """带有代理与安全重试的通用 HTTP GET 请求封装。"""
    proxies = {}
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get(
            url,
            headers=headers or {"User-Agent": BROWSER_UA},
            proxies=proxies,
            timeout=timeout,
            verify=False
        )
        return resp
    except Exception:
        return None


def parse_gist_search_html(html: str, max_age_hours: float = 48.0,
                           now_utc: Optional[datetime] = None) -> Tuple[List[Dict[str, Any]], bool]:
    """
    解析 gist.github.com/search 的返回 HTML。
    提取每个 Gist 卡片的：gist_id, username, updated_at, snippet_files。
    校验时效性，超过 max_age_hours 时标明 has_expired_reached=True 便于提前截断后续页码。
    返回: (有效 gist_cards 列表, 是否已遇到超期条目)
    """
    cards: List[Dict[str, Any]] = []
    has_expired_reached = False
    if not html:
        return cards, has_expired_reached

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        snippets = soup.find_all("div", class_=re.compile(r"gist-snippet"))
        if not snippets:
            snippets = soup.find_all("div", id=re.compile(r"gist-\d+"))
    except Exception:
        snippets = []

    seen_ids = set()

    for snip in snippets:
        # 1. 提取用户名与 gist_id
        links = snip.find_all("a")
        username, gist_id = "", ""
        snippet_files = []
        for a in links:
            href = a.get("href", "")
            m = re.match(r"^/([^/]+)/([0-9a-f]{20,})(?:#file-(.+))?$", href)
            if m:
                u, gid, fname = m.group(1), m.group(2), m.group(3)
                if not username and not gist_id:
                    username, gist_id = u, gid
                if fname:
                    snippet_files.append(fname.replace("-", "."))

        if not username or not gist_id:
            m_id = re.search(r'href="(?:\/)([^\/"\s]+)\/([0-9a-f]{20,})', str(snip))
            if m_id:
                username, gist_id = m_id.group(1), m_id.group(2)

        if not username or not gist_id or gist_id in seen_ids:
            continue

        # 2. 提取时间戳
        time_tag = snip.find("relative-time")
        updated_at = time_tag.get("datetime", "") if time_tag else ""

        # 3. 校验更新时间窗口
        if updated_at:
            if not is_within_max_age(updated_at, max_age_hours, now_utc=now_utc):
                has_expired_reached = True
                continue

        seen_ids.add(gist_id)
        cards.append({
            "gist_id": gist_id,
            "username": username,
            "updated_at": updated_at,
            "gist_url": f"{GIST_BASE_URL}/{username}/{gist_id}",
            "snippet_files": list(set(snippet_files))
        })

    return cards, has_expired_reached


def _search_single_query_targets(query: str, config: Optional[Dict[str, Any]] = None,
                                 max_targets: Optional[int] = None,
                                 max_age_hours: Optional[float] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """单条语法的 Gist 检索执行函数。"""
    cfg = config or load_gist_config()
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or DEFAULT_TIMEOUT)
    target_limit = max_targets if max_targets is not None else int(cfg.get("default_targets") or DEFAULT_TARGETS)
    age_limit = max_age_hours if max_age_hours is not None else float(cfg.get("max_age_hours") or DEFAULT_MAX_AGE_HOURS)

    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    collected_targets: List[Dict[str, Any]] = []
    seen_ids = set()
    page = 1
    max_pages = max(1, (target_limit + 9) // 10)  # Gist 搜索每页约 10 条结果

    stats = {
        "query": query,
        "pages_searched": 0,
        "total_cards_found": 0,
        "valid_fresh_targets": 0,
        "expired_truncated": False
    }

    while page <= max_pages and len(collected_targets) < target_limit:
        encoded_q = urllib.parse.quote_plus(query)
        search_url = f"{GIST_SEARCH_BASE_URL}?q={encoded_q}&s=updated&o=desc&p={page}"
        resp = _make_http_request(search_url, headers=headers, proxy_url=proxy, timeout=timeout)
        stats["pages_searched"] += 1

        if not resp or resp.status_code != 200:
            status_code = resp.status_code if resp else "timeout/error"
            print(f"      [Gist Search] 第 {page} 页检索异常 (HTTP {status_code})")
            break

        cards, expired = parse_gist_search_html(resp.text, max_age_hours=age_limit)
        stats["total_cards_found"] += len(cards)

        for card in cards:
            gid = card["gist_id"]
            if gid not in seen_ids:
                seen_ids.add(gid)
                collected_targets.append(card)
                if len(collected_targets) >= target_limit:
                    break

        if expired:
            stats["expired_truncated"] = True
            break

        if len(cards) == 0:
            break

        page += 1
        time.sleep(1.0)  # 轻量保护，平滑检索间隔

    stats["valid_fresh_targets"] = len(collected_targets)
    return collected_targets[:target_limit], stats


def search_gist_targets(query: Any, config: Optional[Dict[str, Any]] = None,
                        max_targets: Optional[int] = None,
                        max_age_hours: Optional[float] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    在 GitHub Gist Web 上检索匹配的 Gist 列表。
    支持单条语法或多条语法列表（默认同时抓取最新有效 Clash YAML 与商用机场直连 Token 订阅并智能聚合）。
    自动添加 &s=updated&o=desc 排序参数以确保获取全网最新资产。
    默认抓取 20 条最新有效的目标（可通过 max_targets 调整）。
    返回: (目标 Gist 卡片列表, 检索统计信息)
    """
    if isinstance(query, (list, tuple)):
        all_cards: List[Dict[str, Any]] = []
        seen_ids = set()
        total_pages = 0
        total_found = 0
        cfg = config or load_gist_config()
        target_limit = max_targets if max_targets is not None else int(cfg.get("default_targets") or DEFAULT_TARGETS)

        for sub_q in query:
            cards, sub_stats = _search_single_query_targets(
                query=str(sub_q),
                config=cfg,
                max_targets=target_limit,
                max_age_hours=max_age_hours
            )
            total_pages += sub_stats.get("pages_searched", 0)
            total_found += sub_stats.get("total_cards_found", 0)
            for c in cards:
                gid = c["gist_id"]
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    all_cards.append(c)

        # 按更新时间 updated_at 降序重排序，保证两路来源中最新鲜的资产排在最前面
        def _get_dt(card):
            dt = parse_iso_datetime(card.get("updated_at", ""))
            return dt or datetime.min.replace(tzinfo=timezone.utc)

        all_cards.sort(key=_get_dt, reverse=True)
        final_cards = all_cards[:target_limit]

        combined_stats = {
            "query": " + ".join(str(q) for q in query),
            "pages_searched": total_pages,
            "total_cards_found": total_found,
            "valid_fresh_targets": len(final_cards),
            "expired_truncated": False
        }
        return final_cards, combined_stats

    return _search_single_query_targets(str(query), config, max_targets, max_age_hours)


def extract_raw_urls_from_gist(gist_target: Dict[str, Any],
                               config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """
    访问具体 Gist 页面，提取页面内所有文件的方案 B (Fastly CDN Raw 直链)。
    格式: https://gist.githubusercontent.com/{username}/{gist_id}/raw/{commit_hash}/{filename}
    返回: 文件字典列表 [{'filename': ..., 'raw_url': ..., 'username': ..., 'gist_id': ...}]
    """
    cfg = config or load_gist_config()
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or DEFAULT_TIMEOUT)
    username = gist_target.get("username", "")
    gist_id = gist_target.get("gist_id", "")
    gist_url = gist_target.get("gist_url") or f"{GIST_BASE_URL}/{username}/{gist_id}"

    resp = _make_http_request(gist_url, headers={"User-Agent": BROWSER_UA}, proxy_url=proxy, timeout=timeout)
    if not resp or resp.status_code != 200:
        return []

    # 匹配 Raw 链接: href="/{username}/{gist_id}/raw/{hash}/{filename}"
    pattern = rf'href="(\/{re.escape(username)}\/{re.escape(gist_id)}\/raw\/[^\s"]+)"'
    matches = set(re.findall(pattern, resp.text, re.IGNORECASE))
    if not matches:
        # 兼容宽松匹配: href="/.../.../raw/..."
        matches = set(re.findall(r'href="(\/[^\/"\s]+\/[0-9a-f]{20,}\/raw\/[^\s"]+)"', resp.text, re.IGNORECASE))

    file_items: List[Dict[str, str]] = []
    seen_urls = set()

    for path in sorted(list(matches)):
        cdn_raw_url = f"{GIST_RAW_BASE_URL}{path}"
        if cdn_raw_url in seen_urls:
            continue
        seen_urls.add(cdn_raw_url)
        fname = path.split("/")[-1]
        file_items.append({
            "filename": fname,
            "raw_url": cdn_raw_url,
            "username": username,
            "gist_id": gist_id,
            "gist_url": gist_url
        })

    return file_items


def extract_nested_subscription_urls(text: str) -> List[str]:
    """
    从文件内容 (如 subscribes.txt) 中识别商用机场面板直连订阅链接。
    识别特征: http/https 链接且包含 /subscribe, /link/, /sub?, token= 等。
    """
    sub_urls = []
    if not text:
        return sub_urls

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith(("http://", "https://")):
            continue
        # 排除静态规则 dat/mmdb 下载链接与 github 源码直链
        if "github.com" in line and "/raw/" not in line:
            continue
        if any(kw in line.lower() for kw in ("subscribe", "token=", "sub?", "/link/", "/api/v1/client")):
            sub_urls.append(line)

    return list(dict.fromkeys(sub_urls))  # 保序去重


def fetch_gist_nodes(targets: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None,
                     max_nodes_per_sub: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    利用方案 B (CDN Raw 直链免控拉取)，遍历所有目标 Gist 并解析出代理节点。
    支持自动展开 Gist 内嵌的 subscribes.txt 等直连机场订阅链接。
    严格执行防污染契约：单源节点数超过上限 (默认 200) 时直接丢弃。
    """
    cfg = config or load_gist_config()
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or DEFAULT_TIMEOUT)
    limit = max_nodes_per_sub if max_nodes_per_sub is not None else int(cfg.get("max_nodes_per_subscription") or DEFAULT_MAX_NODES_PER_SUB)

    # 1. 第一步：并发探测各 Gist 页面，收集其下的 CDN Raw 直链
    all_raw_files: List[Dict[str, str]] = []
    workers = min(10, max(2, len(targets))) if targets else 1

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(extract_raw_urls_from_gist, t, cfg): t for t in targets}
        for future in as_completed(future_map):
            try:
                files = future.result()
                if files:
                    all_raw_files.extend(files)
            except Exception:
                pass

    if not all_raw_files:
        return []

    # 2. 第二步：并发下载各 CDN Raw 文件并解析节点
    client_headers = {
        "User-Agent": SUBSCRIPTION_UA,
        "Accept": "*/*"
    }

    collected_proxies: List[Dict[str, Any]] = []

    def _process_single_raw_file(file_item: Dict[str, str]) -> List[Dict[str, Any]]:
        raw_url = file_item["raw_url"]
        fname = file_item["filename"].lower()
        resp = _make_http_request(raw_url, headers=client_headers, proxy_url=proxy, timeout=timeout)
        if not resp or resp.status_code != 200 or len(resp.text) < 10:
            return []

        text = resp.text
        source_label = f"gist:{file_item['username']}/{file_item['gist_id'][:8]}/{file_item['filename']}"

        # 检查是否为订阅直链列表 (如 subscribes.txt)
        nested_subs = extract_nested_subscription_urls(text)
        if nested_subs and (fname.endswith(".txt") or "sub" in fname):
            nested_nodes: List[Dict[str, Any]] = []
            # 限制单 Gist 最多拉取前 5 条直链，防止嵌套雪崩
            for sub_url in nested_subs[:5]:
                try:
                    s_resp = _make_http_request(sub_url, headers=client_headers, proxy_url=proxy, timeout=timeout)
                    if s_resp and s_resp.status_code == 200 and len(s_resp.text) > 20:
                        parsed = load_proxies(s_resp.text)
                        if parsed:
                            if limit > 0 and len(parsed) > limit:
                                print(f"      [跳过超量嵌套源] {sub_url} 节点数 ({len(parsed)}) 超过上限 ({limit})，丢弃以防垃圾源干扰")
                                continue
                            for n in parsed:
                                n.setdefault("_source_target", sub_url)
                                n.setdefault("_source_gist", source_label)
                            nested_nodes.extend(parsed)
                except Exception:
                    pass
            return nested_nodes

        # 正常节点解析 (Clash YAML / sing-box JSON / Base64)
        try:
            nodes = load_proxies(text)
            if nodes:
                if limit > 0 and len(nodes) > limit:
                    print(f"      [跳过超量源] Gist {source_label} 节点数 ({len(nodes)}) 超过上限 ({limit})，丢弃以防低质公开聚合源干扰")
                    return []
                for n in nodes:
                    n.setdefault("_source_target", raw_url)
                    n.setdefault("_source_gist", source_label)
                return nodes
        except Exception:
            pass

        return []

    fetch_workers = min(16, max(4, len(all_raw_files)))
    with ThreadPoolExecutor(max_workers=fetch_workers) as executor:
        futures = {executor.submit(_process_single_raw_file, fi): fi for fi in all_raw_files}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    collected_proxies.extend(res)
            except Exception:
                pass

    return deduplicate_and_sort_proxies(collected_proxies)


def search_and_fetch_gist_proxies(query_or_preset: Optional[str] = None,
                                  config_path: Optional[str] = None,
                                  max_targets: Optional[int] = None,
                                  max_nodes_per_sub: Optional[int] = None,
                                  max_age_hours: Optional[float] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    高阶统一调用入口：
    按预设/语法在 GitHub Gist 检索最新有效 Gist，利用 CDN Raw 免控拉取并解析出清洗去重后的节点。
    返回: (去重节点列表, 命中的目标 Gist 卡片列表)
    """
    cfg = load_gist_config(config_path)
    query = resolve_gist_query(query_or_preset, cfg.get("default_query"))
    targets, stats = search_gist_targets(
        query=query,
        config=cfg,
        max_targets=max_targets,
        max_age_hours=max_age_hours
    )
    if not targets:
        return [], []

    proxies = fetch_gist_nodes(
        targets,
        config=cfg,
        max_nodes_per_sub=max_nodes_per_sub
    )
    return proxies, targets
