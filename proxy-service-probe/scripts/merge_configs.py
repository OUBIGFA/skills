# -*- coding: utf-8 -*-
"""
合并多个订阅/配置到一个目标订阅底库 (merge_configs.py)。
同时原生支持 Clash YAML (.yaml/.yml) 与 sing-box JSON (.json) 两种核心格式。

合流准则（用户核心契约）：
- 默认合流模式：自动按连接身份指纹执行去重，确保底库无重复节点；
  根据规则重新排序和编号，优先保留目标订阅的原节点以及原有编号，
  新节点按国家在空缺/后续分配空号补齐，并按标准地区聚拢排序。
- 中间插入模式 (--insert / --resort / --reorder-all)：
  打破原有编号壁垒，完全按能力顺位 (✨️ > ❇️ > Key > Fast > _NF > _D+ > ♥️)
  重排并从 1 重新依次递增连续编号。

用法：
  # 1. 默认合流模式 (优先保留 base.yaml 原节点及原编号，新节点补空号排位)
  python merge_configs.py --base base.yaml --add probed_nodes.yaml --apply

  # 2. 中间插入模式 (完全重排重编号)
  python merge_configs.py --base base.yaml --add probed_nodes.yaml --insert --apply

  # 3. 合并到新文件
  python merge_configs.py --base base.yaml --add add1.yaml add2.json --out final.yaml --apply
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
    ap = argparse.ArgumentParser(
        description='合并多个订阅配置（默认优先保留底库原节点与编号，支持中间插入完全重排重编号）'
    )
    ap.add_argument('--base', required=True, help='底库目标配置（支持 .yaml / .yml / .json）')
    ap.add_argument('--add', nargs='+', required=True, help='要并入的配置或节点源，可多个')
    ap.add_argument('--out', default=None, help='结果写到新文件（默认就地更新底库并生成 .bak 备份）')
    ap.add_argument('--apply', action='store_true', help='实际写入（默认仅预览）')
    ap.add_argument('--insert', '--resort', '--reorder-all', dest='insert_mode', action='store_true',
                    help='中间插入模式：打破原有编号完全按能力与规则重排序并从 1 重新编号（默认模式优先保留底库原节点及编号）')
    ap.add_argument('--no-dedup', '--keep-dup', dest='dedup', action='store_false',
                    help='保留重复节点（默认自动按连接身份指纹去重）')
    ap.add_argument('--dedup', dest='dedup', action='store_true',
                    help='按连接身份指纹去重（默认即启用）')
    ap.set_defaults(dedup=True, insert_mode=False)
    a = ap.parse_args()

    from core.merger import merge_clash_proxies, merge_into_clash_config, merge_into_target_file
    from core.parsers import load_proxies

    base_path = os.path.abspath(a.base)
    if not os.path.isfile(base_path):
        print(f'错误: 底库目标文件不存在: {base_path}')
        sys.exit(1)

    with open(base_path, 'r', encoding='utf-8-sig') as f:
        head_sample = f.read(512).strip()
    is_clash_yaml = not (base_path.endswith('.json') or head_sample.startswith('{'))

    # 读取待并入配置中的所有节点
    additions = []
    for path in a.add:
        p = os.path.abspath(path)
        if os.path.exists(p) and os.path.samefile(p, base_path):
            print(f'{os.path.basename(p)}：与底库是同一个文件，跳过')
            continue
        nodes = load_proxies(p)
        print(f'{os.path.basename(p)}：解析到 {len(nodes)} 个候选节点')
        additions.extend(nodes)

    if not additions:
        print('警告: 未从待并入配置中读取到有效节点。')
        return

    mode_desc = '【中间插入模式】打破原编号，完全按综合能力重排序并重新连续编号' if a.insert_mode else '【默认合流模式】优先保留目标订阅的原节点以及原有编号，新节点补空号排位'
    print(f'\n[*] 合流执行模式: {mode_desc}')
    print(f'[*] 底库目标文件: {base_path} ({"Clash YAML" if is_clash_yaml else "sing-box JSON"})')

    if is_clash_yaml:
        from core.renderer import read_template_text
        _, _, base_data = read_template_text(base_path)
        base_proxies = base_data.get("proxies") or []
        print(f'[*] 底库现有节点: {len(base_proxies)} 个')

        merged, stats = merge_clash_proxies(
            base_proxies, additions,
            insert_mode=a.insert_mode,
            dedup=a.dedup
        )

        if stats['skipped']:
            print(f'\n[指纹去重] 过滤 {len(stats["skipped"])} 个重复节点：')
            for new_tag, kept_tag in stats['skipped'][:10]:
                print(f'  {new_tag}  ≡  {kept_tag}')
            if len(stats['skipped']) > 10:
                print(f'  ... 等共 {len(stats["skipped"])} 项')

        print(f'\n合流统计结果: 底库原有 {stats["base_count"]} 个，新增入库 {stats["added_count"]} 个，合流后总计 {stats["total_count"]} 个节点')

        if not a.apply:
            print('\n[预览模式] 未实际写回。确认无误后添加 --apply 执行写入。')
            return

        dest = os.path.abspath(a.out or base_path)
        out_file, _ = merge_into_clash_config(
            base_path=base_path,
            additions=additions,
            output_path=dest,
            insert_mode=a.insert_mode,
            dedup=a.dedup
        )
        print(f'[✓] 合流成功写入文件: {out_file}')

    else:
        # sing-box JSON 模式
        out_file, stats = merge_into_target_file(
            target_path=base_path,
            new_nodes_or_file=additions,
            output_path=a.out,
            insert_mode=a.insert_mode,
            dedup=a.dedup
        )
        print(f'\n合流统计结果: 底库原有 {stats["base_count"]} 个，新增入库 {stats["added_count"]} 个，合流后总计 {stats["total_count"]} 个节点')
        if not a.apply:
            print('\n[预览模式] 未实际写回。确认无误后添加 --apply 执行写入。')
            return
        print(f'[✓] 合流成功写入文件: {out_file}')


if __name__ == '__main__':
    main()
