import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_mixcloud_html import inspect_page


class MixcloudHtmlDiagnosticsTests(unittest.TestCase):
    def test_records_html_structure_without_extracting_tracks(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit):
                return b"<html><head><title>Riley show</title></head><body>comments tracklist</body></html>"
        with patch("diagnose_mixcloud_html.urlopen", return_value=Response()):
            row = inspect_page("https://www.mixcloud.com/example/show/")
        self.assertEqual(row["http_status"], "200")
        self.assertEqual(row["html_title"], "Riley show")
        self.assertEqual(row["contains_tracklist_word"], "true")
        self.assertEqual(row["contains_comments_word"], "true")
        self.assertEqual(row["error"], "")

    def test_preserves_http_errors(self):
        from urllib.error import HTTPError
        err = HTTPError("https://www.mixcloud.com/example/", 403, "Forbidden", {}, None)
        with patch("diagnose_mixcloud_html.urlopen", side_effect=err):
            row = inspect_page("https://www.mixcloud.com/example/")
        self.assertEqual(row["http_status"], "403")
        self.assertIn("HTTPError", row["error"])


if __name__ == "__main__":
    unittest.main()
