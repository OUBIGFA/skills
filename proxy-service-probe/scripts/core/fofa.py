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
import hashlib
import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any

import requests
import urllib3
import yaml

try:
    from core.egress_geo import FOCUS_REGIONS, classify_candidate_focus, summarize_candidate_focus
    from core.parsers import load_proxies
    from core.sub_filter import check_subscription_non_long_term, filter_subscription_batch
except ImportError:
    try:
        from .egress_geo import FOCUS_REGIONS, classify_candidate_focus, summarize_candidate_focus
        from .parsers import load_proxies
        from .sub_filter import check_subscription_non_long_term, filter_subscription_batch
    except ImportError:
        from scripts.core.egress_geo import FOCUS_REGIONS, classify_candidate_focus, summarize_candidate_focus
        from scripts.core.parsers import load_proxies
        from scripts.core.sub_filter import check_subscription_non_long_term, filter_subscription_batch

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
    # 官方优先主力：家宽/双ISP/高纯净度过盾优质订阅 (优先检索 Hinet/HKT/双ISP/住宅/商业计费特征)
    "residential": '(server="nginx" || server="caddy" || server="cloudflare" || server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html" && (body="家宽" || body="住宅" || body="双ISP" || body="Hinet" || body="HKT" || body="ISP")',
    "isp": '(server="nginx" || server="caddy" || server="cloudflare" || server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html" && (body="家宽" || body="住宅" || body="双ISP" || body="Hinet" || body="HKT" || body="ISP")',
    "home": '(server="nginx" || server="caddy" || server="cloudflare" || server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html" && (body="家宽" || body="住宅" || body="双ISP" || body="Hinet" || body="HKT" || body="ISP")',
    # 方案二：工业级反代 + 动态订阅计量特征 (实测存活率高，不写死日期)
    "recommended": '(server="nginx" || server="caddy" || server="cloudflare" || server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html"',
    # 方案三：动态计费特征 + 协议断言 (长期托管订阅源)
    "billing": '(header="upload=" && header="download=" && header="total=") && body="proxies:" && body!="<html"',
    # 方案四：VLESS / Reality 节点专项订阅
    "vless": 'body="proxies:" && body="type: vless" && status_code="200" && body!="<html"',
    # 方案五：Hysteria 2 极速节点专项订阅
    "hy2": 'body="type: hysteria2" && body="server" && status_code="200" && body!="<html"',
    # 方案六：通用 subscription-userinfo 动态流量池
    "sub_userinfo": 'header="subscription-userinfo" && status_code="200"',
    # 方案七：多协议综合型搜索
    "comprehensive": 'status_code="200" && body!="<html" && (body="proxies:" || body="\\"outbounds\\":" || (header="text/plain" && (body="dm1lc3M6" || body="c3M6Ly" || body="dHJvamFuOi")))'
}

DEFAULT_PRESET = "residential"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
SUBSCRIPTION_UA = "ClashforWindows/0.20.39"


