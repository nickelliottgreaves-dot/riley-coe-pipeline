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


    def test_every_required_venue_has_an_official_source_registry_entry(self):
        import csv, re
        required_path = ROOT / "config" / "required_venues.csv"
        source_path = ROOT / "config" / "venue_sources.csv"
        norm = lambda s: "".join(ch for ch in re.sub(r"\s+", " ", s.casefold()) if ch.isalnum())
        with required_path.open(encoding="utf-8-sig", newline="") as f:
            required = [r["venue"] for r in csv.DictReader(f) if r["mandatory"].strip().lower() == "true"]
        with source_path.open(encoding="utf-8-sig", newline="") as f:
            sources = {norm(r["venue"]): r for r in csv.DictReader(f)}
        for venue in required:
            self.assertIn(norm(venue), sources, f"Missing source registry entry: {venue}")
            row = sources[norm(venue)]
            self.assertTrue(row["source_url"].startswith("https://"), f"Missing URL for {venue}")
            self.assertIn(row["source_status"], {"verified_official_calendar", "verified_official_site", "verified_official_social_listing", "verified_ticketing_calendar", "verified_third_party_calendar"})

    def test_false_complete_flags_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "run_manifest.json").write_text(json.dumps({"run_date":"2026-10-13","window_start":"2026-10-13","window_end":"2026-10-26","previous_successful_run":"2026-10-05","researcher_notes":"fixture","claimed_status":"COMPLETE"}))
            result = subprocess.run([sys.executable, str(VALIDATOR), "--run-dir", str(p)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("episode_coverage_complete is not true", result.stdout)
            self.assertIn("venue_sweep_complete is not true", result.stdout)
            self.assertIn("Missing venue_discovery_coverage.csv for COMPLETE run", result.stdout)

if __name__ == "__main__":
    unittest.main()
