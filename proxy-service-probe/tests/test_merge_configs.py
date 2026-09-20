# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import common
import merge_configs


def node(tag, server):
    return {
        'type': 'trojan',
        'tag': tag,
        'server': server,
        'server_port': 443,
        'password': server,
    }


class MergeConfigTests(unittest.TestCase):
    def test_merge_only_extends_groups_that_cover_all_base_nodes(self):
        base = {
            'outbounds': [
                node('A', 'a.example'),
                node('B', 'b.example'),
                {'type': 'urltest', 'tag': 'all', 'outbounds': ['A', 'B']},
                {'type': 'selector', 'tag': 'main', 'outbounds': ['all', 'A', 'B']},
                {'type': 'urltest', 'tag': 'region-a', 'outbounds': ['A']},
            ]
        }
        additions = [[node('C', 'c.example')]]

        result = merge_configs.merge_config_data(base, additions)

        groups = {o['tag']: o['outbounds'] for o in base['outbounds'] if 'outbounds' in o}
        self.assertEqual(groups['all'], ['A', 'B', 'C'])
        self.assertEqual(groups['main'], ['all', 'A', 'B', 'C'])
        self.assertEqual(groups['region-a'], ['A'])
        self.assertEqual(result['added'], ['C'])
        common.validate_config(base)

    def test_merge_deduplicates_same_tag_by_position(self):
        base = {
            'outbounds': [
                node('A', 'same.example'),
                node('A', 'same.example'),
                {'type': 'selector', 'tag': 'select', 'outbounds': ['A', 'A'], 'default': 'A'},
            ],
            'route': {'final': 'A'},
        }

        merge_configs.merge_config_data(base, [[]])

        self.assertEqual(
            [o['tag'] for o in base['outbounds'] if o.get('type') in common.NODE_TYPES],
            ['A'],
        )
        common.validate_config(base)


if __name__ == '__main__':
    unittest.main()
