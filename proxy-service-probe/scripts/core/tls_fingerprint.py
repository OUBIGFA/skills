# -*- coding: utf-8 -*-
"""自适应双模浏览器 TLS/JA4 指纹伪装与流式两阶段探测底座。

支持两种通信内核：
- Mode A (增强仿真模式): 优先加载 curl_cffi，模拟真实 Chrome 131 BoringSSL JA4 与 HTTP/2 握手指纹；
- Mode B (零依赖回退模式): 在无 curl_cffi 时使用内置 ssl 模块深度调优的 SSLContext (Cipher 乱序 + ALPN + Chrome 完整 Client Hints)。

两阶段流式截断机制：
- 阶段一：毫秒级响应头短路拦截 (0 KB Body 下载)，命中 cf-mitigated: challenge 或验证码重定向立即中断连接；
- 阶段二：流式截断下载 (最多仅读取前 16KB 响应载荷)，防止大网页下载拖慢全并发流水线。
"""
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Chrome 131 默认客户端提示头与标准化指纹头
CHROME_CLIENT_HINTS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}

# Chrome 131 标准加密套件排序
CHROME_CIPHER_SUITES = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:AES128-SHA:AES256-SHA"
)

# 探测 curl_cffi 可用性
_HAS_CURL_CFFI = False
try:
    import curl_cffi.requests  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False


def is_curl_cffi_available() -> bool:
    """返回当前环境是否支持 curl_cffi 原生指纹仿真。"""
    return _HAS_CURL_CFFI


def create_tuned_ssl_context() -> ssl.SSLContext:
    """构建调优的标准库 SSLContext，注入 Chrome Cipher 套件序与 ALPN 协商。"""
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers(CHROME_CIPHER_SUITES)
    except Exception:
        pass
    try:
        ctx.set_alpn_protocols(["h2", "http/1.1"])
    except Exception:
        pass
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


class TunedHTTPAdapter(urllib.request.HTTPSHandler):
    """装载调优 SSLContext 的自定义 HTTPSHandler。"""

    def __init__(self, context: Optional[ssl.SSLContext] = None):
        super().__init__(context=context or create_tuned_ssl_context())


class StreamingResponse:
    """统一的流式探测响应载荷。"""

    def __init__(
        self,
        status_code: int,
        headers: Dict[str, str],
        body_bytes: bytes,
        engine: str,
        short_circuited: bool = False
    ):
        self.status_code = status_code
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body_bytes = body_bytes
        self.engine = engine
        self.short_circuited = short_circuited
        self._text_cached: Optional[str] = None

    @property
    def text(self) -> str:
        if self._text_cached is None:
            self._text_cached = self.body_bytes.decode("utf-8", errors="ignore")
        return self._text_cached

    @property
    def is_cf_mitigated(self) -> bool:
        """是否命中 Cloudflare 官方质询响应头 cf-mitigated: challenge。"""
        return self.headers.get("cf-mitigated", "").strip().lower() == "challenge"

    @property
    def is_google_sorry(self) -> bool:
        """是否被 Google 验证码重定向拦截 (Location: .../sorry/index)。"""
        loc = self.headers.get("location", "").lower()
        return "/sorry/" in loc or self.status_code == 429

    def json(self) -> Any:
        """尝试将截断读取的载荷解析为 JSON。"""
        return json.loads(self.text)


def _format_proxy_for_curl(proxy: Union[str, Dict[str, str]]) -> Optional[str]:
    """将各类代理表示法统一为 curl_cffi 接受的代理 URL 格式。"""
    if not proxy:
        return None
    if isinstance(proxy, str):
        return proxy
    if isinstance(proxy, dict):
        return proxy.get("https") or proxy.get("http") or proxy.get("all")
    return None


def _format_proxy_for_urllib(proxy: Union[str, Dict[str, str]]) -> Dict[str, str]:
    """将各类代理表示法统一为 urllib 接受的 proxies 字典。"""
    if not proxy:
        return {}
    if isinstance(proxy, str):
        return {"http": proxy, "https": proxy}
    if isinstance(proxy, dict):
        return dict(proxy)
    return {}


