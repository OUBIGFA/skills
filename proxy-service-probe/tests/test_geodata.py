# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from geodata import CONTINENT, COUNTRY_ZH, region_rank
from verdict import city_key, norm_city


class GeodataTests(unittest.TestCase):
    def test_english_city_lookup_is_case_insensitive(self):
        expected = {
            'Yokohama': '横滨',
            'Toyokawa': '丰川',
            'Pyeongtaek': '平泽',
            'Chuncheon': '春川',
        }
        for raw, translated in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(city_key(raw), translated)

    def test_every_known_country_has_a_continent(self):
        self.assertEqual(set(COUNTRY_ZH) - set(CONTINENT), set())

    def test_china_follows_every_known_region_and_unknown_stays_last(self):
        for cc in COUNTRY_ZH:
            if cc != 'CN':
                with self.subTest(cc=cc):
                    self.assertLess(region_rank(cc), region_rank('CN'))
        self.assertEqual(region_rank('cn'), region_rank('CN'))
        for cc in (None, '', 'UNK', 'ZZ'):
            self.assertGreater(region_rank(cc), region_rank('CN'))

    def test_city_normalization_uses_full_admin_suffix_list(self):
        self.assertEqual(norm_city('首尔特别市'), '首尔')
        self.assertEqual(norm_city('达卡专区'), '达卡')
        self.assertEqual(norm_city('北荷兰省'), '北荷兰')


if __name__ == '__main__':
    unittest.main()
