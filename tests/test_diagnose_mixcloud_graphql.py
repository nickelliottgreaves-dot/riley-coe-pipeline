import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_mixcloud_graphql import probe


class MixcloudGraphQLDiagnosticsTests(unittest.TestCase):
    def test_extracts_only_diagnostic_comment_counts(self):
        payload = {"data": {"cloudcastLookup": {
            "name": "Test show", "owner": {"username": "SixMusicAlternative"},
            "comments": {"totalCount": 1, "edges": [{"node": {
                "comment": "1. Song\\nArtist", "user": {"username": "SixMusicAlternative"}}}]}
        }}}
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return __import__("json").dumps(payload).encode()
        with patch("diagnose_mixcloud_graphql.urlopen", return_value=Response()):
            row = probe("SixMusicAlternative", "test-show")
        self.assertEqual(row["show_found"], "true")
        self.assertEqual(row["creator_comment_count"], "1")
        self.assertEqual(row["numbered_lines_in_creator_comments"], "1")

    def test_preserves_http_failure(self):
        from urllib.error import HTTPError
        err = HTTPError("https://app.mixcloud.com/graphql", 403, "Forbidden", {}, None)
        with patch("diagnose_mixcloud_graphql.urlopen", side_effect=err):
            row = probe("SixMusicAlternative", "test-show")
        self.assertEqual(row["http_status"], "403")
        self.assertIn("HTTPError", row["error"])


if __name__ == "__main__":
    unittest.main()
