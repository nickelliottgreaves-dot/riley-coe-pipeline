import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"build_verified_artist_pool_proposal.py"

class VerifiedPoolProposalTests(unittest.TestCase):
    def write(self,path,fields,rows):
        with path.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

    def test_only_exactly_crosschecked_artists_enter_proposal_and_pool_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); pool=root/"pool.csv"; candidates=root/"verified.csv"; out=root/"out"
            pool_fields=["index","artist","status","source_basis"]
            pool_rows=[{"index":"1","artist":"Existing Artist","status":"ACTIVE","source_basis":"baseline"}]
            self.write(pool,pool_fields,pool_rows)
            cand_fields=["episode_date","episode_pid","episode_title","track_position","track_title","artist_candidate","radiofiles_artist_candidate","bbc_episode_url","radiofiles_episode_url","crosscheck_status","evidence"]
            self.write(candidates,cand_fields,[
                {"episode_date":"2026-10-13","episode_pid":"m0031tk4","track_title":"Song A","artist_candidate":"Existing Artist","radiofiles_artist_candidate":"Existing Artist","crosscheck_status":"EXACT_FULL_TRACKLIST_MATCH","bbc_episode_url":"https://bbc.example/a","radiofiles_episode_url":"https://radiofiles.example/a"},
                {"episode_date":"2026-10-13","episode_pid":"m0031tk4","track_title":"Song B","artist_candidate":"New Artist & Collaborator","radiofiles_artist_candidate":"New Artist","crosscheck_status":"EXACT_FULL_TRACKLIST_MATCH","bbc_episode_url":"https://bbc.example/a","radiofiles_episode_url":"https://radiofiles.example/a"},
                {"episode_date":"2026-10-14","episode_pid":"m0031tk5","track_title":"Song C","artist_candidate":"Unsafe Candidate","radiofiles_artist_candidate":"Unsafe Candidate","crosscheck_status":"MISMATCH_REQUIRES_REVIEW","bbc_episode_url":"https://bbc.example/b","radiofiles_episode_url":"https://radiofiles.example/b"},
                {"episode_date":"2026-10-13","episode_pid":"m0031tk4","track_title":"Song D","artist_candidate":"Blondie","radiofiles_artist_candidate":"Blondie","crosscheck_status":"EXACT_FULL_TRACKLIST_MATCH","bbc_episode_url":"https://bbc.example/a","radiofiles_episode_url":"https://radiofiles.example/a"},
            ])
            reconciliation=root/"reconciliation.csv"
            self.write(reconciliation,["artist_candidate","reconciliation_status","best_similarity_score","closest_pool_candidates","episode_dates","track_examples","source_urls"],[
                {"artist_candidate":"Blondie","reconciliation_status":"UNMATCHED_REVIEW_ONLY","best_similarity_score":"0.75","closest_pool_candidates":"Du Blonde","episode_dates":"2026-10-13","track_examples":"Song D","source_urls":"https://radiofiles.example/a"}
            ])
            subprocess.run([sys.executable,str(SCRIPT),"--pool",str(pool),"--verified-candidates",str(candidates),"--reconciliation",str(reconciliation),"--out-dir",str(out)],check=True,capture_output=True,text=True)
            import datetime
            stamp=datetime.date.today().strftime("%Y%m%d")
            with (out/f"artist_pool_proposed_{stamp}.csv").open(newline="",encoding="utf-8") as f:
                proposed=list(csv.DictReader(f))
            with (out/f"artist_pool_additions_{stamp}.csv").open(newline="",encoding="utf-8") as f:
                additions=list(csv.DictReader(f))
            audit=json.loads((out/f"artist_pool_proposal_audit_{stamp}.json").read_text())
            self.assertEqual([r["artist"] for r in proposed],["Existing Artist","New Artist"])
            self.assertEqual([r["artist"] for r in additions],["New Artist"])
            with (out/f"artist_pool_ambiguous_review_{stamp}.csv").open(newline="",encoding="utf-8") as f:
                ambiguous=list(csv.DictReader(f))
            self.assertEqual([r["artist_candidate"] for r in ambiguous],["Blondie"])
            self.assertIn("New Artist & Collaborator", additions[0]["source_basis"])
            self.assertFalse(audit["authoritative_pool_modified"])
            self.assertEqual(pool.read_text().splitlines(),["index,artist,status,source_basis","1,Existing Artist,ACTIVE,baseline"])

if __name__=="__main__":
    unittest.main()
