from __future__ import annotations

import csv
import tempfile
import unittest

from scripts.run_gig_finder import combine_venue_coverage, prepare_source_registry


class GigFinderCoverageTests(unittest.TestCase):
    def test_all_configured_sources_get_rows_even_without_discovery(self):
        sources = [
            {"venue": "Venue A", "source_url": "https://example.test/a", "notes": ""},
            {"venue": "Venue B", "source_url": "https://example.test/b", "notes": ""},
        ]
        rows = combine_venue_coverage(sources, [], [], [])
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["outcome"] for row in rows], ["not_checked", "not_checked"])
        self.assertTrue(all(row["calendar_coverage_verified"] == "false" for row in rows))

    def test_partial_page_failure_is_not_mistaken_for_complete_coverage(self):
        sources = [{"venue": "Venue A", "source_url": "https://example.test/a", "notes": ""}]
        page = [{"venue": "Venue A", "status": "fetched", "http_status": "200", "text_file": "page_text/venue-a.txt", "notes": ""}]
        discovery = [{"venue": "Venue A", "status": "ok", "structured_events_found": "1", "candidate_links_found": "2", "notes": ""}]
        crawl = [{"venue": "Venue A", "pages_fetched": "3", "pages_failed": "1", "crawl_cap_reached": "false", "status": "PARTIAL", "notes": "One detail page failed."}]
        row = combine_venue_coverage(sources, page, discovery, crawl)[0]
        self.assertEqual(row["outcome"], "partial")
        self.assertEqual(row["detail_pages_failed"], "1")
        self.assertEqual(row["calendar_coverage_verified"], "false")

    def test_empty_but_successfully_checked_capture_is_not_claimed_as_no_gigs(self):
        sources = [{"venue": "Venue A", "source_url": "https://example.test/a", "notes": ""}]
        page = [{"venue": "Venue A", "status": "fetched", "http_status": "200", "text_file": "page_text/venue-a.txt", "notes": ""}]
        discovery = [{"venue": "Venue A", "status": "ok", "structured_events_found": "0", "candidate_links_found": "0", "notes": ""}]
        row = combine_venue_coverage(sources, page, discovery, [])[0]
        self.assertEqual(row["outcome"], "checked_in_captured_scope")
        self.assertNotIn("no relevant events", row["outcome"])
        self.assertEqual(row["calendar_coverage_verified"], "false")


    def test_simulated_failure_changes_only_collector_copy_not_authoritative_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.csv"
            with sources.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["venue", "source_url", "source_status", "notes"])
                writer.writeheader()
                writer.writerow({"venue": "Venue A", "source_url": "https://example.test/a", "source_status": "official", "notes": ""})
                writer.writerow({"venue": "Venue B", "source_url": "https://example.test/b", "source_status": "official", "notes": ""})
            copied, selected = prepare_source_registry(sources, root, "Venue A")
            self.assertEqual(selected, "Venue A")
            with copied.open(encoding="utf-8-sig", newline="") as handle:
                rows = {row["venue"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["Venue A"]["source_url"], "http://127.0.0.1:9/simulated-source-failure")
            self.assertEqual(rows["Venue A"]["source_status"], "simulated_failure")
            self.assertEqual(rows["Venue B"]["source_url"], "https://example.test/b")
            with sources.open(encoding="utf-8-sig", newline="") as handle:
                original = {row["venue"]: row for row in csv.DictReader(handle)}
            self.assertEqual(original["Venue A"]["source_url"], "https://example.test/a")

    def test_simulated_failure_requires_exactly_one_configured_venue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.csv"
            with sources.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["venue", "source_url", "source_status", "notes"])
                writer.writeheader()
                writer.writerow({"venue": "Venue A", "source_url": "https://example.test/a", "source_status": "official", "notes": ""})
            with self.assertRaises(ValueError):
                prepare_source_registry(sources, root, "Missing Venue")


if __name__ == "__main__":
    unittest.main()
