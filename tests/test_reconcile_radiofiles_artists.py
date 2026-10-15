import csv
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.reconcile_radiofiles_artists import main, norm

class RadioFilesReconciliationTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(norm("YĪN YĪN"), "yin yin")
        self.assertEqual(norm("Joe Gibbs & The Professionals"), "joe gibbs and the professionals")
        self.assertEqual(norm("Allo Darlin’"), "allo darlin")

    def test_outputs_review_only_without_mutating_pool(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pool = root / "pool.csv"
            aliases = root / "aliases.csv"
            episodes = root / "episodes.csv"
            tracks = root / "tracks.csv"
            out = root / "out"
            pool.write_text("index,artist,status,source_basis\n1,Joy Division,ACTIVE,test\n", encoding="utf-8")
            aliases.write_text("alias,canonical,source_basis,review_status\nJD,Joy Division,test,APPROVED\n", encoding="utf-8")
            episodes.write_text("episode_date,episode_title,episode_pid,track_count_reported,track_count_returned,count_match,tracklist_status,source_url,notes\n2026-10-14,Riley & Coe,m1,2,2,True,needs_review,https://example.test,\n", encoding="utf-8")
            tracks.write_text("episode_date,episode_title,episode_pid,track_position,track_title,artist_candidate,source_url,tracklist_api_url,source,verification_status,notes\n2026-10-14,Riley & Coe,m1,1,Song,Joy Division,https://example.test,https://example.test/api,RadioFiles,needs_manual_crosscheck,test\n2026-10-14,Riley & Coe,m1,2,Other,New Artist,https://example.test,https://example.test/api,RadioFiles,needs_manual_crosscheck,test\n", encoding="utf-8")
            old = sys.argv
            try:
                sys.argv = ["reconcile_radiofiles_artists.py", "--pool", str(pool), "--aliases", str(aliases), "--episodes", str(episodes), "--tracks", str(tracks), "--out-dir", str(out)]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old
            with (out / "radiofiles_artist_reconciliation.csv").open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(next(r for r in rows if r["artist_candidate"] == "Joy Division")["reconciliation_status"], "EXACT_NORMALIZED_POOL_MATCH")
            new = next(r for r in rows if r["artist_candidate"] == "New Artist")
            self.assertEqual(new["reconciliation_status"], "UNMATCHED_REVIEW_ONLY")
            self.assertTrue(new["promotion_status"].startswith("NOT_PROMOTED"))
            with pool.open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)

if __name__ == "__main__":
    unittest.main()
