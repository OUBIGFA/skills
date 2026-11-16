# -*- coding: utf-8 -*-
"""
FoFa / NOSEC 自动化登录与 Token 续期模块 (scripts/core/fofa_login.py)
基于 Playwright 浏览器自动化实现：
1. 导航至 NOSEC / FoFa 统一认证中心 (https://i.nosec.org/login?service=https://fofa.info/f_login)。
2. 自动填入账号凭据并处理 Cloudflare Turnstile 人机验证。
3. 捕获认证成功后的 fofa.info 会话 Cookie (fofa_token JWT)。
4. 自动持久化保存至 fofa_config.json，使后续 FoFa 搜索在接下来 30 天内全自动调用高存活 Web API，
   彻底免去每隔一个月手动开 F12 抓取复制 token 的繁琐步骤。
"""
import json
import os
import sys
import time
from typing import Dict, Optional, Tuple, Any

# 导入同目录核心模块
try:
    from .fofa import (
        get_default_config_path,
        load_fofa_config,
        inspect_jwt_token,
    )
except (ImportError, ValueError):
    try:
        from scripts.core.fofa import (
            get_default_config_path,
            load_fofa_config,
            inspect_jwt_token,
        )
    except ImportError:
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        PARENT_DIR = os.path.dirname(CURRENT_DIR)
        for p in [CURRENT_DIR, PARENT_DIR]:
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            from core.fofa import (
                get_default_config_path,
                load_fofa_config,
                inspect_jwt_token,
            )
        except ImportError:
            from fofa import (
                get_default_config_path,
                load_fofa_config,
                inspect_jwt_token,
            )

LOGIN_URL = "https://i.nosec.org/login?service=https://fofa.info/f_login"


def get_default_profile_dir() -> str:
    """返回默认的 FoFa 专用浏览器持久化数据目录 (cache/fofa_profile)。"""
    skill_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pdir = os.path.join(skill_root, "cache", "fofa_profile")
    return os.path.abspath(pdir)


