import importlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import egress_geo as geo
from core.ai_probe import probe_gemini
from audit_geolocation import parse_ipcx, review_status, select_sample

IP = '43.167.208.94'
IP2 = '8.8.8.8'
V6 = '2606:4700:4700::1111'


def record(provider, cc, ip=IP):
    return {'provider': provider, 'family': provider, 'status': 'ok', 'cc': cc, 'ip': ip}


def egress(ip=IP):
    family = 'ipv6' if ':' in ip else 'ipv4'
    result = {'ipv4': {'ip': None}, 'ipv6': {'ip': None}, 'observed_ips': [ip],
              'cf_trace': {'status': 'ok', 'ip': ip, 'loc': 'JP', 'colo': 'SIN', 'colo_cc': 'SG'}}
    result[family]['ip'] = ip
    return result


def info(cc='JP', ip=IP):
    records = [record('ipinfo', cc, ip), record('ipwhois', cc, ip)]
    return {**geo.geo_consensus(records), 'ip': ip, 'records': records}


class GoogleRegionTests(unittest.TestCase):
    def test_gemini_plain_escaped_and_whitespace(self):
        for text in [',2,1,200,"JPN" [45631641,null,true]',
                     r',2,1,200,\"JPN\" [45631641,null,true]',
                     ', 2, 1, 200, "JPN" [45631641, null, true]']:
            result = geo.parse_gemini_region(text)
            self.assertEqual(result['country_code'], 'JP')
            self.assertTrue(result['gemini_available'])

    def test_ambiguous_or_invalid_gemini_is_unknown(self):
        self.assertIsNone(geo.parse_gemini_region(',2,1,200,"USA",2,1,200,"JPN"')['country_code'])
        self.assertIsNone(geo.parse_gemini_region(',2,1,200,"ZZZ"')['country_code'])

    def test_youtube_requires_unique_matching_pair(self):
        valid = '"INNERTUBE_CONTEXT_GL":"JP","countryCode":"JP"'
        self.assertEqual(geo.parse_youtube_region(valid)['country_code'], 'JP')
        for text in ['"INNERTUBE_CONTEXT_GL":"US"', valid + ',"countryCode":"US"',
                     '"INNERTUBE_CONTEXT_GL":"US","countryCode":"JP"', '<html>en-US</html>']:
            self.assertIsNone(geo.parse_youtube_region(text)['country_code'])

    @patch.object(geo, 'fetch_evidence')
    def test_no_google_com_us_vote_and_gemini_beats_yt_default(self, fetch):
        fetch.side_effect = [({'status': 'ok'}, ',2,1,200,"JPN"'),
                             ({'status': 'ok'}, '"INNERTUBE_CONTEXT_GL":"US"')]
        result = geo.probe_google_region({})
        self.assertEqual(result['country_code'], 'JP')
        self.assertEqual(result['source'], 'gemini_page')
        self.assertIsNone(result['details']['google_search'])
        self.assertEqual(fetch.call_count, 2)

    @patch.object(geo, 'fetch_evidence')
    def test_china_cannot_be_outvoted(self, fetch):
        fetch.side_effect = [({'status': 'ok'}, ',2,1,200,"CHN" [45631641,null,true]'),
                             ({'status': 'ok'}, '"INNERTUBE_CONTEXT_GL":"JP","countryCode":"JP"')]
        result = geo.probe_google_region({})
        self.assertEqual(result['country_code'], 'CN')
        self.assertTrue(result['is_sent_to_china'])
        self.assertTrue(result['conflict'])
        self.assertFalse(result['gemini_available'])

    @patch.object(geo, 'probe_google_region', return_value={'source': None, 'gemini_available': None})
    def test_missing_marker_does_not_recurse(self, probe):
        self.assertEqual(probe_gemini({})['status'], 'unknown')
        probe.assert_called_once()
        probe.reset_mock()
        self.assertEqual(probe_gemini({}, {'source': 'youtube_premium'})['status'], 'unknown')
        probe.assert_not_called()


