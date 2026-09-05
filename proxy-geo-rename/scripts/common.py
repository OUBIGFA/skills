# -*- coding: utf-8 -*-
"""会话参数与内核管理：probe.py 初始化 session.json，后续脚本从 workdir 读取，
避免每步重复传参。"""
import json
import os
import re
import socket
import shutil
import subprocess
import sys
import time


NODE_TYPES = {
    'hysteria', 'hysteria2', 'tuic', 'http', 'shadowsocks', 'shadowsocksr',
    'trojan', 'vmess', 'vless', 'wireguard', 'socks', 'ssh', 'shadowtls',
    'anytls', 'mieru',
}


def ensure_utf8_stdout():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')


def session_path(workdir):
    return os.path.join(workdir, 'session.json')


def fp_of(node):
    """节点指纹：协议|服务器|端口。检测结果与配置节点的关联键——
    客户端可能在检测前后改节点名（如 karing 自动加国旗前缀），
    按名字关联会断链，指纹不受改名/调序影响。无 server 的类型退回 tag。"""
    if node.get('server'):
        return f"{node.get('type')}|{node['server']}|{node.get('server_port')}"
    return f"tag|{node.get('tag')}"


def sig(o):
    """完整连接身份指纹；忽略名称及整理时会移除的运行时引用。"""
    identity = {
        key: value for key, value in o.items()
        if key not in {'tag', 'detour', 'domain_resolver'}
    }
    if 'server' in identity:
        identity['server'] = str(identity['server']).lower().rstrip('.')
    return json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _unique(items):
    return list(dict.fromkeys(items))


def _remap_rule_refs(rules, mapping):
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        if rule.get('outbound') in mapping:
            rule['outbound'] = mapping[rule['outbound']]
        _remap_rule_refs(rule.get('rules'), mapping)


def remap_refs(config, mapping):
    """同步出站标签引用，并清除分组中重复的成员。"""
    mapping = {old: new for old, new in mapping.items() if old != new}
    for outbound in config.get('outbounds', []):
        if isinstance(outbound.get('outbounds'), list):
            outbound['outbounds'] = _unique(
                mapping.get(tag, tag) for tag in outbound['outbounds']
            )
        for field in ('default', 'detour'):
            if outbound.get(field) in mapping:
                outbound[field] = mapping[outbound[field]]

    route = config.get('route') or {}
    if route.get('final') in mapping:
        route['final'] = mapping[route['final']]
    _remap_rule_refs(route.get('rules'), mapping)

    for server in (config.get('dns') or {}).get('servers', []):
        if server.get('detour') in mapping:
            server['detour'] = mapping[server['detour']]


def deduplicate_nodes(config, node_types=NODE_TYPES):
    """按连接指纹保留首个节点，并按列表位置删除后续重复项。"""
    seen = {}
    removed_indexes = set()
    mapping = {}
    removed = []
    for index, outbound in enumerate(config.get('outbounds', [])):
        if outbound.get('type') not in node_types:
            continue
        fingerprint = sig(outbound)
        if fingerprint not in seen:
            seen[fingerprint] = (index, outbound.get('tag'))
            continue
        kept_tag = seen[fingerprint][1]
        removed_tag = outbound.get('tag')
        removed_indexes.add(index)
        removed.append((removed_tag, kept_tag))
        if removed_tag != kept_tag:
            mapping[removed_tag] = kept_tag

    if not removed_indexes:
        return []

    config['outbounds'] = [
        outbound for index, outbound in enumerate(config.get('outbounds', []))
        if index not in removed_indexes
    ]
    remap_refs(config, mapping)
    return removed


def strip_node_detours(config, node_types=NODE_TYPES):
    count = 0
    for outbound in config.get('outbounds', []):
        if outbound.get('type') in node_types and 'detour' in outbound:
            outbound.pop('detour')
            count += 1
    return count


def _validate_ref(tag, tags, label):
    if tag and tag not in tags:
        raise ValueError(f'{label} 引用缺失: {tag}')


def _validate_rule_refs(rules, tags):
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        _validate_ref(rule.get('outbound'), tags, '路由规则 outbound')
        _validate_rule_refs(rule.get('rules'), tags)


