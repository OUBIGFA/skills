# -*- coding: utf-8 -*-
"""家宽真实性多因子交叉判定与反向域名 (PTR/rDNS) 专家分析模块。

精准识别以下四类 IP 形态：
- Level 1: 原生民用住宅宽带 (True Residential) -> 信誉分 >= 80 授予 🏠，< 80 授予 _ISP
- Level 2: 商用/机房双 ISP (Commercial Dual-ISP) -> 严禁 🏠，统一打标为 _ISP 后缀
- Level 3: 住宅代理池轮换 IP (Residential Proxy) -> 剥离 🏠 与 ♥️ 资格，标记高风控
- Level 4: 数据中心/机房 (Datacenter / Hosting) -> 普通机房节点，不带家宽相关标记
"""
import concurrent.futures
import re
import socket
from typing import Any, Dict, Optional, Tuple

# 典型真实民用宽带 PTR 正则匹配规则 (覆盖主流 HK/TW/JP/SG/US/KR/EU 运营商)
RESIDENTIAL_PTR_PATTERNS = [
    # 台湾 Hinet / 中华电信 / 远传 / 台湾大
    r'(?i)\.dynamic\.hinet\.net$',
    r'(?i)\.hinet-ip\.hinet\.net$',
    r'(?i)\.tfn\.net\.tw$',
    r'(?i)\.seed\.net\.tw$',
    # 香港 HKT / Netvigator / HKBN
    r'(?i)\.netvigator\.com$',
    r'(?i)\.hkbn\.net$',
    r'(?i)\.pccw\.com$',
    r'(?i)\.i-cable\.com$',
    # 日本 So-net / OCN / KDDI / SoftBank
    r'(?i)\.dynamic\..*\.so-net\.ne\.jp$',
    r'(?i)\.user\.ocn\.ne\.jp$',
    r'(?i)\.dion\.ne\.jp$',
    r'(?i)\.mesh\.ad\.jp$',
    r'(?i)\.asahi-net\.or\.jp$',
    r'(?i)\.open\.ad\.jp$',
    r'(?i)\.bbtec\.net$',
    # 美国 Comcast / Spectrum / AT&T / Verizon / Cox
    r'(?i)^cpe-.*\.cableone\.net$',
    r'(?i)^c-.*\.hsd1\..*\.comcast\.net$',
    r'(?i)\.res\.rr\.com$',
    r'(?i)\.attlocal\.net$',
    r'(?i)\.spectrum\.com$',
    r'(?i)\.verizon\.net$',
    r'(?i)\.fios\.verizon\.net$',
    r'(?i)\.cox\.net$',
    r'(?i)\.centurylink\.net$',
    # 韩国 KT / SK / LG
    r'(?i)\.kornet\.net$',
    r'(?i)\.xspeed\.hanaro\.com$',
    # 新加坡 SingNet / StarHub / M1
    r'(?i)\.singnet\.com\.sg$',
    r'(?i)\.starhub\.net\.sg$',
    r'(?i)\.m1\.com\.sg$',
    # 泛住宅民用动态标识
    r'(?i)\b(?:dynamic|dyn|cpe|dialup|broadband|dhcp|pool|res|home|dsl|cable|consumer)\b',
]

# 典型机房 / 云厂商 / 托管服务商 PTR 正则匹配规则
DATACENTER_PTR_PATTERNS = [
    r'(?i)\.compute.*\.amazonaws\.com$',
    r'(?i)\.googleusercontent\.com$',
    r'(?i)\.clients\.your-server\.de$',
    r'(?i)\.vps.*\.ovh\.net$',
    r'(?i)\.linode\.com$',
    r'(?i)\.digitalocean\.com$',
    r'(?i)\.azure\.com$',
    r'(?i)\.oraclecloud\.com$',
    r'(?i)\.vultr\.com$',
    r'(?i)\.choopa\.net$',
    r'(?i)\.cloudflare\.com$',
    r'(?i)\.leaseweb\.net$',
    r'(?i)\.datapacket\.com$',
    r'(?i)\.m247\.com$',
    r'(?i)\.clouvider\.net$',
    r'(?i)\.packetexchange\.net$',
    r'(?i)\.contaboserver\.net$',
    r'(?i)\.ipxo\.com$',
    r'(?i)\b(?:server|dedicated|hosting|vps|cloud|datacenter|colocation|transit|noc|gw|infra)\b',
]

