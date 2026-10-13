#!/usr/bin/env python3
"""Inventory recent Riley & Coe Mixcloud uploads without overstating tracklist completeness.

Mixcloud's public API is used only to discover cloudcasts and retrieve exposed
metadata. API sections alone are NOT treated as proof that a tracklist is complete.
Every candidate must be checked against the actual visible show page or another
official source before it can be marked complete in the run evidence.
"""
from __future__ import annotations
import argparse, csv, json, re, sys, time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
            # Ask the public profile for its declared cloudcasts connection;
            # this avoids hard-coding a connection path if Mixcloud changes it.
            if pages == 1 and isinstance(exc, HTTPError) and exc.code == 404:
                profile_url = f"{API_ROOT}/{username.strip('/')}/?metadata=1"
                try:
                    profile = get_json(profile_url)
                    connection = str(profile.get("metadata", {}).get("connections", {}).get("cloudcasts") or "")
                    if connection and connection not in visited:
                        errors.pop()
                        url = connection
                        continue
                    errors.append(f"Mixcloud profile metadata did not expose a cloudcasts connection: {profile_url}")
                except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as profile_exc:
                    errors.append(f"Mixcloud profile metadata request failed for {profile_url}: {profile_exc}")
            break
        data = payload.get("data", [])
        if not isinstance(data, list):
            errors.append(f"Unexpected Mixcloud API response shape at {url}")
            break
        should_stop = False
        for item in data:
            if not isinstance(item, dict):
                continue
            published = parse_date(item.get("created_time") or item.get("updated_time"))
            if published and since <= published <= until:
                found.append(item)
            elif published and published < since:
                # Lists are usually newest-first; stop only after the page has
                # no in-window results and its oldest dated item predates since.
                should_stop = True
        if should_stop:
            break
        next_url = payload.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        time.sleep(0.15)
    if pages >= 30 and url and url not in visited:
        errors.append("Stopped after 30 pages as a safety limit; inventory may be incomplete.")
    return found, errors

class MixcloudHTMLParser(HTMLParser):
    """Capture visible page text and links for the public-HTML fallback."""
    def __init__(self):
        super().__init__()
        self.text = []
        self.links = []
        self._anchor = None
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag == "a" and attrs.get("href"):
            self._anchor = {"href": attrs["href"], "text": []}
    def handle_endtag(self, tag):
        if tag == "a" and self._anchor:
            self.links.append((self._anchor["href"], " ".join(self._anchor["text"]).strip()))
            self._anchor = None
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
    def handle_data(self, data):
        if self._skip:
            return
        value = " ".join(data.split())
        if value:
            self.text.append(value)
            if self._anchor is not None:
                self._anchor["text"].append(value)

def parse_mixcloud_title_date(title: str) -> date | None:
    # Public show titles usually include weekday + ordinal day + month + year.
    match = __import__("re").search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", title or "", __import__("re").I)
    if not match:
        return None
    from datetime import datetime
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(" ".join(match.groups()), fmt).date()
        except ValueError:
            pass
    return None

