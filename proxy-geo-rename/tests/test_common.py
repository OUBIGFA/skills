# -*- coding: utf-8 -*-
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import common


def node(tag, server, password='secret'):
    return {
        'type': 'trojan',
        'tag': tag,
        'server': server,
        'server_port': 443,
        'password': password,
    }


class CommonConfigTests(unittest.TestCase):
    def test_signature_distinguishes_all_connection_fields(self):
        first = node('A', 'same.example', password='secret')
        first['username'] = 'alice'
        second = copy.deepcopy(first)
        second['tag'] = 'B'
        second['username'] = 'bob'
        self.assertNotEqual(common.sig(first), common.sig(second))

    def test_signature_ignores_tag_and_removed_runtime_links(self):
        first = node('A', 'same.example')
        first.update({'detour': 'front-a', 'domain_resolver': 'dns-a'})
        second = copy.deepcopy(first)
        second.update({'tag': 'B', 'detour': 'front-b', 'domain_resolver': 'dns-b'})
        self.assertEqual(common.sig(first), common.sig(second))

    def test_deduplicate_same_tag_keeps_one_node_and_valid_references(self):
        config = {
            'outbounds': [
                node('A', 'same.example'),
                node('A', 'same.example'),
                node('B', 'other.example'),
                {
                    'type': 'selector',
                    'tag': 'select',
                    'outbounds': ['A', 'A', 'B'],
                    'default': 'A',
                },
                {'type': 'direct', 'tag': 'direct', 'detour': 'A'},
            ],
            'route': {
                'final': 'A',
                'rules': [{'outbound': 'A'}],
            },
            'dns': {'servers': [{'tag': 'dns', 'address': '1.1.1.1', 'detour': 'A'}]},
        }

        removed = common.deduplicate_nodes(config)

        self.assertEqual(removed, [('A', 'A')])
        self.assertEqual(
            [o['tag'] for o in config['outbounds'] if o.get('type') in common.NODE_TYPES],
            ['A', 'B'],
        )
        self.assertEqual(config['outbounds'][2]['outbounds'], ['A', 'B'])
        common.validate_config(config)

    def test_remap_refs_updates_every_supported_reference(self):
        config = {
            'outbounds': [
                node('old', 'one.example'),
                {
                    'type': 'selector',
                    'tag': 'select',
                    'outbounds': ['old'],
                    'default': 'old',
                    'detour': 'old',
                },
            ],
            'route': {
                'final': 'old',
                'rules': [
                    {'outbound': 'old'},
                    {'rules': [{'outbound': 'old'}]},
                ],
            },
            'dns': {'servers': [{'tag': 'dns', 'address': '1.1.1.1', 'detour': 'old'}]},
        }

        common.remap_refs(config, {'old': 'new'})

        selector = config['outbounds'][1]
        self.assertEqual(selector['outbounds'], ['new'])
        self.assertEqual(selector['default'], 'new')
        self.assertEqual(selector['detour'], 'new')
        self.assertEqual(config['route']['final'], 'new')
        self.assertEqual(config['route']['rules'][0]['outbound'], 'new')
        self.assertEqual(config['route']['rules'][1]['rules'][0]['outbound'], 'new')
        self.assertEqual(config['dns']['servers'][0]['detour'], 'new')

    def test_validate_config_rejects_non_member_default(self):
        config = {
            'outbounds': [
                node('A', 'one.example'),
                {'type': 'selector', 'tag': 'select', 'outbounds': ['A'], 'default': 'missing'},
            ]
        }

        with self.assertRaisesRegex(ValueError, 'default.*missing'):
            common.validate_config(config)

    def test_write_config_skips_unchanged_file_without_backup(self):
        config = {'outbounds': [node('A', 'one.example')]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            original = json.dumps(config, ensure_ascii=False, indent=4) + '\n'
            path.write_text(original, encoding='utf-8', newline='')

            changed, backup = common.write_config(str(path), copy.deepcopy(config), backup=True)

            self.assertFalse(changed)
            self.assertIsNone(backup)
            self.assertEqual(path.read_text(encoding='utf-8'), original)
            self.assertEqual(list(path.parent.glob('*.backup.*.json')), [])

    def test_write_config_preserves_indent_crlf_and_trailing_newline(self):
        original_config = {'outbounds': [node('A', 'one.example')]}
        changed_config = copy.deepcopy(original_config)
        changed_config['route'] = {'final': 'A'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            original = json.dumps(original_config, ensure_ascii=False, indent=4).replace('\n', '\r\n') + '\r\n'
            path.write_bytes(original.encode('utf-8'))

            changed, backup = common.write_config(str(path), changed_config, backup=True)

            self.assertTrue(changed)
            self.assertIsNotNone(backup)
            raw = path.read_bytes()
            self.assertIn(b'\r\n    \"outbounds\"', raw)
            self.assertTrue(raw.endswith(b'\r\n'))
            self.assertEqual(Path(backup).read_bytes(), original.encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
