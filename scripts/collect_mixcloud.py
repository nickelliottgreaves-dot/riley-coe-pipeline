#!/usr/bin/env python3
"""Inventory recent Riley & Coe Mixcloud uploads without overstating tracklist completeness.

Mixcloud's public API is used only to discover cloudcasts and retrieve exposed
metadata. API sections alone are NOT treated as proof that a tracklist is complete.
Every candidate must be checked against the actual visible show page or another
official source before it can be marked complete in the run evidence.
"""
from __future__ import annotations
import argparse, csv, json, re, sys, time
from html.parser import HTMLParser
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
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

def resolve_cloudcasts_endpoint(username: str) -> str:
    """Resolve the account's canonical cloudcasts connection from Mixcloud metadata.

    Mixcloud documents connections on user objects and provides a user search
    endpoint. Try those canonical routes before the legacy guessed URL.
    """
    requested = username.strip("/")
    candidates = list(dict.fromkeys([requested, requested.lower()]))
    for candidate in candidates:
        profile_url = f"{API_ROOT}/{candidate}/?metadata=1"
        try:
            profile = get_json(profile_url)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            continue
        connections = profile.get("metadata", {}).get("connections", {})
        endpoint = connections.get("cloudcasts")
        if isinstance(endpoint, str) and endpoint.startswith(API_ROOT + "/"):
            return endpoint
        key = str(profile.get("key") or "").strip()
        if key.startswith("/") and key.count("/") >= 2:
            return f"{API_ROOT}{key.rstrip('/')}/cloudcasts/"

    # Resolve aliases/canonical keys via the documented public user search.
    search_url = f"{API_ROOT}/search/?{urlencode({'q': requested, 'type': 'user'})}"
    try:
        results = get_json(search_url)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        results = {}
    data = results.get("data", [])
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            url = str(item.get("url") or "").strip()
            name = str(item.get("name") or "").strip()
            slug = key.strip("/").split("/", 1)[0] if key else ""
            if requested.casefold() not in {slug.casefold(), name.casefold()} and requested.casefold() not in url.casefold():
                continue
            if key.startswith("/") and key.count("/") >= 2:
                profile_url = f"{API_ROOT}{key.rstrip('/')}/?metadata=1"
                try:
                    profile = get_json(profile_url)
                    endpoint = profile.get("metadata", {}).get("connections", {}).get("cloudcasts")
                    if isinstance(endpoint, str) and endpoint.startswith(API_ROOT + "/"):
                        return endpoint
                except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                    pass
                return f"{API_ROOT}{key.rstrip('/')}/cloudcasts/"

    # Compatibility fallback. If this route is no longer exposed, the caller
    # records the failure rather than silently reporting an empty inventory.
    return f"{API_ROOT}/{requested}/cloudcasts/"

class CloudcastLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.anchor: dict | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.anchor = {"href": attrs["href"], "text": []}

    def handle_data(self, data):
        if self.anchor is not None:
            text = " ".join(data.split())
            if text:
                self.anchor["text"].append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.links.append((self.anchor["href"], " ".join(self.anchor["text"])))
            self.anchor = None


def episode_date_from_text(value: str) -> date | None:
    """Parse dates in visible Mixcloud show titles and URL slugs.

    Mixcloud titles/slugs have appeared in day-month-year, month-day-year,
    and ISO year-month-day forms. Try explicit formats rather than treating a
    dated upload as absent merely because its slug format changed.
    """
    patterns = [
        (r"(?i)(\\d{1,2})(?:st|nd|rd|th)?[\\s_-]+"
         r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
         r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\\s_-]+(20\\d{2})",
         lambda m: f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y"),
        (r"(?i)(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
         r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\\s_-]+"
         r"(\\d{1,2})(?:st|nd|rd|th)?[\\s,_-]+(20\\d{2})",
         lambda m: f"{m.group(2)} {m.group(1)[:3]} {m.group(3)}", "%d %b %Y"),
        (r"(?<!\\d)(20\\d{2})[-_/](0?[1-9]|1[0-2])[-_/](0?[1-9]|[12]\\d|3[01])(?!\\d)",
         lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%Y-%m-%d"),
    ]
    for pattern, build, date_format in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        try:
            return datetime.strptime(build(match), date_format).date()
        except ValueError:
            continue
    return None


