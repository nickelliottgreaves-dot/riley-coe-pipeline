#!/usr/bin/env python3
"""Small, conservative first-pass gig finder for the nine core venues.

This orchestrates the existing structured-data collector and compares each
candidate performer against the current artist pool. It deliberately labels
matches as candidates: fetching a landing page is not proof of a complete
calendar or a verified gig.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
MATCH_FIELDS = [
    "event_date", "venue", "event_title", "event_artist", "matched_pool_artist",
    "match_type", "source_url", "verified", "notes",
]
COVERAGE_FIELDS = [
    "venue", "source_url", "source_status", "fetch_status",
    "candidate_events", "candidate_links", "calendar_coverage_verified", "notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_noise_event_title(title: str) -> bool:
    """Reject page furniture and price/location labels misread as event titles."""
    value = " ".join((title or "").casefold().split())
    if not value:
        return True
    if value in {"location", "venue", "venue space", "tickets", "details", "event details",
                 "buy tickets", "book now", "limited availability", "sold out"}:
        return True
    if re.fullmatch(r"(?:from:\s*)?£?\s*\d+(?:\.\d{1,2})?(?:\s*[-–]\s*£?\s*\d+(?:\.\d{1,2})?)?", value):
        return True
    if re.fullmatch(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)", value):
        return True
    return False


def inspection_to_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert second-stage page inspection into one review-only row per billed act."""
    candidates = []
    for row in rows:
        event_date = (row.get("event_date") or "").strip()[:10]
        title = (row.get("event_title") or "").strip()
        venue = (row.get("venue") or "").strip()
        source_url = (row.get("page_url") or "").strip()
        if not event_date or not title or not venue or is_noise_event_title(title):
            continue
        performers = [name.strip() for name in (row.get("performer_names") or "").split(";") if name.strip()]
        for artist in dict.fromkeys(performers):
            candidates.append({
                "event_date": event_date,
                "venue": venue,
                "event_title": title,
                "artist": artist,
                "artist_role": "unknown",
                "source_url": source_url,
                "verified": "false",
                "notes": (row.get("notes") or "Extracted from event page; manual verification remains required."),
            })
    return candidates


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", (value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def match_candidates(
    events: list[dict[str, str]],
    pool_rows: list[dict[str, str]],
    alias_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    pool_by_key: dict[str, list[str]] = {}
    for row in pool_rows:
        name = (row.get("artist") or "").strip()
        key = normalize(name)
        if key:
            pool_by_key.setdefault(key, []).append(name)

    aliases: dict[str, str] = {}
    for row in alias_rows:
        if (row.get("review_status") or "").strip().casefold() != "approved":
            continue
        alias = (row.get("alias") or "").strip()
        canonical = (row.get("canonical") or "").strip()
        if alias and canonical and normalize(canonical) in pool_by_key:
            aliases[normalize(alias)] = canonical

    matches = []
    for event in events:
        # Event-page parsers can return multiple billed acts separated by
        # semicolons. Match each independently rather than requiring the whole
        # combined billing string to equal one pool entry.
        artists = [name.strip() for name in (event.get("artist") or "").split(";") if name.strip()]
        for artist in dict.fromkeys(artists):
            key = normalize(artist)
            if not key:
                continue
            if key in pool_by_key and len(pool_by_key[key]) == 1:
                matched = pool_by_key[key][0]
                match_type = "exact"
            elif key in aliases:
                matched = aliases[key]
                match_type = "approved_alias"
            else:
                continue
            matches.append({
                "event_date": (event.get("event_date") or "").strip(),
                "venue": (event.get("venue") or "").strip(),
                "event_title": (event.get("event_title") or "").strip(),
                "event_artist": artist,
                "matched_pool_artist": matched,
                "match_type": match_type,
                "source_url": (event.get("source_url") or "").strip(),
                "verified": "false",
                "notes": "Candidate pool match only; event, date, room, artist role and calendar coverage require verification.",
            })
    return matches