def request_streaming(
    method: str,
    url: str,
    proxy: Optional[Union[str, Dict[str, str]]] = None,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Union[bytes, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 4.0,
    max_body_bytes: int = 16384,
    prefer_curl_cffi: bool = True
) -> StreamingResponse:
    """
    两阶段流式请求统一执行器。

    执行流程：
    1. 优先使用 curl_cffi Chrome 131 仿真模式发起流式请求；
    2. 检查响应头：若出现 cf-mitigated: challenge 或 Google /sorry/ 重定向，直接短路截断，0 KB Body 下载；
    3. 否则读取前 max_body_bytes (默认 16KB)，即刻中断流式连接并返回。
    """
    req_headers = dict(CHROME_CLIENT_HINTS)
    if headers:
        req_headers.update(headers)

    body_payload: Optional[bytes] = None
    if json_data is not None:
        body_payload = json.dumps(json_data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        body_payload = data.encode("utf-8")
    elif isinstance(data, bytes):
        body_payload = data

    # Mode A: curl_cffi (Chrome 131 真实 BoringSSL / JA4 / H2 仿真)
    if prefer_curl_cffi and _HAS_CURL_CFFI:
        try:
            proxy_url = _format_proxy_for_curl(proxy)
            proxies_dict = {"http": proxy_url, "https": proxy_url} if proxy_url else None

            # 发起 stream=True 流式请求
            resp = curl_cffi.requests.request(
                method=method.upper(),
                url=url,
                headers=req_headers,
                data=body_payload,
                proxies=proxies_dict,
                timeout=timeout,
                impersonate="chrome131",
                stream=True,
                allow_redirects=False
            )

            status = resp.status_code
            resp_headers = dict(resp.headers)
            lower_headers = {k.lower(): v for k, v in resp_headers.items()}

            # 阶段一：响应头毫秒级短路判定 (0 KB Body 下载)
            if lower_headers.get("cf-mitigated") == "challenge" or "/sorry/" in lower_headers.get("location", ""):
                resp.close()
                return StreamingResponse(
                    status_code=status,
                    headers=resp_headers,
                    body_bytes=b"",
                    engine="curl_cffi:chrome131",
                    short_circuited=True
                )

            # 阶段二：读取前 max_body_bytes
            chunks = []
            bytes_read = 0
            for chunk in resp.iter_content(chunk_size=4096):
                if not chunk:
                    break
                chunks.append(chunk)
                bytes_read += len(chunk)
                if bytes_read >= max_body_bytes:
                    break
            resp.close()

            truncated_bytes = b"".join(chunks)[:max_body_bytes]
            return StreamingResponse(
                status_code=status,
                headers=resp_headers,
                body_bytes=truncated_bytes,
                engine="curl_cffi:chrome131",
                short_circuited=False
            )
        except Exception as e:
            logger.debug("curl_cffi 模式请求失败 (%s)，回退至 Tuned SSL: %s", url, e)

    # Mode B: 内置标准库 Tuned SSLContext 零依赖模式
    parsed = urllib.parse.urlsplit(url)
    proxies_dict = _format_proxy_for_urllib(proxy)
    proxy_handler = urllib.request.ProxyHandler(proxies_dict) if proxies_dict else None

    handlers = [TunedHTTPAdapter()]
    if proxy_handler:
        handlers.append(proxy_handler)

    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        url=url,
        data=body_payload,
        headers=req_headers,
        method=method.upper()
    )

    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            lower_headers = {k.lower(): v for k, v in resp_headers.items()}

            # 阶段一短路
            if lower_headers.get("cf-mitigated") == "challenge" or "/sorry/" in lower_headers.get("location", ""):
                return StreamingResponse(
                    status_code=status,
                    headers=resp_headers,
                    body_bytes=b"",
                    engine="tuned_ssl",
                    short_circuited=True
                )

            # 阶段二截断读取
            raw_body = resp.read(max_body_bytes)
            return StreamingResponse(
                status_code=status,
                headers=resp_headers,
                body_bytes=raw_body,
                engine="tuned_ssl",
                short_circuited=False
            )
    except urllib.error.HTTPError as e:
        resp_headers = dict(e.headers) if hasattr(e, "headers") else {}
        lower_headers = {k.lower(): v for k, v in resp_headers.items()}
        short_circuited = lower_headers.get("cf-mitigated") == "challenge"
        raw_body = b"" if short_circuited else e.read(max_body_bytes)
        return StreamingResponse(
            status_code=e.code,
            headers=resp_headers,
            body_bytes=raw_body,
            engine="tuned_ssl",
            short_circuited=short_circuited
        )
