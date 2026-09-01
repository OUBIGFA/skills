# -*- coding: utf-8 -*-
"""
从客户端运行时导出的配置中提取干净的可导入订阅配置。

用途：GUI 客户端（karing 等）"导出配置"给出的是**运行时快照**，含客户端自己的
入站端口、fakeip、clash_api、遥测规则、导出时的公网 IP 等内部产物。把它再导入
回客户端，会与客户端正在使用的同名端口/组件冲突，表现为大量节点显示不可用——
节点本身没问题。本脚本只保留节点本体，其余交给客户端自行生成。

用法：
  python make_profile.py --config <运行时导出.json> [--out <输出.json>]
                         [--exclude 节点A,节点B] [--keep-dead]
"""
import argparse
import json
import os
import sys

from common import ensure_utf8_stdout
from probe import NODE_TYPES

ensure_utf8_stdout()

# 客户端运行时快照的特征（命中越多越确定）
DUMP_SIGNS = [
    ('inbounds', '含客户端自己的入站监听端口'),
    ('experimental', '含 clash_api / 统计 / 缓存等客户端内部组件'),
]


def detect_dump(d):
    hits = [why for key, why in DUMP_SIGNS if d.get(key)]
    for s in d.get('dns', {}).get('servers', []):
        if s.get('type') == 'fakeip':
            hits.append('含 fakeip（客户端专有）')
            break
    for r in d.get('dns', {}).get('rules', []):
        if r.get('client_subnet'):
            hits.append(f"含导出时的公网 IP：{r['client_subnet']}")
            break
    return hits


def main():
    ap = argparse.ArgumentParser(description='提取干净的可导入配置')
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', default=None, help='默认为 <原名>_clean.json')
    ap.add_argument('--exclude', default='', help='逗号分隔，要剔除的节点名（如已确认失效的）')
    ap.add_argument('--keep-dead', action='store_true',
                    help='保留 --exclude 指定的节点（仅打印提示不剔除）')
    a = ap.parse_args()

    src = os.path.abspath(a.config)
    out = a.out or (src[:-5] if src.lower().endswith('.json') else src) + '_clean.json'
    d = json.load(open(src, encoding='utf-8'))

    hits = detect_dump(d)
    if hits:
        print('检测到这是客户端运行时导出的配置：')
        for h in hits:
            print('  -', h)
        print('直接导回客户端会冲突，本脚本将只保留节点本体。\n')

    drop = {x.strip() for x in a.exclude.split(',') if x.strip()}
    nodes, dropped = [], []
    for o in d.get('outbounds', []):
        if o.get('type') not in NODE_TYPES:
            continue
        if o.get('tag') in drop and not a.keep_dead:
            dropped.append(o['tag'])
            continue
        # domain_resolver 指向的是快照内部的 DNS 标签，脱离快照即为悬空引用；detour 为链式前置，一并剔除
        nodes.append({k: v for k, v in o.items() if k not in ('domain_resolver', 'detour')})
    if not nodes:
        print('未找到节点')
        sys.exit(1)

    tags = [n['tag'] for n in nodes]
    cfg = {'outbounds': nodes + [
        {'type': 'urltest', 'tag': '♻️ 自动选择', 'outbounds': tags,
         'url': 'https://www.gstatic.com/generate_204', 'interval': '10m',
         'tolerance': 50},
        {'type': 'selector', 'tag': '🚀 节点选择',
         'outbounds': ['♻️ 自动选择'] + tags, 'default': '♻️ 自动选择'},
    ], 'route': {'final': '🚀 节点选择'}}

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'已生成：{out}')
    print(f'保留节点 {len(nodes)} 个' + (f'，剔除 {len(dropped)} 个：{dropped}' if dropped else ''))
    print('说明：入站/DNS/路由/实验性配置一律不写入，由客户端自行生成，避免冲突。')
    print('注意：客户端定制字段（tls_tricks、tls_fragment 等）已原样保留——'
          '官方 sing-box 内核校验会报未知字段，属正常，导入定制客户端即可用。')


if __name__ == '__main__':
    main()