def get_default_config_path() -> str:
    """获取技能根目录下的 fofa_config.json 默认绝对路径。"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 从 scripts/core 向上两级到达技能根目录
    skill_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    return os.path.join(skill_root, "fofa_config.json")


def inspect_jwt_token(token: str) -> Dict[str, Any]:
    """
    检查 FoFa Web JWT 授权凭据的有效性与过期时间。
    解析 payload 中的 exp 与 username，并比对本地时间戳。
    """
    if not token or not isinstance(token, str):
        return {"valid": False, "is_jwt": False, "expired": False, "msg": "Token 为空"}
    parts = token.strip().split(".")
    if len(parts) != 3:
        return {"valid": True, "is_jwt": False, "expired": False, "msg": "非 JWT 格式凭据 (保持透传)"}
    try:
        p1 = parts[1]
        p1 += "=" * ((4 - len(p1) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p1.encode()).decode("utf-8", errors="replace"))
        exp = payload.get("exp")
        username = payload.get("username", "")
        uid = payload.get("id") or payload.get("mid") or ""
        if exp:
            exp_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
            now = time.time()
            if now > exp:
                return {
                    "valid": False,
                    "is_jwt": True,
                    "expired": True,
                    "username": username,
                    "uid": uid,
                    "exp": exp,
                    "exp_dt": exp_dt,
                    "msg": f"Token 已于 {exp_dt} 过期"
                }
            return {
                "valid": True,
                "is_jwt": True,
                "expired": False,
                "username": username,
                "uid": uid,
                "exp": exp,
                "exp_dt": exp_dt,
                "msg": f"Token 有效 (将于 {exp_dt} 到期)"
            }
        return {"valid": True, "is_jwt": True, "expired": False, "username": username, "uid": uid, "msg": "JWT 无 exp 限制"}
    except Exception as e:
        return {"valid": False, "is_jwt": True, "expired": False, "msg": f"JWT 解析失败: {e}"}


def load_fofa_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 FoFa 配置文件。
    优先读取传入的 config_path，未指定则读取技能主目录下的 fofa_config.json。
    支持 base_url 镜像/中转配置 (参考 fofatoto)，
    支持 tokens 多 Token 轮询列表 (参考 Fofa-hack / fofa-auto)，
    同时支持系统环境变量 (FOFA_TOKEN, FOFA_KEY, FOFA_EMAIL, FOFA_BASE_URL, FOFA_PROXY) 进行运行时覆盖。
    """
    path = config_path or get_default_config_path()
    config: Dict[str, Any] = {
        "base_url": "https://fofa.info",
        "token": "",
        "tokens": [],
        "email": "",
        "key": "",
        "quake_key": "",
        "proxy": "",
        "page_size": 80,
        "timeout": 12,
        "max_nodes_per_subscription": 300,
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
    if os.environ.get("FOFA_BASE_URL"):
        config["base_url"] = os.environ["FOFA_BASE_URL"]
    if os.environ.get("FOFA_TOKEN"):
        config["token"] = os.environ["FOFA_TOKEN"]
    if os.environ.get("FOFA_KEY"):
        config["key"] = os.environ["FOFA_KEY"]
    if os.environ.get("FOFA_EMAIL"):
        config["email"] = os.environ["FOFA_EMAIL"]
    elif os.environ.get("FOFA_USER"):
        config["email"] = os.environ["FOFA_USER"]
    if os.environ.get("FOFA_PASSWORD"):
        config["password"] = os.environ["FOFA_PASSWORD"]
    elif os.environ.get("FOFA_PASS"):
        config["password"] = os.environ["FOFA_PASS"]
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

    # 解析 account 字典配置
    if isinstance(config.get("account"), dict):
        if not config.get("email"):
            config["email"] = config["account"].get("username") or config["account"].get("email") or ""
        if not config.get("password"):
            config["password"] = config["account"].get("password") or ""

    # 规范化 tokens_list 列表以支持多账号轮流请求
    tokens_list: List[str] = []
    if isinstance(config.get("tokens"), list):
        for t in config["tokens"]:
            if isinstance(t, str) and t.strip() and t.strip() not in tokens_list:
                tokens_list.append(t.strip())
    raw_token = config.get("token")
    if isinstance(raw_token, str) and raw_token.strip():
        for t in re.split(r'[\r\n,]+', raw_token.strip()):
            t_clean = t.strip()
            if t_clean and t_clean not in tokens_list:
                tokens_list.append(t_clean)
    config["tokens_list"] = tokens_list

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


FOFA_AES_PASS = "fofa-v5-secure-2025"
_CACHED_DYNAMIC_KEY = None


def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16) -> Tuple[bytes, bytes]:
    derived = b""
    prev = b""
    while len(derived) < key_len + iv_len:
        prev = hashlib.md5(prev + password + salt).digest()
        derived += prev
    return derived[:key_len], derived[key_len:key_len + iv_len]


def _aes_decrypt_openssl(b64data: str, passphrase: str) -> str:
    raw = base64.b64decode(b64data)
    if raw[:8] != b"Salted__":
        raise ValueError("not salted openssl format")
    salt, ciphertext = raw[8:16], raw[16:]
    key, iv = _evp_bytes_to_key(passphrase.encode(), salt)
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.Util.Padding import unpad
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8")
    except Exception:
        pass
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8")
    except Exception:
        return ""


