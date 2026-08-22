# -*- coding: utf-8 -*-
"""
合并多个订阅/配置到一个底库，按连接身份去重，并统一命名排序。

去重看的是**连接身份**（协议+地址+端口+凭据+传输方式+SNI），不看名字——
同一个节点在不同订阅里往往名字完全不同，按名字去重会漏；而同址同端口但凭据
不同的是真的两个节点，按地址去重会误删。

默认会顺带做统一命名与地区排序（合并后正是要做的事），只想合并就加 --no-rename。

用法：
  python merge_configs.py --base <底库.json> --add <订阅1.json> <订阅2.json> [--apply]
  python merge_configs.py --base <底库.json> --add *.json --out <新文件.json> --apply

常用选项：
  --out           合并结果写到新文件，底库保持不动
  --no-rename     只合并去重，不改名不排序
  --keep-base-dup 保留底库自身已有的重复节点（默认一并清理）
"""
import argparse
import json
import os
import shutil
import sys
import time

from common import ensure_utf8_stdout
from probe import NODE_TYPES

ensure_utf8_stdout()


def sig(o):
    """节点的连接身份指纹。地址统一小写并去掉末尾的点（DNS 根点写法差异）。"""
    cred = (o.get('password') or o.get('uuid') or o.get('auth_str')
            or o.get('username') or o.get('private_key') or '')
    tr = o.get('transport') or {}
    tls = o.get('tls') or {}
    return (o.get('type'), str(o.get('server', '')).lower().rstrip('.'),
            o.get('server_port'), str(cred), o.get('method', ''),
            tr.get('type', ''), tr.get('path', ''), tls.get('server_name', ''))


def load_nodes(path):
    d = json.load(open(path, encoding='utf-8'))
    if 'outbounds' not in d:
        print(f'{os.path.basename(path)}：不是 sing-box 配置（没有 outbounds），跳过')
        return d, []
    return d, [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]


def sanitize(node, base_dns_tags, merged_tags):
    """摘掉指向源配置内部、在底库里不存在的引用，避免合并后出现悬空引用。"""
    n = dict(node)
    dr = n.get('domain_resolver')
    tag = dr.get('server') if isinstance(dr, dict) else dr
    if tag and tag not in base_dns_tags:
        n.pop('domain_resolver', None)
    if n.get('detour') and n['detour'] not in merged_tags:
        n.pop('detour', None)      # 链式代理的前置不在合并范围内，降级为直接连接
    return n


