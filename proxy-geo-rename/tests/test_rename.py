# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import common
import rename


def node(tag, server, detour=None):
    value = {
        'type': 'trojan',
        'tag': tag,
        'server': server,
        'server_port': 443,
        'password': server,
    }
    if detour:
        value['detour'] = detour
    return value


class RenameTests(unittest.TestCase):
    def test_apply_mapping_updates_all_references_without_sorting(self):
        config = {
            'outbounds': [
                node('old-a', 'a.example'),
                node('old-b', 'b.example', detour='old-a'),
                {
                    'type': 'selector',
                    'tag': 'select',
                    'outbounds': ['old-a', 'old-b'],
                    'default': 'old-a',
                },
            ],
            'route': {
                'final': 'old-a',
                'rules': [{'outbound': 'old-b'}],
            },
            'dns': {'servers': [{'tag': 'dns', 'address': '1.1.1.1', 'detour': 'old-a'}]},
        }

        rename.apply_mapping(
            config,
            {'old-a': '🇯🇵 日本_东京_1', 'old-b': '🇺🇸 美国_洛杉矶_1'},
            strip_detour=True,
        )

        node_tags = [
            outbound['tag'] for outbound in config['outbounds']
            if outbound.get('type') in common.NODE_TYPES
        ]
        self.assertEqual(node_tags, ['🇯🇵 日本_东京_1', '🇺🇸 美国_洛杉矶_1'])
        self.assertNotIn('detour', config['outbounds'][1])
        self.assertEqual(config['outbounds'][2]['default'], '🇯🇵 日本_东京_1')
        self.assertEqual(config['route']['rules'][0]['outbound'], '🇺🇸 美国_洛杉矶_1')
        common.validate_config(config)


if __name__ == '__main__':
    unittest.main()