def validate_config(config):
    """校验所有已维护的出站标签和引用。"""
    outbounds = config.get('outbounds')
    if not isinstance(outbounds, list):
        raise ValueError('配置缺少 outbounds 列表')
    tags = [outbound.get('tag') for outbound in outbounds]
    if any(not tag for tag in tags):
        raise ValueError('存在缺少 tag 的出站')
    duplicates = _unique(tag for tag in tags if tags.count(tag) > 1)
    if duplicates:
        raise ValueError(f'存在重名 tag: {duplicates}')
    tagset = set(tags)

    for outbound in outbounds:
        members = outbound.get('outbounds')
        if members is not None:
            if not isinstance(members, list):
                raise ValueError(f'{outbound["tag"]} 的 outbounds 不是列表')
            for member in members:
                _validate_ref(member, tagset, f'{outbound["tag"]} 分组成员')
        default = outbound.get('default')
        _validate_ref(default, tagset, f'{outbound["tag"]} default')
        if default and isinstance(members, list) and default not in members:
            raise ValueError(f'{outbound["tag"]} default 不是分组成员: {default}')
        _validate_ref(outbound.get('detour'), tagset, f'{outbound["tag"]} detour')

    route = config.get('route') or {}
    _validate_ref(route.get('final'), tagset, 'route.final')
    _validate_rule_refs(route.get('rules'), tagset)
    for server in (config.get('dns') or {}).get('servers', []):
        _validate_ref(server.get('detour'), tagset, f'DNS {server.get("tag", "server")} detour')


def _json_style(raw):
    text = raw.decode('utf-8-sig') if raw else ''
    match = re.search(r'\r?\n([ \t]+)"', text)
    whitespace = match.group(1) if match else '  '
    indent = '\t' if whitespace.startswith('\t') else len(whitespace)
    newline = '\r\n' if '\r\n' in text else '\n'
    trailing_newline = text.endswith(('\n', '\r'))
    bom = raw.startswith(b'\xef\xbb\xbf') if raw else False
    return indent, newline, trailing_newline, bom


def _backup_path(path):
    stem = path[:-5] if path.lower().endswith('.json') else path
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    candidate = f'{stem}.backup.{timestamp}.json'
    suffix = 2
    while os.path.exists(candidate):
        candidate = f'{stem}.backup.{timestamp}.{suffix}.json'
        suffix += 1
    return candidate


def write_config(path, config, backup=False, style_from=None):
    """校验并写入 JSON；内容无变化时不写文件，也不生成备份。"""
    validate_config(config)
    path = os.path.abspath(path)
    if os.path.exists(path):
        with open(path, 'rb') as handle:
            current = handle.read()
    else:
        current = b''
    if current:
        current_data = json.loads(current.decode('utf-8-sig'))
        if current_data == config:
            return False, None

    style_path = path if current else style_from
    if style_path and os.path.exists(style_path):
        with open(style_path, 'rb') as handle:
            style_raw = handle.read()
    else:
        style_raw = b''
    indent, newline, trailing_newline, bom = _json_style(style_raw)
    output = json.dumps(config, ensure_ascii=False, indent=indent)
    if newline != '\n':
        output = output.replace('\n', newline)
    if trailing_newline:
        output += newline
    encoded = output.encode('utf-8')
    if bom:
        encoded = b'\xef\xbb\xbf' + encoded

    backup_path = None
    if backup and current:
        backup_path = _backup_path(path)
        shutil.copy2(path, backup_path)
    with open(path, 'wb') as handle:
        handle.write(encoded)
    return True, backup_path


def pair_nodes(recs, nodes):
    """把检测结果与配置节点一一配对，返回 {结果下标: 节点下标}。
    三级关联：指纹 → 名字 → 同长度时按位置兜底（兼容早期无指纹的结果文件）。
    配对后回填指纹到结果，后续步骤即使配置再被改名也能对上。"""
    by_fp, by_tag = {}, {}
    for j, n in enumerate(nodes):
        by_fp.setdefault(fp_of(n), []).append(j)
        by_tag.setdefault(n.get('tag'), []).append(j)
    out, used = {}, set()

    def take(i, cands):
        for j in cands:
            if j not in used:
                out[i] = j
                used.add(j)
                return True
        return False

    for i, r in enumerate(recs):
        if r.get('fp'):
            take(i, by_fp.get(r['fp'], []))
    for i, r in enumerate(recs):
        if i not in out:
            take(i, by_tag.get(r.get('tag'), []))
    if len(recs) == len(nodes):
        for i in range(len(recs)):
            if i not in out and i not in used:
                out[i] = i
                used.add(i)
    for i, j in out.items():
        recs[i]['fp'] = fp_of(nodes[j])
    return out


