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
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","artist_candidate","track_title","extraction_method","review_status","evidence_text","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_title":"Example","episode_url":"https://www.bbc.co.uk/programmes/m0031tk4","artist_candidate":"Example Artist","track_title":"Example Song","extraction_method":"visible_text_title_by_artist","review_status":"needs_manual_review","evidence_text":"Example Song by Example Artist","notes":"review"})
            radiofiles=tmp_path/"radiofiles_episodes.csv"
            with radiofiles.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","source_url","has_tracklist","tracklist_status","track_count_reported","track_count_returned","count_match","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_title":"RadioFiles Example","episode_pid":"m0031tk4","source_url":"https://radiofiles.io/programmes/m0031tk4","has_tracklist":"true","tracklist_status":"candidate","track_count_reported":"1","track_count_returned":"1","count_match":"true","notes":"RadioFiles episode"})
            radiofiles_tracks=tmp_path/"radiofiles_tracks.csv"
            with radiofiles_tracks.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_title":"RadioFiles Example","episode_pid":"m0031tk4","track_position":"1","track_title":"Radio Song","artist_candidate":"Radio Artist","source_url":"https://radiofiles.io/programmes/m0031tk4","tracklist_api_url":"https://radiofiles.io/api/tracklist/m0031tk4","source":"RadioFiles","verification_status":"candidate","notes":"review"})
            out=tmp_path/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--bbc-episodes",str(bbc),
                "--bbc-track-candidates",str(candidates),
                "--radiofiles-episodes",str(radiofiles),"--radiofiles-track-candidates",str(radiofiles_tracks),
                "--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f:
                episodes=list(csv.DictReader(f))
            self.assertEqual(episodes[0]["tracklist_status"],"not_yet_checked")
            self.assertIn("visible_tracklist_heading_detected_needs_review",episodes[0]["notes"])
            self.assertEqual(len(episodes),2)
            self.assertEqual(episodes[1]["source"],"RadioFiles public tracklist")
            self.assertEqual(episodes[1]["tracks_extracted"],"1")
            self.assertIn("count_match=true",episodes[1]["notes"])
            with (out/"bbc_track_candidates.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["artist_candidate"],"Example Artist")
            with (out/"tracklist_candidate_review.csv").open(newline="",encoding="utf-8") as f:
                review=list(csv.DictReader(f))
            self.assertEqual(len(review),2)
            self.assertEqual({row["artist_candidate"] for row in review},{"Example Artist","Radio Artist"})
            self.assertTrue(all(row["review_status"]=="needs_manual_review" for row in review))
            self.assertTrue(any(name.startswith("Riley_Coe_tracklist_candidate_review_") for name in json.loads((out/"run_manifest.json").read_text())["dated_exports"]))
            with (out/"input_file_audit.csv").open(newline="",encoding="utf-8") as f:
                audit=list(csv.DictReader(f))
            self.assertTrue(any(r["input_name"]=="bbc_track_candidates" and r["status"]=="present" for r in audit))
            self.assertTrue(any(r["input_name"]=="radiofiles_episode_candidates" and r["status"]=="present" for r in audit))

    def test_exact_full_tracklist_crosschecks_drive_episode_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/"run"
            bbc=root/"bbc.csv"; radio=root/"radio.csv"; rf_tracks=root/"radio_tracks.csv"
            embedded=root/"embedded.csv"; crosscheck=root/"crosscheck.csv"; verified=root/"verified.csv"
            with bbc.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","tracklist_status","notes"]);w.writeheader()
                w.writerows([
                    {"episode_date":"2026-10-13","episode_title":"Exact","episode_url":"https://www.bbc.co.uk/sounds/play/m001","tracklist_status":"candidate","notes":"BBC source"},
                    {"episode_date":"2026-10-12","episode_title":"Mismatch","episode_url":"https://www.bbc.co.uk/sounds/play/m002","tracklist_status":"candidate","notes":"BBC source"},
                    {"episode_date":"2026-10-11","episode_title":"Unavailable","episode_url":"https://www.bbc.co.uk/sounds/play/m003","tracklist_status":"next_data_not_found","notes":"No embedded list"},
                ])
            with radio.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","source_url","tracklist_status","notes"]);w.writeheader()
                w.writerows([
                    {"episode_date":"2026-10-13","episode_title":"Exact","episode_pid":"m001","source_url":"https://radiofiles.io/app?pid=m001","tracklist_status":"candidate","notes":"RadioFiles exact"},
                    {"episode_date":"2026-10-12","episode_title":"Mismatch","episode_pid":"m002","source_url":"https://radiofiles.io/app?pid=m002","tracklist_status":"candidate","notes":"RadioFiles mismatch"},
                    {"episode_date":"2026-10-11","episode_title":"Unavailable","episode_pid":"m003","source_url":"https://radiofiles.io/app?pid=m003","tracklist_status":"no_tracklist","notes":"Tracklist has zero rows; source=none"},
                ])
            with rf_tracks.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"]);w.writeheader()
                w.writerows([
                    {"episode_date":"2026-10-13","episode_title":"Exact","episode_pid":"m001","track_position":"1","track_title":"Track A","artist_candidate":"Artist A","source_url":"https://radiofiles.io/app?pid=m001","tracklist_api_url":"https://radiofiles.io/api/m001","source":"RadioFiles","verification_status":"candidate","notes":""},
                    {"episode_date":"2026-10-12","episode_title":"Mismatch","episode_pid":"m002","track_position":"1","track_title":"Wrong Track","artist_candidate":"Artist B","source_url":"https://radiofiles.io/app?pid=m002","tracklist_api_url":"https://radiofiles.io/api/m002","source":"RadioFiles","verification_status":"candidate","notes":""},
                ])
            with embedded.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","track_position","track_title","artist_candidate","source_url","review_status","notes","segment_urn"]);w.writeheader()
                w.writerows([
                    {"episode_date":"2026-10-13","episode_title":"Exact","episode_url":"https://www.bbc.co.uk/sounds/play/m001","track_position":"1","track_title":"Track A","artist_candidate":"Artist A & Guest","source_url":"https://www.bbc.co.uk/sounds/play/m001","review_status":"candidate","notes":"","segment_urn":"urn:1"},
                    {"episode_date":"2026-10-12","episode_title":"Mismatch","episode_url":"https://www.bbc.co.uk/sounds/play/m002","track_position":"1","track_title":"Track B","artist_candidate":"Artist B","source_url":"https://www.bbc.co.uk/sounds/play/m002","review_status":"candidate","notes":"","segment_urn":"urn:2"},
                ])
            with crosscheck.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_pid","episode_date","bbc_track_rows","radiofiles_track_rows","matched_track_rows","mismatched_track_rows","crosscheck_status","bbc_episode_url","radiofiles_episode_url","notes"]);w.writeheader()
                w.writerows([
                    {"episode_pid":"m001","episode_date":"2026-10-13","bbc_track_rows":"1","radiofiles_track_rows":"1","matched_track_rows":"1","mismatched_track_rows":"0","crosscheck_status":"EXACT_FULL_TRACKLIST_MATCH","bbc_episode_url":"https://www.bbc.co.uk/sounds/play/m001","radiofiles_episode_url":"https://radiofiles.io/app?pid=m001","notes":""},
                    {"episode_pid":"m002","episode_date":"2026-10-12","bbc_track_rows":"2","radiofiles_track_rows":"1","matched_track_rows":"0","mismatched_track_rows":"2","crosscheck_status":"MISMATCH_REQUIRES_REVIEW","bbc_episode_url":"https://www.bbc.co.uk/sounds/play/m002","radiofiles_episode_url":"https://radiofiles.io/app?pid=m002","notes":"Mismatch"},
                ])
            with verified.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_pid","episode_title","track_position","track_title","artist_candidate","radiofiles_artist_candidate","bbc_episode_url","radiofiles_episode_url","crosscheck_status","evidence"]);w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_pid":"m001","episode_title":"Exact","track_position":"1","track_title":"Track A","artist_candidate":"Artist A & Guest","radiofiles_artist_candidate":"Artist A","bbc_episode_url":"https://www.bbc.co.uk/sounds/play/m001","radiofiles_episode_url":"https://radiofiles.io/app?pid=m001","crosscheck_status":"EXACT_FULL_TRACKLIST_MATCH","evidence":"Exact position/title match with compatible artist credits."})
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-11","--end","2026-10-24","--bbc-episodes",str(bbc),
                "--radiofiles-episodes",str(radio),"--radiofiles-track-candidates",str(rf_tracks),
                "--bbc-embedded-track-candidates",str(embedded),"--bbc-radiofiles-episode-crosscheck",str(crosscheck),
                "--bbc-radiofiles-verified-candidates",str(verified),"--out-dir",str(out)],
                check=True,capture_output=True,text=True)
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            states={(r["episode_date"],r["source"]):r["tracklist_status"] for r in rows}
            self.assertEqual(states[("2026-10-13","BBC Sounds official episode page")],"complete")
            self.assertEqual(states[("2026-10-13","RadioFiles public tracklist")],"complete")
            self.assertEqual(states[("2026-10-12","BBC Sounds official episode page")],"incomplete")
            self.assertEqual(states[("2026-10-12","RadioFiles public tracklist")],"incomplete")
            self.assertEqual(states[("2026-10-11","BBC Sounds official episode page")],"unavailable")
            self.assertEqual(states[("2026-10-11","RadioFiles public tracklist")],"unavailable")
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertIs(manifest["episode_coverage_complete"],False)
            with (out/"tracklist_candidate_review.csv").open(newline="",encoding="utf-8") as f: review=list(csv.DictReader(f))
            exact=[r for r in review if r["episode_date"]=="2026-10-13"]
            self.assertEqual(len(exact),2)
            self.assertTrue(all(r["review_status"]=="verified_full_tracklist_match" for r in exact))
            mismatch=[r for r in review if r["episode_date"]=="2026-10-12"]
            self.assertTrue(all(r["review_status"]!="verified_full_tracklist_match" for r in mismatch))

    def test_merges_inspected_event_jsonld_as_unverified_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            inspection=root/"inspection.csv"
            fields=["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","status","notes"]
            with inspection.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/","event_title":"Example Live","event_date":"2026-10-20","performer_names":"Example Artist; Support Artist","event_jsonld_found":"false","status":"visible_event_candidate_needs_review","notes":"Visible listing candidate"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/example","event_title":"Example Live","event_date":"2026-10-20T19:00:00+01:00","performer_names":"Example Artist; Support Artist","price":"18.00","currency":"GBP","availability":"InStock","event_jsonld_found":"true","notes":"Structured candidate only"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/unresolved","event_title":"Unresolved Live","event_date":"2026-10-21","performer_names":"","event_jsonld_found":"true","notes":"No performer metadata"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/undated","event_title":"Undated Live","event_date":"","performer_names":"Undated Artist","event_jsonld_found":"true","notes":"No date metadata"})
                w.writerow({"venue":"The Sands Centre - Carlisle, CA1 1JQ","page_url":"https://example.com/out-of-scope","event_title":"Out of Scope","event_date":"2026-10-22","performer_names":"Out of Scope Artist","event_jsonld_found":"true","notes":"External venue candidate"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/listing/visible-live","event_title":"Visible Live","event_date":"2026-10-22","performer_names":"Visible Artist; Visible Support","price":"18.00","currency":"GBP","availability":"not_checked","event_jsonld_found":"false","status":"visible_event_candidate_needs_review","notes":"Extracted from visible Date/Venue labels"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--event-page-inspection",str(inspection),
                "--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"events.csv").open(newline="",encoding="utf-8") as f:
                events=list(csv.DictReader(f))
            self.assertEqual({row["artist"] for row in events},{"Example Artist","Support Artist","Visible Artist","Visible Support"})
            self.assertTrue(all(row["verified"]=="false" for row in events))
            self.assertTrue(all(row["artist_role"]=="performer_role_unverified" for row in events))
            self.assertTrue(all(row["price"]=="18.00 GBP" for row in events))
            example=next(row for row in events if row["event_title"]=="Example Live" and row["artist"]=="Example Artist")
            self.assertEqual(example["source_url"],"https://thecluny.com/gigs/example")
            self.assertEqual(example["discovery_method"],"inspected_page_jsonld")
            visible_rows=[row for row in events if row["discovery_method"]=="visible_event_text"]
            self.assertEqual(len(visible_rows),2)
            self.assertTrue(all("Visible event-text candidate" in row["notes"] for row in visible_rows))
            with (out/"unresolved_event_candidates.csv").open(newline="",encoding="utf-8") as f:
                unresolved=list(csv.DictReader(f))
            self.assertEqual(len(unresolved),3)
            self.assertIn("Unresolved Live",{row["event_title"] for row in unresolved})
            out_of_scope=next(row for row in unresolved if row["event_title"]=="Out of Scope")
            self.assertIn("excluded from the in-scope event list",out_of_scope["notes"])
            undated=next(row for row in unresolved if row["event_title"]=="Undated Live")
            self.assertEqual(undated["artist_candidate"],"Undated Artist")
            self.assertIn("Date missing or invalid",undated["notes"])

    def test_shared_calendar_room_ambiguity_is_not_misattributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            inspection=root/"inspection.csv"
            fields=["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","status","notes"]
            with inspection.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
                for venue in ["The Cluny","Cluny 2"]:
                    w.writerow({"venue":venue,"page_url":"https://thecluny.com/gigs/","event_title":"Shared Calendar Show",
                        "event_date":"2026-10-20","performer_names":"Pool Artist; Support Act",
                        "event_jsonld_found":"false","status":"visible_event_candidate_needs_review","notes":"Same shared listing"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--event-page-inspection",str(inspection),
                "--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"events.csv").open(newline="",encoding="utf-8") as f:
                events=list(csv.DictReader(f))
            self.assertEqual(events,[])
            with (out/"unresolved_event_candidates.csv").open(newline="",encoding="utf-8") as f:
                unresolved=list(csv.DictReader(f))
            self.assertEqual(len(unresolved),2)
            self.assertTrue(all(r["discovery_method"]=="shared_calendar_room_ambiguous" for r in unresolved))
            self.assertTrue(all("actual room is independently confirmed" in r["notes"] for r in unresolved))

    def test_includes_full_pool_page_text_search_and_match_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); search=root/"pool_search.csv"; out=root/"run"
            with search.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]); w.writeheader()
                w.writerow({"artist":"Example Artist","searched":"true","result":"found_in_collected_pages",
                    "evidence_url":"https://venue.example/calendar","notes":"Candidate text match; manual verification required."})
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-15","--end","2026-10-28","--pool-venue-page-matches",str(search),"--out-dir",str(out)],
                check=True,capture_output=True,text=True)
            with (out/"artist_pool_venue_page_matches.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["artist"],"Example Artist")
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["artist_pool_page_search_rows"],1)
            self.assertEqual(manifest["artist_pool_page_search_completed"],1)
            self.assertEqual(manifest["artist_pool_page_text_matches"],1)
            self.assertIs(manifest["artist_pool_compared_against_captured_pages"],False)

    def test_full_pool_page_search_requires_every_artist_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); search=root/"pool_search.csv"; out=root/"run"
            with (ROOT/"data/artist_pool.csv").open(encoding="utf-8-sig",newline="") as f:
                pool=list(csv.DictReader(f))
            with search.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]); w.writeheader()
                for row in pool:
                    w.writerow({"artist":row["artist"],"searched":"true","result":"not_found_in_collected_pages",
                        "evidence_url":"https://venue.example/calendar","notes":"Bounded corpus search."})
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-15","--end","2026-10-28","--pool-venue-page-matches",str(search),"--out-dir",str(out)],
                check=True,capture_output=True,text=True)
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertIs(manifest["artist_pool_compared_against_captured_pages"],True)
            self.assertIs(manifest["artist_pool_compared"],True)
            self.assertIs(manifest["event_artist_comparison_complete"],True)
            self.assertEqual(manifest["artist_pool_page_search_completed"],len(pool))
            # Removing a pool row makes the search incomplete even if all
            # remaining rows are marked searched.
            out2=root/"run-missing-row"
            short= root/"pool_search_short.csv"
            with short.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]); w.writeheader()
                for row in pool[:-1]:
                    w.writerow({"artist":row["artist"],"searched":"true","result":"not_found_in_collected_pages",
                        "evidence_url":"https://venue.example/calendar","notes":"Bounded corpus search."})
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-15","--end","2026-10-28","--pool-venue-page-matches",str(short),"--out-dir",str(out2)],
                check=True,capture_output=True,text=True)
            manifest2=json.loads((out2/"run_manifest.json").read_text())
            self.assertIs(manifest2["artist_pool_compared_against_captured_pages"],False)
            self.assertIs(manifest2["artist_pool_compared"],False)

    def test_creates_partial_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--bbc-episodes",str(Path(tmp)/"missing-bbc.csv"),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["claimed_status"],"PARTIAL")
            self.assertIs(manifest["episode_coverage_complete"],False)
            self.assertIs(manifest["venue_sweep_complete"],False)
            self.assertIs(manifest["artist_pool_compared"],False)
            self.assertIs(manifest["artist_pool_compared_against_captured_pages"],False)
            with (ROOT/"data/artist_pool.csv").open(encoding="utf-8-sig",newline="") as f:
                expected_pool_rows=list(csv.DictReader(f))
            self.assertEqual(manifest["artist_pool_page_search_rows"],len(expected_pool_rows))
            self.assertEqual(manifest["artist_pool_page_search_completed"],0)
            self.assertEqual(manifest["artist_pool_page_text_matches"],0)
            self.assertIs(manifest["all_event_sources_verified"],False)
            self.assertEqual(manifest["venue_calendar_checks_completed"],0)
            self.assertEqual(manifest["regression_artists_seeded"],9)
            self.assertEqual(manifest["regression_artist_checks_completed"],0)
            self.assertTrue(any(name.startswith("Riley_Coe_events_") for name in manifest["dated_exports"]))
            self.assertTrue(any(name.startswith("Riley_Coe_deduplicated_event_artists_") for name in manifest["dated_exports"]))
            self.assertIn("missing_or_unsupplied_inputs",manifest)
            with (out/"input_file_audit.csv").open(newline="") as f:
                inputs=list(csv.DictReader(f))
            self.assertTrue(any(row["input_name"]=="bbc_episode_inventory" and row["status"]=="missing" for row in inputs))
            self.assertTrue(any(row["input_name"]=="bbc_episode_inventory" and row["status"]=="missing" for row in inputs))
            with (out/"venue_coverage.csv").open(newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(r["status"]=="not_checked" for r in rows))
            self.assertTrue((out/"pool_matches.csv").exists())
            with (out/"venue_discovery_coverage.csv").open(newline="",encoding="utf-8") as f:
                discovery=list(csv.DictReader(f))
            self.assertEqual(len(discovery),len(list(csv.DictReader((ROOT/"config/venue_sources.csv").open(encoding="utf-8-sig",newline="")))))
            self.assertTrue(all(row["calendar_coverage_verified"]=="false" for row in discovery))
            self.assertTrue(all(row["homepage_fetch_status"]=="not_run" for row in discovery))
            self.assertIn("The Cluny",{row["venue"] for row in discovery})
            self.assertIn("The Newgate Social",{row["venue"] for row in discovery})
            self.assertTrue(any(name.startswith("Riley_Coe_venue_discovery_coverage_") for name in manifest["dated_exports"]))
            with (out/"regression_artist_checks.csv").open(newline="") as f:
                regression=list(csv.DictReader(f))
            self.assertEqual(len(regression),9)
            self.assertTrue(all(row["searched"]=="false" and row["result"]=="not_checked" for row in regression))
            again=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--out-dir",str(out)],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertIn("Refusing to overwrite",again.stderr)

if __name__=="__main__": unittest.main()
