# -*- coding: utf-8 -*-
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.fofa_login import (
    get_default_profile_dir,
    login_fofa_and_extract_token,
)


class TestFoFaLoginProfile(unittest.TestCase):
    def test_default_profile_dir_path(self):
        pdir = get_default_profile_dir()
        self.assertTrue(isinstance(pdir, str))
        self.assertTrue(pdir.endswith("fofa_profile"))
        self.assertTrue(os.path.isabs(pdir))

    @patch("playwright.sync_api.sync_playwright")
    def test_launch_persistent_context_called(self, mock_playwright):
        # 模拟 playwright 结构
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_context = MagicMock()
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_context.cookies.return_value = [
            {"name": "fofa_token", "value": "header.payload.signature"}
        ]

        # inspect_jwt_token mock
        with patch("core.fofa_login.inspect_jwt_token") as mock_jwt:
            mock_jwt.return_value = {
                "valid": True,
                "username": "test_user",
                "exp_dt": "2026-12-01 00:00:00",
            }
            with patch("core.fofa_login.update_fofa_config_token"):
                ok, token, msg = login_fofa_and_extract_token(
                    email="test@example.com",
                    password="password",
                    user_data_dir="D:/custom_profile",
                    timeout=5,
                    save_to_config=False,
                )
                self.assertTrue(ok)
                self.assertEqual(token, "header.payload.signature")

        # 验证调用了 launch_persistent_context 且传参了 user_data_dir
        mock_p.chromium.launch_persistent_context.assert_called_once()
        call_kwargs = mock_p.chromium.launch_persistent_context.call_args[1]
        self.assertEqual(call_kwargs.get("user_data_dir"), os.path.abspath("D:/custom_profile"))

    @patch("playwright.sync_api.sync_playwright")
    def test_default_profile_used_when_none(self, mock_playwright):
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_context = MagicMock()
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.cookies.return_value = [{"name": "fofa_token", "value": "dummy.token"}]

        with patch("core.fofa_login.inspect_jwt_token") as mock_jwt:
            mock_jwt.return_value = {"valid": True, "username": "u", "exp_dt": "2026-12-01"}
            with patch("core.fofa_login.update_fofa_config_token"):
                ok, _, _ = login_fofa_and_extract_token(
                    email="u@example.com",
                    password="p",
                    user_data_dir=None,
                    timeout=5,
                    save_to_config=False,
                )
                self.assertTrue(ok)

        call_kwargs = mock_p.chromium.launch_persistent_context.call_args[1]
        self.assertEqual(call_kwargs.get("user_data_dir"), get_default_profile_dir())


if __name__ == "__main__":
    unittest.main()
