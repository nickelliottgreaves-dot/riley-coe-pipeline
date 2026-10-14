import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class RadioFilesArtistPoolReviewTests(unittest.TestCase):
    def test_normalized_alias_near_match_and_unmatched_are_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pool=root/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["index","artist","status","source_basis"]); w.writeheader()
                w.writerows([
                    {"index":"1","artist":"Yīn Yīn","status":"ACTIVE","source_basis":"seed"},
                    {"index":"2","artist":"The Nightingales","status":"ACTIVE","source_basis":"seed"},
                    {"index":"3","artist":"Joy Division","status":"ACTIVE","source_basis":"seed"},
                ])
            aliases=root/"aliases.csv"
            with aliases.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["alias","canonical","source_basis","review_status"]); w.writeheader()
                w.writerow({"alias":"Nightengales","canonical":"The Nightingales","source_basis":"test","review_status":"needs_review"})
            candidates=root/"candidates.csv"
            with candidates.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","track_title","artist_candidate","source_url"]); w.writeheader()
                w.writerows([
                    {"episode_date":"2026-10-12","episode_title":"Example","track_title":"Song A","artist_candidate":"Yin Yin","source_url":"https://example.test/1"},
                    {"episode_date":"2026-10-12","episode_title":"Example","track_title":"Song B","artist_candidate":"Nightengales","source_url":"https://example.test/1"},
                    {"episode_date":"2026-10-13","episode_title":"Example 2","track_title":"Song C","artist_candidate":"A Certain Ratio","source_url":"https://example.test/2"},
                    {"episode_date":"2026-10-13","episode_title":"Example 2","track_title":"Song D","artist_candidate":"Unknown Artist","source_url":"https://example.test/2"},
                ])
            out=root/"out"
            subprocess.run([sys.executable,str(ROOT/"scripts/compare_radiofiles_artist_pool.py"),
                "--pool",str(pool),"--candidates",str(candidates),"--aliases",str(aliases),"--out-dir",str(out)],
                check=True,capture_output=True,text=True)
            with (out/"radiofiles_artist_pool_review.csv").open(newline="",encoding="utf-8") as f:
                rows={r["artist_candidate"]:r for r in csv.DictReader(f)}
            self.assertEqual(rows["Yin Yin"]["pool_match_status"],"normalized_pool_match")
            self.assertEqual(rows["Nightengales"]["pool_match_status"],"configured_alias_match")
            self.assertEqual(rows["A Certain Ratio"]["pool_match_status"],"no_pool_match_review")
            self.assertEqual(rows["Unknown Artist"]["review_decision"],"needs_manual_review")
            self.assertIn("RadioFiles public JSON",rows["Yin Yin"]["candidate_sources"])
            summary=json.loads((out/"radiofiles_artist_pool_review_summary.json").read_text())
            self.assertFalse(summary["authoritative_pool_modified"])
            self.assertEqual(summary["artists_added_to_pool"],0)
            self.assertEqual(summary["candidate_track_rows_read"],4)

    def test_combined_bbc_candidates_use_episode_url_and_custom_output_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pool=root/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["index","artist","status","source_basis"]);w.writeheader()
                w.writerow({"index":"1","artist":"Known Artist","status":"ACTIVE","source_basis":"seed"})
            candidates=root/"combined.csv"
            with candidates.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["episode_date","episode_title","episode_url","track_title","artist_candidate","extraction_method"]);w.writeheader()
                w.writerow({"episode_date":"2026-10-13","episode_title":"Example","episode_url":"https://www.bbc.co.uk/programmes/m0032d4c","track_title":"Song","artist_candidate":"New Candidate","extraction_method":"bbc_programme_heading_artist_followed_by_track_title"})
            out=root/"out"
            subprocess.run([sys.executable,str(ROOT/"scripts/compare_radiofiles_artist_pool.py"),
                "--pool",str(pool),"--candidates",str(candidates),"--out-dir",str(out),
                "--output-name","tracklist_artist_pool_review.csv","--source-label","Combined BBC Sounds and RadioFiles candidates"],
                check=True,capture_output=True,text=True)
            with (out/"tracklist_artist_pool_review.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertIn("https://www.bbc.co.uk/programmes/m0032d4c",rows[0]["source_episode_urls"])
            self.assertIn("bbc_programme_heading_artist_followed_by_track_title",rows[0]["candidate_sources"])
            self.assertIn("Combined BBC Sounds and RadioFiles candidates",rows[0]["notes"])
            self.assertNotIn("RadioFiles is a third-party mirror",rows[0]["notes"])
            summary=json.loads((out/"tracklist_artist_pool_review_summary.json").read_text())
            self.assertEqual(summary["review_csv"],"tracklist_artist_pool_review.csv")
            self.assertFalse(summary["authoritative_pool_modified"])

if __name__=="__main__": unittest.main()