def get_fofa_web_private_key(proxy_url: Optional[str] = None, timeout: int = 8) -> str:
    """
    获取 FoFa Web API 请求签名的 RSA 私钥。
    优先返回内置经过验证的 RSA 私钥；若内置密钥不可用或 FoFa 轮换了密钥，
    自动从 https://fofa.info/ 主页动态获取加密的 apiKey 并解密 (参考 feiwell/fofa-auto 实现)。
    """
    global _CACHED_DYNAMIC_KEY
    if _CACHED_DYNAMIC_KEY:
        return _CACHED_DYNAMIC_KEY

    # 优先测试内置私钥是否可用
    if FOFA_WEB_PRIVATE_KEY:
        _CACHED_DYNAMIC_KEY = FOFA_WEB_PRIVATE_KEY
        return FOFA_WEB_PRIVATE_KEY

    # 动态抓取与解密备选
    try:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        headers = {"User-Agent": DEFAULT_UA}
        r = requests.get("https://fofa.info/", headers=headers, proxies=proxies, timeout=timeout, verify=False)
        if r.status_code == 200:
            m = re.search(r'apiKey[:\s]*"([^"]+)"', r.text)
            if m:
                pem = _aes_decrypt_openssl(m.group(1), FOFA_AES_PASS)
                if pem and "BEGIN RSA PRIVATE KEY" in pem:
                    _CACHED_DYNAMIC_KEY = pem
                    return pem
    except Exception:
        pass

    return FOFA_WEB_PRIVATE_KEY


