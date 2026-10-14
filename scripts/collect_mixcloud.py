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
from urllib.parse import urljoin, urlparse, parse_qs
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.mixcloud.com"
GRAPHQL_CLOUDCAST_LOOKUP_AVAILABLE: bool | None = None
DEFAULT_USER = "SixMusicAlternative"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
EPISODE_FIELDS = ["episode_date", "episode_title", "source", "url", "tracklist_status", "tracks_extracted", "notes"]
TRACK_FIELDS = ["episode_date", "episode_title", "episode_url", "artist", "track_title", "track_position", "source", "verification_status"]

def get_json(url: str, timeout: int = 25) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_graphql(query: str, timeout: int = 8) -> dict:
    """Call Mixcloud's public GraphQL API with browser TLS impersonation when available."""
    url = "https://app.mixcloud.com/graphql?" + urlencode({"query": query})
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    else:
        try:
            response = curl_requests.get(url, headers=headers, timeout=timeout, impersonate="chrome")
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ValueError(f"Mixcloud GraphQL HTTP request failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Unexpected Mixcloud GraphQL response shape")
    if payload.get("errors"):
        raise ValueError("Mixcloud GraphQL errors: " + json.dumps(payload["errors"])[:500])
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Mixcloud GraphQL response has no data object")
    return data

def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None



