#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from urllib import parse, request, error

TIMEOUT = 30
DOTENV_CACHE = None


def load_dotenv() -> dict[str, str]:
    global DOTENV_CACHE
    if DOTENV_CACHE is not None:
        return DOTENV_CACHE

    candidates = []
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        candidates.append(parent / '.env')
    candidates.append(Path.cwd() / '.env')

    data: dict[str, str] = {}
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        for raw_line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in data:
                data[key] = value
    DOTENV_CACHE = data
    return data


def env(name: str) -> str:
    value = (os.getenv(name) or '').strip()
    if value:
        return value

    value = (load_dotenv().get(name) or '').strip()
    if value:
        return value

    if os.name == 'nt':
        try:
            import subprocess
            for scope in ('User', 'Machine'):
                result = subprocess.run(
                    [
                        'powershell.exe',
                        '-NoProfile',
                        '-Command',
                        f"[Environment]::GetEnvironmentVariable('{name}','{scope}')",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                value = (result.stdout or '').strip()
                if value:
                    return value
        except Exception:
            pass

    return ''


def build_endpoints(include_local: bool = True, include_cloud: bool = True):
    endpoints = []
    if include_local:
        base = env('CLI_PROXY_API_BASE')
        mkey = env('CLI_PROXY_API_MKEY')
        if base and mkey:
            endpoints.append({'name': 'local', 'base': base.rstrip('/'), 'mkey': mkey})
    if include_cloud:
        base = env('CLOUD_CLI_PROXY_API_BASE')
        mkey = env('CLOUD_CLI_PROXY_API_MKEY')
        if base and mkey:
            endpoints.append({'name': 'cloud', 'base': base.rstrip('/'), 'mkey': mkey})
    return endpoints


def http_json(method: str, url: str, mkey: str, body: bytes | None = None):
    req = request.Request(url=url, method=method)
    req.add_header('Authorization', f'Bearer {mkey}')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with request.urlopen(req, data=body, timeout=TIMEOUT) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return {'ok': True, 'status': resp.status, 'data': json.loads(raw) if raw else None, 'raw': raw}
    except error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        return {'ok': False, 'status': e.code, 'error': raw}
    except Exception as e:
        return {'ok': False, 'status': None, 'error': str(e)}


def check_endpoint(ep):
    url = ep['base'] + '/v0/management/auth-files'
    res = http_json('GET', url, ep['mkey'])
    if not res['ok']:
        return {'endpoint': ep['name'], 'ok': False, 'error': res['error'], 'status': res['status']}

    files = (res['data'] or {}).get('files') or []
    codex = [x for x in files if x.get('provider') == 'codex']
    alive_statuses = {'ok', 'active'}
    invalid_statuses = {'error'}
    alive = [x for x in codex if x.get('status') in alive_statuses]
    invalid = [x for x in codex if x.get('status') in invalid_statuses]
    pending = [x for x in codex if x.get('status') not in alive_statuses | invalid_statuses]
    return {
        'endpoint': ep['name'],
        'ok': True,
        'total': len(codex),
        'alive': len(alive),
        'invalid': len(invalid),
        'pending': len(pending),
    }


def upload_endpoint(ep, file_path: Path, remote_name: str | None):
    raw = file_path.read_bytes()
    name = remote_name or file_path.name
    qs = parse.urlencode({'name': name})
    url = ep['base'] + '/v0/management/auth-files?' + qs
    res = http_json('POST', url, ep['mkey'], body=raw)
    if not res['ok']:
        return {'endpoint': ep['name'], 'ok': False, 'status': res['status'], 'error': res['error']}
    return {'endpoint': ep['name'], 'ok': True, 'status': res['status'], 'name': name}


def main():
    parser = argparse.ArgumentParser(description='Dual endpoint helper for cpa-codex-free')
    sub = parser.add_subparsers(dest='command', required=True)

    p_check = sub.add_parser('check')
    p_check.add_argument('--local-only', action='store_true')
    p_check.add_argument('--cloud-only', action='store_true')

    p_upload = sub.add_parser('upload')
    p_upload.add_argument('--file', required=True)
    p_upload.add_argument('--name')
    p_upload.add_argument('--local-only', action='store_true')
    p_upload.add_argument('--cloud-only', action='store_true')

    args = parser.parse_args()

    include_local = not args.cloud_only
    include_cloud = not args.local_only
    endpoints = build_endpoints(include_local=include_local, include_cloud=include_cloud)
    if not endpoints:
        print(json.dumps({'ok': False, 'error': 'No endpoint config found'}, ensure_ascii=False))
        return 1

    if args.command == 'check':
        results = [check_endpoint(ep) for ep in endpoints]
        print(json.dumps({'ok': True, 'command': 'check', 'results': results}, ensure_ascii=False, indent=2))
        return 0

    if args.command == 'upload':
        path = Path(args.file)
        if not path.exists():
            print(json.dumps({'ok': False, 'error': f'File not found: {path}'}, ensure_ascii=False))
            return 1
        results = [upload_endpoint(ep, path, args.name) for ep in endpoints]
        print(json.dumps({'ok': True, 'command': 'upload', 'results': results}, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == '__main__':
    sys.exit(main())