class GeoEvidenceTests(unittest.TestCase):
    def test_reputation_score_is_strictly_validated(self):
        self.assertEqual(geo.valid_reputation_score(88), 88)
        for value in (True, "88", -1, 101, float("nan"), None):
            self.assertIsNone(geo.valid_reputation_score(value))

    def test_rotating_exit_reputation_uses_worst_complete_score(self):
        infos = {IP: {"reputation": {"score": 90}}, IP2: {"reputation": {"score": 35}}}
        result = geo.reputation_for_exits(infos, [IP, IP2])
        self.assertEqual(result["score"], 35)
        self.assertEqual(result["status"], "observed")
        result = geo.reputation_for_exits({IP: infos[IP]}, [IP, IP2])
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "unknown")

    def test_free_tier_and_nested_ipapi_schema(self):
        for data in [{'ip': IP, 'country': 'Japan', 'asn': 'AS132203'},
                     {'ip': IP, 'location': {'country_code': 'JP'}, 'asn': {'country': 'SG'}}]:
            self.assertEqual(geo.parse_geo_record('ipapi.is', data, IP)['cc'], 'JP')
        self.assertEqual(geo.parse_geo_record('ipapi.is', {'ip': IP, 'location': None, 'asn': {'country': 'SG'}}, IP)['status'], 'invalid')

    def test_query_ip_binding_and_provider_errors(self):
        for data in [{'ip': IP2, 'country': 'US'}, {'country': 'JP'}, {'ip': IP, 'bogon': True},
                     {'ip': IP, 'error': 'rate limited'}, {'ip': IP, 'success': False}, []]:
            self.assertNotEqual(geo.parse_geo_record('ipinfo', data, IP)['status'], 'ok')
        self.assertEqual(geo.parse_geo_record('dbip', {'ipAddress': IP, 'countryCode': 'JP'}, IP)['cc'], 'JP')

    def test_public_ip_rejects_error_pages_and_private_addresses(self):
        for value in ['999.1.1.1', '192.168.0.1', 'error: 8.8.8.8', '::1', None, '100.64.0.1']:
            self.assertIsNone(geo.public_ip(value))
        self.assertEqual(geo.public_ip(V6), V6)

    def test_vote_tie_single_duplicate_family_and_no_country_blacklist(self):
        self.assertEqual(geo.geo_consensus([record('a', 'JP'), record('b', 'SG')])['country_code'], 'UNK')
        self.assertEqual(geo.geo_consensus([record('a', 'JP')])['country_code'], 'UNK')
        same = [record('a', 'JP'), {**record('mirror', 'JP'), 'family': 'a'}]
        self.assertEqual(geo.geo_consensus(same)['country_code'], 'UNK')
        self.assertEqual(geo.geo_consensus([record('a', 'SC'), record('b', 'SC')])['country_code'], 'SC')
        self.assertEqual(geo.geo_consensus([record('a', 'JP'), record('b', 'JP'), record('c', 'SG')])['confidence'], 'medium')

    def test_colo_not_a_vote_and_original_label_not_evidence(self):
        cf = {'status': 'ok', 'ip': IP, 'loc': 'SG', 'colo': 'SIN', 'colo_cc': 'SG'}
        result = geo.arbitrate_geo(cf, ip_info=info(), exit_ips=[IP], orig_cc='US')
        self.assertEqual(result['cc'], 'JP')
        self.assertTrue(result['conflict'])
        self.assertTrue(result['needs_review'])
        self.assertEqual(geo.arbitrate_geo(orig_cc='SG')['cc'], 'UNK')
        self.assertEqual(geo.arbitrate_geo(cf, exit_ips=[IP])['cc'], 'UNK')

    def test_service_region_and_database_region_are_separate(self):
        google = {'country_code': 'JP', 'source': 'gemini_page'}
        result = geo.arbitrate_geo(google_region=google, ip_info=info('SG'), exit_ips=[IP])
        self.assertEqual(result['cc'], 'UNK')
        self.assertEqual(result['candidate_cc'], 'JP')
        self.assertEqual(result['geoip_cc'], 'SG')
        self.assertEqual(result['scope'], 'google_service_region')
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['confidence'], 'low')

    def test_sent_to_china_preserves_korea_and_uses_existing_poison_policy(self):
        from core.tagger import tag_and_rename_nodes
        google = {'country_code': 'CN', 'source': 'gemini_page', 'is_sent_to_china': True}
        result = geo.arbitrate_geo(google_region=google, ip_info=info('KR'), exit_ips=[IP])
        self.assertEqual(result['cc'], 'KR')
        self.assertEqual(result['scope'], 'ip_geolocation')
        self.assertTrue(result['is_poisoned'])
        self.assertEqual(result['poison_tag'], '_⚠️CN')
        row = {'proxy': {'name': '🇮🇩 印度尼西亚_3'}, 'cc': 'KR', 'geo_decision': result,
               'ai_supported': True, 'youtube_passed': True, 'shield_passed': True}
        tag_and_rename_nodes([row])
        self.assertFalse(row['ai_supported'])
        # 导出前按地区重新从 1 编号，报告名称与配置一致
        self.assertEqual(row['final_name'], '🇰🇷 韩国_1_⚠️CN')
        self.assertEqual(probe_gemini({}, google)['status'], 'blocked')
        module = importlib.import_module('probe_singbox')
        name = module.format_node_name('KR', 3, ai_supported=True, comprehensive_sparkle=True, poison_tag='_⚠️CN')
        self.assertEqual(name, '🇰🇷 韩国_3_⚠️CN')

    @patch.object(geo, 'query_ip_info', return_value=info('KR'))
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_changing_google_signal_is_not_used_to_rename(self, probe, google, lookup):
        google.side_effect = [{'country_code': 'TW', 'source': 'gemini_page'},
                              {'country_code': 'US', 'source': 'gemini_page'}]
        result = geo.probe_geolocation({})
        self.assertEqual(result['google_region']['status'], 'unstable')
        self.assertIsNone(result['google_region']['country_code'])
        self.assertEqual(result['cc'], 'KR')
        self.assertTrue(result['geo_decision']['needs_review'])
        self.assertEqual(google.call_count, 2)

    @staticmethod
    def google_obs(gemini=None, youtube=None):
        return {'country_code': gemini or youtube, 'details': {'gemini': gemini, 'youtube': youtube},
                'source': 'gemini_page' if gemini else 'youtube_premium' if youtube else None}

    @patch.object(geo, 'query_ip_info', return_value=info('SG'))
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_google_geoip_conflict_falls_back_to_gemini(self, probe, google, lookup):
        google.return_value = self.google_obs(gemini='JP', youtube='SG')
        decision = geo.probe_geolocation({})['geo_decision']
        self.assertEqual((decision['cc'], decision['flag']), ('JP', geo.flag_emoji('JP')))
        self.assertEqual(decision['basis'], 'google_fallback_gemini')
        self.assertEqual(decision['unknown_basis'], 'google_geoip_conflict')
        self.assertTrue(decision['needs_review'])

    @patch.object(geo, 'query_ip_info', return_value=geo.empty_ip_info())
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_unstable_gemini_without_geoip_uses_latest_gemini(self, probe, google, lookup):
        google.side_effect = [{**self.google_obs(gemini='TW', youtube='US'), 'conflict': True},
                              self.google_obs(gemini='US')]
        result = geo.probe_geolocation({})
        self.assertEqual(result['google_region']['status'], 'unstable')
        self.assertEqual(result['cc'], 'US')
        self.assertEqual(result['geo_decision']['unknown_basis'], 'insufficient_or_conflicting_evidence')

    @patch.object(geo, 'query_ip_info', return_value=info('SG'))
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_youtube_region_is_fallback_when_gemini_missing(self, probe, google, lookup):
        google.return_value = self.google_obs(youtube='DE')
        decision = geo.probe_geolocation({})['geo_decision']
        self.assertEqual((decision['cc'], decision['basis']), ('DE', 'google_fallback_youtube'))

    @patch.object(geo, 'query_ip_info', return_value=geo.empty_ip_info())
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_without_any_google_region_stays_unknown(self, probe, google, lookup):
        google.return_value = self.google_obs()
        result = geo.probe_geolocation({})
        self.assertEqual(result['cc'], 'UNK')
        self.assertNotIn('unknown_basis', result['geo_decision'])

    @patch.object(geo, 'query_ip_info', return_value=info('KR'))
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress', return_value=egress())
    def test_known_geoip_country_is_not_overridden(self, probe, google, lookup):
        google.return_value = self.google_obs(gemini='KR')
        decision = geo.probe_geolocation({})['geo_decision']
        self.assertEqual(decision['cc'], 'KR')
        self.assertNotIn('unknown_basis', decision)

    def test_dual_stack_is_not_rotation(self):
        self.assertFalse(geo.arbitrate_geo(exit_ips=[IP, V6])['is_pool'])
        self.assertTrue(geo.arbitrate_geo(exit_ips=[IP, IP2])['is_pool'])

    @patch.object(geo, 'fetch_evidence')
    @patch.object(geo, 'probe_cloudflare_trace')
    def test_ipv6_cf_is_not_put_into_ipv4(self, cf, fetch):
        cf.return_value = {'status': 'ok', 'ip': V6}
        fetch.side_effect = [({'status': 'ok'}, json.dumps({'ip': IP})),
                             ({'status': 'ok'}, json.dumps({'ip': V6}))]
        result = geo.probe_egress({})
        self.assertEqual(result['ipv4']['ip'], IP)
        self.assertEqual(result['ipv6']['ip'], V6)
        self.assertEqual(set(result['observed_ips']), {IP, V6})

    @patch.object(geo, 'query_ip_info')
    @patch.object(geo, 'probe_google_region')
    @patch.object(geo, 'probe_egress')
    def test_orchestration_queries_all_exits_and_marks_rotation(self, probe, google, lookup):
        probe.side_effect = [egress(IP), egress(IP2)]
        google.return_value = {'country_code': 'JP', 'source': 'gemini_page'}
        lookup.side_effect = lambda ip, timeout: info('JP' if ip == IP else 'US', ip)
        result = geo.probe_geolocation({})
        self.assertEqual(set(result['ip_info_by_ip']), {IP, IP2})
        self.assertFalse(result['geo_decision']['egress_stable'])
        self.assertTrue(result['geo_decision']['is_pool'])
        self.assertTrue(result['geo_decision']['needs_review'])

    @patch.object(geo, 'fetch_evidence', return_value=({'status': 'error', 'error': 'http_429'}, ''))
    def test_outage_is_unknown_with_diagnostics(self, fetch):
        result = geo.query_ip_info(IP)
        self.assertEqual(result['country_code'], 'UNK')
        self.assertEqual(len(result['records']), 4)
        self.assertTrue(all(r['error'] == 'http_429' for r in result['records']))


