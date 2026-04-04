import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from lxml import html as lxml_html
from scrapling.fetchers import Fetcher


def slugify(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "site").replace(":", "_")
    path = parsed.path.strip("/").replace("/", "_") or "index"
    raw = f"{host}_{path}"
    raw = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", raw)
    return raw[:120]


def extract_text_from_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    tree = lxml_html.fromstring(raw_html)
    texts = [t.strip() for t in tree.xpath("//body//text()")]
    texts = [t for t in texts if t]
    return "\n".join(texts)


def fetch_one(url: str, timeout: int = 30, insecure: bool = False) -> dict:
    verify = not insecure
    used_insecure = insecure
    try:
        page = Fetcher.get(url, timeout=timeout, verify=verify)
    except Exception as e:
        msg = str(e).lower()
        if ("certificate" in msg or "ssl" in msg) and not insecure:
            page = Fetcher.get(url, timeout=timeout, verify=False)
            used_insecure = True
        else:
            raise

    html_content = getattr(page, "html_content", None) or getattr(page, "html", "") or ""
    title = None
    try:
        title = page.css("title::text").get()
    except Exception:
        title = None
    text = extract_text_from_html(html_content)

    return {
        "input_url": url,
        "final_url": getattr(page, "url", url),
        "status": getattr(page, "status", None),
        "title": title,
        "text": text,
        "html_length": len(html_content),
        "used_insecure_ssl": used_insecure,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def save_outputs(item: dict, out_dir: Path) -> dict:
    slug = slugify(item["final_url"] or item["input_url"])
    md_path = out_dir / f"{slug}.md"
    json_path = out_dir / f"{slug}.json"

    md = (
        f"# {item.get('title') or 'Untitled'}\n\n"
        f"- Source: {item.get('input_url')}\n"
        f"- Final URL: {item.get('final_url')}\n"
        f"- Status: {item.get('status')}\n"
        f"- Fetched At: {item.get('fetched_at')}\n"
        f"- Insecure SSL Fallback: {item.get('used_insecure_ssl')}\n\n"
        f"## Content\n\n{item.get('text') or ''}\n"
    )

    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "input_url": item.get("input_url"),
        "final_url": item.get("final_url"),
        "status": item.get("status"),
        "title": item.get("title"),
        "md_path": str(md_path),
        "json_path": str(json_path),
        "used_insecure_ssl": item.get("used_insecure_ssl"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract webpage content with Scrapling")
    parser.add_argument("urls", nargs="+", help="One or more URLs")
    parser.add_argument("--out-dir", default="D:/Software/scrapling-bot/output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds")
    parser.add_argument("--insecure", action="store_true", help="Disable SSL verification")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for url in args.urls:
        try:
            item = fetch_one(url, timeout=args.timeout, insecure=args.insecure)
            saved = save_outputs(item, out_dir)
            saved["ok"] = True
            results.append(saved)
        except Exception as e:
            results.append({
                "input_url": url,
                "ok": False,
                "error": str(e),
            })

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "out_dir": str(out_dir),
        "summary": str(summary_path),
        "results": results,
    }, ensure_ascii=False, indent=2))

    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