def update_fofa_config_token(new_token: str, email: Optional[str] = None,
                             config_path: Optional[str] = None) -> bool:
    """
    将新提取的 FoFa Token (及可选的 email) 写回 fofa_config.json 配置文件。
    保持原有配置项（如 quake_key, proxy, default_query 等）完整不丢失。
    """
    path = config_path or get_default_config_path()
    cfg: Dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[FoFa Login] 警告: 读取原配置文件失败，将初始化新配置: {e}")

    # 更新 token 字段
    cfg["token"] = new_token
    if email:
        cfg["email"] = email
        if isinstance(cfg.get("account"), dict) and not cfg["account"].get("username"):
            cfg["account"]["username"] = email

    # 若存在 tokens 多 Token 列表配置，将新 Token 插入首位并剔除已过期的旧 Token
    if "tokens" in cfg and isinstance(cfg["tokens"], list):
        filtered = [
            t for t in cfg["tokens"]
            if t != new_token and not inspect_jwt_token(t).get("expired")
        ]
        cfg["tokens"] = [new_token] + filtered

    try:
        cfg_dir = os.path.dirname(os.path.abspath(path))
        if cfg_dir and not os.path.exists(cfg_dir):
            os.makedirs(cfg_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[FoFa Login] 错误: 写入配置文件 {path} 失败: {e}")
        return False


def login_fofa_and_extract_token(
    email: Optional[str] = None,
    password: Optional[str] = None,
    config_path: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    proxy: Optional[str] = None,
    headless: bool = False,
    timeout: int = 60,
    save_to_config: bool = True,
    force_refresh: bool = False,
) -> Tuple[bool, Optional[str], str]:
    """
    执行自动化登录 FoFa 并获取有效 Web Token。

    :param email: 登录邮箱或用户名。若未提供，优先读取配置文件或环境变量 FOFA_EMAIL/FOFA_USER。
    :param password: 登录密码。若未提供，优先读取配置文件或环境变量 FOFA_PASSWORD。
    :param config_path: fofa_config.json 绝对路径。
    :param user_data_dir: 浏览器用户持久化配置目录。若未提供，优先读取配置或默认使用 cache/fofa_profile。
    :param proxy: 代理服务器地址 (如 http://127.0.0.1:3067)。
    :param headless: 是否使用无头模式。默认 False (为确保可视窗口交互顺利完成)。
    :param timeout: 登录与验证总超时秒数 (默认 60s)。
    :param save_to_config: 成功后是否自动更新写回 fofa_config.json。
    :param force_refresh: 是否强制清除旧 fofa_token Cookie 重新获取。
    :return: (是否成功, token_string, 提示说明信息)
    """
    # 动态载入 playwright，避免在未安装环境报错
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            False,
            None,
            "未检测到 playwright 依赖库。请先安装: pip install playwright && playwright install chromium"
        )

    # 1. 尝试从已有配置补全参数 (兼容顶层 email/password 与 account 字典)
    cfg = load_fofa_config(config_path)
    acc = cfg.get("account") if isinstance(cfg.get("account"), dict) else {}
    final_email = (
        email
        or cfg.get("email")
        or acc.get("username")
        or acc.get("email")
        or os.environ.get("FOFA_EMAIL")
        or os.environ.get("FOFA_USER")
        or ""
    )
    final_pwd = (
        password
        or cfg.get("password")
        or acc.get("password")
        or os.environ.get("FOFA_PASSWORD")
        or ""
    )
    final_proxy = proxy or cfg.get("proxy") or os.environ.get("FOFA_PROXY") or ""
    final_user_data_dir = os.path.abspath(user_data_dir or cfg.get("user_data_dir") or get_default_profile_dir())

    try:
        os.makedirs(final_user_data_dir, exist_ok=True)
    except Exception as e:
        print(f"[FoFa Login] 警告: 创建持久化目录失败: {e}")

    def _is_placeholder(val: str) -> bool:
        if not val or not isinstance(val, str):
            return True
        v = val.strip().lower()
        return not v or any(p in v for p in ("your_", "example.com", "placeholder", "your-", "<your"))

    if _is_placeholder(final_email):
        final_email = ""
    if _is_placeholder(final_pwd):
        final_pwd = ""

    print("[*] 正在启动持久化浏览器环境执行 FoFa / NOSEC 登录与 Token 提取流程...")
    print(f"    - 持久化配置: {final_user_data_dir}")
    if final_email:
        print(f"    - 目标账号: {final_email}")
    else:
        print("    - 目标账号: [未预设，将在浏览器中等待手动输入]")
    if final_proxy:
        print(f"    - 网络代理: {final_proxy}")
    print(f"    - 窗口模式: {'无头模式 (Headless)' if headless else '可视窗口模式 (Headed - 便于人机验证交互)'}")
    print(f"    - 最大超时: {timeout} 秒")

    extracted_token: Optional[str] = None
    success = False
    message = ""

    with sync_playwright() as p:
        # 使用持久化上下文以保留 Cookies、LocalStorage、设备指纹与 Turnstile 信任状态
        # 注意：不硬编码过时 User-Agent，也不覆盖 plugins/languages 等原生指纹，避免与真实内核版本不一致而被 Turnstile 拦截
        launch_kwargs: Dict[str, Any] = {
            "user_data_dir": final_user_data_dir,
            "headless": headless,
            "viewport": {"width": 1280, "height": 850},
            "ignore_default_args": ["--enable-automation"],
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
        }
        if final_proxy:
            launch_kwargs["proxy"] = {"server": final_proxy}

        # 优先使用用户配置或本机 Chrome Dev，其次按 Chrome / Edge / 内置 Chromium 回退
        configured_browser = str(cfg.get("browser_path") or os.environ.get("FOFA_BROWSER_PATH") or "").strip()
        preferred_exe_paths = [
            p_cand for p_cand in (
                configured_browser,
                r"C:\Program Files\Google\Chrome Dev\Application\chrome.exe",
            )
            if p_cand and os.path.isfile(p_cand)
        ]

        context = None
        last_launch_err: Optional[Exception] = None
        launch_candidates: list = []
        for exe_path in preferred_exe_paths:
            launch_candidates.append(("executable_path", exe_path))
        for ch in ("chrome", "msedge", None):
            launch_candidates.append(("channel", ch))

        for mode, val in launch_candidates:
            try:
                kw = dict(launch_kwargs)
                if mode == "executable_path":
                    kw["executable_path"] = val
                elif val:
                    kw["channel"] = val
                context = p.chromium.launch_persistent_context(**kw)
                print(f"    - 启动内核: {val or 'Playwright Chromium'}")
                break
            except Exception as exc:
                last_launch_err = exc
                continue

        if not context:
            err_msg = f"无法启动 Chrome Dev / Chrome / Edge 浏览器: {last_launch_err or '未知错误'}"
            print(f"[!] 登录失败: {err_msg}")
            return False, None, err_msg

        try:
            # 仅做最小化的 webdriver 隐藏，保持其余浏览器指纹完全原生
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            page = context.pages[0] if context.pages else context.new_page()

            # 若指定 force_refresh，先清理已有的 fofa_token Cookie，确保捕获新签发凭据
            if force_refresh:
                try:
                    existing_cookies = context.cookies()
                    kept = [c for c in existing_cookies if c.get("name") != "fofa_token"]
                    context.clear_cookies()
                    if kept:
                        context.add_cookies(kept)
                except Exception:
                    pass

            # 2. 导航至登录页面
            print("[*] 正在载入 NOSEC 认证中心登录页...")
            try:
                page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                err_msg = f"打开登录页失败: {e}"
                print(f"[!] 登录失败: {err_msg}")
                return False, None, err_msg

            page.wait_for_timeout(1500)

            def _fill_form_once() -> None:
                """仅在登录页就绪后填一次账号、密码并勾选保持登录与服务协议，避免轮询中频繁操作 DOM 干扰人机验证。"""
                if final_email:
                    try:
                        loc = page.locator('input[name="username"]')
                        if loc.count() > 0:
                            curr_val = loc.input_value()
                            if not curr_val or curr_val != final_email:
                                loc.fill(final_email)
                    except Exception:
                        pass
                if final_pwd:
                    try:
                        loc = page.locator('input[name="password"]')
                        if loc.count() > 0:
                            curr_pwd = loc.input_value()
                            if not curr_pwd:
                                loc.fill(final_pwd)
                    except Exception:
                        pass
                for cb_sel in ('#rememberMe', '#fofa_service'):
                    try:
                        cb = page.locator(cb_sel)
                        if cb.count() > 0 and not cb.first.is_checked():
                            cb.first.check()
                    except Exception:
                        pass

            _fill_form_once()

            # 4. 轮询检测登录重定向与 fofa_token Cookie 状态
            start_time = time.time()
            deadline = start_time + timeout
            last_submitted_ts_token = ""

            print("[*] 正在等待认证完成及登录重定向...")
            if not headless:
                print("    (若浏览器窗口中显示人机验证框，请在弹出窗口中手动点击完成后将自动提交并提取 Token)")

            while time.time() < deadline:
                if page.is_closed() is True:
                    message = "浏览器窗口已被手动关闭，登录取消"
                    break

                # 检查当前所有 Cookie 中是否已出现有效的 fofa_token
                try:
                    cookies = context.cookies()
                    for c in cookies:
                        if c.get("name") == "fofa_token" and c.get("value"):
                            info = inspect_jwt_token(c["value"])
                            if info.get("valid") and not info.get("expired"):
                                extracted_token = c["value"]
                                success = True
                                message = f"成功捕获有效 Token (用户: {info.get('username')}, 到期: {info.get('exp_dt')})"
                                break
                except Exception:
                    pass

                # 若已跳转至 fofa.info，同时检查 localStorage 中是否存有 fofa_token
                if not success:
                    try:
                        if "fofa.info" in (page.url or ""):
                            ls_tok = page.evaluate("""() => {
                                try {
                                    return localStorage.getItem('fofa_token') || '';
                                } catch (e) {
                                    return '';
                                }
                            }""")
                            if ls_tok:
                                info = inspect_jwt_token(ls_tok)
                                if info.get("valid") and not info.get("expired"):
                                    extracted_token = ls_tok
                                    success = True
                                    message = f"成功捕获有效 Token (用户: {info.get('username')}, 到期: {info.get('exp_dt')})"
                    except Exception:
                        pass

                if success:
                    break

                # 检查页面是否显示登录错误提示
                try:
                    err_text = page.evaluate("""() => {
                        const alert = document.querySelector('.alert-danger, .error-message, .flash-notice');
                        return alert ? alert.innerText.trim() : '';
                    }""")
                    if err_text and ("错误" in err_text or "失败" in err_text):
                        message = f"登录页面返回错误: {err_text}"
                        break
                except Exception:
                    pass

                # 当检测到 Turnstile 令牌已生成时，自动点击登录按钮
                if final_email and final_pwd:
                    try:
                        ts_loc = page.locator('input[name="cf-turnstile-response"]')
                        ts_val = ts_loc.input_value() if ts_loc.count() > 0 else ""
                        if len(ts_val) > 20 and ts_val != last_submitted_ts_token:
                            for cb_sel in ('#rememberMe', '#fofa_service'):
                                try:
                                    cb = page.locator(cb_sel)
                                    if cb.count() > 0 and not cb.first.is_checked():
                                        cb.first.check()
                                except Exception:
                                    pass
                            submit_btn = page.locator('button[type="submit"], input[type="submit"]')
                            if submit_btn.count() > 0:
                                print("[*] 验证已就绪，正在自动提交登录表单...")
                                try:
                                    submit_btn.first.click(timeout=3000)
                                except Exception:
                                    page.evaluate("() => { const f = document.querySelector('#login-form'); if (f) f.submit(); }")
                                last_submitted_ts_token = ts_val
                    except Exception:
                        pass

                page.wait_for_timeout(1000)

            if not success and not message:
                message = f"登录流程超时 ({timeout}秒)，未在规定时间内获取到 fofa_token"

        finally:
            try:
                context.close()
            except Exception:
                pass

    # 5. 持久化写回配置文件
    if success and extracted_token:
        print(f"[+] {message}")
        if save_to_config:
            if update_fofa_config_token(extracted_token, email=final_email, config_path=config_path):
                print(f"[+] 新 Token 已成功持久化写回配置文件: {config_path or get_default_config_path()}")
            else:
                print(f"[!] 警告: Token 获取成功但未能写回配置文件")
        return True, extracted_token, message

    print(f"[!] 登录失败: {message}")
    return False, None, message


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FoFa / NOSEC 自动登录与 Token 提取")
    parser.add_argument("--username", "-u", default=None, help="FoFa / NOSEC 登录邮箱或用户名")
    parser.add_argument("--password", "-p", default=None, help="FoFa / NOSEC 登录密码")
    parser.add_argument("--proxy", default=None, help="代理服务器 (如 http://127.0.0.1:3067)")
    parser.add_argument("--config", "-c", default=None, help="配置文件路径")
    parser.add_argument("--user-data-dir", "-d", default=None, help="浏览器持久化用户数据目录 (默认 scripts/core/data/fofa_profile)")
    parser.add_argument("--headless", action="store_true", help="使用无头模式")
    parser.add_argument("--timeout", type=int, default=60, help="超时时间 (秒)")
    args = parser.parse_args()

    ok, tok, msg = login_fofa_and_extract_token(
        email=args.username,
        password=args.password,
        config_path=args.config,
        user_data_dir=args.user_data_dir,
        proxy=args.proxy,
        headless=args.headless,
        timeout=args.timeout,
        save_to_config=True
    )
    sys.exit(0 if ok else 1)