def fetch_html_cloudcasts(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Best-effort fallback using links rendered on the public account page.

    It only inventories episode candidates; it does not claim the profile's
    rendered links are exhaustive or that visible tracklists have been checked.
    """
    profile_url = f"https://www.mixcloud.com/{username.strip('/')}/"
    req = Request(profile_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    errors: list[str] = []
    try:
        with urlopen(req, timeout=25) as response:
            raw = response.read(4_000_001)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return [], [f"Mixcloud public profile HTML fallback failed for {profile_url}: {exc}"]
    truncated = len(raw) > 4_000_000
    parser = CloudcastLinkParser()
    parser.feed(raw[:4_000_000].decode("utf-8", errors="replace"))
    found: list[dict] = []
    seen: set[str] = set()
    account = username.strip("/").casefold()
    for href, link_text in parser.links:
        public_url = urljoin(profile_url, href)
        parsed = urlparse(public_url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        if parsed.netloc.casefold() not in {"www.mixcloud.com", "mixcloud.com"} or len(parts) < 2:
            continue
        if parts[0].casefold() != account or "riley-coe" not in parts[1].casefold():
            continue
        if public_url in seen:
            continue
        seen.add(public_url)
        episode_date = episode_date_from_text(link_text + " " + path.replace("/", " "))
        if not episode_date or not (since <= episode_date <= until):
            continue
        found.append({
            "name": link_text or parts[1].replace("-", " "),
            "url": public_url,
            "key": "/" + path.strip("/") + "/",
            "created_time": episode_date.isoformat() + "T12:00:00Z",
        })
    if truncated:
        errors.append("Mixcloud profile HTML was truncated at 4 MB; candidate inventory may be incomplete.")
    if not found:
        errors.append("Mixcloud profile HTML yielded no dated Riley & Coe links in the requested window; links may be client-rendered or not exposed.")
    return found, errors


def fetch_cloudcasts(username: str, since: date, until: date) -> tuple[list[dict], list[str], list[str]]:
    endpoint = resolve_cloudcasts_endpoint(username)
    url = f"{endpoint.rstrip('/')}/?{urlencode({'limit': 100, 'offset': 0})}"
    found: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
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
    if not found and any("HTTP Error 404" in err for err in errors):
        primary_error = errors[0]
        fallback_found, fallback_errors = fetch_search_cloudcasts(username, since, until)
        if fallback_found:
            found = fallback_found
            errors = []
            warnings.append(
                f"Account cloudcasts listing failed ({primary_error}); recovered {len(found)} dated show candidate(s) via public search. "
                "Search results are not guaranteed exhaustive and require visible-page verification."
            )
        else:
            html_found, html_errors = fetch_html_cloudcasts(username, since, until)
            if html_found:
                found = html_found
                errors = []
                warnings.append(
                    f"Account cloudcasts listing failed ({primary_error}); public search yielded no matching dated shows, "
                    f"so {len(found)} candidate(s) were recovered from the rendered profile page. "
                    "Profile links may be incomplete; visible tracklists still require verification."
                )
            else:
                errors.extend(fallback_errors)
                errors.extend(html_errors)
    return found, errors, warnings

def fetch_search_cloudcasts(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Best-effort dated fallback when the account's cloudcasts connection is unavailable.

    Search is a discovery fallback only; it may omit results, so callers must
    retain an explicit warning and never interpret it as a complete archive.
    """
    query = urlencode({
        "q": "Riley",
        "type": "cloudcast",
        "limit": 100,
        "offset": 0,
        "since": since.isoformat(),
        "until": until.isoformat(),
    })
    url = f"{API_ROOT}/search/?{query}"
    found: list[dict] = []
    errors: list[str] = []
    visited: set[str] = set()
    pages = 0
    account = username.strip("/").casefold()
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
            public_url = str(item.get("url") or "").strip()
            key = str(item.get("key") or "").strip()
            path = urlparse(public_url).path.strip("/") if public_url else key.strip("/")
            slug = path.split("/", 1)[0].casefold() if path else ""
            if slug != account:
                continue
            published = parse_date(item.get("created_time") or item.get("updated_time"))
            if published and since <= published <= until:
                found.append(item)
        next_url = payload.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        time.sleep(0.15)
    if pages >= 30 and url and url not in visited:
        errors.append("Mixcloud search fallback stopped after 30 pages; inventory may be incomplete.")
    return found, errors


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
    try:
        items, errors, warnings = fetch_cloudcasts(args.username, since, until)
    except Exception as exc:  # final defensive guard; retain an audit even on unexpected API failures
        items = []
        errors.append(f"Unexpected collector error: {type(exc).__name__}: {exc}")
        warnings = []

    episodes, tracks = [], []
    for item in items:
        try:
            detail = fetch_show_detail(item) if not sections_from(item) else item
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
        "episodes_found": len(episodes),
        "candidate_artist_rows": len(tracks),
        "episodes_marked_complete": sum(r["tracklist_status"] == "complete" for r in episodes),
        "episodes_requiring_manual_verification": sum(r["tracklist_status"] != "complete" for r in episodes),
        "errors": errors,
        "warnings": warnings,
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