def fetch_cloudcasts(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Discover recent uploads using Mixcloud's current GraphQL user connection."""
    found: list[dict] = []
    errors: list[str] = []
    accounts = list(dict.fromkeys([username.strip("/").casefold(), username.strip("/")]))
    for account in accounts:
        cursor = None
        visited_cursors = set()
        pages = 0
        account_found = False
        while pages < 10:
            after = f', after: "{cursor}"' if cursor else ""
            query = """{
              userLookup(lookup: {username: "%s"}) {
                displayName
                uploads(first: 100%s) {
                  edges { node { name slug url publishDate owner { username displayName } } }
                  pageInfo { endCursor hasNextPage }
                }
              }
            }""" % (account, after)
            try:
                data = get_graphql(query)
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"Mixcloud GraphQL user-upload discovery failed for {account}: {type(exc).__name__}: {exc}")
                break
            user = data.get("userLookup") or {}
            if not user:
                errors.append(f"Mixcloud GraphQL returned no userLookup for {account}; data keys=" + ",".join(sorted(data.keys())))
                break
            uploads = user.get("uploads") or {}
            edges = uploads.get("edges") or []
            for edge in edges:
                item = (edge or {}).get("node") or {}
                if not isinstance(item, dict):
                    continue
                published = parse_date(item.get("publishDate") or item.get("created_time"))
                if not published or not (since <= published <= until):
                    continue
                owner = item.get("owner") or {}
                slug = str(item.get("slug") or "").strip("/")
                url = str(item.get("url") or "").strip()
                owner_username = str(owner.get("username") or account)
                if not url and slug:
                    url = f"https://www.mixcloud.com/{owner_username}/{slug}/"
                found.append({
                    "name": str(item.get("name") or slug or "Riley & Coe episode"),
                    "title": str(item.get("name") or slug or "Riley & Coe episode"),
                    "url": url, "key": f"/{owner_username}/{slug}/" if slug else "",
                    "created_time": published.isoformat(), "owner": owner,
                    "_graphql_discovery": True
                })
            if found:
                account_found = True
                break
            page_info = uploads.get("pageInfo") or {}
            if not edges and not page_info.get("hasNextPage"):
                errors.append(f"Mixcloud GraphQL user lookup for {account} returned no upload edges.")
                break
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor or cursor in visited_cursors:
                errors.append("Mixcloud GraphQL pagination returned a missing or repeated cursor.")
                break
            visited_cursors.add(cursor)
            pages += 1
        if pages >= 10:
            errors.append("Stopped after 10 Mixcloud GraphQL upload pages; inventory may be incomplete.")
        if account_found:
            return found, []
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
    """Discover dated show links from profile, uploads, and internal search pages."""
    profile = f"https://www.mixcloud.com/{username.strip('/')}/"
    urls = [profile, urljoin(profile, "uploads/"), "https://www.mixcloud.com/search/?q=Riley%20%26%20Coe"]
    # Mixcloud's own API and profile routes can return 404/generic shells.
    # Search-engine result pages are an independent way to discover dated public show URLs.
    month_cursor = since.replace(day=1)
    months = []
    while month_cursor <= until:
        months.append(month_cursor)
        month_cursor = date(month_cursor.year + (month_cursor.month == 12), 1 if month_cursor.month == 12 else month_cursor.month + 1, 1)
    for month in months:
        query = f'site:mixcloud.com/{username.strip("/")} "Riley & Coe" "{month.strftime("%B %Y")}"'
        urls.append("https://html.duckduckgo.com/html/?" + urlencode({"q": query}))
        urls.append("https://www.google.com/search?" + urlencode({"q": query}))
    errors: list[str] = []
    items: list[dict] = []
    seen: set[str] = set()
    diagnostics: list[str] = []
    for page_url in urls:
        req = Request(page_url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        })
        try:
            with urlopen(req, timeout=8) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else page_url
                page = response.read(5_000_001).decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            diagnostics.append(f"{page_url}: {type(exc).__name__}: {exc}")
            continue
        parser = MixcloudHTMLParser()
        parser.feed(page)
        links = list(parser.links)
        raw_patterns = [
            rf"(?:https?:)?//(?:www\.)?mixcloud\.com/{re.escape(username.strip('/'))}/([^/?#<>\s]+)/?"
        ]
        for pattern in raw_patterns:
            for slug in re.findall(pattern, page, flags=re.I):
                links.append((f"https://www.mixcloud.com/{username.strip('/')}/{slug}", slug.strip("/").replace("-", " ")))
        added = 0
        for href, anchor_title in links:
            absolute = urljoin(final_url or profile, href)
            parsed = urlparse(absolute)
            if parsed.netloc.lower().endswith(("duckduckgo.com", "google.com")):
                params = parse_qs(parsed.query)
                redirect_target = next((values[0] for key in ("uddg", "q", "url") for values in [params.get(key, [])] if values and values[0].startswith("http")), "")
                if redirect_target:
                    absolute = redirect_target
                    parsed = urlparse(absolute)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.netloc.lower() not in {"www.mixcloud.com", "mixcloud.com"} or len(parts) != 2:
                continue
            if parts[0].casefold() != username.strip("/").casefold():
                continue
            if not parts[1].casefold().startswith("riley-coe-"):
                continue
            canonical = absolute.split("?", 1)[0].rstrip("/") + "/"
            if canonical == profile.rstrip("/") + "/" or canonical in seen:
                continue
            title = anchor_title.strip() or parts[-1].replace("-", " ")
            published = parse_mixcloud_title_date(parts[-1].replace("-", " ")) or parse_mixcloud_title_date(title)
            if not published or not (since <= published <= until):
                continue
            seen.add(canonical)
            items.append({"name": title, "title": title, "url": canonical, "created_time": published.isoformat(), "_html_fallback": True})
            added += 1
        diagnostics.append(f"{page_url} -> {final_url}; html_chars={len(page)}; anchors={len(parser.links)}; candidate_links={len(links)}; dated_shows_added={added}; sample_links={links[:8]}")
    # Browser rendering may expose upload cards omitted from static HTML.
    browser_items, browser_errors = fetch_cloudcasts_browser(username, since, until)
    if browser_items:
        existing = {str(item.get("url") or "").rstrip("/") for item in items}
        for item in browser_items:
            if str(item.get("url") or "").rstrip("/") not in existing:
                items.append(item)
                existing.add(str(item.get("url") or "").rstrip("/"))
    elif browser_errors:
        diagnostics.extend(browser_errors)
    if not items:
        errors.append("Mixcloud HTML/browser discovery found no dated show links. " + " | ".join(diagnostics))
    return items, errors




