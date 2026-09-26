class PipelineIntegrationTests(unittest.TestCase):
    """两条流水线共用 core.probe_flow 的服务检测，属地结论均取自共享的 probe_geolocation。"""

    @staticmethod
    def listeners(stack, entries, **kwargs):
        return {key: 12345 for key, _, _ in entries}, {}

    @staticmethod
    def shared_flow(result, ai=None):
        stack = ExitStack()
        flow = 'core.probe_flow'
        stack.enter_context(patch(f'{flow}.check_alive', return_value={'alive': True, 'latency_ms': 80.0, 'attempts': []}))
        stack.enter_context(patch(f'{flow}.probe_runner_baseline', return_value={IP2}))
        stack.enter_context(patch(f'{flow}.probe_egress', side_effect=[egress()]))
        shared = stack.enter_context(patch(f'{flow}.probe_geolocation', return_value=result))
        if ai is not None:
            stack.enter_context(patch(f'{flow}.probe_all_ai', return_value=ai))
        stack.enter_context(patch('builtins.print'))
        return stack, shared

    @patch.object(sys, 'platform', 'linux')
    def test_mihomo_report_retains_shared_evidence(self):
        module = importlib.import_module('probe_services')
        node = {'name': '🇸🇬 新加坡_4', 'type': 'vless', 'server': IP, 'port': 443}
        result = {'cc': 'JP', 'exit_ip': IP, 'google_region': {'country_code': 'JP'},
                  'geo_decision': {'egress_stable': True, 'is_pool': False}, 'ip_info': info(),
                  'ip_info_by_ip': {IP: info()}, 'egress': egress(), 'egress_after': egress()}
        stack, shared = self.shared_flow(result)
        with stack, tempfile.TemporaryDirectory() as temp, \
                patch.object(module, 'load_proxies', return_value=[node]), \
                patch.object(module, 'find_mihomo_bin', return_value='test-kernel'), \
                patch('core.mihomo_runner.start_node_group', self.listeners):
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
        ai = {'ai_supported': True, 'details': {}, 'observations': {}}
        stack, shared = self.shared_flow(result, ai=ai)
        with stack, tempfile.TemporaryDirectory() as temp, \
                patch.object(module, 'find_singbox_bin', return_value='sing-box'), \
                patch.object(module, 'find_mihomo_bin', return_value='test-kernel'), \
                patch.object(module, 'start_physical_relay', return_value=None), \
                patch('core.singbox_runner.start_singbox_group', self.listeners), \
                patch('core.singbox_runner.find_singbox_bin', return_value=None):
            source, report = Path(temp) / 'in.json', Path(temp) / 'report.json'
            source.write_text(json.dumps({'outbounds': [
                {'type': 'vless', 'tag': '🇸🇬 新加坡_4', 'server': IP, 'server_port': 443,
                 'uuid': '00000000-0000-0000-0000-000000000001'}]}, ensure_ascii=False), encoding='utf-8')
            argv = ['--input', str(source), '--output', str(Path(temp) / 'out.json'), '--tests', 'ip,ai',
                    '--report', str(report)]
            self.assertEqual(module.main(argv), 0)
            saved = json.loads(report.read_text(encoding='utf-8'))['results'][0]
        # 原名国旗 (新加坡) 不参与定国；出口不稳定/轮换池时 AI 全通资格被剥离
        self.assertEqual(saved['cc'], 'UNK')
        self.assertFalse(saved['ai_supported'])
        shared.assert_called_once()


if __name__ == '__main__':
    unittest.main()