class AuditTests(unittest.TestCase):
    def test_ipcx_country_bound_to_current_ip(self):
        html = f'<span id="current-ip">{IP}</span><span>国家/地区</span><span class="dim mono">JP</span></div>'
        result = parse_ipcx(html)
        self.assertEqual(result['ip'], IP)
        self.assertEqual(result['country_code'], 'JP')
        self.assertEqual(parse_ipcx('Japan JP 8.8.8.8')['status'], 'missing_marker')

    def test_sampling_is_reproducible_and_preserves_input(self):
        proxies = [{'name': f'🇸🇬 新加坡_{i}', 'type': 'vless'} for i in range(25)]
        proxies += [{'name': '🇺🇸 链式_1', 'type': 'ss', 'dialer-proxy': 'front'}]
        before = deepcopy(proxies)
        selected = select_sample(proxies, 20, 42, ['🇸🇬 新加坡_4'])
        self.assertEqual(selected[0]['name'], '🇸🇬 新加坡_4')
        self.assertEqual(selected, select_sample(proxies, 20, 42, ['🇸🇬 新加坡_4']))
        self.assertEqual(proxies, before)
        self.assertEqual(len(selected), 20)
        self.assertTrue(all(not p.get('dialer-proxy') for p in selected))

    def test_independent_reviews_surface_a_country_correction(self):
        row = {'exit_ip': IP, 'cc': 'US', 'google_region': {'country_code': 'US'},
               'geo_decision': {'egress_stable': True, 'is_pool': False,
                                'observed_ips': [IP], 'conflict': False},
               'ipcx_review': {'ip': IP, 'country_code': 'JP'},
               'gemini_review': {'country_code': 'JP'}}
        from audit_geolocation import review_country
        self.assertEqual(review_country(row), 'JP')
        self.assertEqual(review_status(row), 'verified_correction')

    def test_failed_or_different_exit_is_not_verified(self):
        row = {'exit_ip': IP, 'cc': 'JP', 'google_region': {'country_code': 'JP'},
               'geo_decision': {'egress_stable': True, 'is_pool': False, 'observed_ips': [IP], 'conflict': False},
               'ipcx_review': {'ip': IP2, 'country_code': 'JP'}, 'gemini_review': {'country_code': 'JP'}}
        self.assertEqual(review_status(row), 'different_review_egress')
        row['ipcx_review'] = {'status': 'error'}
        self.assertEqual(review_status(row), 'insufficient_review_evidence')
        row['ipcx_review'] = {'ip': IP, 'country_code': 'JP'}
        self.assertEqual(review_status(row), 'verified')


