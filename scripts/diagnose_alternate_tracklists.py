#!/usr/bin/env python3
"""Diagnose alternate official BBC Sounds and RadioFiles tracklist access.

This is an evidence probe, not an artist importer. It records rendered pages,
Show more behaviour, links, and network request metadata without certifying any
tracklist complete.
"""
from __future__ import annotations
import argparse, csv, json, re
from datetime import datetime, timezone
from pathlib import Path

BBC_URL = "https://www.bbc.co.uk/sounds/play/m0032d2m"
RADIOFILES_URL = "https://radiofiles.io/show/riley-coe"
RADIOFILES_EPISODE_URL = "https://radiofiles.io/app?show=m001mf2c&pid=m0032d2m"
FIELDS = ["source", "url", "http_status", "page_title", "body_chars_before", "body_chars_after",
          "show_more_clicks", "show_more_still_visible", "tracklist_heading", "numbered_track_markers",
          "links", "network_requests", "body_excerpt", "error"]


def count_numbered_markers(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d{1,3}\.\s*$", text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--bbc-url", default=BBC_URL)
    ap.add_argument("--radiofiles-url", default=RADIOFILES_URL)
    ap.add_argument("--max-show-more-clicks", type=int, default=40)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for source, url in (("bbc_sounds", args.bbc_url), ("radiofiles_show", args.radiofiles_url), ("radiofiles_episode", RADIOFILES_EPISODE_URL)):
            page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
            network = []
            def capture_response(response):
                url_lower = response.url.casefold()
                if any(k in url_lower for k in ("api", "graphql", "programme", "episode", "track", "radiofiles")):
                    entry = f"{response.status} {response.request.method} {response.url}"
                    if "/tracklist?" in url_lower or "/episodes?" in url_lower:
                        try:
                            entry += " body=" + response.text()[:6000]
                        except Exception as exc:
                            entry += f" body_error={type(exc).__name__}"
                    network.append(entry)
            page.on("response", capture_response)
            status, title, before, after, error = "", "", "", "", ""
            clicks = 0
            still_visible = False
            links = []
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                status = str(response.status if response else "")
                page.wait_for_timeout(3500)
                title = page.title()
                before = page.locator("body").inner_text(timeout=10000)
                links = page.locator("a").evaluate_all("(els) => els.map(a => ({text:(a.innerText||'').trim(),href:a.href})).filter(x => x.href && x.text).slice(0,100)")
                if source == "bbc_sounds":
                    for _ in range(args.max_show_more_clicks):
                        button = page.get_by_role("button", name=re.compile(r"show more", re.I)).last
                        if not button.count() or not button.is_visible():
                            break
                        previous = len(page.locator("body").inner_text(timeout=10000))
                        button.click(timeout=5000)
                        page.wait_for_timeout(350)
                        current = len(page.locator("body").inner_text(timeout=10000))
                        clicks += 1
                        if current <= previous:
                            break
                    still_visible = bool(page.get_by_role("button", name=re.compile(r"show more", re.I)).count())
                after = page.locator("body").inner_text(timeout=10000)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                try:
                    after = page.locator("body").inner_text(timeout=3000)
                    title = page.title()
                except Exception:
                    pass
            rows.append({
                "source": source, "url": url, "http_status": status, "page_title": title,
                "body_chars_before": str(len(before)), "body_chars_after": str(len(after)),
                "show_more_clicks": str(clicks), "show_more_still_visible": str(still_visible).lower(),
                "tracklist_heading": str("tracklist" in after.casefold() or "music played" in after.casefold()).lower(),
                "numbered_track_markers": str(count_numbered_markers(after)),
                "links": json.dumps(links, ensure_ascii=False)[:12000],
                "network_requests": " | ".join(network[:100])[:10000],
                "body_excerpt": re.sub(r"\s+", " ", after[:5000])[:5000], "error": error
            })
            page.close()
        browser.close()
    with (args.out_dir / "alternate_tracklist_diagnostics.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources_probed": len(rows),
        "bbc_show_more_clicks": next((int(r["show_more_clicks"]) for r in rows if r["source"] == "bbc_sounds"), 0),
        "bbc_numbered_track_markers_after_expansion": next((int(r["numbered_track_markers"]) for r in rows if r["source"] == "bbc_sounds"), 0),
        "radiofiles_show_page_accessible": next((r["http_status"].startswith("2") and len(r["body_excerpt"]) > 100 for r in rows if r["source"] == "radiofiles_show"), False),
        "radiofiles_episode_page_track_markers": next((int(r["numbered_track_markers"]) for r in rows if r["source"] == "radiofiles_episode"), 0),
        "artists_imported": 0, "tracklists_certified_complete": 0,
        "interpretation": "Diagnostic only. Page visibility, click count and numbered markers are not proof of a complete tracklist."
    }
    (args.out_dir / "alternate_tracklist_diagnostics.json").write_text(json.dumps({**report, "pages": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if len(rows) == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