def fetch_cloudcasts_browser(username: str, since: date, until: date) -> tuple[list[dict], list[str]]:
    """Discover upload cards from the rendered public Mixcloud uploads page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ["Playwright is not installed; rendered profile discovery skipped."]
    profile = f"https://www.mixcloud.com/{username.strip('/')}/uploads/"
    errors = []
    items = []
    seen = set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(profile, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200)
            for _ in range(8):
                clicked = False
                for label in ("Load more", "Show more"):
                    try:
                        control = page.get_by_text(label, exact=True).first
                        if control.is_visible(timeout=300):
                            control.click(timeout=1200)
                            page.wait_for_timeout(300)
                            clicked = True
                            break
                    except Exception:
                        continue
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(300)
                if not clicked:
                    break
            links = page.locator("a[href]").evaluate_all("(nodes) => nodes.map(a => ({href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim()}))")
            browser.close()
        for link in links:
            absolute = str(link.get("href") or "")
            parsed = urlparse(absolute)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.netloc.lower() not in {"www.mixcloud.com", "mixcloud.com"} or len(parts) != 2:
                continue
            if parts[0].casefold() != username.strip("/").casefold() or not parts[1].casefold().startswith("riley-coe-"):
                continue
            slug = parts[1]
            title = str(link.get("text") or "").strip() or slug.replace("-", " ")
            published = parse_mixcloud_title_date(slug.replace("-", " ")) or parse_mixcloud_title_date(title)
            if not published or not (since <= published <= until):
                continue
            canonical = f"https://www.mixcloud.com/{parts[0]}/{slug}/"
            if canonical in seen:
                continue
            seen.add(canonical)
            items.append({"name": title, "title": title, "url": canonical, "created_time": published.isoformat(), "_html_fallback": True, "_browser_discovery": True})
    except Exception as exc:
        errors.append(f"Mixcloud rendered profile discovery failed: {type(exc).__name__}: {exc}")
    if not items and not errors:
        errors.append("Rendered Mixcloud uploads page exposed no dated Riley & Coe episode links.")
    return items, errors

def fetch_show_comment_tracks(item: dict) -> list[dict]:
    """Read numbered tracklist rows from the uploader's public GraphQL comment."""
    public_url = str(item.get("url") or "")
    prefix = "https://www.mixcloud.com/"
    if not public_url.startswith(prefix):
        return []
    parts = [part for part in urlparse(public_url).path.split("/") if part]
    if len(parts) != 2:
        return []
    username, slug = parts
    cloudcast = {}
    last_error = ""
    for account in list(dict.fromkeys([username.casefold(), username])):
        query = """{
          cloudcastLookup(lookup: {username: "%s", slug: "%s"}) {
            name publishDate url
            owner { username displayName }
            comments(first: 100) {
              edges { node { comment created user { displayName username } } }
              totalCount
            }
          }
        }""" % (account, slug)
        try:
            data = get_graphql(query)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        cloudcast = data.get("cloudcastLookup") or {}
        if cloudcast:
            break
    if not cloudcast:
        item["_graphql_comment_error"] = last_error or "GraphQL cloudcastLookup returned no object for either account casing"
        return []
    comments = (cloudcast.get("comments") or {}).get("edges") or []
    item["_graphql_comment_count"] = len(comments)
    owner = cloudcast.get("owner") or item.get("owner") or {}
    creator_username = str(owner.get("username") or username).casefold()
    tracks = []
    position = 0
    import html as html_lib
    import re
    for edge in comments:
        comment = (edge or {}).get("node") or {}
        if not isinstance(comment, dict):
            continue
        user = comment.get("user") or {}
        comment_username = str(user.get("username") or "").casefold()
        # Only trust the upload owner's comment, not listener discussion.
        if comment_username and comment_username != creator_username:
            continue
        body = html_lib.unescape(str(comment.get("comment") or "")).replace("\r", "")
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        local_rows = []
        i = 0
        while i < len(lines):
            if re.fullmatch(r"\d{1,3}\.", lines[i]) and i + 2 < len(lines):
                title, artist = lines[i + 1].strip(), lines[i + 2].strip()
                if title and artist and not re.fullmatch(r"\d{1,3}\.", title):
                    local_rows.append((title, artist))
                    i += 3
                    continue
            i += 1
        # Avoid mixing multiple comments or treating unrelated comments as one list.
        if len(local_rows) > len(tracks):
            tracks = []
            for title, artist in local_rows:
                position += 1
                tracks.append({
                    "episode_date": str(item.get("created_time", ""))[:10],
                    "episode_title": str(item.get("name") or item.get("title") or ""),
                    "episode_url": public_url, "artist": artist, "track_title": title,
                    "track_position": str(position), "source": "Mixcloud GraphQL creator comment",
                    "verification_status": "needs_complete_visible_page_verification"
                })
    return tracks


def parse_visible_track_rows(item: dict, lines: list[str], source: str) -> list[dict]:
    """Parse numbered title/artist triplets from the uploader's visible comment."""
    import re
    start = next((i for i, line in enumerate(lines) if line.casefold() in {"tracklist", "track listing", "tracks"}), None)
    if start is None:
        start = next((i for i, line in enumerate(lines) if line.casefold() == "creator"), None)
    if start is None:
        return []
    tracks = []
    i = start + 1
    while i < len(lines):
        if lines[i].strip().casefold() in {"show more", "load more", "reply", "there is no more content to load", "listeners"}:
            break
        if re.fullmatch(r"\d{1,3}\.", lines[i].strip()) and i + 2 < len(lines):
            title, artist = lines[i + 1].strip(), lines[i + 2].strip()
            invalid = {"show more", "load more", "comments", "listeners", "creator", "favorite", "share", "add to", "more", "reply"}
            if title and artist and title.casefold() not in invalid and artist.casefold() not in invalid and not re.fullmatch(r"\d{1,3}\.", title):
                tracks.append({
                    "episode_date": str(item.get("created_time", ""))[:10],
                    "episode_title": str(item.get("name") or item.get("title") or ""),
                    "episode_url": str(item.get("url") or ""),
                    "artist": artist, "track_title": title,
                    "track_position": str(len(tracks) + 1), "source": source,
                    "verification_status": "needs_complete_visible_page_verification"
                })
                i += 3
                continue
        i += 1
    return tracks


