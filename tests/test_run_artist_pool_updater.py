from __future__ import annotations

import unittest

from scripts.run_artist_pool_updater import summarize_episode_crosschecks


class ArtistPoolUpdaterSummaryTests(unittest.TestCase):
    def test_episode_metrics_reflect_exact_crosschecks_not_raw_bbc_status_labels(self):
        bbc = [{"episode_date": f"2026-10-{day:02d}"} for day in range(1, 13)]
        crosschecks = (
            [{"crosscheck_status": "EXACT_FULL_TRACKLIST_MATCH"} for _ in range(8)]
            + [{"crosscheck_status": "MISMATCH_REQUIRES_REVIEW"} for _ in range(3)]
        )
        result = summarize_episode_crosschecks(bbc, crosschecks)
        self.assertEqual(result["bbc_episode_rows"], 12)
        self.assertEqual(result["crosscheck_rows"], 11)
        self.assertEqual(result["exact_crosschecked_episode_rows"], 8)
        self.assertEqual(result["mismatched_episode_rows"], 3)
        self.assertEqual(result["bbc_episodes_without_crosscheck"], 1)
        self.assertEqual(result["episodes_not_exactly_crosschecked"], 4)


if __name__ == "__main__":
    unittest.main()
