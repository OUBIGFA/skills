# -*- coding: utf-8 -*-
"""
延迟仲裁（数据库投票分歧时使用）：通过节点对各城市锚点做真实 TLS 握手计时，
锚点间耗时差反映出口到各城市的物理距离——数据库标注可以造假，光速不能。

用法：python latency_arbiter.py --workdir <目录> [--targets 节点A,节点B] [--region eu]

默认自动选目标：全部中/低置信节点 + 1 个高置信节点做标定。
标定节点用于验证锚点有效性与测量噪声（其最近锚点应与已知位置相符；
同一节点内小于约 40ms 的锚点差在噪声范围内，只有明显的梯度才可采信）。
结果由使用者解读后写入 overrides.json 交给 rename.py。
"""
import argparse
import json
import os
import socket
import ssl
import time

from common import ensure_utf8_stdout, load_session, start_kernel
from geodata import ANCHORS

ensure_utf8_stdout()

# 仅测耗时，不校验证书
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def connect_rtt(port, host, tries=5):
    """经本地代理端口 CONNECT 锚点后做真实 TLS 握手并计时(ms)。
    代理对 CONNECT 是延迟拨号（立即回 200 不代表已连上），必须用握手触发
    真实往返；同节点内比较不同锚点的耗时差，前段链路为常量。"""
    best = None
    for _ in range(tries):
        try:
            s = socket.create_connection(('127.0.0.1', port), 5)
            s.settimeout(10)
            s.sendall(f'CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n'.encode())
            buf = b''
            while b'\r\n\r\n' not in buf:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
            if b' 200' not in buf.split(b'\r\n', 1)[0]:
                s.close()
                continue
            t0 = time.perf_counter()
            ss = _CTX.wrap_socket(s, server_hostname=host)
            dt = (time.perf_counter() - t0) * 1000
            ss.close()
            best = dt if best is None else min(best, dt)
        except Exception:
            pass
    return best


def measure(tag, port, anchors):
    print(f'\n{tag} (port {port}):', flush=True)
    rows = []
    for name, host in anchors.items():
        r = connect_rtt(port, host)
        rows.append([name, r])
        print(f"  {name:14s} {('%.0f ms' % r) if r is not None else '不通'}", flush=True)
    ok = sorted([x for x in rows if x[1] is not None], key=lambda x: x[1])
    if ok:
        print('  => 最近: ' + ' < '.join(f'{n}({r:.0f})' for n, r in ok), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description='存疑节点延迟仲裁')
    ap.add_argument('--workdir', required=True, help='probe.py 使用的工作目录')
    ap.add_argument('--targets', default=None, help='逗号分隔的节点名（默认自动选择）')
    ap.add_argument('--region', default='all', choices=['all', 'eu', 'na', 'as'],
                    help='锚点大洲（默认全部；已知出口大致方位时可缩小范围提速）')
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    s = load_session(workdir)

    final = os.path.join(workdir, 'probe_result_final.json')
    src = final if os.path.exists(final) else os.path.join(workdir, 'probe_result.json')
    recs = json.load(open(src, encoding='utf-8'))
    by_tag = {r['tag']: r for r in recs}

    if a.targets:
        targets = [t.strip() for t in a.targets.split(',') if t.strip()]
    else:
        calib = next((r['tag'] for r in recs
                      if r.get('conf') == 'high' and r.get('colo_rel') == 'same-country'), None)
        doubt = [r['tag'] for r in recs if r.get('conf') in ('low', 'medium')]
        targets = ([calib] if calib else []) + doubt
        if calib:
            print(f'标定节点（位置已确认，用于验证锚点与噪声）: {calib}')
    if not targets:
        print('没有需要仲裁的节点')
        return

    anchors = {}
    for region, table in ANCHORS.items():
        if a.region == 'all' or a.region.upper() == region:
            anchors.update(table)

    proc = start_kernel(s['singbox'], os.path.join(workdir, 'test_config.json'),
                        workdir, 'singbox_arbiter.log', s['base_port'])
    out = {}
    try:
        for t in targets:
            r = by_tag.get(t)
            if r and r.get('port'):
                out[t] = measure(t, r['port'], anchors)
            elif r and r.get('via_front'):
                print(f'跳过 {t}（经中转复活的节点无固定测试端口，且中转链路延迟噪声大，'
                      f'物理测距不适用——其出口判定依赖多库投票即可）')
            else:
                print(f'跳过 {t}（离线或不存在）')
    finally:
        proc.terminate()
    with open(os.path.join(workdir, 'latency_arbiter.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\n仲裁数据已写入 latency_arbiter.json')
    print('解读后将终裁写入 overrides.json（格式见 SKILL.md），再运行 rename.py')


if __name__ == '__main__':
    main()
