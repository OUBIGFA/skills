# -*- coding: utf-8 -*-
"""真实内核同路径测活对照；报告不包含代理凭据。"""
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from pathlib import Path
sys.path.insert(0, os.path.abspath('scripts'))
from probe_singbox import load_singbox_nodes
from core import mihomo_runner, singbox_runner
from core.liveness import check_alive
HERE = Path(__file__).resolve().parent
SOURCE = Path(r'D:\Data\Desktop\_scratch\test.json')
_, proxies, skipped = load_singbox_nodes(SOURCE)
iface = mihomo_runner.detect_physical_interface()
if sys.platform == 'win32' and not iface:
    raise RuntimeError('No physical interface detected; refusing a TUN-contaminated comparison')
started = time.monotonic()
records = {i: {'name': p['name'], 'type': p['type'], 'network': p.get('network')} for i, p in enumerate(proxies)}
with ExitStack() as stack:
    relay_port = stack.enter_context(mihomo_runner.direct_listener(iface)) if iface else None
    mports, mfailed = mihomo_runner.start_node_group(
        stack, [(i, {k: v for k, v in p.items() if not k.startswith('_')}, None) for i, p in enumerate(proxies)], iface=iface)
    sports, sfailed = singbox_runner.start_singbox_group(
        stack, [(i, p['_singbox_outbound'], None) for i, p in enumerate(proxies)],
        relay=('127.0.0.1', relay_port) if relay_port else None)
    print(f'iface={iface}; parsed={len(proxies)}; skipped={skipped}; loaded mihomo={len(mports)}, sing-box={len(sports)}', flush=True)
    for kernel, failures in (('mihomo', mfailed), ('sing-box', sfailed)):
        for i, reason in failures.items():
            records[i][kernel] = {'alive': False, 'load_error': reason}
    ports = {'mihomo': mports, 'sing-box': sports}
    with ThreadPoolExecutor(max_workers=16) as pool:
        jobs = {pool.submit(check_alive, f'http://127.0.0.1:{port}'): (kernel, i)
                for kernel, mapping in ports.items() for i, port in mapping.items()}
        for future in as_completed(jobs):
            kernel, i = jobs[future]
            records[i][kernel] = future.result()
    for i, row in records.items():
        if row['mihomo']['alive'] != row['sing-box']['alive']:
            for kernel in ports:
                if i in ports[kernel]:
                    row[kernel]['recheck'] = check_alive(f'http://127.0.0.1:{ports[kernel][i]}')
        summary = []
        for kernel in ports:
            res = row[kernel].get('recheck', row[kernel])
            summary.append('{}={} ({}ms)'.format(kernel, 'OK' if res['alive'] else 'DEAD', res.get('latency_ms')))
        print('{}: {}'.format(row['name'], ' | '.join(summary)), flush=True)
report = {'input_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'iface': iface,
          'seconds': round(time.monotonic() - started, 1), 'skipped': skipped, 'nodes': list(records.values())}
(HERE / 'resume_kernel_compare.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('compare_seconds={}'.format(report['seconds']), flush=True)