#!/usr/bin/env python3
"""Verify artist-match candidates against naturally collected venue/independent evidence.

This is deliberately conservative: a candidate is verified only when a naturally
collected official venue source confirms the exact date, venue and performer, or
when two independent secondary domains agree on those fields. Explicit fixture
seeds are not evidence unless the same page was also naturally discovered.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def url_key(value: str) -> tuple[str, str]:
    parsed = urlparse(str(value or "").strip())
    return (parsed.netloc.casefold().removeprefix("www."), parsed.path.rstrip("/"))


def host(value: str) -> str:
    return urlparse(str(value or "").strip()).netloc.casefold().removeprefix("www.")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


VENUE_ALIASES = {
    "the cluny": {"the cluny", "cluny"},
    "cluny 2": {"cluny 2", "cluny two"},
    "boiler shop": {"boiler shop"},
    "wylam brewery": {"wylam brewery"},
    "the grove": {"the grove", "grove newcastle"},
    "glasshouse international centre for music": {
        "glasshouse international centre for music", "the glasshouse",
        "sage gateshead", "sage one", "sage 1",
    },
    "sage two": {"sage two", "sage 2"},
    "cumberland arms": {"cumberland arms", "the cumberland arms"},
    "cobalt studios": {"cobalt studios"},
    "the lubber fiend": {"the lubber fiend", "lubber fiend"},
    "think tank ncl": {"think tank ncl", "think tank"},
    "newcastle university students union": {
        "newcastle university students union", "newcastle university su", "nusu",
    },
    "little buildings": {"little buildings"},
    "o2 city hall newcastle": {
        "o2 city hall newcastle", "o2 city hall", "newcastle city hall", "city hall newcastle",
    },
    "riverside newcastle": {"riverside newcastle", "riverside"},
    "zerox newcastle": {"zerox newcastle", "zerox"},
    "the newgate social": {"the newgate social", "newgate social"},
    "head of steam newcastle": {"head of steam newcastle", "head of steam"},
}


def venue_matches(actual: str, expected: str) -> bool:
    actual_norm = norm(actual)
    expected_norm = norm(expected)
    if actual_norm == expected_norm:
        return True
    aliases = VENUE_ALIASES.get(expected_norm, {expected_norm})
    padded = f" {actual_norm} "
    return any(alias and f" {norm(alias)} " in padded for alias in aliases)


def is_calendar_hub_url(url: str, venue: str, source_rows: list[dict[str, str]], configured_urls: set[tuple[str, str]]) -> bool:
    key = url_key(url)
    if key in configured_urls:
        return True
    venue_norm = norm(venue)
    for source in source_rows:
        if norm(source.get("venue", "")) != venue_norm:
            continue
        source_url = (source.get("source_url") or "").strip()
        if not source_url:
            continue
        source_key = url_key(source_url)
        if source_key[0] != key[0]:
            continue
        candidate_path = key[1].rstrip("/")
        source_path = source_key[1].rstrip("/")
        # A venue homepage can be the parent of its configured /events or /gigs
        # route. Do not use a homepage's unrelated nearby date heading as proof.
        if candidate_path and source_path.startswith(candidate_path + "/"):
            return True
    return False


def contains_performer(row: dict[str, str], performer: str) -> bool:
    performer_norm = norm(performer)
    if not performer_norm:
        return False
    fields = [
        row.get("artist", ""),
        row.get("matched_performer", ""),
        row.get("performer_names", ""),
        row.get("event_title", ""),
    ]
    return any(f" {performer_norm} " in f" {norm(value)} " for value in fields if value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=Path, required=True)
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--inspected", type=Path, required=True)
    ap.add_argument("--primary-sources", type=Path, required=True)
    ap.add_argument("--secondary-sources", type=Path, required=True)
    ap.add_argument("--natural-links", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    matches = read_csv(args.matches)
    events = read_csv(args.events)
    inspected = read_csv(args.inspected)
    primary_rows = read_csv(args.primary_sources)
    secondary_rows = read_csv(args.secondary_sources)
    natural_links = read_csv(args.natural_links)

    primary_by_venue = {
        norm(row.get("venue", "")): {
            "host": host(row.get("source_url", "")),
            "source_url": row.get("source_url", ""),
            "source_type": row.get("source_type") or row.get("source_status", ""),
        }
        for row in primary_rows
    }
    official_hosts_by_venue = {
        venue: info["host"]
        for venue, info in primary_by_venue.items()
        if "official" in norm(info["source_type"]) and info["host"]
    }
    secondary_hosts = {host(row.get("source_url", "")) for row in secondary_rows if host(row.get("source_url", ""))}
    configured_source_urls = {
        url_key(row.get("source_url", ""))
        for row in [*primary_rows, *secondary_rows]
        if row.get("source_url")
    }
    natural_url_keys = set()
    for row in natural_links:
        # A discovered candidate URL is event-level discovery evidence. The
        # source_page_url is only the listing/calendar that linked to it; it
        # must not turn an explicitly seeded inspection URL into natural
        # discovery merely because that page happened to be another link's
        # source page.
        value = (row.get("candidate_url") or "").strip()
        if value.startswith(("https://", "http://")):
            natural_url_keys.add(url_key(value))

    evidence_rows: list[tuple[str, dict[str, str]]] = [
        ("event_candidate", row) for row in events
    ] + [
        ("event_page_inspection", row) for row in inspected
    ]

    results = []
    verified_event_keys = set()
    for match in matches:
        day = (match.get("event_date") or "").strip()[:10]
        venue = (match.get("venue") or "").strip()
        performer = (match.get("matched_performer") or match.get("artist_pool_name") or "").strip()
        venue_key = norm(venue)
        primary_host = official_hosts_by_venue.get(venue_key, "")
        matched_evidence = []
        official_evidence = []
        secondary_evidence_by_host: dict[str, dict] = {}

        for evidence_kind, row in evidence_rows:
            row_day = (row.get("event_date") or "").strip()[:10]
            row_venue = (row.get("venue") or "").strip()
            if row_day != day or not venue_matches(row_venue, venue):
                continue
            if not contains_performer(row, performer):
                continue
            url = (row.get("source_url") or row.get("page_url") or "").strip()
            page_url = (row.get("page_url") or "").strip()
            if not url:
                continue
            key = url_key(url)
            note = str(row.get("notes", ""))
            explicitly_seeded = "explicit regression seed page" in note.casefold()
            naturally_collected = key in natural_url_keys or key in configured_source_urls
            if explicitly_seeded and not naturally_collected:
                continue
            if is_calendar_hub_url(url, venue, [*primary_rows, *secondary_rows], configured_source_urls):
                continue

            domain = host(url)
            is_official = bool(primary_host and domain == primary_host)
            is_secondary = domain in secondary_hosts and domain != primary_host
            item = {
                "kind": evidence_kind,
                "url": url,
                "host": domain,
                "event_title": row.get("event_title", ""),
                "event_date": row_day,
                "venue": row_venue,
                "status": row.get("status", row.get("verified", "")),
                "official": is_official,
                "secondary": is_secondary,
            }
            matched_evidence.append(item)
            if is_official:
                official_evidence.append(item)
            elif is_secondary:
                secondary_evidence_by_host.setdefault(domain, item)

        if official_evidence:
            verification_status = "verified_official_source"
            canonical_title = next((e["event_title"] for e in official_evidence if e["event_title"]), match.get("event_title", ""))
            verification_notes = "Naturally collected official venue source contains matching date, venue and performer evidence."
        elif len(secondary_evidence_by_host) >= 2:
            verification_status = "verified_cross_source"
            canonical_title = next((e["event_title"] for e in matched_evidence if e["event_title"]), match.get("event_title", ""))
            verification_notes = "At least two independent secondary domains agree on date, venue and performer."
        else:
            verification_status = "candidate_needs_manual_review"
            canonical_title = next((e["event_title"] for e in matched_evidence if e["event_title"]), match.get("event_title", ""))
            verification_notes = "Insufficient naturally collected event-level evidence; do not present as verified."

        verified = verification_status != "candidate_needs_manual_review"
        if verified:
            verified_event_keys.add((day, venue_key, norm(canonical_title)))
        out_row = dict(match)
        out_row.update({
            "verification_status": verification_status,
            "verified": "true" if verified else "false",
            "verified_event_title": canonical_title,
            "official_evidence_count": len({e["url"] for e in official_evidence}),
            "independent_source_count": len(secondary_evidence_by_host),
            "evidence_urls": json.dumps(list(dict.fromkeys(e["url"] for e in matched_evidence)), ensure_ascii=False),
            "verification_notes": verification_notes,
        })
        results.append(out_row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(matches[0].keys()) if matches else [
        "artist_pool_name", "event_date", "venue", "event_title", "matched_performer",
        "source_url", "source_kind", "match_basis", "candidate_status", "price", "ticket_status", "verified", "notes"
    ]
    fields += ["verification_status", "verified_event_title", "official_evidence_count", "independent_source_count", "evidence_urls", "verification_notes"]
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    verified_rows = sum(row["verified"] == "true" for row in results)
    summary = {
        "candidate_match_rows": len(results),
        "verified_match_rows": verified_rows,
        "unverified_candidate_match_rows": len(results) - verified_rows,
        "verified_events": len(verified_event_keys),
        "official_evidence_match_rows": sum(row["verification_status"] == "verified_official_source" for row in results),
        "cross_source_verified_match_rows": sum(row["verification_status"] == "verified_cross_source" for row in results),
        "manual_review_match_rows": sum(row["verification_status"] == "candidate_needs_manual_review" for row in results),
        "status": "PASS" if results and verified_rows == len(results) else ("LIMITED" if results else "NO_CANDIDATES"),
        "output_file": str(args.out),
        "pool_modified": False,
    }
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
