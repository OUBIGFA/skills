# -*- coding: utf-8 -*-
"""
FoFa 订阅搜索模块:
实现基于 FoFa 空间测绘引擎的主动订阅搜索与节点抓取能力。
支持以独立 JSON 配置文件 (fofa_config.json) 引用 Token 或 Key，
并集成经过实测验证的高存活率动态订阅语法。
"""
import base64
import copy
from collections import Counter
import json
import os
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

import requests
import urllib3
import yaml

from core.parsers import load_proxies

urllib3.disable_warnings()

# FoFa Web 前端签名 API 凭据 (源自活跃开源项目 Fofa-hack: Cl0udG0d/Fofa-hack)
FOFA_WEB_APP_ID = "9e9fb94330d97833acfbc041ee1a76793f1bc691"
FOFA_WEB_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAv0xjefuBTF6Ox940ZqLLUFFBDtTcB9dAfDjWgyZ2A55K+VdG
c1L5LqJWuyRkhYGFTlI4K5hRiExvjXuwIEed1norp5cKdeTLJwmvPyFgaEh7Ow19
Tu9sTR5hHxThjT8ieArB2kNAdp8Xoo7O8KihmBmtbJ1umRv2XxG+mm2ByPZFlTdW
RFU38oCPkGKlrl/RzOJKRYMv10s1MWBPY6oYkRiOX/EsAUVae6zKRqNR2Q4HzJV8
gOYMPvqkau8hwN8i6r0z0jkDGCRJSW9djWk3Byi3R2oSdZ0IoS+91MFtKvWYdnNH
2Ubhlnu1P+wbeuIFdp2u7ZQOtgPX0mtQ263e5QIDAQABAoIBAD67GwfeTMkxXNr3
5/EcQ1XEP3RQoxLDKHdT4CxDyYFoQCfB0e1xcRs0ywI1be1FyuQjHB5Xpazve8lG
nTwIoB68E2KyqhB9BY14pIosNMQduKNlygi/hKFJbAnYPBqocHIy/NzJHvOHOiXp
dL0AX3VUPkWW3rTAsar9U6aqcFvorMJQ2NPjijcXA0p1MlZAZKODO2wqidfQ487h
xy0ZkriYVi419j83a1cCK0QocXiUUeQM6zRNgQv7LCmrFo2X4JEzlujEveqvsDC4
MBRgkK2lNH+AFuRwOEr4PIlk9rrpHA4O1V13P3hJpH5gxs5oLLM1CWWG9YWLL44G
zD9Tm8ECgYEA8NStMXyAmHLYmd2h0u5jpNGbegf96z9s/RnCVbNHmIqh/pbXizcv
mMeLR7a0BLs9eiCpjNf9hob/JCJTms6SmqJ5NyRMJtZghF6YJuCSO1MTxkI/6RUw
mrygQTiF8RyVUlEoNJyhZCVWqCYjctAisEDaBRnUTpNn0mLvEXgf1pUCgYEAy1kE
d0YqGh/z4c/D09crQMrR/lvTOD+LRMf9lH+SkScT0GzdNIT5yuscRwKsnE6SpC5G
ySJFVhCnCBsQqq+ohsrXt8a99G7ePTMSAGK3QtC7QS3liDmvPBk6mJiLrKiRAZos
vgPg7nTP8VuF0ZIKzkdWbGoMyNxVFZXovQ8BYxECgYBvCR9xGX4Qy6KiDlV18wNu
ElYkxVqFBBE0AJRg/u+bnQ9jWhi2zxLa1eWZgtss80c876I8lbkGNWedOVZioatm
MFLC4bFalqyZWyO7iP7i60LKvfDJfkOSlDUu3OikahFOiqyG1VBz4+M4U500alIU
AVKD14zTTZMopQSkgUXsoQKBgHd8RgiD3Qde0SJVv97BZzP6OWw5rqI1jHMNBK72
SzwpdxYYcd6DaHfYsNP0+VIbRUVdv9A95/oLbOpxZNi2wNL7a8gb6tAvOT1Cvggl
+UM0fWNuQZpLMvGgbXLu59u7bQFBA5tfkhLr5qgOvFIJe3n8JwcrRXndJc26OXil
0Y3RAoGAJOqYN2CD4vOs6CHdnQvyn7ICc41ila/H49fjsiJ70RUD1aD8nYuosOnj
wbG6+eWekyLZ1RVEw3eRF+aMOEFNaK6xKjXGMhuWj3A9xVw9Fauv8a2KBU42Vmcd
t4HRyaBPCQQsIoErdChZj8g7DdxWheuiKoN4gbfK4W1APCcuhUA=
-----END RSA PRIVATE KEY-----"""

# 预设经实测验证的高活性订阅搜索语法
PRESET_QUERIES = {
    # 推荐主力：工业级反代 + 动态订阅计量特征 (实测存活率最高，不写死日期)
    "recommended": '(server="nginx" || server="caddy" || server="cloudflare" || server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html"',
    # 方案二：动态计费特征 + 协议断言 (长期托管订阅源)
    "billing": '(header="upload=" && header="download=" && header="total=") && body="proxies:" && body!="<html"',
    # 方案三：VLESS / Reality 节点专项订阅
    "vless": 'body="proxies:" && body="type: vless" && status_code="200" && body!="<html"',
    # 方案四：Hysteria 2 极速节点专项订阅
    "hy2": 'body="type: hysteria2" && body="server" && status_code="200" && body!="<html"',
    # 方案五：通用 subscription-userinfo 动态流量池
    "sub_userinfo": 'header="subscription-userinfo" && status_code="200"',
    # 方案六：多协议综合型搜索
    "comprehensive": 'status_code="200" && body!="<html" && (body="proxies:" || body="\\"outbounds\\":" || (header="text/plain" && (body="dm1lc3M6" || body="c3M6Ly" || body="dHJvamFuOi")))'
}

DEFAULT_PRESET = "recommended"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
SUBSCRIPTION_UA = "ClashforWindows/0.20.39"


def get_default_config_path() -> str:
    """获取技能根目录下的 fofa_config.json 默认绝对路径。"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 从 scripts/core 向上两级到达技能根目录
    skill_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    return os.path.join(skill_root, "fofa_config.json")


