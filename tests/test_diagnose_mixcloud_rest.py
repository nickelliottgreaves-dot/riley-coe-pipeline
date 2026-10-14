import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_mixcloud_rest import build_probes, probe


class MixcloudRestDiagnosticsTests(unittest.TestCase):
    def test_probe_matrix_includes_comments_and_search_fallbacks(self):
        names = [name for name, _ in build_probes()]
        self.assertIn("cloudcast_comments", names)
        self.assertIn("cloudcasts", names)
        self.assertIn("search_riley_coe", names)
        self.assertIn("search_archive_name", names)

    def test_probe_records_json_shape_without_claiming_tracklist_completeness(self):
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return json.dumps({"data": [{"name": "example"}]}).encode()

        with patch("diagnose_mixcloud_rest.urlopen", return_value=Response()):
            row = probe("https://api.mixcloud.com/example/", "test")
        self.assertEqual(row["http_status"], "200")
        self.assertEqual(row["json_valid"], "true")
        self.assertEqual(row["data_count"], "1")
        self.assertEqual(row["error"], "")

    def test_probe_preserves_http_failure_as_evidence(self):
        error = HTTPError("https://api.mixcloud.com/example/", 404, "Not Found", {}, None)
        with patch("diagnose_mixcloud_rest.urlopen", side_effect=error):
            row = probe("https://api.mixcloud.com/example/", "test")
        self.assertEqual(row["http_status"], "404")
        self.assertIn("HTTPError", row["error"])


if __name__ == "__main__":
    unittest.main()
