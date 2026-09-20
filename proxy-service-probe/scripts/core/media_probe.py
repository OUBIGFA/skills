# -*- coding: utf-8 -*-
"""国际流媒体解锁检测: Netflix (奈飞) 与 Disney+ (迪士尼)。"""
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def probe_netflix(proxies, timeout=(3.0, 6.0)):
    """检测 Netflix 解锁（必须解锁非自制剧才判定为通过）。"""
    session = requests.Session()
    session.trust_env = False
    result = {"status": "failed", "reason": "unknown"}

    urls = [
        "https://www.netflix.com/title/81280792",
        "https://www.netflix.com/title/80018499"
    ]
    for url in urls:
        try:
            resp = session.get(url, proxies=proxies, timeout=timeout, allow_redirects=False,
                               headers={"User-Agent": UA})
            if resp.status_code == 200:
                result = {"status": "passed", "reason": "expected_response"}
                break
            elif resp.status_code in (403, 451):
                result = {"status": "blocked", "reason": f"http_{resp.status_code}"}
            else:
                result = {"status": "failed", "reason": f"http_{resp.status_code}"}
        except requests.RequestException as e:
            result = {"status": "unknown", "reason": f"request_error:{type(e).__name__}"}

    session.close()
    return result


def probe_disney(proxies, timeout=(3.0, 6.0)):
    """检测 Disney+ 解锁。"""
    session = requests.Session()
    session.trust_env = False
    result = {"status": "failed", "reason": "unknown"}

    try:
        url = "https://www.disneyplus.com/"
        resp = session.get(url, proxies=proxies, timeout=timeout, allow_redirects=True,
                           headers={"User-Agent": UA})
        if resp.status_code in (200, 301, 302):
            lower_text = resp.text.lower()
            if any(m in lower_text for m in ("not available in your region", "unsupported directory", "service unavailable")):
                result = {"status": "blocked", "reason": "region_unsupported"}
            else:
                result = {"status": "passed", "reason": "expected_response"}
        elif resp.status_code in (403, 451):
            result = {"status": "blocked", "reason": f"http_{resp.status_code}"}
        else:
            result = {"status": "failed", "reason": f"http_{resp.status_code}"}
    except requests.RequestException as e:
        result = {"status": "unknown", "reason": f"request_error:{type(e).__name__}"}
    finally:
        session.close()

    return result


def probe_all_media(proxies, timeout=(3.0, 6.0)):
    """测试全部流媒体。"""
    nf = probe_netflix(proxies, timeout=timeout)
    dp = probe_disney(proxies, timeout=timeout)

    details = {
        "nf": nf.get("status") == "passed",
        "dp": dp.get("status") == "passed"
    }

    return {
        "details": details,
        "observations": {
            "nf": nf,
            "dp": dp
        },
        "media_supported": any(details.values())
    }