def fetch_show_page_tracks_browser(item: dict) -> list[dict]:
    """Render a public Mixcloud show and expand its creator comment in Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        item["_browser_error"] = "Playwright is not installed."
        return []
    url = str(item.get("url") or "")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(user_agent=USER_AGENT)
            response = page.goto(url, wait_until="domcontentloaded", timeout=12000)
            status = response.status if response is not None else None
            item["_browser_http_status"] = status
            if status == 404:
                item["_browser_error"] = "HTTP 404 from Mixcloud public show page"
                browser.close()
                return []
            page.wait_for_timeout(1200)
            # Lazy-load comments and expand any visible "show/load more" controls.
            for _ in range(8):
                clicked = False
                for label in ("Show more", "Load more", "More comments"):
                    try:
                        control = page.get_by_text(label, exact=True).first
                        if control.is_visible(timeout=300):
                            control.click(timeout=1200)
                            page.wait_for_timeout(350)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            lines = [line.strip() for line in page.locator("body").inner_text(timeout=10000).splitlines() if line.strip()]
            browser.close()
    except Exception as exc:
        item["_browser_error"] = f"{type(exc).__name__}: {exc}"
        return []
    tracks = parse_visible_track_rows(item, lines, "Mixcloud rendered public creator comment")
    item["_browser_text_line_count"] = len(lines)
    item["_browser_track_rows"] = len(tracks)
    item["_browser_has_creator"] = any(line.casefold() == "creator" for line in lines)
    item["_browser_text_sample"] = " | ".join(lines[:24])[:1200]
    return tracks


def fetch_show_page_tracks_reader(item: dict) -> list[dict]:
    """Fallback through Jina Reader when Mixcloud serves a bot-facing 404."""
    url = str(item.get("url") or "")
    if not url.startswith("https://www.mixcloud.com/"):
        return []
    reader_url = "https://r.jina.ai/" + url
    req = Request(reader_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/plain"
    })
    try:
        with urlopen(req, timeout=15) as response:
            text = response.read(5_000_001).decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return []
    parser = MixcloudHTMLParser()
    parser.feed(text)
    lines = [line.strip() for line in parser.text if line.strip()]
    tracks = parse_visible_track_rows(item, lines, "Mixcloud public page via Jina Reader")
    item["_reader_text_line_count"] = len(lines)
    item["_reader_track_rows"] = len(tracks)
    return tracks


def fetch_show_page_tracks(item: dict) -> tuple[dict, list[dict]]:
    """Try the official REST show object, creator comment, then rendered public page."""
    url = str(item.get("url") or "")
    # Mixcloud documents a direct REST object endpoint for every public show URL.
    # This is distinct from the profile inventory route and may expose sections even
    # when the public page itself is inaccessible to automated browsers.
    try:
        detail = fetch_show_detail(item)
        if sections_from(detail):
            episode, rest_tracks = inventory_item(detail)
            episode["source"] = "Mixcloud official REST show object"
            episode["tracklist_status"] = "incomplete"
            episode["notes"] = "REST show sections extracted as candidates; verify against the complete creator-comment tracklist before treating as complete."
            for track in rest_tracks:
                track["source"] = "Mixcloud official REST show object"
                track["verification_status"] = "needs_complete_visible_page_verification"
            if rest_tracks:
                return episode, rest_tracks
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        item["_rest_detail_error"] = f"{type(exc).__name__}: {exc}"
    comment_tracks = fetch_show_comment_tracks(item)
    if comment_tracks:
        episode, _ = inventory_item(item)
        episode["source"] = "Mixcloud GraphQL creator comment"
        episode["tracks_extracted"] = str(len(comment_tracks))
        episode["tracklist_status"] = "incomplete"
        episode["notes"] = "Parsed numbered rows from the uploader's public comment; verify that this is the complete tracklist before treating it as complete."
        return episode, comment_tracks
    browser_tracks = fetch_show_page_tracks_browser(item)
    if item.get("_browser_error") or item.get("_browser_text_line_count") is not None:
        print("Mixcloud browser diagnostics:", item.get("url"), "error=", item.get("_browser_error", ""),
              "lines=", item.get("_browser_text_line_count", 0), "creator=", item.get("_browser_has_creator", False),
              "rows=", item.get("_browser_track_rows", 0), "sample=", item.get("_browser_text_sample", ""))
    if browser_tracks:
        episode, _ = inventory_item(item)
        episode["source"] = "Mixcloud rendered public HTML"
        episode["tracks_extracted"] = str(len(browser_tracks))
        episode["tracklist_status"] = "incomplete"
        episode["notes"] = "Parsed numbered rows from the rendered uploader comment; verify that no further tracks are hidden or omitted."
        return episode, browser_tracks
    if item.get("_browser_http_status") == 404:
        reader_tracks = fetch_show_page_tracks_reader(item)
        if reader_tracks:
            episode, _ = inventory_item(item)
            episode["source"] = "Mixcloud public page via Jina Reader"
            episode["tracks_extracted"] = str(len(reader_tracks))
            episode["tracklist_status"] = "incomplete"
            episode["notes"] = "Parsed track rows from a text-reader proxy of the public Mixcloud page; verify complete coverage before treating as complete."
            return episode, reader_tracks
        episode, _ = inventory_item(item)
        episode["source"] = "Mixcloud public HTML fallback"
        episode["tracks_extracted"] = "0"
        episode["tracklist_status"] = "unavailable"
        episode["notes"] = "Mixcloud returned HTTP 404 and the text-reader fallback exposed no numbered track rows."
        return episode, []
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=8) as response:
        html = response.read(5_000_001).decode("utf-8", errors="replace")
    parser = MixcloudHTMLParser()
    parser.feed(html)
    lines = [line.strip() for line in parser.text if line.strip()]
    # Some shows expose a dedicated tracklist; others put numbered rows in
    # the creator's comment. Handle both visible layouts without certifying completeness.
    start = next((i for i, line in enumerate(lines) if line.casefold() in {"tracklist", "track listing", "tracks"}), None)
    if start is None:
        start = next((i for i, line in enumerate(lines) if line.casefold() == "creator"), None)
    tracks = []
    if start is not None:
        import re
        i = start + 1
        position = 0
        stop_markers = {"show more", "load more", "reply", "there is no more content to load", "listeners"}
        while i < len(lines):
            if lines[i].casefold() in stop_markers:
                break
            if re.fullmatch(r"\d{1,3}\.", lines[i]):
                if i + 2 < len(lines):
                    title = lines[i + 1].strip()
                    artist = lines[i + 2].strip()
                    invalid = {"show more", "load more", "comments", "listeners", "creator", "favorite", "share", "add to", "more"}
                    if title.casefold() not in invalid and artist.casefold() not in invalid and not re.fullmatch(r"\d{1,3}\.", title):
                        position += 1
                        tracks.append({"episode_date": str(item.get("created_time", ""))[:10], "episode_title": str(item.get("name") or item.get("title") or ""),
                            "episode_url": url, "artist": artist, "track_title": title, "track_position": str(position),
                            "source": "Mixcloud visible public show page", "verification_status": "needs_complete_visible_page_verification"})
                        i += 3
                        continue
            i += 1
    episode, _ = inventory_item(item)
    episode["source"] = "Mixcloud public HTML fallback"
    episode["tracks_extracted"] = str(len(tracks))
    episode["tracklist_status"] = "incomplete" if tracks else "unavailable"
    episode["notes"] = ("Extracted visible ordinal/title/artist rows from the public HTML page; compare with the complete visible tracklist. " if tracks else "Public HTML page yielded no clearly structured track rows; manual review required. ") + (f"GraphQL comment lookup: {item.get('_graphql_comment_error')}; comments_seen={item.get('_graphql_comment_count', 0)}. " if item.get("_graphql_comment_error") or item.get("_graphql_comment_count") is not None else "") + "No tracklist is certified complete automatically."
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

    if not items:
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
            if item.get("_html_fallback") or item.get("_graphql_discovery"):
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
    if episodes and not tracks:
        errors.append("No track rows could be extracted from any discovered Mixcloud episode; inventory-only success is not sufficient for the gig-matching pipeline.")
    out = args.out_dir
    write_csv(out / "mixcloud_episode_inventory.csv", EPISODE_FIELDS, episodes)
    write_csv(out / "mixcloud_api_track_candidates.csv", TRACK_FIELDS, tracks)
    audit = {
        "collector": "Mixcloud GraphQL and public HTML inventory",
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
            "Mixcloud discovery uses the public GraphQL endpoint and HTML/search fallbacks; BBC episode coverage is audited separately.",
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
