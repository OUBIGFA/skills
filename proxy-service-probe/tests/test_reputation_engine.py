# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from scripts.core.reputation_engine import (
    calculate_composite_reputation_score,
    evaluate_ip_reputation,
    reverse_ip_for_dnsbl,
)


class TestReputationEngine(unittest.TestCase):
    def test_reverse_ip_for_dnsbl(self):
        self.assertEqual(reverse_ip_for_dnsbl("1.2.3.4"), "4.3.2.1")
        self.assertEqual(reverse_ip_for_dnsbl("192.168.1.1"), "1.1.168.192")
        self.assertIsNone(reverse_ip_for_dnsbl("invalid_ip"))
        self.assertIsNone(reverse_ip_for_dnsbl("2001:db8::1"))

    def test_calculate_score_clean_residential(self):
        # 纯净原生家宽 (fraud=0) -> 100 - 0 + 5 奖励 -> 封顶 100
        score, bd = calculate_composite_reputation_score(
            scamalytics={"fraud_score": 0},
            abuseipdb=None,
            dnsbl_hits=[],
            residential_level="Level 1: True Residential",
            is_datacenter=False
        )
        self.assertEqual(score, 100)
        self.assertEqual(bd["bonuses"].get("clean_residential"), 5.0)

    def test_calculate_score_datacenter_and_penalties(self):
        # 纯机房 (DC penalty -10)，fraud=25 (penalty (25-15)*0.5 = 5)，abuse=20 (penalty 8)
        score, bd = calculate_composite_reputation_score(
            scamalytics={"fraud_score": 25},
            abuseipdb={"abuse_score": 20},
            dnsbl_hits=["bl.spamcop.net"],  # -15
            residential_level="Level 4: Datacenter",
            is_datacenter=True
        )
        # 100 - 5 (fraud) - 8 (abuse) - 10 (dc) - 15 (blacklist) = 62
        self.assertEqual(score, 62)
        self.assertEqual(bd["penalties"]["fraud"], 5.0)
        self.assertEqual(bd["penalties"]["abuse"], 8.0)
        self.assertEqual(bd["penalties"]["datacenter"], 10.0)
        self.assertEqual(bd["penalties"]["blacklist"], 15.0)

    def test_calculate_score_high_fraud(self):
        # 高危欺诈 (fraud=60) -> penalty 25 + (60-40)*0.8 = 41
        score, bd = calculate_composite_reputation_score(
            scamalytics={"fraud_score": 60},
            abuseipdb=None,
            dnsbl_hits=[],
            residential_level="Level 3: Residential Proxy",
            is_datacenter=False
        )
        # 100 - 41 = 59
        self.assertEqual(score, 59)
        self.assertEqual(bd["penalties"]["fraud"], 41.0)

    def test_fallback_when_external_fails(self):
        # 外部探针均失败，使用 Net.Coffee 兜底分 85
        score, bd = calculate_composite_reputation_score(
            scamalytics=None,
            abuseipdb=None,
            dnsbl_hits=[],
            residential_level="Level 4: Datacenter",
            is_datacenter=True,
            fallback_score=85
        )
        self.assertEqual(score, 85)
        self.assertTrue(bd.get("fallback_used"))

    @patch("scripts.core.reputation_engine.fetch_scamalytics")
    @patch("scripts.core.reputation_engine.resolve_ptr")
    @patch("scripts.core.reputation_engine.probe_dnsbl")
    def test_evaluate_ip_reputation_flow(self, mock_dnsbl, mock_ptr, mock_scama):
        mock_ptr.return_value = "114-36-1-2.dynamic.hinet.net"
        mock_scama.return_value = {
            "provider": "Scamalytics",
            "fraud_score": 5,
            "is_datacenter": False,
            "is_proxy": False,
            "is_residential_proxy": False,
            "risk_level": "low"
        }
        mock_dnsbl.return_value = []

        res = evaluate_ip_reputation(
            ip="114.36.1.2",
            asn_raw="AS3462",
            isp_name="Chunghwa Telecom",
            use_cache=False
        )
        self.assertEqual(res["score"], 100)
        self.assertEqual(res["residential_level"], "Level 1: True Residential")
        self.assertTrue(res["can_grant_home_badge"])
        self.assertFalse(res["can_grant_isp_suffix"])
        self.assertEqual(res["flags"]["residential"], True)
        self.assertEqual(res["flags"]["datacenter"], False)


if __name__ == "__main__":
    unittest.main()