def _sign_fofa_web_message(message: str, private_key_pem: Optional[str] = None) -> str:
    """
    对 FoFa Web API 请求参数执行 RSA-SHA256 PKCS1_v1_5 签名。
    算法与签名私钥来自活跃开源项目 Fofa-hack (Cl0udG0d/Fofa-hack) 及 fofa-auto (feiwell/fofa-auto)，
    通过逆向 Web 端签名协议调用官方 api.fofa.info 接口，
    直接绕过 /result 页面被安全策略/WAF挂起(Tarpit)的问题。
    """
    pem_str = private_key_pem or get_fofa_web_private_key()
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        key = load_pem_private_key(pem_str.encode('utf-8'), password=None)
        sig = key.sign(message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode('utf-8')
    except Exception:
        pass

    try:
        from Cryptodome.Signature import PKCS1_v1_5
        from Cryptodome.Hash import SHA256
        from Cryptodome.PublicKey import RSA
        priv_key = RSA.importKey(pem_str)
        h = SHA256.new(message.encode('utf-8'))
        return base64.b64encode(PKCS1_v1_5.new(priv_key).sign(h)).decode('utf-8')
    except Exception:
        pass

    try:
        from Crypto.Signature import pkcs1_15
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA
        priv_key = RSA.import_key(pem_str)
        h = SHA256.new(message.encode('utf-8'))
        return base64.b64encode(pkcs1_15.new(priv_key).sign(h)).decode('utf-8')
    except Exception:
        return ""


def _search_fofa_signed_web_api(qbase64: str, token: str, page: int = 1, size: int = 50,
                                proxy: Optional[str] = None, timeout: int = 12) -> Tuple[List[str], Optional[str]]:
    """
    通过 api.fofa.info 内部签名接口执行检索，直接获取 JSON 格式资产列表。
    单页上限为 50 条 (未付费/个人版 Web Token 超过 50 条服务端会返回 820004 限制)。
    返回: (targets, error_msg)
    """
    token_clean = token.strip()
    if not token_clean:
        return [], "Token 为空"

    jwt_info = inspect_jwt_token(token_clean)
    if jwt_info.get("expired"):
        user_desc = f" (用户: {jwt_info['username']})" if jwt_info.get("username") else ""
        err = f"Web Token{user_desc} 已于 {jwt_info['exp_dt']} 过期"
        print(f"      [FoFa Web] 警告: {err}！")
        return [], err

    ts = int(time.time() * 1000)
    fetch_size = min(int(size or 50), 50)
    message = f"fullfalsepage{page}qbase64{qbase64}size{fetch_size}ts{ts}"
    sign = _sign_fofa_web_message(message)
    if not sign:
        return [], "RSA 签名生成失败"

    url = (f"https://api.fofa.info/v1/search?qbase64={urllib.parse.quote(qbase64)}"
           f"&full=false&page={page}&size={fetch_size}&ts={ts}&sign={urllib.parse.quote(sign)}"
           f"&app_id={FOFA_WEB_APP_ID}")

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json, text/plain, */*",
        "Authorization": token_clean,
        "Cookie": f"fofa_token={token_clean}",
        "X-Fofa-Timezone": "Asia/Shanghai"
    }

    resp = _make_request(url, headers=headers, proxy_url=proxy, timeout=timeout)
    if not resp:
        return [], "请求超时或网络不可达"
    if resp.status_code != 200:
        return [], f"HTTP 状态码异常 ({resp.status_code})"

    try:
        data = resp.json()
        code = data.get("code")
        if code == 0 and "data" in data and isinstance(data["data"], dict):
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
            return targets, None
        else:
            msg = data.get("message") or str(data)
            print(f"      [FoFa Web] 检索提示 [代码 {code}]: {msg}")
            if code == -23 or ("Token" in msg and "失效" in msg):
                print("      [FoFa Web] 提示: 网页端 Token 已失效，请在浏览器登录 fofa.info 复制最新的 Authorization Token 或配置官方 API Key")
            elif code == -3000 or "IP异常" in msg:
                print("      [FoFa Web] 提示: 当前代理/IP触发了 FoFa 未登录风控限制，需配置有效账号 Token 或官方 API Key")
            return [], msg
    except Exception as e:
        return [], f"解析 JSON 响应异常: {e}"


def search_fofa_targets(query: str, config: Optional[Dict[str, Any]] = None,
                        page: int = 1, page_size: int = 80) -> List[str]:
    """
    使用 FoFa 搜索语法检索在线订阅源目标地址。
    优先调用官方 API Key (若配置，支持自定义 base_url 与正确 URL 编码)；
    次优调用 FoFa Web 内部签名 API (结合 RSA 签名与 Authorization Token，支持多 Token 轮询)；
    保底尝试 Nuxt 网页资产解析 (仅在非确定性 Token 失效下执行，设 4s 短超时防 Tarpit 挂起)。
    """
    cfg = config or load_fofa_config()
    actual_query = resolve_query(query, cfg.get("default_query"))
    qbase64 = base64.b64encode(actual_query.encode("utf-8")).decode("utf-8")
    proxy = cfg.get("proxy") or None
    timeout = int(cfg.get("timeout") or 12)
    base_url = (cfg.get("base_url") or "https://fofa.info").rstrip("/")

    # 1. 尝试官方 API (如果配置了 key)
    if cfg.get("key"):
        email_arg = f"email={urllib.parse.quote(cfg['email'], safe='')}&" if cfg.get("email") else ""
        quoted_key = urllib.parse.quote(cfg['key'], safe='')
        quoted_qbase64 = urllib.parse.quote(qbase64, safe='')
        api_url = f"{base_url}/api/v1/search/all?{email_arg}key={quoted_key}&qbase64={quoted_qbase64}&page={page}&size={page_size}&fields=ip,port,host,link"
        r = _make_request(api_url, headers={"User-Agent": DEFAULT_UA}, proxy_url=proxy, timeout=timeout)
        if r and r.status_code == 200:
            try:
                data = r.json()
                if data.get("error"):
                    errmsg = data.get("errmsg", "未知错误")
                    print(f"      [FoFa API] 检索失败: {errmsg}")
                elif "results" in data:
                    targets = []
                    for row in data["results"]:
                        if isinstance(row, list) and len(row) >= 4:
                            ip, port, host, link = row[0], row[1], row[2], row[3]
                            t = link or (f"https://{host}" if str(port) == "443" else f"http://{ip}:{port}")
                            if t and t not in targets:
                                targets.append(t)
                        elif isinstance(row, str) and row.strip():
                            t = row.strip()
                            if t and t not in targets:
                                targets.append(t)
                    if targets:
                        return targets
            except Exception:
                pass
        elif r and r.status_code != 200:
            print(f"      [FoFa API] 请求失败 (HTTP {r.status_code})")

    # 2. 尝试 FoFa Web 内部签名 API (支持多 Token 轮询与到期自动续期)
    tokens = cfg.get("tokens_list") or []
    if not tokens and cfg.get("token"):
        tokens = [cfg["token"]]

    # 检查是否存在未过期的可用 Token；若全部过期或缺失，自动尝试通过配置的账号密码续期
    has_valid_jwt = any(
        inspect_jwt_token(t).get("valid") and not inspect_jwt_token(t).get("expired")
        for t in tokens
    )
    if not has_valid_jwt and not cfg.get("key"):
        raw_email = str(cfg.get("email") or (cfg.get("account") or {}).get("username") or "").strip()
        raw_pwd = str(cfg.get("password") or (cfg.get("account") or {}).get("password") or "").strip()
        if raw_email and raw_pwd:
            ok_refresh, refresh_msg = ensure_fofa_token(
                cfg,
                auto_login=True,
                headless=bool(cfg.get("headless", False)),
                timeout=int(cfg.get("login_timeout") or 90),
            )
            if ok_refresh:
                print(f"      [FoFa Auth] {refresh_msg}")
                tokens = cfg.get("tokens_list") or ([cfg["token"]] if cfg.get("token") else [])
            else:
                print(f"      [FoFa Auth] 提示: {refresh_msg}")

    had_expired_token = False
    need_force_refresh = False
    if tokens:
        for idx, tok in enumerate(tokens, 1):
            if len(tokens) > 1:
                print(f"      [FoFa Web] 正在使用第 {idx}/{len(tokens)} 个 Token 检索...")
            targets, err = _search_fofa_signed_web_api(
                qbase64=qbase64,
                token=tok,
                page=page,
                size=page_size,
                proxy=proxy,
                timeout=timeout
            )
            if targets:
                return targets
            if err and ("过期" in err or "失效" in err):
                had_expired_token = True
                if "失效" in err:
                    need_force_refresh = True

    # 若 Token 未过本地 exp 但被服务端判定失效 (-23)，且配置了账号密码，自动触发一次强制续期并重试
    if need_force_refresh and not cfg.get("key"):
        raw_email = str(cfg.get("email") or (cfg.get("account") or {}).get("username") or "").strip()
        raw_pwd = str(cfg.get("password") or (cfg.get("account") or {}).get("password") or "").strip()
        if raw_email and raw_pwd:
            ok_refresh, refresh_msg = ensure_fofa_token(
                cfg,
                auto_login=True,
                headless=bool(cfg.get("headless", False)),
                timeout=int(cfg.get("login_timeout") or 90),
                force_refresh=True,
            )
            if ok_refresh and cfg.get("token"):
                print(f"      [FoFa Auth] {refresh_msg}，正在使用新 Token 重试检索...")
                targets, err = _search_fofa_signed_web_api(
                    qbase64=qbase64,
                    token=cfg["token"],
                    page=page,
                    size=page_size,
                    proxy=proxy,
                    timeout=timeout
                )
                if targets:
                    return targets
                had_expired_token = bool(err and ("过期" in err or "失效" in err))

    if not tokens and not cfg.get("key"):
        print("      [FoFa] 提示: 未配置有效 key 或 token，跳过 FoFa 检索")
        return []

    # 3. Web HTML 兜底提取
    # 注意：如果已明确出现 Token 过期或失效，绝不发起 /result 页面请求 (避免 Cloudflare WAF Tarpit 漫长假死挂起)
    if had_expired_token:
        print("      [FoFa] 提示: 因 Web Token 已过期失效，已自动跳过 /result 页面兜底请求 (防 Cloudflare 假死挂起)")
        return []

    headers = {"User-Agent": DEFAULT_UA}
    cookies = {}
    if tokens:
        headers["Authorization"] = tokens[0]
        cookies["fofa_token"] = tokens[0]

    url = f"{base_url}/result?qbase64={urllib.parse.quote(qbase64)}&page={page}"
    quick_timeout = min(timeout, 4)
    resp = _make_request(url, headers=headers, cookies=cookies, proxy_url=proxy, timeout=quick_timeout)
    if not resp:
        print("      [FoFa] 提示: 网页端接口请求超时或被安全策略拦截 (建议更新 Token 或配置官方 API key)")
        return []
    if resp.status_code != 200:
        print(f"      [FoFa] 提示: 网页端响应异常 (HTTP {resp.status_code})")
        return []

    targets = _extract_nuxt_targets(resp.text)
    if not targets and "login" in resp.url.lower():
        print("      [FoFa] 提示: 网页端 Token 已失效需重新登录 (建议配置官方 API key)")
    return targets


def check_fofa_auth(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    凭据健康与鉴权状态诊断工具。
    依次检测 FoFa 官方 API Key、Web Token 以及 360 Quake Token 的有效性、到期状态与可用额度。
    """
    cfg = config or load_fofa_config()
    proxy = cfg.get("proxy") or None
    report = {
        "fofa_api": {"status": "unconfigured", "msg": "未配置"},
        "fofa_web": {"status": "unconfigured", "msg": "未配置", "tokens": []},
        "quake": {"status": "unconfigured", "msg": "未配置"}
    }

    # 1. 检查 FoFa 官方 API Key
    key = str(cfg.get("key") or "").strip()
    if key:
        base_url = (cfg.get("base_url") or "https://fofa.info").rstrip("/")
        quoted_key = urllib.parse.quote(key, safe="")
        info_url = f"{base_url}/api/v1/info/my?key={quoted_key}"
        try:
            r = _make_request(info_url, headers={"User-Agent": DEFAULT_UA}, proxy_url=proxy, timeout=8)
            if r and r.status_code == 200:
                data = r.json()
                if not data.get("error"):
                    email = data.get("email", "")
                    vip = data.get("vip_level", 0)
                    fcoin = data.get("fcoin", 0)
                    report["fofa_api"] = {
                        "status": "valid",
                        "email": email,
                        "vip_level": vip,
                        "fcoin": fcoin,
                        "msg": f"有效 (邮箱: {email}, VIP等级: {vip}, F币: {fcoin})"
                    }
                else:
                    report["fofa_api"] = {
                        "status": "invalid",
                        "msg": f"无效 ({data.get('errmsg', '未知错误')})"
                    }
            else:
                report["fofa_api"] = {"status": "error", "msg": f"请求失败 (HTTP {r.status_code if r else '超时'})"}
        except Exception as e:
            report["fofa_api"] = {"status": "error", "msg": f"检测异常: {e}"}

    # 2. 检查 FoFa Web Tokens
    tokens = cfg.get("tokens_list") or []
    if not tokens and cfg.get("token"):
        tokens = [cfg["token"]]

    if tokens:
        tokens_report = []
        all_expired = True
        any_valid = False
        for idx, tok in enumerate(tokens, 1):
            info = inspect_jwt_token(tok)
            t_res = {"index": idx, "is_jwt": info.get("is_jwt", False), "username": info.get("username", "")}
            if info.get("expired"):
                t_res["status"] = "expired"
                t_res["msg"] = f"已于 {info.get('exp_dt')} 过期"
            elif not info.get("is_jwt"):
                t_res["status"] = "unknown"
                t_res["msg"] = "非标准 JWT，保持直接调用"
                all_expired = False
                any_valid = True
            else:
                t_res["status"] = "valid_jwt"
                t_res["msg"] = f"有效 (将于 {info.get('exp_dt')} 到期)"
                all_expired = False
                any_valid = True
            tokens_report.append(t_res)

        overall_status = "valid" if any_valid else ("expired" if all_expired else "invalid")
        overall_msg = "存在可用 Token" if any_valid else "所有 Token 均已过期"
        report["fofa_web"] = {
            "status": overall_status,
            "msg": overall_msg,
            "tokens": tokens_report
        }

    # 4. 检查 360 Quake Key
    quake_key = str(cfg.get("quake_key") or "").strip()
    if quake_key:
        try:
            headers = {"X-QuakeToken": quake_key}
            r = _make_request("https://quake.360.net/api/v3/user/info", headers=headers, proxy_url=proxy, timeout=8)
            if r and r.status_code == 200:
                data = r.json()
                if data.get("code") == 0 and "data" in data:
                    user_data = data["data"]
                    user = user_data.get("user") or {}
                    username = user.get("username") or user.get("email") or "Quake用户"
                    month_credit = user_data.get("month_remaining_credit", 0)
                    constant_credit = user_data.get("constant_credit", 0)
                    report["quake"] = {
                        "status": "valid",
                        "username": username,
                        "month_credit": month_credit,
                        "constant_credit": constant_credit,
                        "msg": f"有效 (用户: {username}, 月度剩余: {month_credit}, 永久额度: {constant_credit})"
                    }
                else:
                    report["quake"] = {"status": "invalid", "msg": f"无效 ({data.get('message', '未知错误')})"}
            else:
                report["quake"] = {"status": "error", "msg": f"请求失败 (HTTP {r.status_code if r else '超时'})"}
        except Exception as e:
            report["quake"] = {"status": "error", "msg": f"检测异常: {e}"}

    # 5. 检查 FoFa 自动登录账号凭据
    raw_email = str(cfg.get("email") or "").strip()
    raw_pwd = str(cfg.get("password") or "").strip()
    is_ph = any(p in raw_email.lower() for p in ("your_", "example.com", "placeholder", "your-", "<your")) or \
            any(p in raw_pwd.lower() for p in ("your_", "placeholder", "your-", "<your"))
    has_email = bool(raw_email) and not is_ph
    has_pwd = bool(raw_pwd) and not is_ph

    if has_email and has_pwd:
        report["fofa_account"] = {
            "status": "configured",
            "email": raw_email,
            "msg": f"已配置 (账号: {raw_email}, 支持一键/到期自动登录续期)"
        }
    elif has_email:
        report["fofa_account"] = {
            "status": "partial",
            "email": raw_email,
            "msg": f"仅配置账号 ({raw_email})，未配置密码"
        }
    elif is_ph:
        report["fofa_account"] = {
            "status": "unconfigured",
            "msg": "当前为模板占位符，请在 fofa_config.json 的 account 中替换为您真实的账号密码"
        }
    else:
        report["fofa_account"] = {
            "status": "unconfigured",
            "msg": "未配置 (可在 fofa_config.json 的 email/password 或 account 字段配置)"
        }

    return report


def ensure_fofa_token(config: Dict[str, Any], auto_login: bool = True,
                      headless: bool = False, timeout: int = 60,
                      force_refresh: bool = False) -> Tuple[bool, str]:
    """
    检查配置中的 Token 是否仍然有效。
    若已过期或缺失（或指定 force_refresh=True），且启用了 auto_login 并存在账号凭据（或可交互登录），
    自动调度 fofa_login 模块启动浏览器执行登录，刷新并回写最新有效 Token 到配置文件。
    返回: (是否拥有可用 Token, 状态描述消息)
    """
    tokens = config.get("tokens_list") or []
    if not tokens and config.get("token"):
        tokens = [config["token"]]

    # 1. 检查现有 Token 是否存在有效项
    if not force_refresh:
        for tok in tokens:
            info = inspect_jwt_token(tok)
            if info.get("valid") and not info.get("expired"):
                return True, f"Token 有效 (用户: {info.get('username') or '未知'}, 将于 {info.get('exp_dt')} 到期)"

    if not auto_login:
        return False, "FoFa Web Token 已过期或未配置，未启用自动续期"

    # 2. 检查是否具备自动登录条件 (兼容顶层 email/password 与 account 字典，过滤占位符)
    acc = config.get("account") if isinstance(config.get("account"), dict) else {}
    raw_email = str(config.get("email") or acc.get("username") or acc.get("email") or "").strip()
    raw_pwd = str(config.get("password") or acc.get("password") or "").strip()
    is_ph = any(p in raw_email.lower() for p in ("your_", "example.com", "placeholder", "your-", "<your")) or \
            any(p in raw_pwd.lower() for p in ("your_", "placeholder", "your-", "<your"))
    has_creds = bool(raw_email and raw_pwd) and not is_ph

    if not has_creds and headless:
        return False, "无可用 Token 且未配置登录账号密码，在无头模式下无法执行交互续期"

    try:
        from core.fofa_login import login_fofa_and_extract_token
    except Exception as e:
        return False, f"无法载入自动登录模块: {e}"

    cfg_path = config.get("_config_source") or get_default_config_path()
    proxy = config.get("proxy")

    print("[FoFa Auth] 检测到当前 FoFa Web Token 已过期或未配置，正在尝试自动续期刷新...")
    login_kwargs: Dict[str, Any] = {
        "email": raw_email,
        "password": raw_pwd,
        "config_path": cfg_path,
        "proxy": proxy,
        "headless": headless,
        "timeout": timeout,
        "save_to_config": True,
    }
    if force_refresh:
        login_kwargs["force_refresh"] = True
    ok, new_token, msg = login_fofa_and_extract_token(**login_kwargs)
    if ok and new_token:
        # 同步更新内存配置对象，并剔除已过期的旧 Token
        config["token"] = new_token
        valid_rest = [
            t for t in tokens
            if t != new_token and not inspect_jwt_token(t).get("expired")
        ]
        config["tokens_list"] = [new_token] + valid_rest
        return True, f"Token 自动续期成功: {msg}"

    return False, f"Token 自动续期失败: {msg}"



def fetch_subscription_nodes(targets: List[str], config: Optional[Dict[str, Any]] = None,
                             max_targets: Optional[int] = None, timeout: int = 6,
                             max_nodes_per_sub: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    遍历获取各目标地址的代理订阅内容，解析并提取节点。
    使用 Clash/CFW 客户端 User-Agent 以获取最佳 YAML/Base64 订阅响应。
    当单订阅源节点数量超过上限 (默认 300) 时自动丢弃，防范公开聚合低质垃圾源干扰。
    """
    cfg = config or load_fofa_config()
    proxy = cfg.get("proxy") or None
    client_headers = {
        "User-Agent": SUBSCRIPTION_UA,
        "Accept": "*/*"
    }
    limit = max_nodes_per_sub if max_nodes_per_sub is not None else int(cfg.get("max_nodes_per_subscription") or 300)

    collected_proxies: List[Dict[str, Any]] = []
    crawl_list = targets[:max_targets] if max_targets else targets

    def _fetch_single(target: str) -> List[Dict[str, Any]]:
        url_reason = check_subscription_non_long_term(url=target)
        if url_reason:
            print(f"      [跳过试用/短期源] 目标 {target} ({url_reason})，整源淘汰")
            return []
        r = _make_request(target, headers=client_headers, proxy_url=proxy, timeout=timeout)
        if not r or r.status_code != 200 or len(r.text) < 20:
            return []
        sub_reason = check_subscription_non_long_term(
            url=target, headers=getattr(r, "headers", None), raw_text=r.text
        )
        if sub_reason:
            print(f"      [跳过试用/短期源] 目标 {target} ({sub_reason})，整源淘汰")
            return []
        try:
            nodes = load_proxies(r.text, filter_short_term=False)
            kept = filter_subscription_batch(nodes, f"目标 {target}", limit=limit)
            if kept:
                for n in kept:
                    n.setdefault("_source_target", target)
                return kept
        except Exception:
            pass
        return []

    workers = min(16, max(4, len(crawl_list))) if crawl_list else 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_fetch_single, t): t for t in crawl_list}
        for future in as_completed(future_map):
            try:
                res = future.result()
                if res:
                    collected_proxies.extend(res)
            except Exception:
                pass

    return deduplicate_and_sort_proxies(collected_proxies)