def main():
    ap = argparse.ArgumentParser(description='合并多个订阅并按连接身份去重')
    ap.add_argument('--base', required=True, help='底库配置（结果以它的设置为准）')
    ap.add_argument('--add', nargs='+', required=True, help='要并入的配置，可多个')
    ap.add_argument('--out', default=None, help='结果写到新文件（默认就地更新底库）')
    ap.add_argument('--apply', action='store_true', help='实际写入（默认仅预览）')
    ap.add_argument('--no-rename', dest='rename', action='store_false',
                    help='只合并去重，不做统一命名与排序')
    ap.add_argument('--keep-base-dup', action='store_true',
                    help='保留底库自身的重复节点')
    a = ap.parse_args()

    base_path = os.path.abspath(a.base)
    base, nodes = load_nodes(base_path)
    if not nodes:
        print('底库里没有节点')
        sys.exit(1)
    base_dns_tags = {s.get('tag') for s in base.get('dns', {}).get('servers', [])}

    # 底库自身去重
    seen, base_dup = {}, {}
    for o in nodes:
        s = sig(o)
        if s in seen:
            base_dup[o['tag']] = seen[s]
        else:
            seen[s] = o['tag']
    print(f'底库 {os.path.basename(base_path)}：{len(nodes)} 个节点')
    if base_dup:
        word = '保留' if a.keep_base_dup else '清理'
        print(f'  自身重复 {len(base_dup)} 个（将{word}）：')
        for k, v in base_dup.items():
            print(f'    {k}  ≡  {v}')

    tags = {o.get('tag') for o in base['outbounds']}
    added, skipped = [], []
    for path in a.add:
        p = os.path.abspath(path)
        if os.path.samefile(p, base_path) if os.path.exists(p) else False:
            print(f'{os.path.basename(p)}：与底库是同一个文件，跳过')
            continue
        _, ns = load_nodes(p)
        n0 = len(added)
        for o in ns:
            s = sig(o)
            if s in seen:
                skipped.append((os.path.basename(p), o['tag'], seen[s]))
                continue
            n = sanitize(o, base_dns_tags, tags)
            t, i = n.get('tag', 'node'), 2
            while t in tags:            # 先保证唯一，稍后统一改名
                t = f"{n.get('tag', 'node')}#{i}"
                i += 1
            n['tag'] = t
            tags.add(t)
            seen[s] = t
            added.append(n)
        print(f'{os.path.basename(p)}：{len(ns)} 个节点 → 新增 {len(added) - n0} 个')

    if skipped:
        print(f'\n去重跳过 {len(skipped)} 个（连接信息与已有节点完全相同）：')
        for src, tag, hit in skipped:
            print(f'  [{src}] {tag}  ≡  {hit}')

    drop = {} if a.keep_base_dup else base_dup
    total = len(nodes) - len(drop) + len(added)
    print(f'\n合并结果：{len(nodes)} - {len(drop)} + {len(added)} = {total} 个节点')
    if not a.apply:
        print('\n[预览] 未写入。确认无误后加 --apply')
        return

    if drop:  # 重复节点删掉，引用改指向保留的那个
        base['outbounds'] = [o for o in base['outbounds'] if o.get('tag') not in drop]
        for o in base['outbounds']:
            if o.get('outbounds'):
                o['outbounds'] = [t for t in o['outbounds'] if t not in drop]
            for k in ('default', 'detour'):
                if o.get(k) in drop:
                    o[k] = drop[o[k]]
        rt = base.get('route', {})
        if rt.get('final') in drop:
            rt['final'] = drop[rt['final']]
        for ru in rt.get('rules', []):
            if ru.get('outbound') in drop:
                ru['outbound'] = drop[ru['outbound']]
        for sv in base.get('dns', {}).get('servers', []):
            if sv.get('detour') in drop:
                sv['detour'] = drop[sv['detour']]

    # 新节点接在最后一个节点之后，各分组同步追加成员
    idx = [i for i, o in enumerate(base['outbounds']) if o.get('type') in NODE_TYPES]
    base['outbounds'][idx[-1] + 1:idx[-1] + 1] = added
    for o in base['outbounds']:
        if o.get('type') in ('selector', 'urltest'):
            o['outbounds'] = o.get('outbounds', []) + [n['tag'] for n in added]

    dst = os.path.abspath(a.out) if a.out else base_path
    raw = open(base_path, 'rb').read()
    if dst == base_path:
        bak = base_path[:-5] + f'.backup.{time.strftime("%Y%m%d-%H%M%S")}.json'
        shutil.copy2(base_path, bak)
        print(f'\n已备份：{os.path.basename(bak)}')
    out = json.dumps(base, ensure_ascii=False, indent=2)
    if b'\r\n' in raw:
        out = out.replace('\n', '\r\n')
    open(dst, 'wb').write(out.encode('utf-8'))

    d2 = json.load(open(dst, encoding='utf-8'))
    at = [o['tag'] for o in d2['outbounds']]
    assert len(at) == len(set(at)), '合并后存在重名'
    ts = set(at)
    for o in d2['outbounds']:
        for t in o.get('outbounds', []):
            assert t in ts, f'分组引用缺失: {t}'
    print(f'合并完成并校验通过：{dst}')

    if a.rename:
        print('\n--- 统一命名与地区排序 ---')
        sys.argv = ['sort_nodes.py', '--config', dst, '--apply']
        import sort_nodes
        sort_nodes.main()


if __name__ == '__main__':
    main()