# 核心 Eyeball / 民用宽带运营商 ASN 白名单 (ASN 纯数字)
EYEBALL_ASNS = {
    # 台湾
    3462,   # Data Communication Business Group (Chunghwa / Hinet)
    4780,   # Taiwan Fixed Network
    18049,  # Far EasTone
    # 香港
    4635,   # PCCW / HKT
    4637,   # PCCW Global
    9269,   # Hong Kong Broadband Network (HKBN)
    9304,   # HKBN
    17429,  # Hong Kong Broadband
    # 日本
    17676,  # SoftBank Corp.
    2516,   # KDDI Corporation
    4713,   # NTT Communications (OCN)
    2514,   # NTT PC Communications
    2527,   # Sony Network Communications (So-net)
    # 美国
    7922,   # Comcast Cable
    7018,   # AT&T Services
    20115,  # Charter Communications (Spectrum)
    701,    # Verizon
    10796,  # Charter
    22773,  # Cox Communications
    # 韩国
    4766,   # Korea Telecom (KT)
    9318,   # SK Broadband
    3786,   # LG Uplus
    # 新加坡
    4657,   # StarHub
    7473,   # SingNet
    17547,  # M1
    # 欧洲
    2856,   # British Telecommunications
    3320,   # Deutsche Telekom AG
    3215,   # Orange
    12322,  # Free SAS
}

# 核心 Datacenter / 云厂商 / 托管主机商 ASN 黑名单 (坚决一票否决住宅家宽)
DATACENTER_ASNS = {
    16509,  # Amazon.com (AWS)
    14061,  # DigitalOcean
    16276,  # OVH SAS
    24940,  # Hetzner Online GmbH
    20473,  # The Constant Company (Vultr / Choopa)
    13335,  # Cloudflare
    15169,  # Google LLC
    396982, # Google Cloud Platform
    8075,   # Microsoft Corporation (Azure)
    63949,  # Akamai Connected Cloud (Linode)
    45102,  # Alibaba Cloud
    13238,  # Tencent Cloud
    31898,  # Oracle Corporation
    60068,  # Datacamp Limited (CDN77)
    9009,   # M247 Europe
    202425, # IPXO LLC
    51167,  # Contabo GmbH
    49981,  # WorldStream B.V.
    46844,  # Sharktech
    212238, # Datacamp
    54600,  # PegTech
    62240,  # Clouvider
    39351,  # 31173 Services AB
}

# 常见已知民用 ISP 组织名称关键字
KNOWN_RESIDENTIAL_KEYWORDS = [
    'chunghwa', 'hinet', 'pccw', 'hkt', 'netvigator', 'hkbn', 'home broadband',
    'broadband', 'comcast', 'at&t', 'spectrum', 'charter', 'verizon', 'singnet',
    'starhub', 'kddi', 'so-net', 'softbank', 'kornet', 'deutsche telekom', 'telecom'
]


def parse_asn_number(asn_raw: Any) -> Optional[int]:
    """从各类格式 (如 'AS3462', 3462, 'AS3462 Chunghwa') 提取纯整型 ASN。"""
    if isinstance(asn_raw, int):
        return asn_raw
    if not isinstance(asn_raw, str):
        return None
    m = re.search(r'(?i)\bas?(\d+)\b', asn_raw.strip())
    return int(m.group(1)) if m else None


