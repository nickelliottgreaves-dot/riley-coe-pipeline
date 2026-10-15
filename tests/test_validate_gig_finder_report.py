from __future__ import annotations

import csv
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.validate_gig_finder_report import main


class ValidateGigFinderReportTests(unittest.TestCase):
    def write_csv(self, path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def build_fixture(self, root: Path, *, omit_source_coverage: bool = False) -> tuple[Path, Path, Path]:
        run = root / "run"
        run.mkdir()
        sources = root / "sources.csv"
        pool = root / "pool.csv"
        self.write_csv(sources, ["venue", "source_url", "source_status", "notes"], [
            {"venue": "Test Venue", "source_url": "https://example.test/events", "source_status": "official", "notes": ""}
        ])
        self.write_csv(pool, ["artist", "status"], [{"artist": "Test Artist", "status": "active"}])
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "test-run", "run_date": "2026-10-15",
            "window_start": "2026-10-15", "window_end": "2026-11-11",
            "previous_successful_run": "unknown/not established",
            "researcher_notes": "test fixture", "claimed_status": "PARTIAL"
        }), encoding="utf-8")
        if not omit_source_coverage:
            self.write_csv(run / "venue_coverage.csv", [
                "venue", "source_url", "page_fetch_status", "http_status", "discovery_status",
                "candidate_events", "candidate_links", "detail_pages_fetched", "detail_pages_failed",
                "crawl_cap_reached", "calendar_coverage_verified", "outcome", "notes"
            ], [{
                "venue": "Test Venue", "source_url": "https://example.test/events",
                "page_fetch_status": "page_captured", "http_status": "200",
                "discovery_status": "fetched_candidates_only", "candidate_events": "0",
                "candidate_links": "0", "detail_pages_fetched": "0", "detail_pages_failed": "0",
                "crawl_cap_reached": "false", "calendar_coverage_verified": "false",
                "outcome": "checked_in_captured_scope", "notes": ""
            }])
        self.write_csv(run / "artist_pool_page_matches.csv", [
            "artist", "searched", "result", "evidence_url", "notes"
        ], [{"artist": "Test Artist", "searched": "true", "result": "not_found_in_captured_pages", "evidence_url": "", "notes": "bounded corpus"}])
        self.write_csv(run / "artist_window_event_coverage.csv", [
            "artist", "searched", "candidate_count", "result", "window_start", "window_end", "notes"
        ], [{"artist": "Test Artist", "searched": "true", "candidate_count": "0", "result": "no_exact_dated_candidate_match", "window_start": "2026-10-15", "window_end": "2026-11-11", "notes": "bounded corpus"}])
        self.write_csv(run / "artist_window_event_matches.csv", [
            "artist_pool_name", "event_date", "venue", "event_title", "matched_performer",
            "source_url", "source_kind", "match_basis", "candidate_status", "price",
            "ticket_status", "verified", "notes"
        ], [])
        self.write_csv(run / "out_of_scope_event_candidates.csv", [
            "event_date", "source_venue", "explicit_location", "event_title", "artist", "source_url", "notes"
        ], [])
        inspection_dir = run / "event_inspection"
        inspection_dir.mkdir()
        self.write_csv(inspection_dir / "event_page_crawl_audit.csv", [
            "venue", "seed_candidate_links", "external_seed_links_skipped", "external_event_pages_inspected",
            "pages_fetched", "pages_failed", "same_host_links_added", "crawl_cap_reached", "status", "notes"
        ], [{
            "venue": "Test Venue", "seed_candidate_links": "1", "external_seed_links_skipped": "0",
            "external_event_pages_inspected": "0", "pages_fetched": "1", "pages_failed": "0",
            "same_host_links_added": "0", "crawl_cap_reached": "false", "status": "PARTIAL", "notes": "fixture"
        }])
        self.write_csv(inspection_dir / "event_page_fetch_failures.csv", [
            "venue", "page_url", "crawl_depth", "http_status", "external_page", "error_type", "error_message"
        ], [])
        self.write_csv(run / "stage_results.csv", ["stage", "status", "exit_code", "command", "log_file", "notes"], [])
        return run, pool, sources

    def test_valid_partial_package_passes_and_remains_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            run, pool, sources = self.build_fixture(Path(temp))
            output = StringIO()
            with patch("sys.argv", ["validate_gig_finder_report.py", "--run-dir", str(run), "--pool", str(pool), "--sources", str(sources)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            self.assertTrue(result["valid"])
            self.assertEqual(result["status"], "PARTIAL")

    def test_failure_ledger_must_match_crawl_audit_count(self):
        with tempfile.TemporaryDirectory() as temp:
            run, pool, sources = self.build_fixture(Path(temp))
            failures = run / "event_inspection" / "event_page_fetch_failures.csv"
            with failures.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "venue", "page_url", "crawl_depth", "http_status", "external_page", "error_type", "error_message"
                ])
                writer.writerow({
                    "venue": "Test Venue", "page_url": "https://example.test/broken",
                    "crawl_depth": "1", "http_status": "503", "external_page": "false",
                    "error_type": "ValueError", "error_message": "HTTP 503 returned no visible text"
                })
            output = StringIO()
            with patch("sys.argv", ["validate_gig_finder_report.py", "--run-dir", str(run), "--pool", str(pool), "--sources", str(sources)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 1)
            self.assertIn("event_page_fetch_failures.csv has 1 rows but venue crawl audit records 0 failed fetches", output.getvalue())

    def test_missing_source_coverage_row_fails_integrity_check(self):
        with tempfile.TemporaryDirectory() as temp:
            run, pool, sources = self.build_fixture(Path(temp), omit_source_coverage=True)
            output = StringIO()
            with patch("sys.argv", ["validate_gig_finder_report.py", "--run-dir", str(run), "--pool", str(pool), "--sources", str(sources)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 1)
            self.assertIn("Missing required report file: venue_coverage.csv", output.getvalue())


if __name__ == "__main__":
    unittest.main()
