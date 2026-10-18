# -*- coding: utf-8 -*-
import os
import tempfile
import time
import unittest

from scripts.core.local_cache import LocalReputationCache


class TestLocalReputationCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_cache.db")
        self.cache = LocalReputationCache(db_path=self.db_path, ttl=0.5)

    def tearDown(self):
        del self.cache
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_cache_miss_and_set_hit(self):
        self.assertIsNone(self.cache.get("1.1.1.1"))
        data = {"fraud_score": 5, "isp": "Test ISP"}
        self.cache.set("1.1.1.1", score=95, res_level="Level 1: True Residential", data=data)

        hit = self.cache.get("1.1.1.1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["score"], 95)
        self.assertEqual(hit["residential_level"], "Level 1: True Residential")
        self.assertEqual(hit["fraud_score"], 5)
        self.assertTrue(hit["cached"])

    def test_cache_expiration(self):
        self.cache.set("2.2.2.2", score=80, res_level="Level 4: Datacenter", data={"test": 1})
        self.assertIsNotNone(self.cache.get("2.2.2.2"))
        time.sleep(0.6)
        self.assertIsNone(self.cache.get("2.2.2.2"))

    def test_memory_fallback(self):
        # 使用无法创建文件的无效路径（如包含保留字符）
        mem_cache = LocalReputationCache(db_path="Z:\\non_existent_drive_999\\db.sqlite", ttl=1.0)
        self.assertTrue(mem_cache._use_memory_only)
        mem_cache.set("3.3.3.3", score=88, res_level="Level 2: Commercial Dual-ISP", data={"ok": True})
        hit = mem_cache.get("3.3.3.3")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["score"], 88)
        self.assertEqual(hit["residential_level"], "Level 2: Commercial Dual-ISP")


if __name__ == "__main__":
    unittest.main()
