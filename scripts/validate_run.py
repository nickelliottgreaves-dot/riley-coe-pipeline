#!/usr/bin/env python3
"""Fail-closed validator for Riley & Coe weekly research evidence.

This validates the evidence package; it does not itself discover gigs or scrape
episode tracklists. Missing or incomplete research is never labelled COMPLETE.
"""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_VENUES_FILE = ROOT / "config" / "required_venues.csv"
REQUIRED_FILES = {
    "episodes.csv": ["episode_date", "source", "url", "tracklist_status", "tracks_extracted", "notes"],
    "venue_coverage.csv": ["venue", "checked", "source_url", "status", "notes"],
    "events.csv": ["event_date", "venue", "event_title", "artist", "artist_role", "source_url", "verified", "notes"],
    "pool_matches.csv": ["event_date", "venue", "event_title", "event_artist", "matched_pool_artist", "match_type", "source_url", "verified"],
    "regression_artist_checks.csv": ["artist", "searched", "result", "evidence_url", "notes"],
}
TRACKLIST_STATES = {"complete", "incomplete", "unavailable", "not_yet_checked"}
VENUE_STATES = {"checked_events_found", "checked_no_relevant_events", "inaccessible", "not_checked"}

def read_csv(path: Path, required: list[str], errors: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        errors.append(f"Missing required evidence file: {path.name}")
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            missing = [h for h in required if h not in headers]
            if missing:
                errors.append(f"{path.name}: missing columns: {', '.join(missing)}")
                return []
            return list(reader)
    except (OSError, csv.Error) as exc:
        errors.append(f"Cannot read {path.name}: {exc}")
        return []

def truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"true", "yes", "1", "y"}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--pool", type=Path, default=ROOT / "data" / "artist_pool.csv")
    ap.add_argument("--today", help="Override today's date for reproducible tests (YYYY-MM-DD)")
    args = ap.parse_args()
    run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
    errors: list[str] = []
    warnings: list[str] = []

    if not run_dir.exists():
        errors.append(f"Run directory does not exist: {run_dir}")
        manifest = {}
    else:
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            errors.append("Missing run_manifest.json")
            manifest = {}
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"Invalid run_manifest.json: {exc}")
                manifest = {}

    for key in ("run_date", "window_start", "window_end", "previous_successful_run", "researcher_notes"):
        if not manifest.get(key):
            errors.append(f"run_manifest.json: missing {key}")
    try:
        start = date.fromisoformat(manifest["window_start"])
        end = date.fromisoformat(manifest["window_end"])
        if end < start:
            errors.append("Manifest window_end precedes window_start")
        if (end - start).days > 14:
            errors.append("Research window exceeds 15 calendar days (14-day window expected)")
    except (KeyError, ValueError, TypeError):
        start = end = None
        errors.append("Manifest window_start/window_end must be ISO dates")

    if manifest.get("claimed_status") == "COMPLETE":
        # Completion is a claim that must earn every gate below.
        pass

    if not args.pool.exists():
        errors.append(f"Artist pool missing: {args.pool}")
        pool_rows = []
    else:
        pool_rows = read_csv(args.pool, ["artist", "status"], errors)
    pool_names = [r.get("artist", "").strip() for r in pool_rows if r.get("artist", "").strip()]
    norm = lambda s: " ".join((s or "").casefold().split())
    duplicates = sorted({n for n in map(norm, pool_names) if n and sum(norm(x) == n for x in pool_names) > 1})
    if duplicates:
        errors.append(f"Artist pool contains duplicate normalized names ({len(duplicates)}): {', '.join(duplicates[:10])}")
    if len(pool_names) < 1:
        errors.append("Artist pool has no usable artist rows")

    tables = {}
    for filename, columns in REQUIRED_FILES.items():
        tables[filename] = read_csv(run_dir / filename, columns, errors)

    episodes = tables.get("episodes.csv", [])
    for i, row in enumerate(episodes, 2):
        status = (row.get("tracklist_status") or "").strip().lower()
        if status not in TRACKLIST_STATES:
            errors.append(f"episodes.csv row {i}: invalid tracklist_status {status!r}")
        if status != "complete":
            warnings.append(f"Episode row {i} is {status or 'blank'}; coverage cannot be complete")
        if status == "complete" and (not row.get("url", "").strip() or not row.get("source", "").strip()):
            errors.append(f"episodes.csv row {i}: complete episode lacks source and URL")
        try:
            date.fromisoformat(row.get("episode_date", ""))
        except ValueError:
            errors.append(f"episodes.csv row {i}: invalid episode_date")

    venue_rows = tables.get("venue_coverage.csv", [])
    try:
        with REQUIRED_VENUES_FILE.open(encoding="utf-8-sig", newline="") as f:
            required_venues = [r["venue"].strip() for r in csv.DictReader(f) if r.get("mandatory", "").strip().lower() == "true"]
    except (OSError, KeyError, csv.Error) as exc:
        errors.append(f"Cannot load required venue list: {exc}")
        required_venues = []
    venue_map = {norm(r.get("venue", "")): r for r in venue_rows}
    for venue in required_venues:
        row = venue_map.get(norm(venue))
        if not row:
            errors.append(f"Mandatory venue has no coverage row: {venue}")
            continue
        state = (row.get("status") or "").strip().lower()
        if state not in VENUE_STATES:
            errors.append(f"Venue {venue}: invalid status {state!r}")
        if state in {"inaccessible", "not_checked"}:
            warnings.append(f"Venue {venue} not fully checked (status={state})")
        if not row.get("source_url", "").strip():
            errors.append(f"Venue {venue}: missing evidence/source URL")

    events = tables.get("events.csv", [])
    window_events = []
    for i, row in enumerate(events, 2):
        try:
            d = date.fromisoformat(row.get("event_date", ""))
        except ValueError:
            errors.append(f"events.csv row {i}: invalid event_date")
            continue
        if start and end and not (start <= d <= end):
            errors.append(f"events.csv row {i}: event outside manifest window")
        if not all(row.get(k, "").strip() for k in ("venue", "event_title", "artist", "artist_role", "source_url")):
            errors.append(f"events.csv row {i}: missing venue/title/artist/role/source URL")
        if row.get("source_url", "").strip() and not row.get("source_url", "").strip().startswith(("https://", "http://")):
            errors.append(f"events.csv row {i}: source_url is not an HTTP(S) URL")
        if not truthy(row.get("verified", "")):
            warnings.append(f"Event row {i} is not marked verified")
        window_events.append(row)

    matches = tables.get("pool_matches.csv", [])
    for i, row in enumerate(matches, 2):
        if not row.get("source_url", "").strip():
            errors.append(f"pool_matches.csv row {i}: missing evidence URL")
        if not row.get("match_type", "").strip():
            errors.append(f"pool_matches.csv row {i}: missing match_type")
        if row.get("matched_pool_artist", "").strip() and norm(row["matched_pool_artist"]) not in {norm(n) for n in pool_names}:
            warnings.append(f"Match row {i}: matched_pool_artist is not an exact normalized pool name; alias resolution needs review")

    regressions = tables.get("regression_artist_checks.csv", [])
    for i, row in enumerate(regressions, 2):
        if not row.get("artist", "").strip():
            errors.append(f"regression_artist_checks.csv row {i}: blank artist")
        if truthy(row.get("searched", "")) and not row.get("evidence_url", "").strip():
            errors.append(f"regression_artist_checks.csv row {i}: searched item has no evidence URL")

    if not episodes:
        errors.append("No episode coverage rows: cannot establish tracklist coverage")
    if not venue_rows:
        errors.append("No venue coverage rows: cannot establish venue-first sweep")
    if not events:
        warnings.append("No event rows supplied")
    if not matches:
        warnings.append("No pool match rows supplied")
    if manifest.get("episode_coverage_complete") is not True:
        errors.append("Manifest episode_coverage_complete is not true")
    if manifest.get("venue_sweep_complete") is not True:
        errors.append("Manifest venue_sweep_complete is not true")
    if manifest.get("artist_pool_compared") is not True:
        errors.append("Manifest artist_pool_compared is not true")
    if manifest.get("all_event_sources_verified") is not True:
        errors.append("Manifest all_event_sources_verified is not true")

    # Any inaccessible/not-checked mandatory venue blocks COMPLETE even if a user
    # has accidentally set the manifest booleans to true.
    if any((venue_map.get(norm(v), {}).get("status", "").strip().lower() in {"inaccessible", "not_checked"}) for v in required_venues):
        errors.append("At least one mandatory venue was inaccessible or not checked")

    status = "FAILED" if errors else ("PARTIAL" if warnings else "COMPLETE")
    report = {
        "status": status,
        "run_dir": str(run_dir),
        "pool_artist_rows": len(pool_names),
        "episode_rows": len(episodes),
        "venue_rows": len(venue_rows),
        "event_rows": len(events),
        "pool_match_rows": len(matches),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(report, indent=2))
    if run_dir.exists():
        (run_dir / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if status == "COMPLETE" else 1

if __name__ == "__main__":
    sys.exit(main())
