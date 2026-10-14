#!/usr/bin/env python3
"""Inventory recent Riley & Coe Mixcloud uploads without overstating tracklist completeness.

Mixcloud's public API is used only to discover cloudcasts and retrieve exposed
metadata. API sections alone are NOT treated as proof that a tracklist is complete.
Every candidate must be checked against the actual visible show page or another
official source before it can be marked complete in the run evidence.
"""
from __future__ import annotations
import argparse, csv, json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
import re
from urllib.request import Request, urlopen

API_ROOT = "https://api.mixcloud.com"
DEFAULT_USER = "SixMusicAlternative"
USER_AGENT = "riley-coe-pipeline/0.1 (research evidence collector)"
EPISODE_FIELDS = ["episode_date", "episode_title", "source", "url", "tracklist_status", "tracks_extracted", "notes"]
TRACK_FIELDS = ["episode_date", "episode_title", "episode_url", "artist", "track_title", "track_position", "source", "verification_status"]

def get_json(url: str, timeout: int = 25) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None

def parse_title_date(title: str) -> date | None:
    """Extract the broadcast date from the visible Riley & Coe Mixcloud title."""
    if not re.search(r"riley\s*&\s*coe", title, re.IGNORECASE):
        return None
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b", title, re.IGNORECASE)
    if match:
        day, month, year = match.groups()
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(f"{day} {month} {year}", fmt).date()
            except ValueError:
                continue
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", title)
    if numeric:
        day, month, year = numeric.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None
    return None


def _episode_date_for(item: dict) -> date | None:
    title = str(item.get("name") or item.get("title") or "")
    return parse_title_date(title) or parse_date(item.get("created_time") or item.get("updated_time"))


def _in_window(item: dict, since: date, until: date) -> bool:
    episode_day = _episode_date_for(item)
    if not episode_day or not (since <= episode_day <= until):
        return False
    item["episode_date"] = episode_day.isoformat()
    return True


def _fetch_search_fallback(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Use Mixcloud's documented public search endpoint when the account feed is 404."""
    url = f"{API_ROOT}/search/?{urlencode({'q': 'Riley & Coe', 'type': 'cloudcast', 'limit': 100, 'offset': 0})}"
    found: list[dict] = []
    errors: list[str] = []
    visited: set[str] = set()
    pages = 0
    expected_prefix = f"https://www.mixcloud.com/{username.strip('/')}/".casefold()
    while url and url not in visited and pages < 30:
        visited.add(url)
        pages += 1
        try:
            payload = get_json(url)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"Mixcloud search fallback failed for {url}: {exc}")
            break
        data = payload.get("data", [])
        if not isinstance(data, list):
            errors.append(f"Unexpected Mixcloud search response shape at {url}")
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name") or item.get("title") or "").strip()
            show_url = str(item.get("url") or "").strip()
            if not re.search(r"riley\s*&\s*coe", title, re.IGNORECASE):
                continue
            if not show_url.casefold().startswith(expected_prefix):
                continue
            if not _in_window(item, since, until):
                continue
            item["_search_fallback"] = True
            found.append(item)
        next_url = payload.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        time.sleep(0.15)
    if pages >= 30 and url and url not in visited:
        errors.append("Mixcloud search fallback stopped after 30 pages; inventory may be incomplete.")
    # Deduplicate by public show URL in case search pagination overlaps.
    deduped: dict[str, dict] = {}
    for item in found:
        deduped[str(item.get("url") or "")] = item
    return list(deduped.values()), errors


def fetch_cloudcasts(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    url = f"{API_ROOT}/{username.strip('/')}/cloudcasts/?{urlencode({'limit': 100, 'offset': 0})}"
    found: list[dict] = []
    errors: list[str] = []
    visited: set[str] = set()
    pages = 0
    while url and url not in visited and pages < 30:
        visited.add(url)
        pages += 1
        try:
            payload = get_json(url)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"Mixcloud API request failed for {url}: {exc}")
            break
        data = payload.get("data", [])
        if not isinstance(data, list):
            errors.append(f"Unexpected Mixcloud API response shape at {url}")
            break
        for item in data:
            if isinstance(item, dict) and _in_window(item, since, until):
                found.append(item)
        next_url = payload.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        time.sleep(0.15)
    if pages >= 30 and url and url not in visited:
        errors.append("Stopped after 30 pages as a safety limit; inventory may be incomplete.")
    if found:
        return found, errors

    # The observed account-feed endpoint currently returns HTTP 404, while the
    # documented /search/ endpoint returns HTTP 200. Use it as a discovery
    # fallback, preserving the primary failure in the audit instead of silently
    # presenting search results as a complete inventory.
    fallback, fallback_errors = _fetch_search_fallback(username, since, until)
    if not fallback and not fallback_errors:
        fallback_errors.append("Mixcloud search fallback was attempted but returned no matching Riley & Coe cloudcasts for this date window.")
    return fallback, errors + fallback_errors

def fetch_show_detail(item: dict) -> dict:
    # The user cloudcasts endpoint may omit per-show tracklist sections. Fetch
    # each individual public show object before concluding the sections are absent.
    key = str(item.get("key") or "").strip()
    if key and key.startswith("/"):
        detail_url = API_ROOT + key
    else:
        public_url = str(item.get("url") or "").strip()
        prefix = "https://www.mixcloud.com/"
        if not public_url.startswith(prefix):
            return item
        detail_url = API_ROOT + "/" + public_url[len(prefix):].lstrip("/")
    detail = get_json(detail_url)
    if isinstance(detail, dict):
        merged = dict(item)
        merged.update(detail)
        return merged
    return item

