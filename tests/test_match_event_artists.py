import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"match_event_artists.py"

def write_csv(path, fields, rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

class ArtistMatcherTests(unittest.TestCase):
    def test_exact_alias_fuzzy_and_unmatched_are_separated(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); events=d/"events.csv"; pool=d/"pool.csv"; aliases=d/"aliases.csv"; out=d/"matches.csv"
            write_csv(events,["artist","source_url","verified"],[
                {"artist":"A Certain Ratio","source_url":"https://venue.example/a","verified":"true"},
                {"artist":"ACR","source_url":"https://venue.example/b","verified":"true"},
                {"artist":"Robyn Hitchcok","source_url":"https://venue.example/c","verified":"true"},
                {"artist":"Completely Unknown","source_url":"https://venue.example/d","verified":"true"}])
            write_csv(pool,["artist","status"],[
                {"artist":"A Certain Ratio","status":"ACTIVE"},
                {"artist":"Robyn Hitchcock","status":"ACTIVE"}])
            write_csv(aliases,["alias","canonical","source_basis","review_status"],[
                {"alias":"ACR","canonical":"A Certain Ratio","source_basis":"test","review_status":"approved"}])
            result=subprocess.run([sys.executable,str(SCRIPT),"--events",str(events),"--pool",str(pool),"--aliases",str(aliases),"--out",str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with out.open(encoding="utf-8",newline="") as f: rows={r["event_artist"]:r for r in csv.DictReader(f)}
            self.assertEqual(rows["A Certain Ratio"]["match_type"],"exact")
            self.assertEqual(rows["ACR"]["match_type"],"alias")
            self.assertEqual(rows["Robyn Hitchcok"]["match_type"],"fuzzy_candidate")
            self.assertEqual(rows["Robyn Hitchcok"]["matched_pool_artist"],"")
            self.assertEqual(rows["Completely Unknown"]["match_type"],"unmatched")

if __name__=="__main__": unittest.main()
