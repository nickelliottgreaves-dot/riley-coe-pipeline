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

    def test_structurally_valid_partial_package_is_accepted_as_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with (ROOT/"config/required_venues.csv").open(encoding="utf-8-sig",newline="") as f:
                required=[r["venue"] for r in csv.DictReader(f) if r["mandatory"].strip().lower()=="true"]
            with (ROOT/"config/venue_sources.csv").open(encoding="utf-8-sig",newline="") as f:
                sources={r["venue"]:r for r in csv.DictReader(f)}
            (p/"run_manifest.json").write_text(json.dumps({
                "run_date":"2026-10-14","window_start":"2026-10-14","window_end":"2026-10-27",
                "previous_successful_run":"unknown/not yet established","researcher_notes":"Partial fixture",
                "claimed_status":"PARTIAL","episode_coverage_complete":False,"venue_sweep_complete":False,
                "artist_pool_compared":False,"event_artist_pool_compared":False,
                "tracklist_artist_pool_compared":False,"mixcloud_visible_tracklists_verified":False,"all_event_sources_verified":False
            }))
            def write(name,fields,rows):
                with (p/name).open("w",newline="",encoding="utf-8") as f:
                    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            write("episodes.csv",["episode_date","source","url","tracklist_status","tracks_extracted","notes"],[
                {"episode_date":"2026-10-13","source":"BBC Sounds","url":"https://www.bbc.co.uk/programmes/example","tracklist_status":"not_yet_checked","tracks_extracted":"0","notes":"Needs review"}
            ])
            write("venue_coverage.csv",["venue","checked","source_url","status","notes"],[
                {"venue":name,"checked":"false","source_url":sources[name]["source_url"],"status":"not_checked","notes":"Partial fixture"}
                for name in required
            ])
            write("events.csv",["event_date","venue","event_title","artist","artist_role","source_url","verified","notes"],[])
            write("pool_matches.csv",["event_artist","matched_pool_artist","candidate_pool_artist","match_type","source_url","verified","notes"],[])
            with (ROOT/"config/regression_artists.csv").open(encoding="utf-8-sig",newline="") as f:
                seeds=list(csv.DictReader(f))
            write("regression_artist_checks.csv",["artist","searched","result","evidence_url","notes"],[
                {"artist":r["artist"],"searched":"false","result":"not_checked","evidence_url":"","notes":"Not yet checked"}
                for r in seeds
            ])
            result=subprocess.run([sys.executable,str(VALIDATOR),"--run-dir",str(p)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('"status": "PARTIAL"',result.stdout)
            self.assertNotIn('"status": "COMPLETE"',result.stdout)
            gated=subprocess.run([sys.executable,str(VALIDATOR),"--run-dir",str(p),"--require-complete"],capture_output=True,text=True)
            self.assertNotEqual(gated.returncode,0,"The scheduled evidence gate must reject PARTIAL packages")
            self.assertIn('"status": "PARTIAL"',gated.stdout)

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            result = subprocess.run([sys.executable, str(VALIDATOR), "--run-dir", str(p)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing run_manifest.json", result.stdout)


    def test_every_required_venue_has_a_usable_source_registry_entry(self):
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
            self.assertIn("event_artist_pool_compared is not true", result.stdout)
            self.assertIn("tracklist_artist_pool_compared is not true", result.stdout)
            self.assertIn("mixcloud_visible_tracklists_verified is not true", result.stdout)
            self.assertIn("Missing venue_discovery_coverage.csv for COMPLETE run", result.stdout)

if __name__ == "__main__":
    unittest.main()