def sections_from(item: dict) -> list[dict]:
    sections = item.get("sections")
    if isinstance(sections, list):
        return [s for s in sections if isinstance(s, dict)]
    tracklist = item.get("tracklist")
    if isinstance(tracklist, list):
        return [s for s in tracklist if isinstance(s, dict)]
    return []

def inventory_item(item: dict) -> tuple[dict, list[dict]]:
    title = str(item.get("name") or item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    published = item.get("created_time") or item.get("updated_time") or ""
    parsed = parse_title_date(title) or parse_date(item.get("episode_date") or published)
    episode_date = parsed.isoformat() if parsed else ""
    sections = sections_from(item)
    tracks = []
    for position, section in enumerate(sections, 1):
        artist = str(section.get("artist") or "").strip()
        track_title = str(section.get("song") or section.get("title") or "").strip()
        # Chapters aren't artist rows, but still matter to interpreting a show.
        if artist:
            tracks.append({
                "episode_date": episode_date, "episode_title": title,
                "episode_url": url, "artist": artist, "track_title": track_title,
                "track_position": str(position), "source": "Mixcloud public API",
                "verification_status": "needs_visible_page_verification"
            })
    if not sections:
        status = "unavailable"
        notes = "Public API did not expose structured tracklist sections; inspect the official show page and alternate sources."
    else:
        status = "incomplete"
        notes = f"API exposed {len(sections)} section(s) and {len(tracks)} artist row(s), but API data alone does not prove the visible tracklist is complete. Verify the page manually."
    episode = {
        "episode_date": episode_date, "episode_title": title, "source": "Mixcloud public API",
        "url": url, "tracklist_status": status, "tracks_extracted": str(len(tracks)), "notes": notes
    }
    return episode, tracks

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default=DEFAULT_USER)
    ap.add_argument("--since", required=True, help="Inclusive episode publish date YYYY-MM-DD")
    ap.add_argument("--until", required=True, help="Inclusive episode publish date YYYY-MM-DD")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    try:
        since, until = date.fromisoformat(args.since), date.fromisoformat(args.until)
    except ValueError:
        ap.error("--since and --until must be YYYY-MM-DD")
    if until < since:
        ap.error("--until must be on or after --since")

    errors: list[str] = []
    try:
        items, errors = fetch_cloudcasts(args.username, since, until)
    except Exception as exc:  # final defensive guard; retain an audit even on unexpected API failures
        items = []
        errors.append(f"Unexpected collector error: {type(exc).__name__}: {exc}")

    episodes, tracks = [], []
    for item in items:
        try:
            detail = fetch_show_detail(item) if not sections_from(item) and not item.get("_search_fallback") else item
            episode, item_tracks = inventory_item(detail)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            episode, item_tracks = inventory_item(item)
            episode["notes"] += f" Individual show API request also failed: {type(exc).__name__}: {exc}"
            errors.append(f"{episode['episode_title'] or episode['url']}: show-detail fetch failed: {exc}")
        episodes.append(episode)
        tracks.extend(item_tracks)
        time.sleep(0.15)
    episodes.sort(key=lambda r: (r["episode_date"], r["episode_title"]))
    tracks.sort(key=lambda r: (r["episode_date"], int(r["track_position"] or 0)))
    out = args.out_dir
    write_csv(out / "mixcloud_episode_inventory.csv", EPISODE_FIELDS, episodes)
    write_csv(out / "mixcloud_api_track_candidates.csv", TRACK_FIELDS, tracks)
    audit = {
        "collector": "Mixcloud public API inventory",
        "username": args.username,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "source_status": ("unavailable" if not items and any("404" in e or "inactive" in e.casefold() for e in errors) else ("ok" if not errors else "partial")),
        "fallback_required": bool(not items and any("404" in e or "inactive" in e.casefold() for e in errors)),
        "discovery_method": "account_cloudcasts_then_search_fallback" if any("search fallback" in e.casefold() for e in errors) or any(item.get("_search_fallback") for item in items) else "account_cloudcasts_endpoint",
        "search_fallback_attempted": any("search fallback" in e.casefold() for e in errors) or any(item.get("_search_fallback") for item in items),
        "search_fallback_used": any(item.get("_search_fallback") for item in items),
        "episodes_found": len(episodes),
        "candidate_artist_rows": len(tracks),
        "episodes_marked_complete": sum(r["tracklist_status"] == "complete" for r in episodes),
        "episodes_requiring_manual_verification": sum(r["tracklist_status"] != "complete" for r in episodes),
        "errors": errors,
        "limitations": [
            "This collector inventories Mixcloud public API data only; it does not check BBC Sounds episode coverage.",
            "It deliberately never marks a tracklist complete from API sections alone.",
            "It does not establish the last successfully audited episode; caller must supply the date range.",
            "A run is not complete until visible tracklists and every venue calendar are independently verified."
        ]
    }
    (out / "mixcloud_collection_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    source_unavailable = not items and any("404" in e or "inactive" in e.casefold() for e in errors)
    # A known unavailable public account is an audited source state, not a collector crash.
    # BBC/RadioFiles fallback and the final fail-closed validator determine completeness.
    return 0 if not errors or source_unavailable else 1

if __name__ == "__main__":
    sys.exit(main())
