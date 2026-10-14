import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_bbc_sounds import ProgrammeTrackParser, TextParser, parse_date, merge_episode_fallbacks, resolve_episode_date
from datetime import date


class BBCProgrammeParserTests(unittest.TestCase):
    def test_episode_title_date_wins_over_date_inside_tracklist(self):
        text = "Riley & Coe - 13/10/2026 - BBC Sounds\nTrack title mentions 7 Oct 2026"
        self.assertEqual(parse_date(text), "2026-10-13")

    def test_last_on_date_is_found_when_broadcast_label_and_date_share_line(self):
        self.assertEqual(parse_date("Last on Tue 6 Oct 2026 21:00\\nTrack title mentions 7 Oct 2026"), "2026-10-06")

    def test_radiofiles_episode_inventory_adds_missing_bbc_episode_ids(self):
        episodes=[{"url":"https://www.bbc.co.uk/sounds/play/m00322dj","title":"Delightful - Gideon presents the show solo.","listing_source_url":"https://www.bbc.co.uk/programmes/m001mf2c/episodes"}]
        fallback=[
            {"episode_pid":"m00322dj","episode_date":"2026-10-08","episode_title":"Riley & Coe - 8 Oct 2026"},
            {"episode_pid":"m003228p","episode_date":"2026-10-05","episode_title":"Riley & Coe - 5 Oct 2026"},
            {"episode_pid":"m0031twy","episode_date":"2026-09-30","episode_title":"Riley & Coe - 30 Sep 2026"},
        ]
        merged=merge_episode_fallbacks(episodes,fallback,date(2026,10,1),date(2026,10,14))
        self.assertEqual({row["episode_id"] for row in merged},{"m00322dj","m003228p"})
        existing=next(row for row in merged if row["episode_id"]=="m00322dj")
        self.assertEqual(existing["fallback_date"],"2026-10-08")
        self.assertEqual(len(merged),2)

    def test_fallback_episode_date_beats_incidental_page_date_but_flags_conflict(self):
        ep={"title":"Delightful - Gideon presents the show solo.","fallback_date":"2026-10-08","fallback_title":"Riley & Coe - 8 Oct 2026"}
        dt,note=resolve_episode_date(ep,"Last on 12 Oct 2026\\nA track title mentions 12/10/2026")
        self.assertEqual(dt,"2026-10-08")
        self.assertIn("suggested 2026-10-12",note)
        self.assertIn("manual verification",note)

    def test_explicit_episode_title_date_beats_fallback_and_page_text(self):
        ep={"title":"Riley & Coe - 13/10/2026","fallback_date":"2026-10-12"}
        dt,note=resolve_episode_date(ep,"Last on 12 Oct 2026")
        self.assertEqual(dt,"2026-10-13")
        self.assertEqual(note,"")

    def test_extracts_artist_title_pairs_across_track_heading_levels(self):
        html = """
        <h3>Navigation label</h3><p>Do not collect</p>
        <h2>Music Played</h2>
        <h3>Artist One</h3><p>Track One</p>
        <h4>Artist Two</h4><p>Track Two</p>
        <h5>Artist Three</h5><p>Track Three</p>
        <h6>Artist Four</h6><p>Track Four</p>
        <h2>Broadcast</h2><h3>Related programme</h3><p>Do not collect</p>
        """
        parser = ProgrammeTrackParser()
        parser.feed(html)
        self.assertEqual(parser.pairs, [
            ("Artist One", "Track One"), ("Artist Two", "Track Two"),
            ("Artist Three", "Track Three"), ("Artist Four", "Track Four")
        ])

    def test_text_parser_preserves_html_title(self):
        parser = TextParser()
        parser.feed("<html><head><title>Riley &amp; Coe - 13/10/2026 - BBC Sounds</title></head><body>Music Played</body></html>")
        self.assertIn("13/10/2026", " ".join(parser.title))

    def test_extracts_only_artist_title_pairs_inside_music_played_section(self):
        html = """
        <h2>Next</h2><h3>Navigation label</h3><p>Do not collect</p>
        <h2>Music Played</h2>
        <h3>Artist One</h3><p>Track One</p>
        <h3>Artist Two</h3><p>Track Two</p>
        <h2>Broadcast</h2><h3>Related programme</h3><p>Not a track</p>
        """
        parser = ProgrammeTrackParser()
        parser.feed(html)
        self.assertEqual(parser.pairs, [("Artist One", "Track One"), ("Artist Two", "Track Two")])


if __name__ == "__main__":
    unittest.main()