def build_coverage(
    core_rows: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    events: list[dict[str, str]],
    link_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    audit_by_venue = {normalize(row.get("venue", "")): row for row in audit_rows}
    event_counts: dict[str, int] = {}
    link_counts: dict[str, int] = {}
    for row in events:
        key = normalize(row.get("venue", ""))
        event_counts[key] = event_counts.get(key, 0) + 1
    for row in link_rows:
        key = normalize(row.get("venue", ""))
        link_counts[key] = link_counts.get(key, 0) + 1

    coverage = []
    for core in core_rows:
        venue = core["venue"].strip()
        audit = audit_by_venue.get(normalize(venue), {})
        fetch_status = audit.get("status", "missing_audit")
        coverage.append({
            "venue": venue,
            "source_url": core.get("source_url", ""),
            "source_status": core.get("source_status", ""),
            "fetch_status": fetch_status,
            "candidate_events": str(event_counts.get(normalize(venue), 0)),
            "candidate_links": str(link_counts.get(normalize(venue), 0)),
            "calendar_coverage_verified": "false",
            "notes": (audit.get("notes", "") or "No audit record was produced.")
                    + " A fetched page is not proof that the full calendar was checked.",
        })
    return coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Inclusive ISO date")
    parser.add_argument("--end", required=True, help="Inclusive ISO date")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pool", type=Path, default=ROOT / "data/artist_pool.csv")
    parser.add_argument("--core-sources", type=Path, default=ROOT / "config/core_venues.csv")
    parser.add_argument("--aliases", type=Path, default=ROOT / "config/artist_aliases.csv")
    args = parser.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start or (end - start).days > 14:
        parser.error("Date range must be an inclusive window of at most 15 days")
    if not args.pool.exists():
        parser.error(f"Artist pool does not exist: {args.pool}")
    if not args.aliases.exists():
        parser.error(f"Alias file does not exist: {args.aliases}")
    if not args.core_sources.exists():
        parser.error(f"Core venue registry does not exist: {args.core_sources}")

    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(f"Refusing to overwrite non-empty output directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    core_rows = read_csv(args.core_sources)
    expected = {
        "the cluny", "cluny 2", "boiler shop", "wylam brewery", "the grove",
        "sage two", "cumberland arms", "cobalt studios", "lubber fiend",
    }
    actual = {normalize(row.get("venue", "")) for row in core_rows}
    if len(core_rows) != 9 or actual != {normalize(name) for name in expected}:
        raise SystemExit("Core venue registry must contain exactly the nine agreed core venues/rooms.")

    discovery_dir = out_dir / "discovery"
    command = [
        sys.executable, str(ROOT / "scripts/discover_event_candidates.py"),
        "--sources", str(args.core_sources),
        "--start", start.isoformat(), "--end", end.isoformat(),
        "--out-dir", str(discovery_dir),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    event_path = discovery_dir / "event_candidates.csv"
    audit_path = discovery_dir / "event_discovery_audit.csv"
    link_path = discovery_dir / "event_link_candidates.csv"
    if not event_path.exists() or not audit_path.exists() or not link_path.exists():
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("Core discovery did not produce its required candidate and audit files.")

    audit_rows = read_csv(audit_path)
    links = read_csv(link_path)

    # Landing-page JSON-LD alone proved too thin in the live run (1 event row
    # across 9 venues and 1,029 candidate links). Inspect a bounded number of
    # official-host calendar/detail pages before matching artists.
    inspection_dir = discovery_dir / "event_pages"
    inspect_command = [
        sys.executable, str(ROOT / "scripts/inspect_event_links.py"),
        "--links", str(link_path),
        "--sources", str(args.core_sources),
        "--start", start.isoformat(), "--end", end.isoformat(),
        "--out-dir", str(inspection_dir),
        "--max-pages-per-venue", "30",
        "--max-depth", "2",
    ]
    inspected = subprocess.run(inspect_command, cwd=ROOT, capture_output=True, text=True, check=False)
    inspection_path = inspection_dir / "event_page_inspection.csv"
    if not inspection_path.exists():
        print(inspected.stdout)
        print(inspected.stderr, file=sys.stderr)
        raise SystemExit("Second-stage event-page inspection did not produce its inspection CSV.")

    events = inspection_to_candidates(read_csv(inspection_path))
    # Keep any first-pass structured event rows that already contain a named
    # performer; deduplicate after combining the two evidence paths.
    first_pass = read_csv(event_path)
    events.extend(row for row in first_pass if (row.get("artist") or "").strip())
    deduped = {}
    for row in events:
        key = (normalize(row.get("event_date", "")), normalize(row.get("venue", "")),
               normalize(row.get("event_title", "")), normalize(row.get("artist", "")),
               (row.get("source_url") or "").strip())
        deduped[key] = row
    events = list(deduped.values())

    pool_rows = read_csv(args.pool)
    alias_rows = read_csv(args.aliases)
    if not pool_rows or "artist" not in pool_rows[0]:
        raise SystemExit("The current artist pool is empty or missing its artist column.")
    matches = match_candidates(events, pool_rows, alias_rows)
    coverage = build_coverage(core_rows, audit_rows, events, links)
    write_csv(out_dir / "candidate_pool_matches.csv", MATCH_FIELDS, matches)
    write_csv(out_dir / "core_venue_coverage.csv", COVERAGE_FIELDS, coverage)

    failed_sources = sum(row["fetch_status"] != "fetched_candidates_only" for row in coverage)
    summary = {
        "run_date": date.today().isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "artist_pool_rows_loaded": len(pool_rows),
        "core_venues_expected": 9,
        "core_venues_with_fetch_success": sum(row["fetch_status"] == "fetched_candidates_only" for row in coverage),
        "core_venues_with_fetch_failure_or_missing_audit": failed_sources,
        "candidate_event_artist_rows": len(events),
        "candidate_pool_matches": len(matches),
        "verified_gigs": 0,
        "calendar_coverage_verified": False,
        "status": "LIMITED_RESULTS",
        "status_reason": "This first-pass collector reads structured data from configured landing pages only; it does not prove complete calendars or verify individual events.",
        "discovery_exit_code": result.returncode,
        "event_inspection_exit_code": inspected.returncode,
        "event_pages_inspected": sum(int(row.get("pages_fetched", 0)) + int(row.get("pages_failed", 0)) for row in read_csv(inspection_dir / "event_page_crawl_audit.csv")) if (inspection_dir / "event_page_crawl_audit.csv").exists() else 0,
        "event_inspection_candidates_with_named_performers": len(events),
        "outputs": [
            "discovery/event_candidates.csv",
            "discovery/event_link_candidates.csv",
            "discovery/event_discovery_audit.csv",
            "discovery/event_pages/event_page_inspection.csv",
            "discovery/event_pages/event_page_crawl_audit.csv",
            "candidate_pool_matches.csv",
            "core_venue_coverage.csv",
            "run_summary.json",
        ],
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if failed_sources == 0 and result.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
