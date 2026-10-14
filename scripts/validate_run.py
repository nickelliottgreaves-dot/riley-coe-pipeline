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
    "pool_matches.csv": ["event_artist", "matched_pool_artist", "candidate_pool_artist", "match_type", "source_url", "verified", "notes"],
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
    norm_venue = lambda s: "".join(ch for ch in norm(s) if ch.isalnum())
    normalize_event_artist = lambda s: "".join(ch for ch in norm(s) if ch.isalnum())
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
            if status == "complete" or manifest.get("claimed_status") == "COMPLETE":
                errors.append(f"episodes.csv row {i}: invalid episode_date")
            else:
                warnings.append(f"Episode row {i} has no valid episode_date; retain for review but it cannot support complete coverage")

    venue_rows = tables.get("venue_coverage.csv", [])
    try:
        with REQUIRED_VENUES_FILE.open(encoding="utf-8-sig", newline="") as f:
            required_venues = [r["venue"].strip() for r in csv.DictReader(f) if r.get("mandatory", "").strip().lower() == "true"]
    except (OSError, KeyError, csv.Error) as exc:
        errors.append(f"Cannot load required venue list: {exc}")
        required_venues = []
    # The source registry is a separate prerequisite: an unknown venue URL must
    # not be silently treated as a completed official-calendar check.
    source_registry = ROOT / "config" / "venue_sources.csv"
    try:
        with source_registry.open(encoding="utf-8-sig", newline="") as f:
            source_rows = list(csv.DictReader(f))
        source_map = {norm_venue(r.get("venue", "")): r for r in source_rows}
        for required_name in required_venues:
            source = source_map.get(norm_venue(required_name))
            if not source:
                errors.append(f"Mandatory venue missing from config/venue_sources.csv: {required_name}")
            elif not source.get("source_url", "").strip().startswith(("https://", "http://")):
                errors.append(f"Mandatory venue has no verified source URL in venue_sources.csv: {required_name}")
            elif source.get("source_status", "").strip() not in {
                "verified_official_calendar", "verified_official_site",
                "verified_official_social_listing", "verified_ticketing_calendar",
                "verified_third_party_calendar"
            }:
                errors.append(f"Mandatory venue source is not verified: {required_name}")
            elif source.get("source_status", "").strip() in {"verified_ticketing_calendar", "verified_third_party_calendar"} and not source.get("notes", "").strip():
                errors.append(f"Mandatory fallback/ticketing source lacks a rationale in venue_sources.csv: {required_name}")
    except (OSError, csv.Error) as exc:
        errors.append(f"Cannot load config/venue_sources.csv: {exc}")

    discovery_path = run_dir / "venue_discovery_coverage.csv"
    if discovery_path.exists():
        discovery_rows = read_csv(discovery_path, ["venue", "source_url", "homepage_fetch_status", "structured_event_count", "candidate_link_count", "detail_pages_fetched", "detail_pages_failed", "crawl_cap_reached", "calendar_coverage_verified", "notes"], errors)
        discovery_map = {norm_venue(r.get("venue", "")): r for r in discovery_rows}
        for required_name in required_venues:
            row = discovery_map.get(norm_venue(required_name))
            if not row:
                errors.append(f"venue_discovery_coverage.csv: missing mandatory venue row: {required_name}")
            elif manifest.get("claimed_status") == "COMPLETE" and not truthy(row.get("calendar_coverage_verified", "")):
                errors.append(f"venue_discovery_coverage.csv: COMPLETE run lacks verified calendar coverage for {required_name}")
        if manifest.get("claimed_status") == "COMPLETE":
            if any((r.get("crawl_cap_reached") or "").strip().lower() == "true" for r in discovery_rows):
                errors.append("venue_discovery_coverage.csv: COMPLETE run has a venue crawl cap recorded")
            if any(int(r.get("detail_pages_failed") or 0) > 0 for r in discovery_rows if (r.get("detail_pages_failed") or "").strip().isdigit()):
                errors.append("venue_discovery_coverage.csv: COMPLETE run has failed detail-page fetches")
    elif manifest.get("claimed_status") == "COMPLETE":
        errors.append("Missing venue_discovery_coverage.csv for COMPLETE run")
    else:
        warnings.append("venue_discovery_coverage.csv missing; per-venue discovery provenance unavailable")

    venue_map = {norm_venue(r.get("venue", "")): r for r in venue_rows}
    for venue in required_venues:
        row = venue_map.get(norm_venue(venue))
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

    # If a venue's calendar check says events were found, at least one event
    # act row must be present for that venue. A genuinely empty window can pass
    # only when the venue evidence explicitly says no relevant events were found.
    events = tables.get("events.csv", [])
    checked_event_venues = {
        norm_venue(r.get("venue", "")) for r in venue_rows
        if (r.get("status") or "").strip().lower() == "checked_events_found"
    }
    event_venues_present = {norm_venue(r.get("venue", "")) for r in events if r.get("venue", "").strip()}
    for venue_key in sorted(checked_event_venues - event_venues_present):
        errors.append(f"Venue marked checked_events_found has no event rows: {venue_key}")
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
    allowed_match_types = {"exact", "alias", "fuzzy_candidate", "fuzzy_reviewed", "unmatched", "false_positive_rejected"}
    pool_name_keys = {norm(n) for n in pool_names}
    try:
        alias_rows = read_csv(ROOT / "config" / "artist_aliases.csv", ["alias", "canonical", "review_status"], errors)
        approved_alias_map = {normalize_event_artist(r.get("alias", "")): normalize_event_artist(r.get("canonical", "")) for r in alias_rows if (r.get("review_status") or "").strip().lower() == "approved"}
    except Exception as exc:
        approved_alias_map = {}
        errors.append(f"Cannot load artist alias registry: {exc}")
    for i, row in enumerate(matches, 2):
        if not row.get("source_url", "").strip():
            errors.append(f"pool_matches.csv row {i}: missing evidence URL")
        match_type = (row.get("match_type") or "").strip().lower()
        event_name = (row.get("event_artist") or "").strip()
        matched_name = (row.get("matched_pool_artist") or "").strip()
        candidate_names = [x.strip() for x in (row.get("candidate_pool_artist") or "").split("|") if x.strip()]
        if match_type not in allowed_match_types:
            errors.append(f"pool_matches.csv row {i}: invalid match_type {match_type!r}")
        if match_type in {"exact", "alias", "fuzzy_reviewed"} and not matched_name:
            errors.append(f"pool_matches.csv row {i}: confirmed match type has no matched_pool_artist")
        if match_type == "fuzzy_candidate" and (matched_name or not candidate_names):
            errors.append(f"pool_matches.csv row {i}: fuzzy_candidate must have candidate_pool_artist and no confirmed match")
        if matched_name and norm(matched_name) not in pool_name_keys:
            errors.append(f"pool_matches.csv row {i}: matched_pool_artist is not an exact normalized pool name")
        if match_type == "exact" and normalize_event_artist(event_name) != normalize_event_artist(matched_name):
            errors.append(f"pool_matches.csv row {i}: exact match names do not normalize to the same artist")
        if match_type == "alias" and approved_alias_map.get(normalize_event_artist(event_name)) != normalize_event_artist(matched_name):
            errors.append(f"pool_matches.csv row {i}: alias match is not approved in config/artist_aliases.csv")
        for candidate in candidate_names:
            if norm(candidate) not in pool_name_keys:
                errors.append(f"pool_matches.csv row {i}: candidate is not an exact pool entry: {candidate}")

    # Every distinct billed event artist must appear in the match table, including non-matches.
    expected_event_artists = {
        normalize_event_artist(r.get("artist", "")) for r in events if r.get("artist", "").strip()
    }
    compared_event_artists = {
        normalize_event_artist(r.get("event_artist", "")) for r in matches if r.get("event_artist", "").strip()
    }
    missing_comparisons = sorted(expected_event_artists - compared_event_artists)
    extra_comparisons = sorted(compared_event_artists - expected_event_artists)
    if missing_comparisons:
        errors.append(
            f"{len(missing_comparisons)} distinct event artist(s) missing from pool_matches.csv: "
            + ", ".join(missing_comparisons[:15])
        )
    if extra_comparisons:
        warnings.append(
            f"{len(extra_comparisons)} pool-match artist(s) are not present in events.csv: "
            + ", ".join(extra_comparisons[:15])
        )

    regressions = tables.get("regression_artist_checks.csv", [])
    regression_seed_path = ROOT / "config" / "regression_artists.csv"
    try:
        with regression_seed_path.open(encoding="utf-8-sig", newline="") as f:
            regression_seed = list(csv.DictReader(f))
        seed_names = {norm(r.get("artist", "")) for r in regression_seed if r.get("artist", "").strip()}
    except (OSError, csv.Error) as exc:
        seed_names = set()
        errors.append(f"Cannot load regression artist seed list: {exc}")
    regression_names = {norm(r.get("artist", "")) for r in regressions if r.get("artist", "").strip()}
    missing_regression_rows = sorted(seed_names - regression_names)
    if missing_regression_rows:
        errors.append("Missing required regression artist checks: " + ", ".join(missing_regression_rows))
    for i, row in enumerate(regressions, 2):
        if not row.get("artist", "").strip():
            errors.append(f"regression_artist_checks.csv row {i}: blank artist")
        searched=truthy(row.get("searched", ""))
        if searched and not row.get("evidence_url", "").strip():
            errors.append(f"regression_artist_checks.csv row {i}: searched item has no evidence URL")
        if not searched:
            warnings.append(f"Regression artist {row.get('artist','')} has not been searched")
            if manifest.get("claimed_status") == "COMPLETE":
                errors.append(f"regression_artist_checks.csv row {i}: COMPLETE run has an unsearched regression artist")
        elif row.get("evidence_url", "").strip() and not row.get("evidence_url", "").strip().startswith(("https://", "http://")):
            errors.append(f"regression_artist_checks.csv row {i}: evidence_url is not an HTTP(S) URL")

    if not episodes:
        errors.append("No episode coverage rows: cannot establish tracklist coverage")
    if not venue_rows:
        errors.append("No venue coverage rows: cannot establish venue-first sweep")
    for flag, label in (
        ("episode_coverage_complete", "episode_coverage_complete"),
        ("venue_sweep_complete", "venue_sweep_complete"),
        ("artist_pool_compared", "artist_pool_compared"),
        ("all_event_sources_verified", "all_event_sources_verified"),
    ):
        if manifest.get(flag) is not True:
            message=f"Manifest {label} is not true"
            if manifest.get("claimed_status") == "COMPLETE":
                errors.append(message)
            else:
                warnings.append(message)

    # Any inaccessible/not-checked mandatory venue blocks COMPLETE even if a user
    # has accidentally set the manifest booleans to true.
    if any((venue_map.get(norm_venue(v), {}).get("status", "").strip().lower() in {"inaccessible", "not_checked"}) for v in required_venues):
        message="At least one mandatory venue was inaccessible or not checked"
        if manifest.get("claimed_status") == "COMPLETE":
            errors.append(message)
        else:
            warnings.append(message)

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
    # A structurally valid PARTIAL package is still a successful pipeline output.
    # The explicit PARTIAL status and warnings preserve the incomplete-coverage signal.
    return 0 if status in {"COMPLETE", "PARTIAL"} else 1

if __name__ == "__main__":
    sys.exit(main())
