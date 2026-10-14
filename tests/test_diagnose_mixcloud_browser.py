import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_mixcloud_browser import inspect_rendered_text


class MixcloudBrowserDiagnosticsTests(unittest.TestCase):
    def test_identifies_known_artist_text_but_does_not_claim_extraction(self):
        row = inspect_rendered_text("https://www.mixcloud.com/a/b/", "Comments Creator Lande Hekt", "Test", "200", ["200 https://app.mixcloud.com/graphql"])
        self.assertEqual(row["known_artist_hits"], "Lande Hekt")
        self.assertEqual(row["creator_comment_text_found"], "true")
        self.assertEqual(row["navigation_status"], "200")
        self.assertEqual(row["page_state"], "rendered_content")

    def test_no_known_artists_is_not_complete(self):
        row = inspect_rendered_text("https://www.mixcloud.com/a/b/", "Comments Creator", "Test", "200", [])
        self.assertEqual(row["known_artist_hits"], "")
        self.assertEqual(row["creator_comment_text_found"], "false")
        self.assertEqual(row["page_state"], "shell_or_empty")

    def test_http_200_soft_404_is_not_treated_as_a_valid_show_page(self):
        row = inspect_rendered_text("https://www.mixcloud.com/a/b/", "Home Link Page Not Found Sign up to Mixcloud", "Mixcloud - This is Audio Culture", "200", [])
        self.assertEqual(row["navigation_status"], "200")
        self.assertEqual(row["page_state"], "page_not_found")


if __name__ == "__main__":
    unittest.main()
