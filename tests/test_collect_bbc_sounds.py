import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_bbc_sounds import ProgrammeTrackParser, TextParser, parse_date


class BBCProgrammeParserTests(unittest.TestCase):
    def test_episode_title_date_wins_over_date_inside_tracklist(self):
        text = "Riley & Coe - 13/10/2026 - BBC Sounds\nTrack title mentions 7 Oct 2026"
        self.assertEqual(parse_date(text), "2026-10-13")

    def test_last_on_date_is_found_when_broadcast_label_and_date_share_line(self):
        self.assertEqual(parse_date("Last on Tue 6 Oct 2026 21:00\\nTrack title mentions 7 Oct 2026"), "2026-10-06")

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
