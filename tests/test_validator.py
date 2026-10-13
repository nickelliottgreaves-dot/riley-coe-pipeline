import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_run.py"

class ValidatorTests(unittest.TestCase):
    def test_missing_run_directory_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "missing"
            result = subprocess.run([sys.executable, str(VALIDATOR), "--run-dir", str(p)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('"status": "FAILED"', result.stdout)

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            result = subprocess.run([sys.executable, str(VALIDATOR), "--run-dir", str(p)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing run_manifest.json", result.stdout)

    def test_false_complete_flags_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "run_manifest.json").write_text(json.dumps({"run_date":"2026-10-13","window_start":"2026-10-13","window_end":"2026-10-26","previous_successful_run":"2026-10-05","researcher_notes":"fixture","claimed_status":"COMPLETE"}))
            result = subprocess.run([sys.executable, str(VALIDATOR), "--run-dir", str(p)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("episode_coverage_complete is not true", result.stdout)
            self.assertIn("venue_sweep_complete is not true", result.stdout)

if __name__ == "__main__":
    unittest.main()
