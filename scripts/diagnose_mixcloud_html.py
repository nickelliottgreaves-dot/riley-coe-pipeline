#!/usr/bin/env python3
"""Test whether public Mixcloud HTML exposes page or creator-comment tracklists.

This is a diagnostic only: it stores response metadata and small structural
signals, never extracts artists and never certifies a tracklist complete.
"""
from __future__ import annotations
import argparse, csv, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SHOWS = [
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/",
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-wednesday-30th-september-2026/",
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-1st-september-2026/",
]
FIELDS = ["url", "http_status", "content_type", "bytes_read", "html_title",
          "contains_tracklist_word", "contains_comments_word", "contains_creator_word",
          "embedded_json_markers", "sample", "error"]
UA = "Mozilla/5.0 (compatible; riley-coe-pipeline/0.5; public page diagnostics)"


def inspect_page(url: str, timeout: int = 20) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(req, timeout=timeout) as response:
            status = response.status
            ctype = response.headers.get("Content-Type", "")
            raw = response.read(2_000_001)
        raw = raw[:2_000_000]
        html = raw.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\\s+", " ", re.sub(r"<[^>]+>", "", title_match.group(1))).strip()[:250] if title_match else ""
        markers = [m for m in ("__NEXT_DATA__", "application/ld+json", "comment", "cloudcast", "tracklist", "sections") if m.casefold() in html.casefold()]
        return {
            "url": url, "http_status": str(status), "content_type": ctype,
            "bytes_read": str(len(raw)), "html_title": title,
            "contains_tracklist_word": str("tracklist" in html.casefold()).lower(),
            "contains_comments_word": str("comment" in html.casefold()).lower(),
            "contains_creator_word": str("creator" in html.casefold()).lower(),
            "embedded_json_markers": ";".join(markers),
            "sample": re.sub(r"\\s+", " ", html[:350])[:350], "error": ""
        }
    except HTTPError as exc:
        body = ""
        try: body = exc.read(350).decode("utf-8", errors="replace")
        except Exception: pass
        return {"url": url, "http_status": str(exc.code), "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
                "bytes_read": "0", "html_title": "", "contains_tracklist_word": "", "contains_comments_word": "",
                "contains_creator_word": "", "embedded_json_markers": "", "sample": body[:350], "error": f"HTTPError: {exc.reason}"}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"url": url, "http_status": "", "content_type": "", "bytes_read": "0", "html_title": "",
                "contains_tracklist_word": "", "contains_comments_word": "", "contains_creator_word": "",
                "embedded_json_markers": "", "sample": "", "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for url in SHOWS:
        rows.append(inspect_page(url))
        time.sleep(.2)
    with (args.out_dir / "mixcloud_html_page_diagnostics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "pages_probed": len(rows),
        "http_successes": sum(r["http_status"].startswith("2") for r in rows),
        "pages_with_tracklist_marker": sum(r["contains_tracklist_word"] == "true" for r in rows),
        "pages_with_comment_marker": sum(r["contains_comments_word"] == "true" for r in rows),
        "artist_rows_extracted": 0,
        "tracklists_certified_complete": 0,
        "interpretation": "Page accessibility and marker presence are diagnostic only; neither proves a complete tracklist.",
        "pages": rows,
    }
    (args.out_dir / "mixcloud_html_page_diagnostics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "pages"}, indent=2))
    return 0 if report["http_successes"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
