# -*- coding: utf-8 -*-
import unittest

from scripts.core.residential_judge import (
    classify_residential,
    match_ptr_pattern,
    parse_asn_number,
)


class TestResidentialJudge(unittest.TestCase):
    def test_parse_asn(self):
        self.assertEqual(parse_asn_number("AS3462"), 3462)
        self.assertEqual(parse_asn_number("as16509 amazon"), 16509)
        self.assertEqual(parse_asn_number(7922), 7922)
        self.assertIsNone(parse_asn_number("unknown"))

    def test_ptr_matching(self):
        # 住宅 PTR
        is_res, is_dc, pat = match_ptr_pattern("114-36-1-1.dynamic.hinet.net")
        self.assertTrue(is_res)
        self.assertFalse(is_dc)

        is_res, is_dc, pat = match_ptr_pattern("cpe-10-1-1-1.cableone.net")
        self.assertTrue(is_res)

        # 机房 PTR
        is_res, is_dc, pat = match_ptr_pattern("ec2-54-1-1-1.compute-1.amazonaws.com")
        self.assertFalse(is_res)
        self.assertTrue(is_dc)

    def test_level_1_true_residential(self):
        res = classify_residential(
            ip="114.36.1.1",
            ptr="114-36-1-1.dynamic.hinet.net",
            asn_raw="AS3462",
            isp_name="Chunghwa Telecom",
            scamalytics={"fraud_score": 0, "is_datacenter": False, "is_residential_proxy": False},
            ipinfo_flags={"datacenter": False}
        )
        self.assertEqual(res["level"], "Level 1: True Residential")
        self.assertTrue(res["is_residential"])
        self.assertTrue(res["can_grant_home_badge"])
        self.assertTrue(res["can_grant_isp_suffix"])

    def test_level_2_commercial_dual_isp(self):
        # 虽有 ISP 标签，但缺少原生住宅 PTR 或在 IDC 托管环境运营
        res = classify_residential(
            ip="198.51.100.1",
            ptr="static-198-51-100-1.clouvider.net",
            asn_raw="AS62240",
            isp_name="Cogent Dual ISP Residential",
            scamalytics={"fraud_score": 10, "is_datacenter": True, "is_residential_proxy": False},
            ipinfo_flags={"residential": True, "datacenter": True}
        )
        self.assertEqual(res["level"], "Level 2: Commercial Dual-ISP")
        self.assertFalse(res["is_residential"])
        self.assertTrue(res["is_dual_isp"])
        self.assertFalse(res["can_grant_home_badge"])  # 严禁授予 🏠
        self.assertTrue(res["can_grant_isp_suffix"])   # 授予 _ISP

    def test_level_3_residential_proxy(self):
        # 住宅代理池污染 IP
        res = classify_residential(
            ip="203.0.113.5",
            ptr="client-203-0-113-5.dyn.home.net",
            asn_raw="AS7922",
            isp_name="Comcast",
            scamalytics={"fraud_score": 85, "is_datacenter": False, "is_residential_proxy": True},
            ipinfo_flags={"residential": True}
        )
        self.assertEqual(res["level"], "Level 3: Residential Proxy")
        self.assertFalse(res["can_grant_home_badge"])
        self.assertFalse(res["can_grant_isp_suffix"])
        self.assertTrue(res["is_proxy_pool"])

    def test_level_4_datacenter(self):
        # 纯机房 AWS
        res = classify_residential(
            ip="54.238.100.1",
            ptr="ec2-54-238-100-1.ap-northeast-1.compute.amazonaws.com",
            asn_raw="AS16509",
            isp_name="Amazon.com",
            scamalytics={"fraud_score": 0, "is_datacenter": True, "is_residential_proxy": False},
            ipinfo_flags={"datacenter": True}
        )
        self.assertEqual(res["level"], "Level 4: Datacenter")
        self.assertTrue(res["is_datacenter"])
        self.assertFalse(res["can_grant_home_badge"])
        self.assertFalse(res["can_grant_isp_suffix"])


if __name__ == "__main__":
    unittest.main()