def save_session(workdir, data):
    os.makedirs(workdir, exist_ok=True)
    with open(session_path(workdir), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_session(workdir):
    p = session_path(workdir)
    if not os.path.exists(p):
        print(f'未找到 {p}，请先运行 probe.py')
        sys.exit(1)
    return json.load(open(p, encoding='utf-8'))


def start_kernel(singbox, config_path, workdir, logname, first_port):
    """启动 sing-box 并等待首个入站端口就绪。"""
    log = open(os.path.join(workdir, logname), 'w', encoding='utf-8')
    proc = subprocess.Popen([singbox, 'run', '-c', config_path],
                            stdout=log, stderr=log, cwd=workdir)
    for _ in range(20):
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        try:
            s = socket.create_connection(('127.0.0.1', first_port), 1)
            s.close()
            return proc
        except OSError:
            pass
    print(f'sing-box 内核启动失败，详见 {logname}')
    sys.exit(1)


# ---------- 本机前置代理探测 ----------
# 用途：节点服务器从本机直连被墙时，经本机正在运行的代理客户端中转再测。
# 出口判定不受中转影响（出口仍是目标节点自己的出口 IP）。

_PROXY_PROC = 'sing|clash|mihomo|v2ray|xray|neko|hiddify|karing|verge|flclash|sparkle'
_COMMON_PORTS = (7890, 7897, 2080, 1080, 10808, 10809, 20170, 20171)


def _socks5_ok(port, timeout=6):
    """无依赖的 SOCKS5 验证：握手 + CONNECT 出网拿 204，两步都过才算可用。"""
    s = None
    try:
        s = socket.create_connection(('127.0.0.1', port), 3)
        s.settimeout(timeout)
        s.sendall(b'\x05\x01\x00')
        if s.recv(2) != b'\x05\x00':
            return False
        host = b'www.gstatic.com'
        s.sendall(b'\x05\x01\x00\x03' + bytes([len(host)]) + host + (80).to_bytes(2, 'big'))
        r = s.recv(16)
        if len(r) < 2 or r[1] != 0:
            return False
        s.sendall(b'GET /generate_204 HTTP/1.1\r\nHost: www.gstatic.com\r\n'
                  b'Connection: close\r\n\r\n')
        return b'204' in s.recv(64)
    except Exception:
        return False
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


def _http_ok(port):
    try:
        import requests
        r = requests.get('http://www.gstatic.com/generate_204',
                         proxies={'http': f'http://127.0.0.1:{port}',
                                  'https': f'http://127.0.0.1:{port}'}, timeout=6)
        return r.status_code == 204
    except Exception:
        return False


def find_local_proxies():
    """探测本机可用的前置代理端口，返回 [(port, 'socks'|'http')]，socks 优先
    （SOCKS5 支持 UDP 转发，hysteria2/tuic 等 UDP 协议节点也能经它中转）。"""
    import re
    ports = set(_COMMON_PORTS)
    try:
        ps = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'$p=(Get-Process | Where-Object {{$_.ProcessName -imatch "{_PROXY_PROC}"}}).Id; '
             'if($p){(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue '
             '| Where-Object {$_.OwningProcess -in $p}).LocalPort}'],
            capture_output=True, text=True, timeout=20)
        ports |= {int(x) for x in re.findall(r'\d+', ps.stdout or '')}
    except Exception:
        pass
    good = []
    for port in sorted(ports):
        if _socks5_ok(port):
            good.append((port, 'socks'))
        elif _http_ok(port):
            good.append((port, 'http'))
    good.sort(key=lambda x: x[1] != 'socks')
    return good


def reorder_outbounds(d, ranked, node_types):
    """按 ranked（tag → 权重）重排节点在配置中的顺序，并同步各分组的成员顺序。
    非节点出站（分组、direct、block）保持原有相对位置，只有节点参与排序——
    客户端界面按配置顺序展示，排好序后同一地区的节点才会挨在一起。"""
    outs = d.get('outbounds', [])
    slots = [i for i, o in enumerate(outs) if o.get('type') in node_types]
    if not slots:
        return
    big = 10 ** 9
    ordered = sorted((outs[i] for i in slots),
                     key=lambda o: ranked.get(o.get('tag'), big))
    slotset, it = set(slots), iter(ordered)
    d['outbounds'] = [next(it) if i in slotset else o for i, o in enumerate(outs)]
    node_tags = {o.get('tag') for o in ordered}
    for o in d['outbounds']:
        mem = o.get('outbounds')
        if not mem:
            continue
        # 组内非节点成员（如自动选择、直连）留在前面，节点部分按同一顺序排列
        o['outbounds'] = ([t for t in mem if t not in node_tags] +
                          sorted([t for t in mem if t in node_tags],
                                 key=lambda t: ranked.get(t, big)))
