# -*- coding: utf-8 -*-
"""
按检测终判生成统一命名【地区缩写_地区_城市_编号】并写回配置。
默认 dry-run 只打印预览；确认无误后加 --apply 写回（写回前自动备份原文件）。
高/中置信节点按检测结果命名；低置信节点保留原名，除非 overrides.json 给出终裁；
离线节点一律保留原名——无法验证的绝不硬猜。

用法：python rename.py --workdir <目录> [--overrides overrides.json] [--apply]

overrides.json 格式（延迟仲裁后的人工/物理终裁，tag 为节点原名）：
  {"节点原名": {"cc": "DE", "country_zh": "德国", "city_zh": "法兰克福",
                "note": "数据库分歧，物理测距终裁"}}
只想追加备注不改判定时，仅提供 note 键即可。
"""
import argparse
import csv
import json
import os
import shutil
import sys
import time

from common import ensure_utf8_stdout, load_session, pair_nodes, reorder_outbounds
from geodata import flag, region_rank
from probe import NODE_TYPES
from sort_nodes import detect_suffix

ensure_utf8_stdout()


def auto_note(r):
    parts = []
    if r.get('via_front'):
        parts.append('服务器直连被墙，经本机代理中转确认存活（裸连网络下不可用）')
    if r.get('split_exit') or len(r.get('exit_pool') or []) > 1:
        parts.append('出口分流/轮换，按主出口判定')
    if r.get('conf') == 'medium':
        parts.append('中置信')
    if r.get('city_basis') == 'colo':
        parts.append('城市按接入机房推定')
    elif r.get('city_basis') == 'single-source':
        parts.append('城市为单源结果')
    return '；'.join(parts)


