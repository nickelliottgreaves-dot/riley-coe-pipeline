import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class EvidencePackageTests(unittest.TestCase):
    def test_preserves_bbc_candidates_and_normalizes_unverified_tracklist_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path=Path(tmp)
            bbc=tmp_path/"bbc.csv"
            with bbc.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","tracklist_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_title":"Example","episode_url":"https://www.bbc.co.uk/programmes/m0031tk4","tracklist_status":"visible_tracklist_heading_detected_needs_review","notes":"Heading found"})
            candidates=tmp_path/"bbc_track_candidates.csv"
            with candidates.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist_candidate","track_title","review_status"])
                w.writeheader()
                w.writerow({"artist_candidate":"Example Artist","track_title":"Example Song","review_status":"needs_manual_review"})
            out=tmp_path/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--bbc-episodes",str(bbc),
                "--bbc-track-candidates",str(candidates),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f:
                episodes=list(csv.DictReader(f))
            self.assertEqual(episodes[0]["tracklist_status"],"not_yet_checked")
            self.assertIn("visible_tracklist_heading_detected_needs_review",episodes[0]["notes"])
            with (out/"bbc_track_candidates.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["artist_candidate"],"Example Artist")
            with (out/"input_file_audit.csv").open(newline="",encoding="utf-8") as f:
                audit=list(csv.DictReader(f))
            self.assertTrue(any(r["input_name"]=="bbc_track_candidates" and r["status"]=="present" for r in audit))

    def test_creates_partial_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--episodes",str(Path(tmp)/"missing-mixcloud.csv"),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["claimed_status"],"PARTIAL")
            self.assertEqual(manifest["venue_calendar_checks_completed"],0)
            self.assertEqual(manifest["regression_artists_seeded"],9)
            self.assertEqual(manifest["regression_artist_checks_completed"],0)
            self.assertIn("missing_or_unsupplied_inputs",manifest)
            with (out/"input_file_audit.csv").open(newline="") as f:
                inputs=list(csv.DictReader(f))
            self.assertTrue(any(row["input_name"]=="mixcloud_episode_inventory" and row["status"]=="missing" for row in inputs))
            self.assertTrue(any(row["input_name"]=="bbc_episode_inventory" and row["status"]=="not_supplied" for row in inputs))
            with (out/"venue_coverage.csv").open(newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(r["status"]=="not_checked" for r in rows))
            self.assertTrue((out/"pool_matches.csv").exists())
            with (out/"regression_artist_checks.csv").open(newline="") as f:
                regression=list(csv.DictReader(f))
            self.assertEqual(len(regression),9)
            self.assertTrue(all(row["searched"]=="false" and row["result"]=="not_checked" for row in regression))
            again=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--out-dir",str(out)],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertIn("Refusing to overwrite",again.stderr)

if __name__=="__main__": unittest.main()
