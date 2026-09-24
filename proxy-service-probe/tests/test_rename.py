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

    def test_number_plan_positions_first_and_skips_kept_names(self):
        def item(idx, cc, czh, city=''):
            return (idx, f'raw-{idx}', {}, cc, czh, city, '高', '', '', '_')
        plan = [item(0, 'US', '美国'), item(1, 'HK', '香港'), item(2, 'US', '美国'), item(3, 'HK', '香港')]
        keep = [{'old': '🇺🇸 美国_1', 'new': '（保留原名）', 'conf': '低置信'}]
        mapping, rows = rename.number_plan(plan, keep, do_sort=True)
        # 先按地区排好位置（香港在美国前），再依次编号；保留原名已占用的美国_1 被跳过
        self.assertEqual([r['new'] for r in rows],
                         ['🇭🇰 香港_1', '🇭🇰 香港_2', '🇺🇸 美国_2', '🇺🇸 美国_3', '（保留原名）'])
        self.assertEqual(mapping['raw-2'], '🇺🇸 美国_3')


if __name__ == '__main__':
    unittest.main()