def main():
    ap = argparse.ArgumentParser(description='按检测结果统一重命名节点')
    ap.add_argument('--workdir', required=True, help='probe.py 使用的工作目录')
    ap.add_argument('--overrides', default=None, help='终裁覆盖文件（JSON）')
    ap.add_argument('--apply', action='store_true', help='实际写回（默认仅预览）')
    ap.add_argument('--no-sort', dest='sort', action='store_false',
                    help='保持配置原有节点顺序（默认按地区排序）')
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    s = load_session(workdir)
    src_path = s['config']

    final = os.path.join(workdir, 'probe_result_final.json')
    result = final if os.path.exists(final) else os.path.join(workdir, 'probe_result.json')
    recs = json.load(open(result, encoding='utf-8'))
    overrides = json.load(open(a.overrides, encoding='utf-8')) if a.overrides else {}

    d = json.load(open(src_path, encoding='utf-8'))
    nodes = [o for o in d['outbounds'] if o.get('type') in NODE_TYPES]
    # 按指纹配对，配置在检测后被客户端改过名也能对上
    rec_of = {j: recs[i] for i, j in pair_nodes(recs, nodes).items()}

    mapping, rows, counters = {}, [], {}
    plan, keep = [], []
    for idx, o in enumerate(nodes):
        tag = o['tag']
        r = rec_of.get(idx) or {}
        ok = r.get('status') == 'ok'
        # 终裁按当前名或检测时的原名匹配均可
        ov = overrides.get(tag) or overrides.get(r.get('tag')) or {}
        note = '；'.join(filter(None, [auto_note(r), ov.get('note', '')]))
        cc_target = ov.get('cc') or r.get('cc')
        suf = detect_suffix(tag, cc_target)
        if ok and ov.get('cc'):
            plan.append((idx, tag, r, ov['cc'], ov['country_zh'], ov['city_zh'], '终裁', note, suf))
        elif ok and r.get('conf') in ('high', 'medium'):
            plan.append((idx, tag, r, r['cc'], r['country_zh'], r['city_zh'],
                         '高' if r['conf'] == 'high' else '中', note, suf))
        else:
            keep.append({'old': tag, 'new': '（保留原名）', 'exit': r.get('exit_ip', ''),
                         'geo': '', 'votes': '', 'conf': ('离线' if not ok else '低置信'),
                         'colo': r.get('colo', ''), 'note': note})

    # 按地区排序：同一地区的节点聚在一起，编号也随之连续，客户端里一眼能扫完一个区
    if a.sort:
        plan.sort(key=lambda p: (region_rank(p[3]), p[3], p[5] or '', p[0]))

    for idx, tag, r, cc, czh, city, conf, note, suf in plan:
        key = (cc, city)
        counters[key] = counters.get(key, 0) + 1
        # 格式【国旗 国家_城市_编号[_后缀]】；国旗取不到时退回国家码前缀，保证仍能一眼看出地区
        em = flag(cc)
        prefix = f'{em} ' if em else f'{cc}_'
        parts = [f'{prefix}{czh}']
        if city:
            parts.append(city)
        parts.append(str(counters[key]))
        if suf:
            parts.append(suf)
        new = '_'.join(parts)
        mapping[tag] = new
        rows.append({'old': tag, 'new': new, 'exit': r.get('exit_ip', ''),
                     'geo': f'{czh}·{city}',
                     'votes': f"{r.get('votes')}/{r.get('answered')}",
                     'conf': conf, 'colo': r.get('colo', ''), 'note': note})
    rows += keep  # 未识别的排在最后，不打断已归类的地区分块

    kept = [x['old'] for x in rows if x['new'] == '（保留原名）']
    news = list(mapping.values())
    assert len(news) == len(set(news)), '新名称内部冲突'
    assert not set(news) & set(kept), '新名称与保留名冲突'

    print(f'{"旧名称":40s} -> 新名称')
    for x in rows:
        print(f"{x['old']:40s} -> {x['new']}  [{x['conf']}] {x['note']}")
    print(f'\n重命名 {len(mapping)} 个，保留原名 {len(kept)} 个'
          f'（其中低置信 {sum(1 for x in rows if x["conf"] == "低置信")} 个）')

    with open(os.path.join(workdir, 'rename_map.csv'), 'w',
              encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['旧名称', '新名称', '出口IP', '判定', '票数', '置信', '接入机房', '备注'])
        for x in rows:
            w.writerow([x['old'], x['new'], x['exit'], x['geo'], x['votes'],
                        x['conf'], x['colo'], x['note']])

    if not a.apply:
        print('\n[预览模式] 未写回。确认无误后加 --apply 执行；'
              '低置信节点如需命名，先经延迟仲裁写 overrides.json')
        return

    # 同步全部引用
    for o in d['outbounds']:
        if o.get('type') in ('selector', 'urltest'):
            o['outbounds'] = [mapping.get(t, t) for t in o.get('outbounds', [])]
            if o.get('default') in mapping:
                o['default'] = mapping[o['default']]
        else:
            if o.get('detour') in mapping:
                o['detour'] = mapping[o['detour']]
            if o.get('tag') in mapping:
                o['tag'] = mapping[o['tag']]
    rt = d.get('route', {})
    if rt.get('final') in mapping:
        rt['final'] = mapping[rt['final']]
    for ru in rt.get('rules', []):
        if ru.get('outbound') in mapping:
            ru['outbound'] = mapping[ru['outbound']]
    for sv in d.get('dns', {}).get('servers', []):
        if sv.get('detour') in mapping:
            sv['detour'] = mapping[sv['detour']]

    if a.sort:  # 按上面排好的顺序重排配置与分组成员，客户端里同地区才会连成一块
        order = [x['new'] for x in rows if x['new'] != '（保留原名）'] + \
                [x['old'] for x in rows if x['new'] == '（保留原名）']
        reorder_outbounds(d, {t: i for i, t in enumerate(order)}, NODE_TYPES)

    # 备份 + 按原文件换行风格写回
    raw = open(src_path, 'rb').read()
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = (src_path[:-5] if src_path.lower().endswith('.json') else src_path) \
        + f'.backup.{ts}.json'
    shutil.copy2(src_path, bak)
    out = json.dumps(d, ensure_ascii=False, indent=2)
    crlf = b'\r\n' in raw
    if crlf:
        out = out.replace('\n', '\r\n')
    if raw.rstrip(b'\r\n') != raw:
        out += '\r\n' if crlf else '\n'
    open(src_path, 'wb').write(out.encode('utf-8'))

    # 写回后校验
    d2 = json.load(open(src_path, encoding='utf-8'))
    tags = [o['tag'] for o in d2['outbounds']]
    assert len(tags) == len(set(tags)), '写回后存在重名 tag'
    tagset = set(tags)
    for o in d2['outbounds']:
        for t in o.get('outbounds', []):
            assert t in tagset, f'分组引用缺失: {t}'
    print(f'\n已写回并校验通过（JSON 合法、无重名、分组引用完整）；备份: {os.path.basename(bak)}')

    lines = ['# 节点地区检测与重命名报告', '',
             f'- 配置文件：{src_path}',
             f'- 检测时间：{time.strftime("%Y-%m-%d %H:%M")}',
             '- 方法：真实连接测出口 → 多独立地理库投票 + Cloudflare 接入机房物理决胜'
             '（存疑出口另做城市锚点延迟仲裁）',
             f'- 结果：重命名 {len(mapping)} 个；保留原名 {len(kept)} 个',
             f'- 备份文件：{os.path.basename(bak)}', '',
             '| 旧名称 | 新名称 | 出口IP | 票数 | 置信 | 接入 | 备注 |',
             '|---|---|---|---|---|---|---|']
    for x in rows:
        lines.append(f"| {x['old']} | {x['new']} | {x['exit']} | {x['votes']} "
                     f"| {x['conf']} | {x['colo']} | {x['note']} |")
    if kept:
        lines += ['', '## 保留原名的节点（离线未验证或低置信未终裁）', '']
        lines += [f'- {t}' for t in kept]
    with open(os.path.join(workdir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('报告已写入 report.md / rename_map.csv')


if __name__ == '__main__':
    main()
