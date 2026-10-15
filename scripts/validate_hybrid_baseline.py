#!/usr/bin/env python3
"""Validate the hybrid gig-research baseline without modifying the artist pool."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "data" / "artist_pool.csv"
VENUES = ROOT / "config" / "definitive_venues.csv"
SOURCES = ROOT / "config" / "hybrid_venue_sources.csv"
FIXTURES = ROOT / "tests" / "fixtures" / "known_gig_regressions.csv"

EXPECTED_VENUES = {
    "The Cluny",
    "Cluny 2",
    "Boiler Shop",
    "Wylam Brewery",
    "The Grove",
    "Glasshouse International Centre for Music",
    "Sage Two",
    "Cumberland Arms",
    "Cobalt Studios",
    "The Lubber Fiend",
    "Think Tank? NCL",
    "Newcastle University Students' Union",
    "Little Buildings",
    "O2 City Hall Newcastle",
    "Riverside Newcastle",
    "ZEROX Newcastle",
    "The Newgate Social",
    "Head of Steam Newcastle",
}
EXPECTED_FIXTURES = {
    ("2026-10-15", "Boiler Shop", "Heaven 17"),
    ("2026-10-16", "The Lubber Fiend", "Ye Gods"),
    ("2026-10-21", "O2 City Hall Newcastle", "Dexys Midnight Runners"),
    ("2026-10-17", "Boiler Shop", "Cabaret Voltaire"),
    ("2026-10-23", "Boiler Shop", "The Wedding Present"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def main() -> int:
    problems: list[str] = []
    for path in (POOL, VENUES, SOURCES, FIXTURES):
        if not path.is_file():
            problems.append(f"Required file missing: {path.relative_to(ROOT)}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    pool_rows = read_csv(POOL)
    venue_rows = read_csv(VENUES)
    source_rows = read_csv(SOURCES)
    fixture_rows = read_csv(FIXTURES)

    pool_names = {norm(row.get("artist", "")) for row in pool_rows if row.get("artist", "").strip()}
    venue_names = [row.get("venue_name", "").strip() for row in venue_rows]
    venue_set = set(venue_names)
    fixture_keys = {
        (row.get("event_date", "").strip(), row.get("venue", "").strip(), row.get("performer", "").strip())
        for row in fixture_rows
    }

    if len(pool_rows) < 833:
        problems.append(f"Artist pool has {len(pool_rows)} rows; expected at least the 833-row baseline.")
    if len(venue_rows) != 18 or venue_set != EXPECTED_VENUES or len(venue_set) != len(venue_rows):
        problems.append(f"Venue registry mismatch: {len(venue_rows)} rows, {len(venue_set)} unique names.")
    source_names = [row.get("venue", "").strip() for row in source_rows]
    source_set = set(source_names)
    if len(source_rows) != 18 or source_set != EXPECTED_VENUES or len(source_set) != len(source_rows):
        problems.append(f"Compatible source registry mismatch: {len(source_rows)} rows, {len(source_set)} unique names.")
    invalid_sources = [row.get("venue", "") for row in source_rows if not row.get("source_url", "").strip().startswith(("https://", "http://"))]
    if invalid_sources:
        problems.append("Invalid/missing HTTP(S) source URLs: " + ", ".join(invalid_sources))
    if len(fixture_rows) != 5 or fixture_keys != EXPECTED_FIXTURES:
        problems.append(f"Known-gig regression fixture mismatch: {len(fixture_rows)} rows.")
    missing_artists = sorted(
        performer for _, _, performer in EXPECTED_FIXTURES if norm(performer) not in pool_names
    )
    if missing_artists:
        problems.append("Known fixture performers missing from artist pool: " + ", ".join(missing_artists))
    blank_sources = [row.get("venue_name", "") for row in venue_rows if not row.get("primary_source_url", "").strip()]
    if blank_sources:
        problems.append("Venue rows without a primary source URL: " + ", ".join(blank_sources))

    result = {
        "status": "PASS" if not problems else "FAIL",
        "artist_pool_rows": len(pool_rows),
        "venue_rows": len(venue_rows),
        "compatible_source_rows": len(source_rows),
        "known_gig_fixtures": len(fixture_rows),
        "known_fixture_performers_in_pool": len(EXPECTED_FIXTURES) - len(missing_artists),
        "problems": problems,
        "pool_modified": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
