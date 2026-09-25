# -*- coding: utf-8 -*-
"""导出的 Clash YAML 保留母版 template.yaml 的注释与空行；母版被手动改写后仍能正确解析或给出明确错误。"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from core.renderer import STREAMING_RULES, check_template, export_clash_yaml, render_clash_config, \
    resolve_template_path

NODES = [
    {"name": "🇯🇵 Key日本_1", "type": "trojan", "server": "jp1.example", "port": 443, "password": "p\\1"},
    {"name": "🇺🇸 美国_1_Lnd", "type": "ss", "server": "us1.example", "port": 8388, "cipher": "aes-128-gcm",
     "password": "x"},
]


def read(path, encoding="utf-8"):
    with open(path, "r", encoding=encoding) as f:
        return f.read()


BUNDLED = read(resolve_template_path())


class TestTemplateTextRendering(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def template(self, text, encoding="utf-8", newline=None):
        path = os.path.join(self.temp.name, "tpl.yaml")
        with open(path, "w", encoding=encoding, newline=newline) as f:
            f.write(text)
        return path

    def export(self, template_path=None):
        out = os.path.join(self.temp.name, "out.yaml")
        log = io.StringIO()
        with redirect_stdout(log):
            export_clash_yaml([dict(n) for n in NODES], out, template_path=template_path)
        text = read(out)
        self.assertEqual(yaml.safe_load(text), render_clash_config([dict(n) for n in NODES], template_path))
        return text, log.getvalue()

    def test_bundled_template_comments_and_blank_lines_kept_verbatim(self):
        text, log = self.export()
        head, rest = BUNDLED.split("proxies: []\n", 1)
        tail = rest.split("proxy-groups: []\n", 1)[1]
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith(tail))
        self.assertIn("  - DIRECT\n\nrules:\n\n  # --- 进程分流规则 (优先匹配) ---\n", text)
        self.assertNotIn("&id0", text)
        self.assertEqual(log, "")
        cfg = yaml.safe_load(text)
        self.assertEqual(cfg["proxies"][0]["password"], "p\\1")
        self.assertEqual(cfg["proxies"][1]["dialer-proxy"], "🛡️ Front前置")

    def test_placeholder_with_comment_bom_and_crlf(self):
        edited = BUNDLED.replace("proxies: []\n", "proxies:   []   # 节点由脚本生成\n")
        text, log = self.export(self.template(edited, encoding="utf-8-sig", newline="\r\n"))
        self.assertEqual(log, "")
        self.assertIn("# 权威防 DNS 泄露模块", text)
        self.assertNotIn(chr(0xFEFF), text)

    def test_leftover_nodes_in_template_are_replaced(self):
        old = "proxies:\n- name: 旧节点\n  type: ss\n# 旧注释\n- name: 旧节点2\n  type: ss\n"
        text, log = self.export(self.template(BUNDLED.replace("proxies: []\n", old)))
        self.assertEqual(log, "")
        self.assertNotIn("旧节点", text)

    def test_deleted_placeholders_are_inserted_before_rules(self):
        edited = BUNDLED.replace("proxies: []\nproxy-groups: []\n", "")
        text, log = self.export(self.template(edited))
        self.assertEqual(log, "")
        self.assertLess(text.index("\nproxies:\n"), text.index("\nrules:\n"))
        self.assertIn("# 权威防 DNS 泄露模块", text)

    def test_custom_rule_and_comment_are_kept(self):
        edited = BUNDLED.replace("# 默认规则\n", "# 我的规则\n- DOMAIN-SUFFIX,example.org,DIRECT\n\n# 默认规则\n")
        text, log = self.export(self.template(edited))
        self.assertEqual(log, "")
        self.assertIn("# 我的规则\n- DOMAIN-SUFFIX,example.org,DIRECT\n\n# 默认规则\n", text)

    def test_missing_streaming_rules_are_inserted_in_place(self):
        edited = "".join(line for line in BUNDLED.splitlines(keepends=True) if "🎬 国际流媒体" not in line)
        text, log = self.export(self.template(edited))
        self.assertEqual(log, "")
        self.assertIn(f"- {STREAMING_RULES[0]}\n", text)
        self.assertIn("# 解锁其他 AI 服务 (走 🔀 AI 服务)", text)

    def test_unlineable_rules_fall_back_with_notice(self):
        path = self.template('# 自定义母版\nmode: rule\nrules: ["MATCH,DIRECT"]\n')
        text, log = self.export(path)
        self.assertIn("无法逐行保留", log)
        self.assertEqual(len(yaml.safe_load(text)["proxies"]), 2)

    def test_rule_without_policy_is_reported_not_crashing(self):
        edited = BUNDLED.replace("- MATCH,↪️ 漏网之鱼\n", "- MATCH\n")
        with self.assertRaises(ValueError) as ctx:
            check_template(self.template(edited))
        self.assertIn("缺少策略: MATCH", str(ctx.exception))

    def test_yaml_syntax_error_reports_line(self):
        path = self.template(BUNDLED.replace("mode: rule\n", "mode: rule\n\tbad: tab\n"))
        with self.assertRaises(ValueError) as ctx:
            check_template(path)
        self.assertIn("语法错误", str(ctx.exception))
        self.assertIn("line", str(ctx.exception))

    def test_unknown_group_and_rule_provider_are_reported_before_testing(self):
        edited = BUNDLED.replace("- MATCH,↪️ 漏网之鱼\n", "- DOMAIN,a.com,🎮 游戏\n- RULE-SET,NoSuch,DIRECT\n- MATCH,↪️ 漏网之鱼\n")
        with self.assertRaises(ValueError) as ctx:
            check_template(self.template(edited))
        self.assertIn("🎮 游戏", str(ctx.exception))
        self.assertIn("NoSuch", str(ctx.exception))
        self.assertEqual(check_template(), resolve_template_path())


if __name__ == "__main__":
    unittest.main()
