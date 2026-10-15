#!/usr/bin/env python3
"""Run the independent candidate-finding process using the shared contract.

Collection failures are recorded and the runner still assembles a PARTIAL
candidate package when possible. This runner intentionally does not use the
legacy assembler or promote any candidate to verified.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .workflow_contract import ROOT, build_manifest, load_contract, normalize_key, reporting_window, validate_registries
except ImportError:  # Support direct execution as `python scripts/run_gig_finder.py`.
    from workflow_contract import ROOT, build_manifest, load_contract, normalize_key, reporting_window, validate_registries

SOURCE_FIELDS = ["venue", "source_url", "source_status", "notes"]
DISCOVERY_EVENT_FIELDS = ["event_date", "venue", "event_title", "artist", "artist_role", "source_url", "verified", "price", "ticket_status", "discovery_method", "notes"]
LINK_FIELDS = ["venue", "link_text", "candidate_url", "source_page_url", "candidate_reason", "verified", "notes"]
INSPECTED_FIELDS = ["venue", "page_url", "http_status", "content_type", "page_title", "event_title", "event_date", "performer_names", "price", "currency", "availability", "event_jsonld_found", "visible_text_snapshot", "verified", "status", "notes"]
MATCH_FIELDS = ["artist_pool_name", "event_date", "venue", "event_title", "matched_performer", "source_url", "source_kind", "match_basis", "candidate_status", "price", "ticket_status", "verified", "notes"]
COVERAGE_FIELDS = ["venue", "source_url", "page_fetch_status", "http_status", "discovery_status", "candidate_events", "candidate_links", "detail_pages_fetched", "detail_pages_failed", "external_event_pages_inspected", "crawl_cap_reached", "calendar_coverage_verified", "outcome", "notes"]
STAGE_FIELDS = ["stage", "status", "exit_code", "timeout_seconds", "command", "log_file", "notes"]
STAGE_TIMEOUT_SECONDS = 300


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ensure_csv(path: Path, fields: list[str]) -> None:
    if not path.exists():
        write_csv(path, fields, [])


def run_stage(name: str, command: list[str], out_dir: Path, results: list[dict[str, str]]) -> None:
    log_dir = out_dir / "stage_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    rendered = shlex.join(command)
    try:
        completed = subprocess.run(
            command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=STAGE_TIMEOUT_SECONDS,
        )
        log_path.write_text(completed.stdout or "", encoding="utf-8")
        code = completed.returncode
        status = "success" if code == 0 else "failed"
        notes = "Stage completed." if code == 0 else "Non-zero exit; any outputs and the stage log are retained; later stages continue to produce a PARTIAL report."
    except subprocess.TimeoutExpired as exc:
        code = 124
        status = "timed_out"
        partial_output = exc.stdout or b""
        if isinstance(partial_output, bytes):
            partial_output = partial_output.decode("utf-8", errors="replace")
        log_path.write_text(str(partial_output) + f"\nStage exceeded {STAGE_TIMEOUT_SECONDS}s timeout and was terminated.\n", encoding="utf-8")
        notes = f"Stage exceeded {STAGE_TIMEOUT_SECONDS}s timeout; retained partial log/outputs and continued to produce a PARTIAL report."
    except OSError as exc:
        code = 127
        status = "failed"
        notes = str(exc)
        log_path.write_text(notes + "\n", encoding="utf-8")
    results.append({
        "stage": name, "status": status, "exit_code": str(code),
        "timeout_seconds": str(STAGE_TIMEOUT_SECONDS),
        "command": rendered, "log_file": str(log_path.relative_to(out_dir)),
        "notes": notes,
    })


def prepare_source_registry(
    source_path: Path,
    out_dir: Path,
    simulate_failure_venue: str | None = None,
) -> tuple[Path, str | None]:
    """Return collector input registry, optionally injecting one controlled failure."""
    if not simulate_failure_venue:
        return source_path, None
    rows = read_csv(source_path)
    target_key = normalize_key(simulate_failure_venue)
    matches = [row for row in rows if normalize_key(row.get("venue", "")) == target_key]
    if len(matches) != 1:
        raise ValueError(f"Simulated failure venue must identify exactly one configured source: {simulate_failure_venue}")
    selected = matches[0]
    original_url = selected.get("source_url", "")
    selected["source_url"] = "http://127.0.0.1:9/simulated-source-failure"
    selected["source_status"] = "simulated_failure"
    selected["notes"] = (selected.get("notes", "") + " | Acceptance-test-only simulated fetch failure; original URL: " + original_url).strip(" |")
    out_path = out_dir / "source_registry_for_run.csv"
    write_csv(out_path, SOURCE_FIELDS, rows)
    return out_path, selected.get("venue", simulate_failure_venue)


def combine_venue_coverage(
    sources: list[dict[str, str]],
    page_rows: list[dict[str, str]],
    discovery_rows: list[dict[str, str]],
    crawl_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    def index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
        return {normalize_key(row.get("venue", "")): row for row in rows if normalize_key(row.get("venue", ""))}
    page_by = index(page_rows)
    discovery_by = index(discovery_rows)
    crawl_by = index(crawl_rows)
    result = []
    for source in sources:
        venue = (source.get("venue") or "").strip()
        key = normalize_key(venue)
        page = page_by.get(key, {})
        discovery = discovery_by.get(key, {})
        crawl = crawl_by.get(key, {})
        failed_pages = (crawl.get("pages_failed") or "").strip()
        cap = (crawl.get("crawl_cap_reached") or "").strip().casefold()
        page_status = ("page_captured" if page.get("text_file") else "fetch_failed") if page else "not_checked"
        discovery_status = (discovery.get("status") or "not_checked").strip()
        notes = " ".join(x.strip() for x in [
            source.get("notes", ""), page.get("notes", ""),
            discovery.get("notes", ""), crawl.get("notes", ""),
        ] if x and x.strip())
        has_any_audit = bool(page or discovery or crawl)
        has_failure = (
            page_status.casefold() in {"failed", "inaccessible", "http_error", "error"}
            or discovery_status.casefold() in {"failed", "inaccessible", "error"}
            or (failed_pages.isdigit() and int(failed_pages) > 0)
            or cap in {"true", "yes", "1"}
        )
        if not has_any_audit:
            outcome = "not_checked"
        elif has_failure:
            outcome = "partial"
        elif page or discovery or crawl:
            outcome = "checked_in_captured_scope"
        else:
            outcome = "not_checked"
        result.append({
            "venue": venue,
            "source_url": source.get("source_url", ""),
            "page_fetch_status": page_status,
            "http_status": page.get("http_status", ""),
            "discovery_status": discovery_status,
            "candidate_events": discovery.get("structured_events_found", "0"),
            "candidate_links": discovery.get("candidate_links_found", "0"),
            "detail_pages_fetched": crawl.get("pages_fetched", "0"),
            "detail_pages_failed": failed_pages or "0",
            "external_event_pages_inspected": crawl.get("external_event_pages_inspected", "0"),
            "crawl_cap_reached": cap or "false",
            "calendar_coverage_verified": "false",
            "outcome": outcome,
            "notes": notes or "No usable audit row; calendar coverage is not established.",
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="Inclusive ISO date; defaults to today")
    parser.add_argument("--out-dir", type=Path, help="Unique output directory; defaults under artifacts/runs")
    parser.add_argument("--previous-successful-run", default="unknown/not established")
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--simulate-source-failure", help="Inject a deterministic fetch failure for one configured venue; acceptance testing only.")
    args = parser.parse_args()

    contract = load_contract()
    registry_check = validate_registries(ROOT)
    if not registry_check["valid"]:
        print(json.dumps(registry_check, indent=2), file=sys.stderr)
        return 2

    start, end = reporting_window(args.start, contract=contract)
    run_date = date.today()
    run_id = str(args.run_id or f"local-{datetime.now(timezone.utc).strftime('%H%M%S%f')}")
    if args.out_dir:
        out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    else:
        safe_id = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_") or "local"
        out_dir = ROOT / contract["run_output_root"] / f"{run_date.isoformat()}_{safe_id}"
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"Refusing to overwrite non-empty run directory: {out_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    sources_path = ROOT / contract["venue_sources_path"]
    pool_path = ROOT / contract["artist_pool_path"]
    sources = read_csv(sources_path)
    try:
        collector_sources_path, simulated_failure_venue = prepare_source_registry(
            sources_path, out_dir, args.simulate_source_failure
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    stage_results: list[dict[str, str]] = []

    venue_dir = out_dir / "venue_pages"
    discovery_dir = out_dir / "event_discovery"
    inspection_dir = out_dir / "event_inspection"
    venue_dir.mkdir(parents=True, exist_ok=True)
    discovery_dir.mkdir(parents=True, exist_ok=True)
    inspection_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    run_stage("venue_page_inventory", [
        py, "scripts/collect_venue_pages.py", "--sources", str(collector_sources_path),
        "--out-dir", str(venue_dir),
    ], out_dir, stage_results)
    run_stage("event_candidate_discovery", [
        py, "scripts/discover_event_candidates.py", "--sources", str(collector_sources_path),
        "--start", start.isoformat(), "--end", end.isoformat(), "--out-dir", str(discovery_dir),
    ], out_dir, stage_results)

    ensure_csv(discovery_dir / "event_candidates.csv", DISCOVERY_EVENT_FIELDS)
    ensure_csv(discovery_dir / "event_link_candidates.csv", LINK_FIELDS)
    run_stage("event_page_inspection", [
        py, "scripts/inspect_event_links.py",
        "--links", str(discovery_dir / "event_link_candidates.csv"),
        "--sources", str(collector_sources_path), "--start", start.isoformat(), "--end", end.isoformat(),
        "--max-pages-per-venue", "120", "--max-depth", "3", "--out-dir", str(inspection_dir),
    ], out_dir, stage_results)
    ensure_csv(inspection_dir / "event_page_inspection.csv", INSPECTED_FIELDS)
    ensure_csv(inspection_dir / "event_page_crawl_audit.csv", [
        "venue", "seed_candidate_links", "external_seed_links_skipped", "external_event_pages_inspected", "pages_fetched",
        "pages_failed", "same_host_links_added", "crawl_cap_reached", "status", "notes",
    ])
    ensure_csv(inspection_dir / "event_page_fetch_failures.csv", [
        "venue", "page_url", "crawl_depth", "http_status", "external_page", "error_type", "error_message",
    ])

    pool_page_matches = out_dir / "artist_pool_page_matches.csv"
    run_stage("full_pool_page_comparison", [
        py, "scripts/check_regression_artists.py", "--seeds", str(pool_path),
        "--venue-snapshots", str(venue_dir / "page_text"),
        "--event-snapshots", str(inspection_dir / "snapshots"),
        "--venues", str(collector_sources_path), "--out", str(pool_page_matches),
    ], out_dir, stage_results)
    ensure_csv(pool_page_matches, ["artist", "searched", "result", "evidence_url", "notes"])
    pool_rows = read_csv(pool_path)
    page_match_rows = read_csv(pool_page_matches)
    page_match_keys = {normalize_key(row.get("artist", "")) for row in page_match_rows}
    for pool_row in pool_rows:
        artist = (pool_row.get("artist") or "").strip()
        key = normalize_key(artist)
        if key and key not in page_match_keys:
            page_match_rows.append({
                "artist": artist, "searched": "false",
                "result": "not_searched_due_to_stage_failure", "evidence_url": "",
                "notes": "No per-artist search result was emitted by the page-comparison stage.",
            })
    write_csv(pool_page_matches, ["artist", "searched", "result", "evidence_url", "notes"], page_match_rows)

    matches_path = out_dir / "artist_window_event_matches.csv"
    run_stage("date_window_artist_matching", [
        py, "scripts/match_pool_to_window_events.py", "--pool", str(pool_path),
        "--events", str(discovery_dir / "event_candidates.csv"),
        "--inspected", str(inspection_dir / "event_page_inspection.csv"),
        "--pool-page-matches", str(pool_page_matches),
        "--start", start.isoformat(), "--end", end.isoformat(), "--out", str(matches_path),
    ], out_dir, stage_results)
    ensure_csv(matches_path, MATCH_FIELDS)
    ensure_csv(out_dir / "out_of_scope_event_candidates.csv", ["event_date", "source_venue", "explicit_location", "event_title", "artist", "source_url", "notes"])
    coverage_path = out_dir / "artist_window_event_coverage.csv"
    ensure_csv(coverage_path, [
        "artist", "searched", "candidate_count", "result", "window_start", "window_end", "notes",
    ])
    event_coverage_rows = read_csv(coverage_path)
    event_coverage_keys = {normalize_key(row.get("artist", "")) for row in event_coverage_rows}
    for pool_row in pool_rows:
        artist = (pool_row.get("artist") or "").strip()
        key = normalize_key(artist)
        if key and key not in event_coverage_keys:
            event_coverage_rows.append({
                "artist": artist, "searched": "false", "candidate_count": "0",
                "result": "not_searched_due_to_stage_failure",
                "window_start": start.isoformat(), "window_end": end.isoformat(),
                "notes": "No per-artist event comparison row was emitted by the matching stage.",
            })
    write_csv(coverage_path, [
        "artist", "searched", "candidate_count", "result", "window_start", "window_end", "notes",
    ], event_coverage_rows)

    page_audit = read_csv(venue_dir / "venue_page_access_audit.csv")
    discovery_audit = read_csv(discovery_dir / "event_discovery_audit.csv")
    crawl_audit = read_csv(inspection_dir / "event_page_crawl_audit.csv")
    fetch_failures = read_csv(inspection_dir / "event_page_fetch_failures.csv")
    crawl_audit_failed_pages = sum(int(row.get("pages_failed") or 0) for row in crawl_audit if (row.get("pages_failed") or "0").isdigit())
    coverage = combine_venue_coverage(sources, page_audit, discovery_audit, crawl_audit)
    write_csv(out_dir / "venue_coverage.csv", COVERAGE_FIELDS, coverage)
    write_csv(out_dir / "stage_results.csv", STAGE_FIELDS, stage_results)

    manifest = build_manifest(
        run_date=run_date, window_start=start,
        previous_successful_run=args.previous_successful_run,
        researcher_notes=(
            "Acceptance-test run with simulated source failure for " + simulated_failure_venue
            if simulated_failure_venue else
            "Independent gig-finder run. Candidates are unverified; calendar completeness is not inferred from fetch success."
        ),
        run_id=run_id, branch=os.environ.get("GITHUB_REF_NAME", "local"),
        commit=os.environ.get("GITHUB_SHA", "unknown"), contract=contract,
    )
    matches = read_csv(matches_path)
    out_of_scope_rows = read_csv(out_dir / "out_of_scope_event_candidates.csv")
    artist_coverage = read_csv(out_dir / "artist_window_event_coverage.csv")
    pool_page_rows = read_csv(pool_page_matches)
    pool_count = registry_check["artist_count"]
    page_comparison_complete = (
        len(pool_page_rows) == pool_count
        and all((row.get("searched") or "").casefold() == "true" for row in pool_page_rows)
    )
    event_comparison_complete = (
        len(artist_coverage) == pool_count
        and all((row.get("searched") or "").casefold() == "true" for row in artist_coverage)
    )
    source_outcome_counts = {}
    for row in coverage:
        source_outcome_counts[row["outcome"]] = source_outcome_counts.get(row["outcome"], 0) + 1
    manifest.update({
        "claimed_status": "PARTIAL",
        "source_outcome_counts": source_outcome_counts,
        "artist_pool_compared": page_comparison_complete,
        "artist_pool_event_comparison_complete": event_comparison_complete,
        "configured_source_count": len(sources),
        "sources_with_explicit_coverage_rows": len(coverage),
        "sources_with_calendar_coverage_verified": sum(row["calendar_coverage_verified"] == "true" for row in coverage),
        "artist_pool_rows": registry_check["artist_count"],
        "artist_event_coverage_rows": len(artist_coverage),
        "candidate_match_rows": len(matches),
        "out_of_scope_event_rows": len(out_of_scope_rows),
        "simulated_source_failure": simulated_failure_venue,
        "verified_event_rows": sum((row.get("verified") or "").casefold() == "true" for row in matches),
        "stage_failures": sum(row["status"] != "success" for row in stage_results),
        "source_outcome_counts": source_outcome_counts,
        "episode_discovery_required_for_gig_finder": False,
        "limitations": [
            "A negative match applies only to the captured corpus.",
            "Fetched venue pages do not prove calendar pagination or event coverage is complete.",
            "All event/artist candidates remain unverified until independently checked.",
        ],
    })
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": "PARTIAL",
        "run_id": run_id,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "configured_sources": len(sources),
        "source_coverage_rows": len(coverage),
        "pool_artist_count": registry_check["artist_count"],
        "candidate_match_rows": len(matches),
        "out_of_scope_event_rows": len(out_of_scope_rows),
        "simulated_source_failure": simulated_failure_venue,
        "stage_failures": sum(row["status"] != "success" for row in stage_results),
        "failed_page_fetch_rows": len(fetch_failures),
        "crawl_audit_failed_page_count": crawl_audit_failed_pages,
        "output_directory": str(out_dir),
        "note": "A valid PARTIAL report is the expected result when any source is incomplete; no candidate is marked verified.",
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
