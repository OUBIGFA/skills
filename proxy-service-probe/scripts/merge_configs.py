# -*- coding: utf-8 -*-
"""
合并多个订阅/配置到一个底库。

准则：
- 默认主动去重：自动按连接身份指纹执行去重，确保底库无重复节点（加 --keep-dup 可保留重复）。
- 默认主动剥离链式代理：自动移除代理节点上的 detour 属性，降级为直接连接（加 --keep-detour 可保留）。
- 严格不主动重命名：节点原有 Tag 100% 原样保留，仅在显式传入 --rename 时才规范化命名。
- 严格不主动排序：节点原有先后顺序 100% 原样保留，仅在显式传入 --sort 时才按地区排序。

用法：
  python merge_configs.py --base <底库.json> --add <订阅1.json> <订阅2.json> [--apply]
  python merge_configs.py --base <底库.json> --add *.json --out <新文件.json> [--sort] [--rename] [--apply]
"""
import argparse
import copy
import json
import os
import sys

from common import (NODE_TYPES, deduplicate_nodes, ensure_utf8_stdout, sig,
                    strip_node_detours, validate_config, write_config)

ensure_utf8_stdout()


def load_nodes(path):
    with open(path, encoding='utf-8-sig') as handle:
        d = json.load(handle)
    if 'outbounds' not in d:
        print(f'{os.path.basename(path)}：不是 sing-box 配置（没有 outbounds），跳过')
        return d, []
    return d, [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]


def sanitize(node, base_dns_tags, strip_detour=False):
    """清洗私有 DNS 引用；仅在显式要求时剥离 detour。"""
    n = dict(node)
    dr = n.get('domain_resolver')
    tag = dr.get('server') if isinstance(dr, dict) else dr
    if tag and tag not in base_dns_tags:
        n.pop('domain_resolver', None)
    if strip_detour:
        n.pop('detour', None)
    return n


def _unique_tag(tag, tags):
    candidate = tag or 'node'
    base = candidate
    index = 2
    while candidate in tags:
        candidate = f'{base}#{index}'
        index += 1
    return candidate


def merge_config_data(base, additions, dedup=True, dedup_base=True,
                      strip_detour=True, do_sort=False, do_rename=False):
    removed = deduplicate_nodes(base) if dedup_base else []
    base_nodes = [o for o in base.get('outbounds', []) if o.get('type') in NODE_TYPES]
    if not base_nodes:
        raise ValueError('底库里没有节点')

    base_tags = {o['tag'] for o in base_nodes}
    groups_to_extend = [
        outbound for outbound in base.get('outbounds', [])
        if isinstance(outbound.get('outbounds'), list)
        and base_tags.issubset(set(outbound['outbounds']))
    ]
    dns_tags = {s.get('tag') for s in (base.get('dns') or {}).get('servers', [])}
    tags = {o.get('tag') for o in base.get('outbounds', [])}
    seen = {sig(o): o['tag'] for o in base_nodes}
    added = []
    skipped = []

    for source in additions:
        for original in source:
            fingerprint = sig(original)
            if dedup and fingerprint in seen:
                skipped.append((original.get('tag'), seen[fingerprint]))
                continue
            node = sanitize(copy.deepcopy(original), dns_tags, strip_detour)
            node['tag'] = _unique_tag(node.get('tag'), tags)
            tags.add(node['tag'])
            seen[fingerprint] = node['tag']
            added.append(node)

    if strip_detour:
        strip_node_detours(base)
    node_indexes = [
        index for index, outbound in enumerate(base['outbounds'])
        if outbound.get('type') in NODE_TYPES
    ]
    insert_at = node_indexes[-1] + 1
    base['outbounds'][insert_at:insert_at] = added
    added_tags = [node['tag'] for node in added]
    for group in groups_to_extend:
        group['outbounds'].extend(added_tags)

    postprocess = None
    if do_sort or do_rename:
        from sort_nodes import process_config
        postprocess = process_config(
            base, do_sort=do_sort, do_rename=do_rename,
            dedup=False, strip_detour=False,
        )
    validate_config(base)
    return {
        'removed': removed,
        'skipped': skipped,
        'added': added_tags,
        'postprocess': postprocess,
    }