class PipelineIntegrationTests(unittest.TestCase):
    @patch.object(sys, 'platform', 'linux')
    def test_mihomo_report_retains_shared_evidence(self):
        module = importlib.import_module('probe_services')
        node = {'name': '🇸🇬 新加坡_4', 'type': 'vless', 'server': IP, 'port': 443}
        result = {'cc': 'JP', 'exit_ip': IP, 'google_region': {'country_code': 'JP'},
                  'geo_decision': {'egress_stable': True, 'is_pool': False}, 'ip_info': info(),
                  'ip_info_by_ip': {IP: info()}, 'egress': egress(), 'egress_after': egress()}

        def listeners(stack, entries, **kwargs):
            return {key: 12345 for key, _, _ in entries}, {}

        with tempfile.TemporaryDirectory() as temp, patch.object(module, 'load_proxies', return_value=[node]), \
                patch.object(module, 'find_mihomo_bin', return_value='test-kernel'), \
                patch.object(module, 'start_node_group', listeners), \
                patch.object(module, 'check_alive', return_value={'alive': True, 'latency_ms': 80.0, 'attempts': []}), \
                patch.object(module, 'probe_runner_baseline', return_value={IP2}), \
                patch.object(module, 'probe_egress', side_effect=[egress()]), \
                patch.object(module, 'probe_geolocation', return_value=result) as shared, \
                patch('builtins.print'):
            report = Path(temp) / 'report.json'
            self.assertEqual(module.main(['--input', 'dummy', '--tests', 'ip', '--report', str(report)]), 0)
            saved = json.loads(report.read_text(encoding='utf-8'))['results'][0]
            self.assertEqual(saved['cc'], 'JP')
            self.assertEqual(saved['orig_name'], '🇸🇬 新加坡_4')
            self.assertEqual(saved['ip_info_by_ip'][IP]['country_code'], 'JP')
            self.assertEqual(saved['geo_decision'], result['geo_decision'])
            shared.assert_called_once()

    def test_singbox_uses_same_result_instead_of_old_flag(self):
        module = importlib.import_module('probe_singbox')
        result = {'cc': 'UNK', 'exit_ip': IP, 'google_region': {}, 'ip_info': geo.empty_ip_info(),
                  'geo_decision': {'egress_stable': False, 'is_pool': True}}
        target = {'raw': {'tag': '🇸🇬 新加坡_4'}, 'direct_proxies': {}, 'front_proxies': {}}
        with patch.object(module, 'fast_probe_ip', return_value=IP), \
                patch.object(module, 'run_fast_speed', return_value={'speed_kbs': 10}), \
                patch.object(module, 'probe_geolocation', return_value=result) as shared, \
                patch.object(module, 'probe_all_ai', return_value={'ai_supported': True}), \
                patch.object(module, 'probe_all_media', return_value={}):
            row = module.test_target_node(target)
        self.assertEqual(row['cc'], 'UNK')
        self.assertFalse(row['ai_supported'])
        shared.assert_called_once()


if __name__ == '__main__':
    unittest.main()
