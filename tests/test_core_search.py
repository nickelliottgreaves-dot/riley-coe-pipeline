import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_core_search import build_coverage, inspection_to_candidates, match_candidates, normalize


class CoreSearchTests(unittest.TestCase):
    def test_core_registry_is_exactly_nine_agreed_venues_or_rooms(self):
        with (ROOT / "config/core_venues.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 9)
        self.assertEqual(
            {normalize(row["venue"]) for row in rows},
            {normalize(name) for name in [
                "The Cluny", "Cluny 2", "Boiler Shop", "Wylam Brewery", "The Grove",
                "Sage Two", "Cumberland Arms", "Cobalt Studios", "Lubber Fiend",
            ]},
        )

    def test_matches_every_candidate_event_against_full_supplied_pool(self):
        events = [
            {"event_date": "2026-10-20", "venue": "The Cluny", "event_title": "A", "artist": "A Certain Ratio", "source_url": "https://example.test/a"},
            {"event_date": "2026-10-21", "venue": "Lubber Fiend", "event_title": "B", "artist": "Gallus", "source_url": "https://example.test/b"},
            {"event_date": "2026-10-22", "venue": "The Grove", "event_title": "C", "artist": "Unknown Act", "source_url": "https://example.test/c"},
        ]
        pool = [{"artist": "A Certain Ratio"}, {"artist": "Gallus"}]
        matches = match_candidates(events, pool, [])
        self.assertEqual([row["matched_pool_artist"] for row in matches], ["A Certain Ratio", "Gallus"])
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(row["verified"] == "false" for row in matches))

    def test_inspection_expands_each_billed_act_to_an_independent_candidate(self):
        rows = [{
            "event_date": "2026-10-20",
            "venue": "The Cluny",
            "event_title": "Tour date",
            "performer_names": "Gallus; A Certain Ratio",
            "page_url": "https://example.test/event",
            "notes": "review required",
        }]
        candidates = inspection_to_candidates(rows)
        self.assertEqual([row["artist"] for row in candidates], ["Gallus", "A Certain Ratio"])
        matches = match_candidates(candidates, [{"artist": "Gallus"}, {"artist": "A Certain Ratio"}], [])
        self.assertEqual({row["matched_pool_artist"] for row in matches}, {"Gallus", "A Certain Ratio"})

    def test_inspection_without_named_performer_is_not_a_pool_match(self):
        rows = [{
            "event_date": "2026-10-20",
            "venue": "Wylam Brewery",
            "event_title": "Lord Of The Wings | Food Battle",
            "performer_names": "",
            "page_url": "https://example.test/event",
        }]
        self.assertEqual(inspection_to_candidates(rows), [])

    def test_approved_alias_is_used_only_when_canonical_is_in_pool(self):
        events = [{"event_date": "2026-10-20", "venue": "X", "event_title": "Y", "artist": "Alias Act", "source_url": "https://example.test"}]
        aliases = [{"alias": "Alias Act", "canonical": "Canonical Act", "review_status": "approved"}]
        self.assertEqual(match_candidates(events, [{"artist": "Canonical Act"}], aliases)[0]["match_type"], "approved_alias")
        self.assertEqual(match_candidates(events, [{"artist": "Different Act"}], aliases), [])

    def test_coverage_always_discloses_unverified_calendar(self):
        core = [{"venue": "Lubber Fiend", "source_url": "https://example.test", "source_status": "verified_official_site"}]
        audit = [{"venue": "Lubber Fiend", "status": "fetched_candidates_only", "notes": "page fetched"}]
        coverage = build_coverage(core, audit, [], [])
        self.assertEqual(coverage[0]["calendar_coverage_verified"], "false")
        self.assertEqual(coverage[0]["fetch_status"], "fetched_candidates_only")


if __name__ == "__main__":
    unittest.main()
