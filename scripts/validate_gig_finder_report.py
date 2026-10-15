#!/usr/bin/env python3
"""Validate structure and explicit coverage of an independent gig-finder package.

This checks package integrity, not exhaustive internet coverage. PARTIAL is a
valid outcome when source/artist checks are incomplete; COMPLETE is not accepted
by this candidate-finder validator.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

try:
    from .workflow_contract import ROOT, load_contract, normalize_key
except ImportError:
    from workflow_contract import ROOT, load_contract, normalize_key


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Missing required report file: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path.name} has no header")
        return list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pool", type=Path, default=ROOT / "data/artist_pool.csv")
    parser.add_argument("--sources", type=Path, default=ROOT / "config/venue_sources.csv")
    args = parser.parse_args()
    run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
    errors: list[str] = []
    warnings: list[str] = []

    try:
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [f"Invalid/missing run_manifest.json: {exc}"]}, indent=2))
        return 1

    contract = load_contract()
    for field in ("run_date", "window_start", "window_end", "previous_successful_run", "researcher_notes", "run_id"):
        if not manifest.get(field):
            errors.append(f"run_manifest.json missing required field: {field}")
    if manifest.get("claimed_status") != "PARTIAL":
        errors.append("Candidate-finder report must remain PARTIAL; this validator does not certify COMPLETE research.")
    try:
        start = date.fromisoformat(manifest["window_start"])
        end = date.fromisoformat(manifest["window_end"])
        days = (end - start).days + 1
        if days != contract["reporting_window_days"]:
            errors.append(f"Manifest window is {days} days; shared contract requires {contract['reporting_window_days']}.")
        if days < contract["minimum_reporting_window_days"]:
            errors.append("Manifest window is shorter than the required minimum.")
    except (KeyError, TypeError, ValueError):
        start = end = None
        errors.append("Manifest window_start/window_end must be valid ISO dates.")

    try:
        with args.sources.open(encoding="utf-8-sig", newline="") as handle:
            sources = list(csv.DictReader(handle))
        with args.pool.open(encoding="utf-8-sig", newline="") as handle:
            pool = list(csv.DictReader(handle))
        source_coverage = read_csv(run_dir / "venue_coverage.csv")
        page_matches = read_csv(run_dir / "artist_pool_page_matches.csv")
        event_coverage = read_csv(run_dir / "artist_window_event_coverage.csv")
        matches = read_csv(run_dir / "artist_window_event_matches.csv")
        out_of_scope = read_csv(run_dir / "out_of_scope_event_candidates.csv")
        crawl_audit = read_csv(run_dir / "event_inspection" / "event_page_crawl_audit.csv")
        fetch_failures = read_csv(run_dir / "event_inspection" / "event_page_fetch_failures.csv")
        read_csv(run_dir / "stage_results.csv")
    except (OSError, csv.Error, ValueError) as exc:
        errors.append(str(exc))
        sources, pool, source_coverage, page_matches, event_coverage, matches, out_of_scope, crawl_audit, fetch_failures = [], [], [], [], [], [], [], [], []

    def check_exact_coverage(label: str, expected_names: list[str], rows: list[dict[str, str]], field: str) -> None:
        expected = [normalize_key(name) for name in expected_names if normalize_key(name)]
        actual = [normalize_key(row.get(field, "")) for row in rows if normalize_key(row.get(field, ""))]
        if len(actual) != len(set(actual)):
            errors.append(f"{label} has duplicate normalized rows.")
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            errors.append(f"{label} is missing {len(missing)} expected rows.")
        if extra:
            errors.append(f"{label} has {len(extra)} unexpected rows.")

    source_names = [row.get("venue", "") for row in sources]
    pool_names = [row.get("artist", "") for row in pool]
    check_exact_coverage("venue_coverage.csv", source_names, source_coverage, "venue")
    check_exact_coverage("artist_pool_page_matches.csv", pool_names, page_matches, "artist")
    check_exact_coverage("artist_window_event_coverage.csv", pool_names, event_coverage, "artist")

    if len(source_coverage) != len(sources):
        errors.append(f"Expected one source-coverage row per configured source ({len(sources)}); found {len(source_coverage)}.")
    if len(event_coverage) != len(pool):
        errors.append(f"Expected one event-comparison row per pool row ({len(pool)}); found {len(event_coverage)}.")

    audited_failures = 0
    for row in crawl_audit:
        try:
            audited_failures += int(row.get("pages_failed") or 0)
        except ValueError:
            errors.append(f"Invalid pages_failed count in crawl audit for {row.get('venue', '(unknown venue)')}.")
    if len(fetch_failures) != audited_failures:
        errors.append(
            f"event_page_fetch_failures.csv has {len(fetch_failures)} rows but venue crawl audit records {audited_failures} failed fetches."
        )
    configured_venue_keys = {normalize_key(name) for name in source_names if normalize_key(name)}
    for index, row in enumerate(fetch_failures, 2):
        if not (row.get("page_url") or "").strip():
            errors.append(f"event_page_fetch_failures.csv row {index} has no page URL.")
        if not (row.get("error_message") or "").strip():
            errors.append(f"event_page_fetch_failures.csv row {index} has no error message.")
        if normalize_key(row.get("venue", "")) not in configured_venue_keys:
            errors.append(f"event_page_fetch_failures.csv row {index} references an unknown venue.")

    unchecked_sources = [row.get("venue", "") for row in source_coverage if row.get("outcome") in {"not_checked", "partial"}]
    if unchecked_sources:
        warnings.append(f"{len(unchecked_sources)} venue sources are partial or not checked: {', '.join(unchecked_sources[:8])}")
    unverified_calendars = [row.get("venue", "") for row in source_coverage if (row.get("calendar_coverage_verified") or "").casefold() != "true"]
    if unverified_calendars:
        warnings.append(f"{len(unverified_calendars)} source calendars have not been independently verified; a fetched page is not proof of full calendar coverage.")
    unsearched_artists = [row.get("artist", "") for row in page_matches if (row.get("searched") or "").casefold() != "true"]
    if unsearched_artists:
        warnings.append(f"{len(unsearched_artists)} pool artists lack a completed captured-page search.")
    unjoined_artists = [row.get("artist", "") for row in event_coverage if (row.get("searched") or "").casefold() != "true"]
    if unjoined_artists:
        warnings.append(f"{len(unjoined_artists)} pool artists lack a completed dated-event comparison.")

    if start and end:
        for index, row in enumerate(matches, 2):
            try:
                event_day = date.fromisoformat((row.get("event_date") or "")[:10])
                if not start <= event_day <= end:
                    errors.append(f"artist_window_event_matches.csv row {index} is outside the reporting window.")
            except ValueError:
                errors.append(f"artist_window_event_matches.csv row {index} has an invalid event date.")
            if (row.get("verified") or "").casefold() == "true":
                errors.append(f"artist_window_event_matches.csv row {index} is marked verified by a candidate-only runner.")
            if not (row.get("source_url") or "").strip():
                warnings.append(f"Candidate row {index} has no source URL and needs triage.")

    report = {
        "valid": not errors,
        "status": "PARTIAL",
        "run_id": manifest.get("run_id", ""),
        "window_start": manifest.get("window_start", ""),
        "window_end": manifest.get("window_end", ""),
        "configured_sources": len(sources),
        "source_coverage_rows": len(source_coverage),
        "pool_artists": len(pool),
        "page_search_rows": len(page_matches),
        "event_comparison_rows": len(event_coverage),
        "candidate_match_rows": len(matches),
        "out_of_scope_event_rows": len(out_of_scope),
        "failed_page_fetch_rows": len(fetch_failures),
        "crawl_audit_failed_page_count": audited_failures,
        "errors": errors,
        "warnings": warnings,
        "important_limit": "Valid package structure does not prove exhaustive calendar coverage or independently verified gigs.",
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