def fetch_cloudcasts_search(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Fallback discovery via Mixcloud's documented public cloudcast search."""
    url = f"{API_ROOT}/search/?{urlencode({'q': 'Riley & Coe', 'type': 'cloudcast', 'limit': 100, 'offset': 0})}"
    found, errors, visited = [], [], set()
    scanned, sample_urls = 0, []
    pages = 0
    while url and url not in visited and pages < 5:
        visited.add(url)
        pages += 1
        try:
            payload = get_json(url)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"Mixcloud public search failed for {url}: {type(exc).__name__}: {exc}")
            break
        data = payload.get("data", [])
        if not isinstance(data, list):
            errors.append(f"Unexpected Mixcloud search response shape at {url}")
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            scanned += 1
            public_url = str(item.get("url") or item.get("key") or "")
            if public_url.startswith("/"):
                public_url = "https://www.mixcloud.com" + public_url
            path_parts = [part for part in urlparse(public_url).path.split("/") if part]
            if public_url and len(sample_urls) < 5: sample_urls.append(public_url)
            author = item.get("user") or item.get("owner") or {}
            author_url = str((author.get("url") or author.get("key") or "") if isinstance(author, dict) else "")
            belongs = bool(path_parts and path_parts[0].casefold() == username.strip("/").casefold())
            belongs = belongs or username.strip("/").casefold() in author_url.casefold()
            if not belongs:
                continue
            published = parse_date(item.get("created_time") or item.get("updated_time"))
            title = str(item.get("name") or item.get("title") or "").strip()
            if published and since <= published <= until:
                found.append(item)
            elif not published:
                parsed = parse_mixcloud_title_date(title)
                if parsed and since <= parsed <= until:
                    item = dict(item)
                    item["created_time"] = parsed.isoformat()
                    found.append(item)
        url = payload.get("paging", {}).get("next")
        time.sleep(0.15)
    if not found and not errors:
        errors.append(f"Mixcloud public search returned no dated Riley & Coe cloudcasts for the requested window (scanned {scanned} results; sample URLs: {sample_urls}).")
    return found, errors

