import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class EvidencePackageTests(unittest.TestCase):
    def test_creates_partial_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--out-dir",str(out)],check=True,capture_output=True,text=True)
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["claimed_status"],"PARTIAL")
            self.assertEqual(manifest["venue_calendar_checks_completed"],0)
            with (out/"venue_coverage.csv").open(newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(r["status"]=="not_checked" for r in rows))
            self.assertTrue((out/"pool_matches.csv").exists())
            again=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--out-dir",str(out)],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertIn("Refusing to overwrite",again.stderr)

if __name__=="__main__": unittest.main()
