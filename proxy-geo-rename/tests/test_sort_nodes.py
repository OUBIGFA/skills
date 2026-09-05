# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import common
import sort_nodes


def node(tag, server):
    return {
        'type': 'trojan',
        'tag': tag,
        'server': server,
        'server_port': 443,
        'password': server,
    }


class SortNodeTests(unittest.TestCase):
    def test_offline_scripts_start_without_requests_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'requests.py').write_text(
                "raise ImportError('requests intentionally unavailable')\n",
                encoding='utf-8',
            )
            env = os.environ.copy()
            env['PYTHONPATH'] = tmp
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            for script in ('sort_nodes.py', 'merge_configs.py', 'make_profile.py'):
                with self.subTest(script=script):
                    result = subprocess.run(
                        [sys.executable, str(SCRIPTS / script), '--help'],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        env=env,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_sort_nodes_loads_common_from_its_own_directory(self):
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run(
            [sys.executable, '-c', 'import sort_nodes, common; print(common.__file__)'],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            encoding='utf-8',
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), (SCRIPTS / 'common.py').resolve())

    def test_lowercase_country_and_airport_names_are_recognized(self):
        cases = [
            ('us-lax-01', 'US', '洛杉矶'),
            ('ca-yyz-02', 'CA', '多伦多'),
        ]
        for tag, country, city in cases:
            with self.subTest(tag=tag):
                self.assertEqual(sort_nodes.detect_cc(tag), country)
                self.assertEqual(sort_nodes.parse_position(tag, country), city)
        self.assertIsNone(sort_nodes.detect_cc('VIP custom'))

    def test_country_and_location_tokens_do_not_leak_into_suffix(self):
        self.assertEqual(sort_nodes.detect_suffix('JP Tokyo vmess', 'JP'), '')
        self.assertEqual(sort_nodes.detect_suffix('us-lax-01', 'US'), '')

    def test_rename_without_sort_preserves_order(self):
        config = {
            'outbounds': [
                node('JP Tokyo vmess', 'jp.example'),
                node('us-lax-01', 'us.example'),
                {'type': 'selector', 'tag': 'select', 'outbounds': ['JP Tokyo vmess', 'us-lax-01']},
            ],
            'route': {'final': 'JP Tokyo vmess'},
        }

        result = sort_nodes.process_config(config, do_rename=True)

        tags = [o['tag'] for o in config['outbounds'] if o.get('type') in common.NODE_TYPES]
        self.assertEqual(tags, ['🇯🇵 日本_东京_1', '🇺🇸 美国_洛杉矶_1'])
        self.assertFalse(result['sorted'])
        self.assertEqual(config['route']['final'], '🇯🇵 日本_东京_1')
        common.validate_config(config)

    def test_sort_without_rename_preserves_names(self):
        config = {
            'outbounds': [
                node('US node', 'us.example'),
                node('HK node', 'hk.example'),
            ]
        }

        sort_nodes.process_config(config, do_sort=True, dedup=False, strip_detour=False)

        self.assertEqual([o['tag'] for o in config['outbounds']], ['HK node', 'US node'])


if __name__ == '__main__':
    unittest.main()
