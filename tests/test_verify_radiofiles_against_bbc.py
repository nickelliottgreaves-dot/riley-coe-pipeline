import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_radiofiles_against_bbc.py"

class BBCRadioFilesCrosscheckTests(unittest.TestCase):
    def write_csv(self, path, fields, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_only_exact_full_position_matches_are_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bbc_tracks = root / "bbc_tracks.csv"
            bbc_episodes = root / "bbc_episodes.csv"
            rf_tracks = root / "rf_tracks.csv"
            rf_episodes = root / "rf_episodes.csv"
            self.write_csv(bbc_tracks,
                ["episode_date","episode_url","track_position","track_title","artist_candidate"],
                [
                    {"episode_date":"2026-10-13","episode_url":"https://www.bbc.co.uk/sounds/play/m0031tk4","track_position":"1","track_title":"Song One","artist_candidate":"Artist One"},
                    {"episode_date":"2026-10-13","episode_url":"https://www.bbc.co.uk/sounds/play/m0031tk4","track_position":"2","track_title":"Song Two","artist_candidate":"Artist Two"},
                    {"episode_date":"2026-10-14","episode_url":"https://www.bbc.co.uk/sounds/play/m0031tk5","track_position":"1","track_title":"Song Three","artist_candidate":"Artist Three"},
                ])
            self.write_csv(bbc_episodes, ["episode_date","episode_url","page_fetch_status"], [
                {"episode_date":"2026-10-13","episode_url":"https://www.bbc.co.uk/sounds/play/m0031tk4","page_fetch_status":"fetched"},
                {"episode_date":"2026-10-14","episode_url":"https://www.bbc.co.uk/sounds/play/m0031tk5","page_fetch_status":"fetched"},
            ])
            self.write_csv(rf_tracks,
                ["episode_date","episode_pid","track_position","track_title","artist_candidate","source_url"],
                [
                    {"episode_date":"2026-10-13","episode_pid":"m0031tk4","track_position":"1","track_title":"Song One","artist_candidate":"Artist One","source_url":"https://radiofiles.io/app?pid=m0031tk4"},
                    {"episode_date":"2026-10-13","episode_pid":"m0031tk4","track_position":"2","track_title":"Song Two","artist_candidate":"Artist Two","source_url":"https://radiofiles.io/app?pid=m0031tk4"},
                    {"episode_date":"2026-10-14","episode_pid":"m0031tk5","track_position":"1","track_title":"Wrong Song","artist_candidate":"Artist Three","source_url":"https://radiofiles.io/app?pid=m0031tk5"},
                ])
            self.write_csv(rf_episodes, ["episode_date","episode_pid","source_url","tracklist_status","track_count_returned","episode_title"], [
                {"episode_date":"2026-10-13","episode_pid":"m0031tk4","source_url":"https://radiofiles.io/app?pid=m0031tk4","tracklist_status":"candidate","track_count_returned":"2","episode_title":"Test"},
                {"episode_date":"2026-10-14","episode_pid":"m0031tk5","source_url":"https://radiofiles.io/app?pid=m0031tk5","tracklist_status":"candidate","track_count_returned":"1","episode_title":"Test"},
            ])
            out = root / "out"
            subprocess.run([sys.executable, str(SCRIPT), "--bbc-tracks", str(bbc_tracks),
                "--bbc-episodes", str(bbc_episodes), "--radiofiles-tracks", str(rf_tracks),
                "--radiofiles-episodes", str(rf_episodes), "--out-dir", str(out)],
                check=True, capture_output=True, text=True)
            with (out / "bbc_radiofiles_episode_crosscheck.csv").open(newline="", encoding="utf-8") as handle:
                episodes = list(csv.DictReader(handle))
            by_pid = {row["episode_pid"]: row for row in episodes}
            self.assertEqual(by_pid["m0031tk4"]["crosscheck_status"], "EXACT_FULL_TRACKLIST_MATCH")
            self.assertEqual(by_pid["m0031tk5"]["crosscheck_status"], "MISMATCH_REQUIRES_REVIEW")
            with (out / "verified_episode_artist_candidates.csv").open(newline="", encoding="utf-8") as handle:
                candidates = list(csv.DictReader(handle))
            self.assertEqual({row["artist_candidate"] for row in candidates}, {"Artist One","Artist Two"})
            audit = json.loads((out / "bbc_radiofiles_crosscheck_audit.json").read_text())
            self.assertFalse(audit["pool_modified"])
            self.assertEqual(audit["episodes_with_exact_full_tracklist_match"], 1)

if __name__ == "__main__":
    unittest.main()
