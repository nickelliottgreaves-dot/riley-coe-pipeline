import sys, unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_radiofiles import parse_episode_date, validate_tracklist


class RadioFilesCollectorTests(unittest.TestCase):
    def test_parses_radiofiles_episode_dates(self):
        self.assertEqual(parse_episode_date("12 Oct 2026"), date(2026, 10, 12))
        self.assertEqual(parse_episode_date("2026-10-12"), date(2026, 10, 12))
        self.assertIsNone(parse_episode_date("unknown"))

    def test_matching_count_date_and_rows_remain_review_only(self):
        payload = {
            "tracks": [
                {"title": "Free Way", "artist": "Lafayette And The Lasabres"},
                {"title": "The Swim Thing", "artist": "Dave Lewis"},
            ],
            "count": 2,
            "date": "12 Oct 2026",
            "show_pid": "m001mf2c",
            "source": "bbc (archive)",
        }
        result = validate_tracklist(payload, "m0032d2m", date(2026, 10, 12))
        self.assertTrue(result["count_match"])
        self.assertTrue(result["date_match"])
        self.assertIsNone(result["pid_match"])
        self.assertTrue(result["internally_consistent"])
        self.assertEqual(len(result["tracks"]), 2)
        self.assertEqual(result["tracks"][0]["artist_candidate"], "Lafayette And The Lasabres")

    def test_count_mismatch_does_not_pass_validation(self):
        payload = {
            "tracks": [{"title": "Free Way", "artist": "Lafayette And The Lasabres"}],
            "count": 2,
            "date": "12 Oct 2026",
        }
        result = validate_tracklist(payload, "m0032d2m", date(2026, 10, 12))
        self.assertFalse(result["count_match"])
        self.assertFalse(result["internally_consistent"])

    def test_missing_artist_or_title_does_not_pass_validation(self):
        payload = {
            "tracks": [{"title": "Free Way"}, {"artist": "Dave Lewis"}],
            "count": 2,
            "date": "12 Oct 2026",
        }
        result = validate_tracklist(payload, "m0032d2m", date(2026, 10, 12))
        self.assertFalse(result["internally_consistent"])
        self.assertEqual(len(result["tracks"]), 0)
        self.assertEqual(len(result["row_errors"]), 2)


if __name__ == "__main__":
    unittest.main()
