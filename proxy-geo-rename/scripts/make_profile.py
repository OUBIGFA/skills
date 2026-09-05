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
import copy
import json
import os
import sys

from common import (NODE_TYPES, deduplicate_nodes, ensure_utf8_stdout,
                    validate_config, write_config)

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


def build_profile(source, exclude=None, keep_dead=False):
    drop = set(exclude or [])
    nodes = []
    dropped = []
    used_tags = set()
    for outbound in source.get('outbounds', []):
        if outbound.get('type') not in NODE_TYPES:
            continue
        if outbound.get('tag') in drop and not keep_dead:
            dropped.append(outbound['tag'])
            continue
        node = copy.deepcopy(outbound)
        node.pop('domain_resolver', None)
        node.pop('detour', None)
        base = node.get('tag') or 'node'
        tag = base
        index = 2
        while tag in used_tags:
            tag = f'{base}#{index}'
            index += 1
        node['tag'] = tag
        used_tags.add(tag)
        nodes.append(node)
    if not nodes:
        raise ValueError('未找到节点')

    config = {'outbounds': nodes}
    deduplicate_nodes(config)
    tags = [node['tag'] for node in config['outbounds']]
    config['outbounds'].extend([
        {'type': 'urltest', 'tag': '♻️ 自动选择', 'outbounds': tags,
         'url': 'https://www.gstatic.com/generate_204', 'interval': '10m',
         'tolerance': 50},
        {'type': 'selector', 'tag': '🚀 节点选择',
         'outbounds': ['♻️ 自动选择'] + tags, 'default': '♻️ 自动选择'},
    ])
    config['route'] = {'final': '🚀 节点选择'}
    validate_config(config)
    return config, dropped


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
    try:
        cfg, dropped = build_profile(d, drop, a.keep_dead)
    except ValueError as error:
        print(error)
        sys.exit(1)
    changed, _ = write_config(out, cfg, style_from=src)
    print(f'已生成：{out}')
    node_count = sum(1 for item in cfg['outbounds'] if item.get('type') in NODE_TYPES)
    print(f'保留节点 {node_count} 个' + (f'，剔除 {len(dropped)} 个：{dropped}' if dropped else ''))
    if not changed:
        print('输出内容无变化，未重写文件')
    print('说明：入站/DNS/路由/实验性配置一律不写入，由客户端自行生成，避免冲突。')
    print('注意：客户端定制字段（tls_tricks、tls_fragment 等）已原样保留——'
          '官方 sing-box 内核校验会报未知字段，属正常，导入定制客户端即可用。')


if __name__ == '__main__':
    main()