def resolve_ptr(ip: str, timeout: float = 1.5) -> Optional[str]:
    """执行本地反向域名解析 (rDNS/PTR)，采用线程池保护防 DNS 卡死。"""
    if not ip:
        return None

    def _lookup():
        try:
            name, _, _ = socket.gethostbyaddr(ip)
            return name
        except Exception:
            return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_lookup)
            return future.result(timeout=timeout)
    except Exception:
        return None


def match_ptr_pattern(ptr: Optional[str]) -> Tuple[bool, bool, Optional[str]]:
    """
    检查 PTR 域名是否命中住宅或机房特征。
    返回: (is_res_ptr, is_dc_ptr, matched_pattern)
    """
    if not ptr:
        return False, False, None

    for pattern in RESIDENTIAL_PTR_PATTERNS:
        if re.search(pattern, ptr):
            return True, False, pattern

    for pattern in DATACENTER_PTR_PATTERNS:
        if re.search(pattern, ptr):
            return False, True, pattern

    return False, False, None


def classify_residential(
    ip: str,
    ptr: Optional[str] = None,
    asn_raw: Any = None,
    isp_name: str = "",
    scamalytics: Optional[Dict[str, Any]] = None,
    ipinfo_flags: Optional[Dict[str, Any]] = None,
    dnsbl_hits: int = 0
) -> Dict[str, Any]:
    """
    家宽真实性四级形态交叉判定核心算法。

    判定优先级与共识规则：
    1. Level 3 住宅代理池 (Residential Proxy):
       Scamalytics 显式标记 residential_proxy == True，或 fraud_score >= 40 且有代理特征，或 DNSBL 黑名单命中 >= 1；
    2. Level 1 原生民用住宅宽带 (True Residential):
       ASN 属于已知 Eyeball 运营商，且 (PTR 明确命中动态/宽带正则 或 属于典型民用 ISP 且 Scamalytics/ipinfo 均为 non-datacenter)；
    3. Level 2 商用/机房双 ISP (Commercial Dual-ISP):
       属于 ISP 机构（或具备双 ISP/住宅属性），但处于 IDC 托管环境（如命中机房 PTR/hosting/datacenter），或缺乏原生住宅 PTR；
    4. Level 4 数据中心/机房 (Datacenter / Hosting):
       ASN 命中知名云商黑名单，或 Scamalytics/ipinfo 显式判定 datacenter == True 且无任何 ISP/双ISP 属性。
    """
    scama = scamalytics or {}
    flags = ipinfo_flags or {}
    asn_num = parse_asn_number(asn_raw)
    isp_lower = (isp_name or "").lower()

    is_res_ptr, is_dc_ptr, matched_ptr_pat = match_ptr_pattern(ptr)

    fraud_score = scama.get("fraud_score", 0)
    scama_dc = scama.get("is_datacenter")
    scama_proxy = scama.get("is_proxy")
    scama_res_proxy = scama.get("is_residential_proxy")
    ipinfo_hosting = flags.get("datacenter") or flags.get("hosting")

    is_eyeball_asn = asn_num in EYEBALL_ASNS if asn_num else False
    is_dc_asn = asn_num in DATACENTER_ASNS if asn_num else False
    is_known_res_name = any(kw in isp_lower for kw in KNOWN_RESIDENTIAL_KEYWORDS)
    is_isp_org = (
        is_known_res_name
        or flags.get("residential") is True
        or bool(re.search(r'(?i)\b(?:isp|dual[-_]?isp|residential)\b', isp_lower))
    )

    evidence: Dict[str, Any] = {
        "ip": ip,
        "ptr": ptr,
        "asn": asn_num,
        "isp": isp_name,
        "is_eyeball_asn": is_eyeball_asn,
        "is_dc_asn": is_dc_asn,
        "is_res_ptr": is_res_ptr,
        "is_dc_ptr": is_dc_ptr,
        "matched_ptr_pattern": matched_ptr_pat,
        "scamalytics_fraud_score": fraud_score,
        "scamalytics_datacenter": scama_dc,
        "scamalytics_residential_proxy": scama_res_proxy,
        "dnsbl_hits": dnsbl_hits
    }

    # 1. 优先判定 Level 3: 住宅代理池 (黑灰产僵尸网络或商用高风险轮换池)
    if scama_res_proxy is True or (scama_proxy is True and fraud_score >= 40) or (is_res_ptr and dnsbl_hits >= 2):
        return {
            "level": "Level 3: Residential Proxy",
            "is_residential": False,
            "is_dual_isp": False,
            "is_proxy_pool": True,
            "is_datacenter": bool(scama_dc or is_dc_asn),
            "can_grant_home_badge": False,
            "can_grant_isp_suffix": False,
            "summary_zh": "高风险住宅代理池 (剥离 🏠 与 ♥️ 资格)",
            "evidence": evidence
        }

    # 2. 严格判定 Level 1: 原生民用住宅宽带 (True Residential)
    # 条件：ASN 在 Eyeball 白名单或组织名明显为民用 ISP；且 PTR 具备动态家宽特征；且无机房硬性标记
    if (is_eyeball_asn or is_known_res_name) and is_res_ptr and not scama_dc and not ipinfo_hosting:
        return {
            "level": "Level 1: True Residential",
            "is_residential": True,
            "is_dual_isp": False,
            "is_proxy_pool": False,
            "is_datacenter": False,
            "can_grant_home_badge": True,  # 仅当综合信誉分 >= 80 时正式授予 🏠
            "can_grant_isp_suffix": True,  # 分数 < 80 时降级为 _ISP
            "summary_zh": "原生民用住宅宽带 (具备 🏠 授标资格)",
            "evidence": evidence
        }

    # 若是知名 Eyeball 运营商，且 Scamalytics/ipinfo 确认为非机房，且无机房 PTR，给予 Level 1
    if is_eyeball_asn and scama_dc is False and not is_dc_ptr and ipinfo_hosting is not True:
        return {
            "level": "Level 1: True Residential",
            "is_residential": True,
            "is_dual_isp": False,
            "is_proxy_pool": False,
            "is_datacenter": False,
            "can_grant_home_badge": True,
            "can_grant_isp_suffix": True,
            "summary_zh": "原生民用住宅宽带 (Eyeball 共识)",
            "evidence": evidence
        }

    # 3. 判定 Level 2: 商用/机房双 ISP (Commercial Dual-ISP)
    # 特征：具备 ISP 机构或住宅/双 ISP 特征，但在 IDC 机柜环境下运营（如带有 datacenter/hosting/is_dc_ptr/is_dc_asn，或无原生住宅动态 PTR）
    if is_isp_org:
        return {
            "level": "Level 2: Commercial Dual-ISP",
            "is_residential": False,
            "is_dual_isp": True,
            "is_proxy_pool": False,
            "is_datacenter": bool(scama_dc or ipinfo_hosting or is_dc_ptr or is_dc_asn),
            "can_grant_home_badge": False,  # 严禁授予 🏠
            "can_grant_isp_suffix": True,   # 统一打标为 _ISP 后缀
            "summary_zh": "商用机房双 ISP (严禁 🏠，统一授予 _ISP 后缀)",
            "evidence": evidence
        }

    # 4. 判定 Level 4: 数据中心/机房 (Datacenter / Hosting)
    return {
        "level": "Level 4: Datacenter",
        "is_residential": False,
        "is_dual_isp": False,
        "is_proxy_pool": False,
        "is_datacenter": bool(scama_dc is True or ipinfo_hosting is True or is_dc_asn or is_dc_ptr),
        "can_grant_home_badge": False,
        "can_grant_isp_suffix": False,
        "summary_zh": "数据中心/托管网络",
        "evidence": evidence
    }