def main():
    ap = argparse.ArgumentParser(description='合并多个订阅配置（默认自动去重与剥离 detour，严格不主动改名与排序）')
    ap.add_argument('--base', required=True, help='底库配置（结果以它的设置为准）')
    ap.add_argument('--add', nargs='+', required=True, help='要并入的配置，可多个')
    ap.add_argument('--out', default=None, help='结果写到新文件（默认就地更新底库）')
    ap.add_argument('--apply', action='store_true', help='实际写入（默认仅预览）')
    ap.add_argument('--no-dedup', '--keep-dup', dest='dedup', action='store_false',
                    help='保留重复节点（默认自动按连接身份指纹去重）')
    ap.add_argument('--dedup', dest='dedup', action='store_true',
                    help='按连接身份指纹去重（默认即启用）')
    ap.add_argument('--keep-base-dup', dest='dedup_base', action='store_false',
                    help='保留底库原有的重复节点（默认一并清理）')
    ap.add_argument('--keep-detour', dest='strip_detour', action='store_false',
                    help='保留代理节点的 detour 链式代理（默认自动剥离降级直连）')
    ap.add_argument('--strip-detour', dest='strip_detour', action='store_true',
                    help='移除代理节点的 detour 链式前置（默认即启用）')
    ap.add_argument('--sort', action='store_true', help='合并后按地区排序（默认保持原序，严格按需）')
    ap.add_argument('--rename', action='store_true', help='合并后按地区规范化重命名（默认保持原名，严格按需）')
    ap.set_defaults(dedup=True, dedup_base=True, strip_detour=True)
    a = ap.parse_args()

    base_path = os.path.abspath(a.base)
    base, nodes = load_nodes(base_path)
    if not nodes:
        print('底库里没有节点')
        sys.exit(1)
    print(f'底库 {os.path.basename(base_path)}：{len(nodes)} 个节点')
    additions = []
    for path in a.add:
        p = os.path.abspath(path)
        if os.path.exists(p) and os.path.samefile(p, base_path):
            print(f'{os.path.basename(p)}：与底库是同一个文件，跳过')
            continue
        _, ns = load_nodes(p)
        additions.append(ns)
        print(f'{os.path.basename(p)}：读取 {len(ns)} 个节点')

    result = merge_config_data(
        base, additions, dedup=a.dedup, dedup_base=a.dedup_base,
        strip_detour=a.strip_detour, do_sort=a.sort, do_rename=a.rename,
    )
    if result['removed']:
        print(f'\n[底库去重] 清理 {len(result["removed"])} 个重复节点：')
        for old, kept in result['removed']:
            print(f'  {old}  ≡  {kept}')
    if result['skipped']:
        print(f'\n[跨文件去重] 跳过 {len(result["skipped"])} 个重复节点：')
        for old, kept in result['skipped']:
            print(f'  {old}  ≡  {kept}')
    total = len([o for o in base['outbounds'] if o.get('type') in NODE_TYPES])
    print(f'\n合并结果：新增 {len(result["added"])} 个，共 {total} 个节点')

    if not a.apply:
        print('\n[预览模式] 未写入。确认无误后加 --apply')
        return

    dst = os.path.abspath(a.out) if a.out else base_path
    changed, backup = write_config(
        dst, base, backup=os.path.exists(dst), style_from=base_path,
    )
    if changed:
        suffix = f'；备份: {os.path.basename(backup)}' if backup else ''
        print(f'合并写入并校验通过：{dst}{suffix}')
    else:
        print('合并结果无变化，未写入，也未生成备份')


if __name__ == '__main__':
    main()
