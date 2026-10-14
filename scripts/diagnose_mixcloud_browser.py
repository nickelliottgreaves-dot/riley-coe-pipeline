#!/usr/bin/env python3
"""Render public Mixcloud pages in Chromium to inspect client-loaded comments.

Diagnostic only. No artists are imported and no tracklist is certified complete.
"""
from __future__ import annotations
import argparse, csv, json, re
from datetime import datetime, timezone
from pathlib import Path

SHOWS = [
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-wednesday-30th-september-2026/",
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-1st-september-2026/",
    "https://www.mixcloud.com/SixMusicAlternative/riley-coe-monday-12th-october-2026-gid-solo/",
]
KNOWN = ["Lande Hekt", "Ill Ease", "Doo Rag", "Juni Habel", "The Cutter", "Echo & the Bunnymen"]
FIELDS = ["url", "navigation_status", "page_state", "page_title", "body_chars", "known_artist_hits",
          "tracklist_heading", "creator_comment_text_found", "api_responses", "body_excerpt", "error"]


def inspect_rendered_text(url: str, body: str, title: str, status: str, api_responses: list[str], error: str = "") -> dict:
    lower = body.casefold()
    title_lower = title.casefold()
    page_not_found = "page not found" in lower or "page not found" in title_lower
    hits = [name for name in KNOWN if name.casefold() in lower]
    return {
        "url": url,
        "navigation_status": status,
        "page_state": "page_not_found" if page_not_found else ("rendered_content" if len(body) > 500 or bool(hits) else "shell_or_empty"),
        "page_title": title,
        "body_chars": str(len(body)),
        "known_artist_hits": ";".join(hits),
        "tracklist_heading": str(any(term in lower for term in ("tracklist", "comments"))).lower(),
        "creator_comment_text_found": str("creator" in lower and bool(hits)).lower(),
        "api_responses": " | ".join(api_responses[:40])[:4000],
        "body_excerpt": re.sub(r"\\s+", " ", body[:1800])[:1800],
        "error": error,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for url in SHOWS:
            page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
            api_responses = []
            page.on("response", lambda response: api_responses.append(f"{response.status} {response.request.method} {response.url} payload={str(response.request.post_data or '')[:500]}") if any(x in response.url.casefold() for x in ("graphql", "cloudcast", "comment", "api/")) else None)
            status, title, body, error = "", "", "", ""
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = str(response.status if response else "")
                page.wait_for_timeout(8000)
                title = page.title()
                body = page.locator("body").inner_text(timeout=10000)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                try:
                    title = page.title()
                    body = page.locator("body").inner_text(timeout=3000)
                except Exception:
                    pass
            rows.append(inspect_rendered_text(url, body, title, status, api_responses, error))
            page.close()
        browser.close()
    with (args.out_dir / "mixcloud_browser_diagnostics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "pages_probed": len(rows),
        "pages_with_known_tracklist_artists": sum(bool(r["known_artist_hits"]) for r in rows),
        "pages_returning_not_found": sum(r["page_state"] == "page_not_found" for r in rows),
        "artist_rows_extracted": 0,
        "tracklists_certified_complete": 0,
        "interpretation": "Rendered text and network response evidence only; no tracklist completeness claim.",
        "pages": rows,
    }
    (args.out_dir / "mixcloud_browser_diagnostics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "pages"}, indent=2))
    return 0 if any(r["navigation_status"].startswith("2") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
