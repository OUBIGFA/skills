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
    from core.fofa import (
        get_default_config_path,
        load_fofa_config,
        inspect_jwt_token,
    )
except ImportError:
    # 兼容独立运行
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(CURRENT_DIR)
    if CURRENT_DIR not in sys.path:
        sys.path.insert(0, CURRENT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)
    from core.fofa import (
        get_default_config_path,
        load_fofa_config,
        inspect_jwt_token,
    )

LOGIN_URL = "https://i.nosec.org/login?service=https://fofa.info/f_login"


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

    # 若存在 tokens 多 Token 列表配置，将新 Token 插入首位去重
    if "tokens" in cfg and isinstance(cfg["tokens"], list):
        filtered = [t for t in cfg["tokens"] if t != new_token]
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
    proxy: Optional[str] = None,
    headless: bool = False,
    timeout: int = 60,
    save_to_config: bool = True
) -> Tuple[bool, Optional[str], str]:
    """
    执行自动化登录 FoFa 并获取有效 Web Token。

    :param email: 登录邮箱或用户名。若未提供，优先读取配置文件或环境变量 FOFA_EMAIL/FOFA_USER。
    :param password: 登录密码。若未提供，优先读取配置文件或环境变量 FOFA_PASSWORD。
    :param config_path: fofa_config.json 绝对路径。
    :param proxy: 代理服务器地址 (如 http://127.0.0.1:3067)。
    :param headless: 是否使用无头模式。默认 False (为确保 Cloudflare Turnstile 人机验证顺利通过)。
    :param timeout: 登录与验证总超时秒数 (默认 60s)。
    :param save_to_config: 成功后是否自动更新写回 fofa_config.json。
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

    # 1. 尝试从已有配置补全参数
    cfg = load_fofa_config(config_path)
    final_email = email or cfg.get("email") or os.environ.get("FOFA_EMAIL") or os.environ.get("FOFA_USER") or ""
    final_pwd = password or cfg.get("password") or os.environ.get("FOFA_PASSWORD") or ""
    final_proxy = proxy or cfg.get("proxy") or os.environ.get("FOFA_PROXY") or ""

    def _is_placeholder(val: str) -> bool:
        if not val or not isinstance(val, str):
            return True
        v = val.strip().lower()
        return not v or any(p in v for p in ("your_", "example.com", "placeholder", "your-", "<your"))

    if _is_placeholder(final_email):
        final_email = ""
    if _is_placeholder(final_pwd):
        final_pwd = ""

    print("[*] 正在启动浏览器执行 FoFa / NOSEC 登录与 Token 提取流程...")
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
        # 优先使用系统中已存在的 msedge 或 chromium
        launch_kwargs: Dict[str, Any] = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        }
        if final_proxy:
            launch_kwargs["proxy"] = {"server": final_proxy}

        # 尝试选择合适的浏览器
        browser = None
        for channel in ["msedge", None]:
            try:
                if channel:
                    launch_kwargs["channel"] = channel
                else:
                    launch_kwargs.pop("channel", None)
                browser = p.chromium.launch(**launch_kwargs)
                break
            except Exception:
                continue

        if not browser:
            return False, None, "无法启动 Chromium / Edge 浏览器，请检查 Playwright 运行环境。"

        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 850}
            )
            # 去除自动化特征，防止 navigator.webdriver 干扰 Turnstile
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                if (!window.chrome) {
                    window.chrome = { runtime: {} };
                }
            """)

            page = context.new_page()

            # 2. 导航至登录页面
            print("[*] 正在载入 NOSEC 认证中心登录页...")
            try:
                page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                return False, None, f"打开登录页失败: {e}"

            page.wait_for_timeout(2000)

            # 3. 自动填入账号密码
            if final_email:
                try:
                    page.fill('input[name="username"]', final_email)
                except Exception:
                    pass
            if final_pwd:
                try:
                    page.fill('input[name="password"]', final_pwd)
                except Exception:
                    pass

            # 自动勾选服务协议与保持登录复选框
            try:
                checks = page.locator('input[type="checkbox"]')
                for i in range(checks.count()):
                    box = checks.nth(i)
                    if not box.is_checked():
                        box.check()
            except Exception:
                pass

            # 4. 轮询检测 Turnstile 人机验证与登录成功状态
            start_time = time.time()
            deadline = start_time + timeout
            auto_submitted = False

            print("[*] 正在等待 Cloudflare Turnstile 验证及登录重定向...")
            if not headless:
                print("    (若浏览器窗口弹出验证码勾选框，请在窗口中点击完成验证)")

            while time.time() < deadline:
                # 检查当前所有 Cookie 中是否已出现有效的 fofa_token
                try:
                    cookies = context.cookies()
                    for c in cookies:
                        if c.get("name") == "fofa_token" and c.get("value"):
                            # 校验是否为合法有效 JWT
                            info = inspect_jwt_token(c["value"])
                            if info.get("valid"):
                                extracted_token = c["value"]
                                success = True
                                message = f"成功捕获有效 Token (用户: {info.get('username')}, 到期: {info.get('exp_dt')})"
                                break
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
                except Exception:
                    pass

                # 若已填入账号密码且 Turnstile 验证码已生成但尚未提交，自动点击登录按钮
                if final_email and final_pwd and not auto_submitted:
                    try:
                        ts_val = page.locator('input[name="cf-turnstile-response"]').input_value()
                        if len(ts_val) > 20:
                            print("[*] 检测到 Turnstile 验证已通过，正在自动提交登录...")
                            page.evaluate("""() => {
                                const btn = document.querySelector('button[type="submit"], input[type="submit"]');
                                if (btn && !btn.disabled) {
                                    btn.click();
                                }
                            }""")
                            auto_submitted = True
                    except Exception:
                        pass

                page.wait_for_timeout(1000)

            if not success and not message:
                message = f"登录流程超时 ({timeout}秒)，未在规定时间内获取到 fofa_token"

        finally:
            try:
                browser.close()
            except Exception:
                pass

    # 5. 持久化写回配置文件
    if success and extracted_token:
        print(f"[✓] {message}")
        if save_to_config:
            if update_fofa_config_token(extracted_token, email=final_email, config_path=config_path):
                print(f"[✓] 新 Token 已成功持久化写回配置文件: {config_path or get_default_config_path()}")
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
    parser.add_argument("--headless", action="store_true", help="使用无头模式")
    parser.add_argument("--timeout", type=int, default=60, help="超时时间 (秒)")
    args = parser.parse_args()

    ok, tok, msg = login_fofa_and_extract_token(
        email=args.username,
        password=args.password,
        config_path=args.config,
        proxy=args.proxy,
        headless=args.headless,
        timeout=args.timeout,
        save_to_config=True
    )
    sys.exit(0 if ok else 1)
