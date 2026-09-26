# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

# 确保 scripts 目录在 sys.path
SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from core.merger import clash_proxy_sig, extract_claimed_slots, merge_clash_proxies, merge_into_clash_config


class MergerTests(unittest.TestCase):
    def test_default_preserves_base_nodes_and_slots(self):
        """测试默认模式：优先保留目标订阅的原节点以及原有编号，新节点自动补空号并规范排序。"""
        base_proxies = [
            {"name": "🇭🇰 香港_1", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
            {"name": "🇭🇰 香港_2", "type": "vmess", "server": "1.1.1.2", "port": 443, "uuid": "u2"},
            {"name": "🇭🇰 香港_5", "type": "vmess", "server": "1.1.1.5", "port": 443, "uuid": "u5"},
            {"name": "🇺🇸 美国_1", "type": "vmess", "server": "2.2.2.1", "port": 443, "uuid": "u10"},
        ]

        new_proxies = [
            # 新香港节点（带 AI 和流媒体标记）
            {"name": "🇭🇰 ❇️香港_1_NF", "type": "vless", "server": "1.1.1.3", "port": 443, "uuid": "u3"},
            # 新香港节点（带综合全通标记）
            {"name": "🇭🇰 ✨️香港_1", "type": "trojan", "server": "1.1.1.4", "port": 443, "password": "p4"},
            # 新美国节点
            {"name": "🇺🇸 ❇️美国_1", "type": "vless", "server": "2.2.2.2", "port": 443, "uuid": "u11"},
        ]

        merged, stats = merge_clash_proxies(base_proxies, new_proxies, insert_mode=False)

        names = [p["name"] for p in merged]

        # 验证目标底库原有节点与编号 100% 保留
        self.assertIn("🇭🇰 香港_1", names)
        self.assertIn("🇭🇰 香港_2", names)
        self.assertIn("🇭🇰 香港_5", names)
        self.assertIn("🇺🇸 美国_1", names)

        # 验证新增节点补进空位 3 和 4
        self.assertIn("🇭🇰 ❇️香港_3_NF", names)
        self.assertIn("🇭🇰 ✨️香港_4", names)

        # 验证美国新节点补进空位 2
        self.assertIn("🇺🇸 ❇️美国_2", names)

        # 验证香港节点按编号排序 (1, 2, 3, 4, 5)
        hk_names = [n for n in names if "香港" in n]
        self.assertEqual(hk_names, [
            "🇭🇰 香港_1",
            "🇭🇰 香港_2",
            "🇭🇰 ❇️香港_3_NF",
            "🇭🇰 ✨️香港_4",
            "🇭🇰 香港_5"
        ])

        # 验证美国节点按编号排序 (1, 2)
        us_names = [n for n in names if "美国" in n]
        self.assertEqual(us_names, [
            "🇺🇸 美国_1",
            "🇺🇸 ❇️美国_2"
        ])

        self.assertEqual(stats["base_count"], 4)
        self.assertEqual(stats["added_count"], 3)
        self.assertEqual(stats["total_count"], 7)

    def test_insert_mode_completely_reorders_and_renumbers(self):
        """测试中间插入模式：打破原编号壁垒，完全按能力与规则重新排序并从 1 重新编号。"""
        base_proxies = [
            {"name": "🇭🇰 香港_1", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
            {"name": "🇭🇰 香港_2", "type": "vmess", "server": "1.1.1.2", "port": 443, "uuid": "u2"},
        ]

        new_proxies = [
            # 综合全通且有 AI 的高能力节点
            {"name": "🇭🇰 ✨️❇️Key香港_1", "type": "trojan", "server": "1.1.1.3", "port": 443, "password": "p3", "_is_key": True},
            # AI 解锁节点
            {"name": "🇭🇰 ❇️香港_1", "type": "vless", "server": "1.1.1.4", "port": 443, "uuid": "u4"},
        ]

        merged, stats = merge_clash_proxies(base_proxies, new_proxies, insert_mode=True)
        names = [p["name"] for p in merged]

        # 验证顺位: ✨️❇️Key > ❇️ > 普通
        # 且全部从 1 开始依次递增重新编号
        self.assertEqual(names[0], "🇭🇰 ✨️❇️Key香港_1")
        self.assertEqual(names[1], "🇭🇰 ❇️香港_2")
        self.assertEqual(names[2], "🇭🇰 香港_3")
        self.assertEqual(names[3], "🇭🇰 香港_4")
        self.assertEqual(stats["total_count"], 4)

    def test_connection_deduplication(self):
        """测试连接指纹去重：底库已有相同指纹时自动跳过。"""
        base_proxies = [
            {"name": "🇭🇰 香港_1", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
        ]
        new_proxies = [
            # 相同指纹 (不同名字)
            {"name": "🇭🇰 新抓取_99", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
            # 不同指纹
            {"name": "🇭🇰 独立节点", "type": "vmess", "server": "1.1.1.2", "port": 443, "uuid": "u2"},
        ]

        merged, stats = merge_clash_proxies(base_proxies, new_proxies, insert_mode=False)
        self.assertEqual(stats["skipped_count"], 1)
        self.assertEqual(stats["added_count"], 1)
        self.assertEqual(stats["total_count"], 2)
        names = [p["name"] for p in merged]
        self.assertEqual(names, ["🇭🇰 香港_1", "🇭🇰 独立节点_2"])

    def test_landing_nodes_at_bottom_of_region(self):
        """测试落地节点置于地区最末尾。"""
        base_proxies = [
            {"name": "🇺🇸 美国_1_USAI", "type": "vmess", "server": "2.2.2.1", "port": 443, "uuid": "u1", "is_landing": True},
            {"name": "🇺🇸 美国_2", "type": "vmess", "server": "2.2.2.2", "port": 443, "uuid": "u2"},
        ]
        new_proxies = [
            {"name": "🇺🇸 ❇️美国_1", "type": "vmess", "server": "2.2.2.3", "port": 443, "uuid": "u3"},
        ]

        merged, _ = merge_clash_proxies(base_proxies, new_proxies, insert_mode=False)
        names = [p["name"] for p in merged]
        # 直连节点在前，落地沉底
        self.assertTrue(names[-1].endswith("_USAI"))

    def test_merge_into_target_file_clash_yaml(self):
        """测试写入实际 Clash YAML 文件的端到端合流流程。"""
        import yaml
        from core.merger import merge_into_target_file
        from core.renderer import BUNDLED_TEMPLATE, read_template_text

        with tempfile.TemporaryDirectory() as td:
            base_file = os.path.join(td, "target_base.yaml")
            _, text, data = read_template_text(BUNDLED_TEMPLATE)
            # 填入 2 个底库节点
            data["proxies"] = [
                {"name": "🇭🇰 香港_1", "type": "vmess", "server": "1.1.1.1", "port": 443, "uuid": "u1"},
                {"name": "🇺🇸 美国_1", "type": "vmess", "server": "2.2.2.1", "port": 443, "uuid": "u2"},
            ]
            with open(base_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True)

            new_nodes = [
                {"name": "🇭🇰 ❇️香港_1_NF", "type": "vless", "server": "1.1.1.2", "port": 443, "uuid": "u3"},
            ]

            dest_path, stats = merge_into_target_file(
                target_path=base_file,
                new_nodes_or_file=new_nodes,
                insert_mode=False
            )

            self.assertEqual(dest_path, os.path.abspath(base_file))
            self.assertTrue(os.path.exists(base_file + ".bak"))
            self.assertEqual(stats["added_count"], 1)
            self.assertEqual(stats["total_count"], 3)

            # 读取合并后的 YAML
            with open(base_file, "r", encoding="utf-8") as f:
                updated_data = yaml.safe_load(f)

            proxy_names = [p["name"] for p in updated_data["proxies"]]
            self.assertEqual(proxy_names, ["🇭🇰 香港_1", "🇭🇰 ❇️香港_2_NF", "🇺🇸 美国_1"])


if __name__ == '__main__':
    unittest.main()