def deduplicate_and_sort_proxies(proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对抓取到的候选节点按 (type, server, port, secret) 指纹去重，
    并按重点地区预优先度 (HK/TW/JP/SG/US 重点线索 -> 未标地区 -> 非重点地区)
    与协议优质顺位 (hysteria2/hy2 -> vless -> trojan -> vmess -> ss -> others) 进行保序排序。
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
        key=lambda p: (
            classify_candidate_focus(p.get("name") or p.get("tag") or "")[0],
            type_priority.get(str(p.get("type", "")).lower(), 99),
        )
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


def print_candidate_focus_summary(proxies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """打印候选节点按默认重点地区（高质量 US + 高速直连 HK/TW/JP/SG）的线索分布。"""
    summary = summarize_candidate_focus(proxies)
    fc = summary["focus_counts"]
    focus_parts = ", ".join(f"{cc}:{fc.get(cc, 0)}" for cc in FOCUS_REGIONS)
    print(f"\n[+] 重点地区线索统计 (已优先排前 | 仅预排序线索，最终属地以实测为准):")
    print(f"    - 重点地区 ({focus_parts})，含家宽/专线/直连/AI 线索 {summary['quality_hint_count']} 个")
    print(f"    - 未标地区/中性 {summary['neutral_count']} 个 | 其他非重点地区 {summary['non_focus_count']} 个")
    return summary


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