def fetch_cloudcasts_html(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Discover dated show links from both public profile and uploads pages.

    The profile page can render as a generic shell or omit upload anchors. Try
    the dedicated uploads route as an independent HTML source. Parse both
    ordinary anchors and URL references embedded in page markup, but do not
    infer tracklists from discovery markup.
    """
    profile = f"https://www.mixcloud.com/{username.strip('/')}/"
    urls = [profile, urljoin(profile, "uploads/")]
    errors: list[str] = []
    items: list[dict] = []
    seen: set[str] = set()
    diagnostics: list[str] = []
    base = profile

    for page_url in urls:
        req = Request(page_url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        })
        try:
            with urlopen(req, timeout=25) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else page_url
                html = response.read(5_000_001).decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            diagnostics.append(f"{page_url}: {type(exc).__name__}: {exc}")
            continue

        parser = MixcloudHTMLParser()
        parser.feed(html)
        links = list(parser.links)
        # Some page templates embed upload URLs in JSON or data attributes.
        raw_patterns = [
            rf"(?:https?:)?//(?:www\\.)?mixcloud\\.com/{re.escape(username.strip('/'))}/([^/\\\"'?#<>\\s]+)/?",
            rf"(?:href|url|key)[\\\"']+\\s*[:=]\\s*[\\\"']/{re.escape(username.strip('/'))}/([^/\\\"'?#<>\\s]+)/?"
        ]
        for pattern in raw_patterns:
            for slug in re.findall(pattern, html, flags=re.I):
                links.append((f"https://www.mixcloud.com/{username.strip('/')}/{slug}", slug.strip("/").replace("-", " ")))

        added_from_page = 0
        for href, anchor_title in links:
            absolute = urljoin(final_url or base, href)
            parsed = urlparse(absolute)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.netloc.lower() not in {"www.mixcloud.com", "mixcloud.com"} or len(parts) < 2:
                continue
            if parts[0].casefold() != username.strip("/").casefold():
                continue
            if parts[1].casefold() in {"uploads", "favorites", "playlists", "following", "followers"}:
                continue
            canonical = absolute.split("?", 1)[0].rstrip("/") + "/"
            if canonical == profile.rstrip("/") + "/" or canonical in seen:
                continue
            title = anchor_title.strip() or parts[-1].replace("-", " ")
            published = parse_mixcloud_title_date(title) or parse_mixcloud_title_date(parts[-1].replace("-", " "))
            if not published or not (since <= published <= until):
                continue
            seen.add(canonical)
            added_from_page += 1
            items.append({
                "name": title, "title": title, "url": canonical,
                "created_time": published.isoformat(), "_html_fallback": True
            })
        diagnostics.append(f"{page_url} -> {final_url}; html_chars={len(html)}; anchors={len(parser.links)}; candidate_links={len(links)}; dated_shows_added={added_from_page}")

    if not items:
        errors.append("Mixcloud HTML discovery found no dated show links. " + " | ".join(diagnostics))
    return items, errors

def fetch_show_page_tracks(item: dict) -> tuple[dict, list[dict]]:
    """Extract only clearly structured visible track rows from a public show page."""
    url = str(item.get("url") or "")
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=25) as response:
        html = response.read(5_000_001).decode("utf-8", errors="replace")
    parser = MixcloudHTMLParser()
    parser.feed(html)
    lines = [line.strip() for line in parser.text if line.strip()]
    # Find the tracklist heading and parse visible ordinal/title/artist triplets.
    start = next((i for i, line in enumerate(lines) if line.casefold() in {"tracklist", "track listing", "tracks"}), None)
    tracks = []
    if start is not None:
        import re
        i = start + 1
        position = 0
        while i < len(lines):
            if re.fullmatch(r"\d{1,3}\.", lines[i]):
                if i + 2 < len(lines):
                    title = lines[i + 1]
                    artist = lines[i + 2]
                    if title.casefold() not in {"show more", "load more", "comments", "listeners"} and artist.casefold() not in {"show more", "load more", "comments", "listeners"}:
                        position += 1
                        tracks.append({"episode_date": str(item.get("created_time", ""))[:10], "episode_title": str(item.get("name") or item.get("title") or ""),
                            "episode_url": url, "artist": artist, "track_title": title, "track_position": str(position),
                            "source": "Mixcloud visible public show page", "verification_status": "needs_complete_visible_page_verification"})
                        i += 3
                        continue
            if lines[i].casefold() in {"show more", "load more"}:
                break
            i += 1
    episode, _ = inventory_item(item)
    episode["source"] = "Mixcloud public HTML fallback"
    episode["tracks_extracted"] = str(len(tracks))
    episode["tracklist_status"] = "incomplete" if tracks else "unavailable"
    episode["notes"] = ("Extracted visible ordinal/title/artist rows from the public HTML page; compare with the complete visible tracklist. " if tracks else "Public HTML page yielded no clearly structured track rows; manual review required. ") + "No tracklist is certified complete automatically."
    return episode, tracks

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
    parsed = parse_date(published)
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
    warnings: list[str] = []
    try:
        items, errors = fetch_cloudcasts(args.username, since, until)
    except Exception as exc:  # final defensive guard; retain an audit even on unexpected API failures
        items = []
        errors.append(f"Unexpected collector error: {type(exc).__name__}: {exc}")

    if not items and errors:
        api_errors = list(errors)
        search_items, search_errors = fetch_cloudcasts_search(args.username, since, until)
        if search_items:
            items = search_items
            warnings.extend(api_errors)
            warnings.extend(search_errors)
            errors = []
        else:
            html_items, html_errors = fetch_cloudcasts_html(args.username, since, until)
            if html_items:
                items = html_items
                warnings.extend(api_errors)
                warnings.extend(search_errors)
                errors = html_errors
            else:
                errors = api_errors + search_errors + html_errors

    episodes, tracks = [], []
    for item in items:
        try:
            if item.get("_html_fallback"):
                episode, item_tracks = fetch_show_page_tracks(item)
            else:
                detail = fetch_show_detail(item) if not sections_from(item) else item
                episode, item_tracks = inventory_item(detail)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            episode, item_tracks = inventory_item(item)
            episode["notes"] += f" Individual show-page/detail fetch also failed: {type(exc).__name__}: {exc}"
            errors.append(f"{episode['episode_title'] or episode['url']}: show detail fetch failed: {exc}")
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
    return 0 if not errors else 1

if __name__ == "__main__":
    sys.exit(main())
