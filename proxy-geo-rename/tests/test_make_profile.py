# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import common
import make_profile


def node(tag, server):
    return {
        'type': 'trojan',
        'tag': tag,
        'server': server,
        'server_port': 443,
        'password': server,
        'detour': 'front',
        'domain_resolver': 'dns',
    }


class MakeProfileTests(unittest.TestCase):
    def test_build_profile_deduplicates_nodes_and_strips_runtime_links(self):
        source = {
            'outbounds': [
                node('A', 'same.example'),
                node('A', 'same.example'),
                node('B', 'other.example'),
            ]
        }

        config, dropped = make_profile.build_profile(source)

        self.assertEqual(dropped, [])
        nodes = [o for o in config['outbounds'] if o.get('type') in common.NODE_TYPES]
        self.assertEqual([o['tag'] for o in nodes], ['A', 'B'])
        self.assertTrue(all('detour' not in o and 'domain_resolver' not in o for o in nodes))
        common.validate_config(config)


if __name__ == '__main__':
    unittest.main()
