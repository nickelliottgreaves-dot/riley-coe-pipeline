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
            mixcloud=tmp_path/"mixcloud_tracks.csv"
            with mixcloud.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","artist","track_title","track_position","source","verification_status"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-14","episode_title":"Mixcloud Example","episode_url":"https://www.mixcloud.com/example/show","artist":"Mix Artist","track_title":"Mix Song","track_position":"1","source":"Mixcloud API","verification_status":"candidate"})
            out=tmp_path/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--bbc-episodes",str(bbc),
                "--bbc-track-candidates",str(candidates),"--mixcloud-track-candidates",str(mixcloud),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f:
                episodes=list(csv.DictReader(f))
            self.assertEqual(episodes[0]["tracklist_status"],"not_yet_checked")
            self.assertIn("visible_tracklist_heading_detected_needs_review",episodes[0]["notes"])
            with (out/"bbc_track_candidates.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["artist_candidate"],"Example Artist")
            with (out/"tracklist_candidate_review.csv").open(newline="",encoding="utf-8") as f:
                review=list(csv.DictReader(f))
            self.assertEqual(len(review),2)
            self.assertEqual({row["artist_candidate"] for row in review},{"Example Artist","Mix Artist"})
            self.assertTrue(all(row["review_status"]=="needs_manual_review" for row in review))
            self.assertTrue((out/"mixcloud_api_track_candidates.csv").exists())
            self.assertTrue(any(name.startswith("Riley_Coe_tracklist_candidate_review_") for name in json.loads((out/"run_manifest.json").read_text())["dated_exports"]))
            self.assertTrue(any(name.startswith("Riley_Coe_episode_tracklist_comparison_") for name in json.loads((out/"run_manifest.json").read_text())["dated_exports"]))
            with (out/"input_file_audit.csv").open(newline="",encoding="utf-8") as f:
                audit=list(csv.DictReader(f))
            self.assertTrue(any(r["input_name"]=="bbc_track_candidates" and r["status"]=="present" for r in audit))

    def test_compares_official_and_radiofiles_track_titles_without_certifying_completeness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            bbc=root/"bbc_tracks.csv"
            with bbc.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","artist_candidate","track_title","extraction_method","review_status","evidence_text","notes"])
                w.writeheader()
                for artist,title in [("Official Duo","First Song"),("Official Artist","Second Song")]:
                    w.writerow({"episode_date":"2026-10-12","episode_title":"Example","episode_url":"https://www.bbc.co.uk/sounds/play/m0032d2m","artist_candidate":artist,"track_title":title,"extraction_method":"official_page","review_status":"needs_manual_review","evidence_text":title,"notes":"candidate"})
            radio=root/"radiofiles_tracks.csv"
            with radio.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"])
                w.writeheader()
                for artist,title in [("Primary Artist","First Song"),("Official Artist","Second Song"),("Extra Artist","Third Song")]:
                    w.writerow({"episode_date":"2026-10-12","episode_title":"Example","episode_pid":"m0032d2m","track_position":"1","track_title":title,"artist_candidate":artist,"source_url":"https://radiofiles.io/app?pid=m0032d2m","source":"RadioFiles","verification_status":"candidate","notes":"candidate"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--bbc-track-candidates",str(bbc),
                "--radiofiles-track-candidates",str(radio),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"episode_tracklist_comparison.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["episode_pid"],"m0032d2m")
            self.assertEqual(rows[0]["shared_title_count"],"2")
            self.assertEqual(rows[0]["status"],"bbc_candidate_subset_of_radiofiles")
            self.assertEqual(rows[0]["complete_certified"],"false")
            self.assertIn("Third Song",rows[0]["radiofiles_only_titles"])
            self.assertIn("episode_tracklist_comparison.csv",json.loads((out/"run_manifest.json").read_text())["episode_tracklist_comparison"])

    def test_exact_dated_official_and_radiofiles_title_match_still_requires_mixcloud_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            bbc_episodes=root/"bbc_episodes.csv"
            with bbc_episodes.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","tracklist_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe - 12 Oct 2026","episode_url":"https://www.bbc.co.uk/sounds/play/m0032d2m","tracklist_status":"visible_tracklist_heading_detected_needs_review","notes":"Official Music Played heading detected"})
            bbc_tracks=root/"bbc_tracks.csv"
            with bbc_tracks.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","artist_candidate","track_title","extraction_method","review_status","evidence_text","notes"])
                w.writeheader()
                for artist,title in [("Official Artist A","Song One"),("Official Artist B","Song Two")]:
                    w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe","episode_url":"https://www.bbc.co.uk/sounds/play/m0032d2m","artist_candidate":artist,"track_title":title,"extraction_method":"official_page","review_status":"needs_manual_review","evidence_text":title,"notes":"candidate"})
            radio_episodes=root/"radio_episodes.csv"
            with radio_episodes.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","source_url","tracklist_status","track_count_returned","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe - 12 Oct 2026","episode_pid":"m0032d2m","source_url":"https://radiofiles.io/app?show=m001mf2c&pid=m0032d2m","tracklist_status":"count_and_metadata_verified_needs_crosscheck","track_count_returned":"2","notes":"candidate"})
            radio_tracks=root/"radio_tracks.csv"
            with radio_tracks.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"])
                w.writeheader()
                for artist,title in [("Radio Artist A","Song One"),("Official Artist B","Song Two")]:
                    w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe","episode_pid":"m0032d2m","track_position":"1","track_title":title,"artist_candidate":artist,"source_url":"https://radiofiles.io/app?show=m001mf2c&pid=m0032d2m","source":"RadioFiles","verification_status":"candidate","notes":"candidate"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-01","--end","2026-10-14","--bbc-episodes",str(bbc_episodes),
                "--bbc-track-candidates",str(bbc_tracks),"--radiofiles-episodes",str(radio_episodes),
                "--radiofiles-track-candidates",str(radio_tracks),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"episode_tracklist_comparison.csv").open(newline="",encoding="utf-8") as f:
                comparison=list(csv.DictReader(f))
            self.assertEqual(comparison[0]["title_sets_match"],"true")
            self.assertEqual(comparison[0]["date_match"],"true")
            self.assertEqual(comparison[0]["official_tracklist_heading_detected"],"true")
            self.assertEqual(comparison[0]["complete_certified"],"false")
            self.assertEqual(comparison[0]["status"],"bbc_radiofiles_title_sets_match_mixcloud_verification_required")
            self.assertIn("Mixcloud visible-page tracklist verification is still required",comparison[0]["notes"])
            self.assertIn("not independent source corroboration",comparison[0]["notes"])
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f:
                episodes=list(csv.DictReader(f))
            self.assertTrue(all(row["tracklist_status"]!="complete" for row in episodes))
            self.assertTrue(all(row["tracks_extracted"]=="2" for row in episodes))
            self.assertNotIn("authoritative artist pool", (out/"run_manifest.json").read_text())

    def test_deduplicates_calendar_and_detail_candidates_for_same_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            machine=root/"machine_events.csv"
            with machine.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","artist_role","source_url","verified","notes"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-21","venue":"The Lubber Fiend","event_title":"Bitchin Bajas @ The Lubber Fiend","artist":"Bitchin Bajas","artist_role":"performer_role_unverified","source_url":"https://www.songkick.com/concerts/43291182-bitchin-bajas-at-lubber-fiend","verified":"false","notes":"Songkick event-detail candidate"})
            sweep=root/"manual_sweep.csv"
            with sweep.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","artist_role","pool_match_status","matched_pool_name","source_url","price","ticket_status","notes"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-21","venue":"Lubber Fiend","event_title":"Bitchin Bajas","artist":"Bitchin Bajas","artist_role":"headliner","source_url":"https://www.songkick.com/venues/4426128-lubber-fiend/calendar","price":"12.00","ticket_status":"InStock","notes":"Manual source-visible calendar candidate"})
            inspection=root/"inspection.csv"
            with inspection.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","notes"])
                w.writeheader()
                w.writerow({"venue":"Lubber Fiend","page_url":"https://www.songkick.com/venues/4426128-lubber-fiend/calendar","event_title":"Bitchin Bajas @ The Lubber Fiend","event_date":"2026-10-21","performer_names":"Bitchin Bajas","price":"12.00","currency":"GBP","availability":"InStock","event_jsonld_found":"true","notes":"Inspected-page candidate"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-14","--end","2026-10-27","--events",str(machine),
                "--manual-sweep",str(sweep),"--event-page-inspection",str(inspection),
                "--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"events.csv").open(newline="",encoding="utf-8") as f:
                events=list(csv.DictReader(f))
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]["artist"],"Bitchin Bajas")
            self.assertEqual(events[0]["artist_role"],"headliner")
            self.assertEqual(events[0]["price"],"12.00 GBP")
            self.assertEqual(events[0]["ticket_status"],"InStock")
            self.assertEqual(events[0]["verified"],"false")
            self.assertIn("https://www.songkick.com/venues/4426128-lubber-fiend/calendar",events[0]["notes"])
            self.assertIn("https://www.songkick.com/concerts/43291182-bitchin-bajas-at-lubber-fiend",events[0]["notes"])

    def test_merges_inspected_event_jsonld_as_unverified_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            inspection=root/"inspection.csv"
            fields=["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","notes"]
            with inspection.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/example","event_title":"Example Live","event_date":"2026-10-20T19:00:00+01:00","performer_names":"Example Artist; Support Artist","price":"18.00","currency":"GBP","availability":"InStock","event_jsonld_found":"true","notes":"Structured candidate only"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/unresolved","event_title":"Unresolved Live","event_date":"2026-10-21","performer_names":"","event_jsonld_found":"true","notes":"No performer metadata"})
                w.writerow({"venue":"The Cluny","page_url":"https://thecluny.com/gigs/undated","event_title":"Undated Live","event_date":"","performer_names":"Undated Artist","event_jsonld_found":"true","notes":"No date metadata"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--event-page-inspection",str(inspection),
                "--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"events.csv").open(newline="",encoding="utf-8") as f:
                events=list(csv.DictReader(f))
            self.assertEqual({row["artist"] for row in events},{"Example Artist","Support Artist"})
            self.assertTrue(all(row["verified"]=="false" for row in events))
            self.assertTrue(all(row["artist_role"]=="performer_role_unverified" for row in events))
            self.assertTrue(all(row["price"]=="18.00 GBP" for row in events))
            with (out/"unresolved_event_candidates.csv").open(newline="",encoding="utf-8") as f:
                unresolved=list(csv.DictReader(f))
            self.assertEqual(len(unresolved),2)
            self.assertIn("Unresolved Live",{row["event_title"] for row in unresolved})
            undated=next(row for row in unresolved if row["event_title"]=="Undated Live")
            self.assertEqual(undated["artist_candidate"],"Undated Artist")
            self.assertIn("Date missing or invalid",undated["notes"])

    def test_imports_manual_sweep_and_matches_pool_without_verifying_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sweep=root/"venue-sweep.csv"
            coverage=root/"venue-coverage.csv"
            with coverage.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url","coverage_status","window_start","window_end","coverage_notes","limitations"])
                w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/gigs/","coverage_status":"reviewed_official_calendar","window_start":"2026-10-14","window_end":"2026-10-27","coverage_notes":"Calendar reviewed","limitations":"Hidden support acts may be missed"})
            with sweep.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","artist_role","pool_match_status","matched_pool_name","source_url","price","ticket_status","notes"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-21","venue":"The Cluny","event_title":"Ye Gods live","artist":"Ye Gods","artist_role":"headliner","source_url":"https://thecluny.com/gigs/","price":"12.00","ticket_status":"InStock","notes":"Source-visible manual sweep row"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-14","--end","2026-10-27","--manual-sweep",str(sweep),"--manual-coverage",str(coverage),"--out-dir",str(out)],
                check=True,capture_output=True,text=True)
            with (out/"events.csv").open(newline="",encoding="utf-8") as f:
                events=list(csv.DictReader(f))
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]["artist"],"Ye Gods")
            self.assertEqual(events[0]["verified"],"false")
            self.assertEqual(events[0]["price"],"12.00")
            self.assertIn("Manual source-visible venue sweep",events[0]["notes"])
            with (out/"venue_coverage.csv").open(newline="",encoding="utf-8") as f:
                venue_coverage=list(csv.DictReader(f))
            cluny=next(row for row in venue_coverage if row["venue"]=="The Cluny")
            self.assertEqual(cluny["checked"],"true")
            self.assertEqual(cluny["status"],"checked_events_found")
            self.assertIn("Hidden support acts may be missed",cluny["notes"])
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertTrue(manifest["artist_pool_compared"])
            self.assertFalse(manifest["venue_sweep_complete"])
            with (out/"pool_matches.csv").open(newline="",encoding="utf-8") as f:
                matches=list(csv.DictReader(f))
            match=next(row for row in matches if row["event_artist"]=="Ye Gods")
            self.assertEqual(match["match_type"],"exact")
            self.assertEqual(match["matched_pool_artist"],"Ye Gods")
            self.assertEqual(match["verified"],"false")
            self.assertEqual(json.loads((out/"run_manifest.json").read_text())["manual_sweep_rows"],1)

    def test_creates_partial_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--episodes",str(Path(tmp)/"missing-mixcloud.csv"),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            manifest=json.loads((out/"run_manifest.json").read_text())
            self.assertEqual(manifest["claimed_status"],"PARTIAL")
            self.assertIs(manifest["episode_coverage_complete"],False)
            self.assertIs(manifest["venue_sweep_complete"],False)
            self.assertIs(manifest["artist_pool_compared"],False)
            self.assertIs(manifest["all_event_sources_verified"],False)
            self.assertEqual(manifest["venue_calendar_checks_completed"],0)
            self.assertEqual(manifest["regression_artists_seeded"],9)
            self.assertEqual(manifest["regression_artist_checks_completed"],0)
            self.assertTrue(any(name.startswith("Riley_Coe_events_") for name in manifest["dated_exports"]))
            self.assertTrue(any(name.startswith("Riley_Coe_deduplicated_event_artists_") for name in manifest["dated_exports"]))
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
            with (out/"venue_discovery_coverage.csv").open(newline="",encoding="utf-8") as f:
                discovery=list(csv.DictReader(f))
            self.assertEqual(len(discovery),len(list(csv.DictReader((ROOT/"config/venue_sources.csv").open(encoding="utf-8-sig",newline="")))))
            self.assertTrue(all(row["calendar_coverage_verified"]=="false" for row in discovery))
            self.assertTrue(all(row["homepage_fetch_status"]=="not_run" for row in discovery))
            self.assertIn("The Globe",{row["venue"] for row in discovery})
            self.assertIn("Utilita Arena Newcastle",{row["venue"] for row in discovery})
            self.assertTrue(any(name.startswith("Riley_Coe_venue_discovery_coverage_") for name in manifest["dated_exports"]))
            with (out/"regression_artist_checks.csv").open(newline="") as f:
                regression=list(csv.DictReader(f))
            self.assertEqual(len(regression),9)
            self.assertTrue(all(row["searched"]=="false" and row["result"]=="not_checked" for row in regression))
            again=subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-13","--end","2026-10-26","--out-dir",str(out)],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertIn("Refusing to overwrite",again.stderr)


    def test_merges_radiofiles_track_candidates_as_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            episodes=root/"radiofiles_episodes.csv"
            with episodes.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","source_url","has_tracklist","tracklist_status","track_count_returned","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe — 12 Oct 2026","episode_pid":"m0032d2m",
                    "source_url":"https://radiofiles.io/app?show=m001mf2c&pid=m0032d2m","has_tracklist":"true",
                    "tracklist_status":"count_and_metadata_verified_needs_crosscheck","track_count_returned":"29","notes":"count match"})
            candidates=root/"radiofiles_tracks.csv"
            with candidates.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"])
                w.writeheader()
                w.writerow({"episode_date":"2026-10-12","episode_title":"Riley & Coe — 12 Oct 2026","episode_pid":"m0032d2m",
                    "track_position":"1","track_title":"Free Way","artist_candidate":"Lafayette And The Lasabres",
                    "source_url":"https://radiofiles.io/app?show=m001mf2c&pid=m0032d2m",
                    "tracklist_api_url":"https://radiofiles.io/tracklist?pid=m0032d2m","source":"RadioFiles public JSON",
                    "verification_status":"needs_manual_crosscheck","notes":"count matched"})
            out=root/"run"
            subprocess.run([sys.executable,str(ROOT/"scripts/assemble_run_package.py"),
                "--start","2026-10-01","--end","2026-10-14","--radiofiles-episodes",str(episodes),
                "--radiofiles-track-candidates",str(candidates),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            with (out/"tracklist_candidate_review.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["artist_candidate"],"Lafayette And The Lasabres")
            self.assertEqual(rows[0]["review_status"],"needs_manual_review")
            self.assertEqual(rows[0]["extraction_method"],"radiofiles_json_candidate")
            with (out/"episodes.csv").open(newline="",encoding="utf-8") as f:
                eps=list(csv.DictReader(f))
            radio=next(r for r in eps if r["source"]=="RadioFiles public JSON fallback")
            self.assertEqual(radio["tracklist_status"],"not_yet_checked")
            self.assertIn("independent completeness verification",radio["notes"])
            with (out/"input_file_audit.csv").open(newline="",encoding="utf-8") as f:
                audit=list(csv.DictReader(f))
            self.assertTrue(any(r["input_name"]=="radiofiles_track_candidates" and r["status"]=="present" for r in audit))

if __name__=="__main__": unittest.main()