def load_fofa_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 FoFa 配置文件。
    优先读取传入的 config_path，未指定则读取技能主目录下的 fofa_config.json。
    同时支持系统环境变量 (FOFA_TOKEN, FOFA_KEY, FOFA_EMAIL, FOFA_PROXY) 进行运行时覆盖。
    """
    path = config_path or get_default_config_path()
    config: Dict[str, Any] = {
        "token": "",
        "email": "",
        "key": "",
        "quake_key": "",
        "proxy": "",
        "page_size": 80,
        "timeout": 12,
        "max_nodes_per_subscription": 200,
        "default_query": PRESET_QUERIES[DEFAULT_PRESET],
        "quake_default_query": "",
        "_config_source": path
    }

    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                if isinstance(file_cfg, dict):
                    config.update(file_cfg)
        except Exception as e:
            print(f"[FoFa] 警告: 读取配置文件 {path} 失败: {e}")
    else:
        config["_config_source"] = None

    # 环境变量覆盖
    if os.environ.get("FOFA_TOKEN"):
        config["token"] = os.environ["FOFA_TOKEN"]
    if os.environ.get("FOFA_KEY"):
        config["key"] = os.environ["FOFA_KEY"]
    if os.environ.get("FOFA_EMAIL"):
        config["email"] = os.environ["FOFA_EMAIL"]
    if os.environ.get("QUAKE_KEY"):
        config["quake_key"] = os.environ["QUAKE_KEY"]
    elif os.environ.get("QUAKE_TOKEN"):
        config["quake_key"] = os.environ["QUAKE_TOKEN"]
    if os.environ.get("FOFA_PROXY"):
        config["proxy"] = os.environ["FOFA_PROXY"]
    if os.environ.get("FOFA_MAX_NODES_PER_SUB"):
        try:
            config["max_nodes_per_subscription"] = int(os.environ["FOFA_MAX_NODES_PER_SUB"])
        except ValueError:
            pass

    return config


def resolve_query(query_or_preset: Optional[str], default_query: Optional[str] = None) -> str:
    """根据输入的预设别名或自定义语法解析实际执行的 FOFA 查询语句。"""
    if not query_or_preset:
        return default_query or PRESET_QUERIES[DEFAULT_PRESET]
    q = query_or_preset.strip()
    return PRESET_QUERIES.get(q.lower(), q)


def _make_request(url: str, headers: Dict[str, str], cookies: Optional[Dict[str, str]] = None,
                  proxy_url: Optional[str] = None, timeout: int = 12) -> Optional[requests.Response]:
    """发送 HTTP GET 请求，配置代理时优先走代理，遇到网络异常自动尝试直连。"""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    if proxies:
        try:
            r = requests.get(url, headers=headers, cookies=cookies, proxies=proxies, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
        except Exception:
            pass

    # 直连重试/保底
    try:
        session = requests.Session()
        session.trust_env = False
        r = session.get(url, headers=headers, cookies=cookies, timeout=timeout, verify=False)
        return r
    except Exception:
        return None


def _extract_nuxt_targets(html_text: str) -> List[str]:
    """从 FoFa Nuxt 页面渲染脚本中解析 search assets 目标地址。"""
    targets: List[str] = []
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
    for sc in scripts:
        if 'result-search-assets' not in sc:
            continue
        try:
            d = json.loads(sc)
            if not isinstance(d, list):
                continue

            def resolve(v):
                return d[v] if isinstance(v, int) and 0 <= v < len(d) else v

            # 寻找 asset 索引数组
            asset_indices = None
            if len(d) > 8 and isinstance(d[8], list):
                asset_indices = d[8]
            else:
                for item in d:
                    if isinstance(item, list) and item and isinstance(item[0], int) and 0 <= item[0] < len(d):
                        cand = d[item[0]]
                        if isinstance(cand, dict) and any(k in cand for k in ('ip', 'link', 'port', 2, 3)):
                            asset_indices = item
                            break

            if not asset_indices:
                continue

            for idx in asset_indices:
                if not (isinstance(idx, int) and 0 <= idx < len(d)):
                    continue
                item = d[idx]
                if not isinstance(item, dict):
                    continue
                res = {resolve(k): resolve(v) for k, v in item.items()}
                link = res.get('link')
                ip = res.get('ip')
                port = res.get('port')

                target = ""
                if link and isinstance(link, str) and link.startswith(('http://', 'https://')):
                    target = link.strip()
                elif ip and port:
                    scheme = "https" if str(port) == "443" else "http"
                    target = f"{scheme}://{ip}:{port}"

                if target and target not in targets:
                    targets.append(target)
            break
        except Exception:
            pass

    # 保底：若 Nuxt 提取为空，从 HTML <a> 标签中正则提取非 fofa 的外部 URL
    if not targets:
        raw_links = re.findall(r'href=[\'"](https?://[^\'">\s]+)[\'"]', html_text)
        for link in raw_links:
            if 'fofa.info' not in link and 'beian' not in link and 'miit' not in link:
                clean_link = link.split('?')[0].rstrip('/')
                if clean_link not in targets:
                    targets.append(link)

    return targets


def _sign_fofa_web_message(message: str) -> str:
    """
    对 FoFa Web API 请求参数执行 RSA-SHA256 PKCS1_v1_5 签名。
    算法与签名私钥来自活跃开源项目 Fofa-hack (Cl0udG0d/Fofa-hack)，
    通过逆向 Web 端签名协议调用官方 api.fofa.info 接口，
    直接绕过 /result 页面被安全策略/WAF挂起(Tarpit)的问题。
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        key = load_pem_private_key(FOFA_WEB_PRIVATE_KEY.encode('utf-8'), password=None)
        sig = key.sign(message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode('utf-8')
    except Exception:
        pass

    try:
        from Cryptodome.Signature import PKCS1_v1_5
        from Cryptodome.Hash import SHA256
        from Cryptodome.PublicKey import RSA
        priv_key = RSA.importKey(FOFA_WEB_PRIVATE_KEY)
        h = SHA256.new(message.encode('utf-8'))
        return base64.b64encode(PKCS1_v1_5.new(priv_key).sign(h)).decode('utf-8')
    except Exception:
        return ""


def _search_fofa_signed_web_api(qbase64: str, token: str, page: int = 1, size: int = 50,
                                proxy: Optional[str] = None, timeout: int = 12) -> List[str]:
    """
    通过 api.fofa.info 内部签名接口执行检索，直接获取 JSON 格式资产列表。
    单页上限为 50 条 (未付费/个人版 Web Token 超过 50 条服务端会返回 820004 限制)。
    """
    ts = int(time.time() * 1000)
    fetch_size = min(int(size or 50), 50)
    message = f"fullfalsepage{page}qbase64{qbase64}size{fetch_size}ts{ts}"
    sign = _sign_fofa_web_message(message)
    if not sign:
        return []

    url = (f"https://api.fofa.info/v1/search?qbase64={urllib.parse.quote(qbase64)}"
           f"&full=false&page={page}&size={fetch_size}&ts={ts}&sign={urllib.parse.quote(sign)}"
           f"&app_id={FOFA_WEB_APP_ID}")

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json, text/plain, */*",
        "Authorization": token
    }

    resp = _make_request(url, headers=headers, proxy_url=proxy, timeout=timeout)
    if not resp or resp.status_code != 200:
        return []

    try:
        data = resp.json()
        if data.get("code") == 0 and "data" in data and isinstance(data["data"], dict):
            assets = data["data"].get("assets") or []
            targets = []
            for a in assets:
                link = a.get("link")
                ip = a.get("ip")
                port = a.get("port")
                host = a.get("host")
                t = link or (f"https://{host}" if str(port) == "443" else f"http://{ip}:{port}")
                if t and t not in targets:
                    targets.append(t)
            return targets
        elif data.get("code") != 0:
            msg = data.get("message") or ""
            if "权限不足" in msg or "限制" in msg:
                print(f"      [FoFa Web] 检索提示: {msg}")
    except Exception:
        pass

    return []


def search_fofa_targets(query: str, config: Optional[Dict[str, Any]] = None,
                        page: int = 1, page_size: int = 80) -> List[str]:
    """
    使用 FoFa 搜索语法检索在线订阅源目标地址。
    优先调用官方 API Key (若配置)；
    次优调用 FoFa Web 内部签名 API (结合 Fofa-hack RSA 签名与 Authorization Token，突破网页反爬)；
    保底尝试 Nuxt 网页资产解析。
    """
    cfg = config or load_fofa_config()
    actual_query = resolve_query(query, cfg.get("default_query"))
    qbase64 = base64.b64encode(actual_query.encode("utf-8")).decode("utf-8")
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or 12)

    # 1. 尝试官方 API (如果配置了 key)
    if cfg.get("key"):
        email_arg = f"email={cfg['email']}&" if cfg.get("email") else ""
        api_url = f"https://fofa.info/api/v1/search/all?{email_arg}key={cfg['key']}&qbase64={qbase64}&page={page}&size={page_size}&fields=ip,port,host,link"
        r = _make_request(api_url, headers={"User-Agent": DEFAULT_UA}, proxy_url=proxy, timeout=timeout)
        if r and r.status_code == 200:
            try:
                data = r.json()
                if data.get("error"):
                    print(f"      [FoFa API] 检索提示: {data.get('errmsg', '未知错误')}")
                elif "results" in data:
                    targets = []
                    for row in data["results"]:
                        if isinstance(row, list) and len(row) >= 4:
                            ip, port, host, link = row[0], row[1], row[2], row[3]
                            t = link or (f"https://{host}" if str(port) == "443" else f"http://{ip}:{port}")
                            if t and t not in targets:
                                targets.append(t)
                    if targets:
                        return targets
            except Exception:
                pass
        elif r and r.status_code != 200:
            print(f"      [FoFa API] 请求失败 (HTTP {r.status_code})")

    # 2. 尝试 FoFa Web 内部签名 API (Fofa-hack 方案: RSA 签名 + Authorization Token)
    token = cfg.get("token") or ""
    if token:
        signed_targets = _search_fofa_signed_web_api(
            qbase64=qbase64,
            token=token,
            page=page,
            size=page_size,
            proxy=proxy,
            timeout=timeout
        )
        if signed_targets:
            return signed_targets

    if not token and not cfg.get("key"):
        print("      [FoFa] 提示: 未配置有效 key 或 token，跳过 FoFa 检索")
        return []

    # 3. Web HTML 兜底提取 (如果签名接口异常)
    headers = {"User-Agent": DEFAULT_UA}
    cookies = {}
    if token:
        headers["Authorization"] = token
        cookies["fofa_token"] = token

    url = f"https://fofa.info/result?qbase64={qbase64}&page={page}"
    resp = _make_request(url, headers=headers, cookies=cookies, proxy_url=proxy, timeout=timeout)
    if not resp:
        print("      [FoFa] 提示: 网页端接口请求超时或被安全策略拦截 (建议在 fofa_config.json 配置官方 API key)")
        return []
    if resp.status_code != 200:
        print(f"      [FoFa] 提示: 网页端响应异常 (HTTP {resp.status_code})")
        return []

    targets = _extract_nuxt_targets(resp.text)
    if not targets and "login" in resp.url.lower():
        print("      [FoFa] 提示: 网页端 Token 已失效需重新登录 (建议配置官方 API key)")
    return targets


def fetch_subscription_nodes(targets: List[str], config: Optional[Dict[str, Any]] = None,
                             max_targets: Optional[int] = None, timeout: int = 6,
                             max_nodes_per_sub: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    遍历获取各目标地址的代理订阅内容，解析并提取节点。
    使用 Clash/CFW 客户端 User-Agent 以获取最佳 YAML/Base64 订阅响应。
    当单订阅源节点数量超过上限 (默认 200) 时自动丢弃，防范公开聚合低质垃圾源干扰。
    """
    cfg = config or load_fofa_config()
    proxy = cfg.get("proxy") or None
    client_headers = {
        "User-Agent": SUBSCRIPTION_UA,
        "Accept": "*/*"
    }
    limit = max_nodes_per_sub if max_nodes_per_sub is not None else int(cfg.get("max_nodes_per_subscription") or 200)

    collected_proxies: List[Dict[str, Any]] = []
    crawl_list = targets[:max_targets] if max_targets else targets

    for idx, target in enumerate(crawl_list, 1):
        r = _make_request(target, headers=client_headers, proxy_url=proxy, timeout=timeout)
        if not r or r.status_code != 200 or len(r.text) < 20:
            continue

        try:
            nodes = load_proxies(r.text)
            if nodes:
                if limit > 0 and len(nodes) > limit:
                    print(f"      [跳过超量源] 目标 {target} 节点数 ({len(nodes)}) 超过上限 ({limit})，丢弃以防低质公开聚合源干扰")
                    continue
                # 记录来源 target URL
                for n in nodes:
                    n.setdefault("_source_target", target)
                collected_proxies.extend(nodes)
        except Exception:
            pass

    return deduplicate_and_sort_proxies(collected_proxies)


