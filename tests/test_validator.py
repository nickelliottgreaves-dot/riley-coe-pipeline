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
            self.assertIn(row["source_status"], {"verified_official_calendar", "verified_official_site", "verified_official_social_listing"})

    def test_valid_partial_package_exits_successfully_without_claiming_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); episode_file=root/"bbc_episodes.csv"; out=root/"partial-run"
            with episode_file.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","tracklist_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-15","episode_title":"Fixture episode",
                    "episode_url":"https://www.bbc.co.uk/programmes/mfixture","tracklist_status":"not_yet_checked",
                    "notes":"Test fixture; completeness not established."})
            assembled=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-15","--end","2026-10-28","--bbc-episodes",str(episode_file),
                "--out-dir",str(out)],capture_output=True,text=True)
            self.assertEqual(assembled.returncode,0,assembled.stderr)
            result=subprocess.run([sys.executable,str(VALIDATOR),"--run-dir",str(out)],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn('"status": "PARTIAL"',result.stdout)
            report=json.loads((out/"validation_report.json").read_text())
            self.assertEqual(report["status"],"PARTIAL")
            self.assertTrue(any("episode_coverage_complete" in w for w in report["warnings"]))
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["claimed_status"],"PARTIAL")
            self.assertIs(manifest["episode_coverage_complete"],False)

    def test_episode_complete_status_requires_exact_crosscheck_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); episode_file=root/"bbc_episodes.csv"; out=root/"partial-run"
            with episode_file.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","tracklist_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-15","episode_title":"Fixture episode",
                    "episode_url":"https://www.bbc.co.uk/sounds/play/mfixture","tracklist_status":"not_yet_checked",
                    "notes":"Fixture without crosscheck."})
            assembled=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-15","--end","2026-10-28","--bbc-episodes",str(episode_file),
                "--out-dir",str(out)],capture_output=True,text=True)
            self.assertEqual(assembled.returncode,0,assembled.stderr)
            episodes_path=out/"episodes.csv"
            with episodes_path.open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f)); fields=list(rows[0])
            rows[0]["tracklist_status"]="complete"
            with episodes_path.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            result=subprocess.run([sys.executable,str(VALIDATOR),"--run-dir",str(out)],
                capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn("episodes.csv marks tracklists complete but bbc_radiofiles_episode_crosscheck.csv is missing",result.stdout)

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
