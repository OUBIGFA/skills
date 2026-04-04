# -*- coding: utf-8 -*-

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from markitdown import MarkItDown


def slugify(text: str) -> str:
    text = text.strip().replace('\\', '/').split('/')[-1]
    text = re.sub(r'\?.*$', '', text)
    text = re.sub(r'[^a-zA-Z0-9._-]+', '-', text)
    text = text.strip('-._')
    return text or 'document'


def split_chunks(md_text: str, target=1000, overlap=100) -> List[Dict]:
    lines = md_text.splitlines()
    blocks = []
    cur = []
    cur_len = 0

    for line in lines:
        l = line.strip()
        extra = len(l)
        if cur_len + extra > target and cur:
            blocks.append('\\n'.join(cur).strip())
            if overlap > 0:
                tail = '\\n'.join(cur)[-overlap:]
                cur = [tail] if tail else []
                cur_len = len(tail)
            else:
                cur = []
                cur_len = 0
        cur.append(line)
        cur_len += extra

    if cur:
        blocks.append('\\n'.join(cur).strip())

    return [
        {
            'chunk_id': i + 1,
            'text': b,
        }
        for i, b in enumerate(blocks)
        if b
    ]


def main():
    parser = argparse.ArgumentParser(description='Convert files/URLs to Markdown via MarkItDown')
    parser.add_argument('sources', nargs='+', help='Input file paths or URLs')
    parser.add_argument('--out-dir', required=True, help='Output directory')
    parser.add_argument('--chunks', action='store_true', help='Also generate chunks.jsonl')
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md = MarkItDown(enable_plugins=False)

    summary = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'out_dir': str(out_dir.resolve()),
        'items': [],
    }

    all_chunks = []

    for src in args.sources:
        result = md.convert(src)
        text = result.text_content or ''

        stem = slugify(src)
        if '.' in stem:
            stem = '.'.join(stem.split('.')[:-1]) or stem
        md_path = out_dir / f'{stem}.md'
        md_path.write_text(text, encoding='utf-8')

        item = {
            'source': src,
            'markdown': str(md_path.resolve()),
            'chars': len(text),
        }

        if args.chunks:
            chunks = split_chunks(text)
            for c in chunks:
                rec = {
                    'source_file': src,
                    'section_title': None,
                    'chunk_id': c['chunk_id'],
                    'created_at': summary['created_at'],
                    'text': c['text'],
                }
                all_chunks.append(rec)
            item['chunk_count'] = len(chunks)

        summary['items'].append(item)

    if args.chunks:
        chunks_path = out_dir / 'chunks.jsonl'
        with chunks_path.open('w', encoding='utf-8') as f:
            for row in all_chunks:
                f.write(json.dumps(row, ensure_ascii=False) + '\\n')
        summary['chunks_jsonl'] = str(chunks_path.resolve())

    summary_path = out_dir / 'summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