def deduplicate_and_sort_proxies(proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对抓取到的候选节点按 (type, server, port, secret) 指纹去重，
    并按协议优质顺位 (hysteria2/hy2 -> vless -> trojan -> vmess -> ss -> others) 进行保序排序。
    """
    # 协议顺位权重
    type_priority = {
        "hysteria2": 1,
        "hy2": 1,
        "hysteria": 2,
        "vless": 3,
        "trojan": 4,
        "vmess": 5,
        "ss": 6,
        "shadowsocks": 6,
        "tuic": 7,
        "anytls": 8,
    }

    sorted_raw = sorted(
        proxies,
        key=lambda p: type_priority.get(str(p.get("type", "")).lower(), 99)
    )

    seen = set()
    deduped = []
    name_counts: Dict[str, int] = {}

    for p in sorted_raw:
        ptype = str(p.get("type", "")).strip().lower()
        server = str(p.get("server", "")).strip().lower()
        port = str(p.get("port") or p.get("server_port") or "").strip()
        secret = str(p.get("password") or p.get("uuid") or p.get("auth-str") or p.get("auth") or "").strip()

        if not server or not port:
            continue

        sig = (ptype, server, port, secret)
        if sig in seen:
            continue
        seen.add(sig)

        p_clean = copy.deepcopy(p)
        raw_name = str(p_clean.get("name") or f"{ptype}_{server}_{port}").strip()

        # 避免重名冲突
        if raw_name in name_counts:
            name_counts[raw_name] += 1
            p_clean["name"] = f"{raw_name}_{name_counts[raw_name]}"
        else:
            name_counts[raw_name] = 1
            p_clean["name"] = raw_name

        deduped.append(p_clean)

    return deduped


def normalize_and_dedup_targets(targets: List[str]) -> List[str]:
    """对订阅源 URL 进行规范化并保留出现顺序去重。"""
    seen = set()
    deduped = []
    for t in targets:
        if not t or not isinstance(t, str):
            continue
        t_clean = t.strip()
        if not t_clean.startswith(('http://', 'https://')):
            continue
        try:
            u = urllib.parse.urlparse(t_clean)
            port = f":{u.port}" if u.port and u.port not in (80, 443) else ""
            path = u.path.rstrip('/')
            norm_key = f"{u.scheme.lower()}://{u.hostname.lower()}{port}{path}"
            if u.query:
                norm_key += f"?{u.query}"
        except Exception:
            norm_key = t_clean.lower().rstrip('/')

        if norm_key not in seen:
            seen.add(norm_key)
            deduped.append(t_clean)
    return deduped


def search_all_targets(query_or_preset: Optional[str] = None,
                       config: Optional[Dict[str, Any]] = None,
                       engine: str = "all",
                       page: int = 1,
                       page_size: int = 80,
                       quake_query: Optional[str] = None) -> Tuple[List[str], Dict[str, int]]:
    """
    协同检索 FoFa 与 360 Quake 订阅源目标地址。
    具备高容错性：单一引擎失败或未配置凭证不会阻断整体任务，
    并将两边检索到的目标订阅地址进行全局去重。
    返回: (去重后的目标URL列表, 各引擎匹配统计)
    """
    cfg = config or load_fofa_config()
    engine_mode = str(engine or "all").lower()
    all_targets: List[str] = []
    stats = {"fofa": 0, "quake": 0, "deduped": 0}

    # 1. FoFa 检索
    if engine_mode in ("all", "fofa"):
        try:
            fofa_q = resolve_query(query_or_preset, cfg.get("default_query"))
            f_targets = search_fofa_targets(fofa_q, config=cfg, page=page, page_size=page_size)
            stats["fofa"] = len(f_targets)
            all_targets.extend(f_targets)
            print(f"      [FoFa] 检索完成，发现 {len(f_targets)} 个候选目标源")
        except Exception as e:
            print(f"      [FoFa] 检索异常 (不影响其他引擎): {e}")

    # 2. 360 Quake 检索
    if engine_mode in ("all", "quake"):
        try:
            from core.quake import search_quake_targets
            q_query = quake_query or query_or_preset
            q_targets = search_quake_targets(q_query, config=cfg, page=page, page_size=page_size)
            stats["quake"] = len(q_targets)
            all_targets.extend(q_targets)
        except Exception as e:
            print(f"      [Quake] 检索异常 (不影响其他引擎): {e}")

    deduped = normalize_and_dedup_targets(all_targets)
    stats["deduped"] = len(deduped)

    if engine_mode == "all" and (stats["fofa"] > 0 or stats["quake"] > 0):
        dup_count = (stats["fofa"] + stats["quake"]) - len(deduped)
        print(f"      [测绘聚合] FoFa({stats['fofa']}) + Quake({stats['quake']}) -> 去重后共 {len(deduped)} 个独立目标源 (去重 {dup_count} 个重合源)")

    return deduped, stats


def search_and_fetch_proxies(query_or_preset: Optional[str] = None,
                             config_path: Optional[str] = None,
                             max_targets: Optional[int] = None,
                             page: int = 1,
                             page_size: int = 80,
                             max_nodes_per_sub: Optional[int] = None,
                             engine: str = "all",
                             quake_query: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    高阶统一调用入口：搜索 FoFa 与 Quake 订阅目标并在线提取、去重节点。
    返回: (去重节点列表, 发现的目标URL列表)
    """
    cfg = load_fofa_config(config_path)
    targets, _ = search_all_targets(
        query_or_preset=query_or_preset,
        config=cfg,
        engine=engine,
        page=page,
        page_size=page_size,
        quake_query=quake_query
    )
    if not targets:
        return [], []
    proxies = fetch_subscription_nodes(
        targets,
        config=cfg,
        max_targets=max_targets,
        timeout=int(cfg.get("timeout") or 8),
        max_nodes_per_sub=max_nodes_per_sub
    )
    return proxies, targets
