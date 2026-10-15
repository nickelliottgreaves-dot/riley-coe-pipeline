import csv,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from match_pool_to_window_events import main

class PoolWindowEventMatchTests(unittest.TestCase):
    def test_joins_pool_page_text_hit_to_same_dated_event_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]);w.writeheader();w.writerow({"artist":"The Wedding Present"})
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url"]);w.writeheader()
            url="https://www.boilershop.net/events/the-wedding-present-23-10-26"
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status","price","availability"]);w.writeheader()
                w.writerow({"event_date":"2026-10-23","venue":"Boiler Shop","event_title":"The Wedding Present","performer_names":"","page_url":url,"status":"visible_event_candidate_needs_review","availability":"SoldOut"})
            page_hits=d/"page_hits.csv"
            with page_hits.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]);w.writeheader()
                w.writerow({"artist":"The Wedding Present","searched":"true","result":"found_in_collected_pages","evidence_url":url,"notes":"Matching text: The Wedding Present at Boiler Shop Newcastle"})
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),
                "--inspected",str(inspected),"--pool-page-matches",str(page_hits),"--start","2026-10-15",
                "--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["artist_pool_name"],"The Wedding Present")
            self.assertEqual(rows[0]["source_kind"],"pool_page_text_match")
            self.assertEqual(rows[0]["match_basis"],"full_pool_page_text")
            self.assertEqual(rows[0]["verified"],"false")
            self.assertIn("actual billing",rows[0]["notes"])

    def test_matches_only_exact_performer_names_inside_date_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]);w.writeheader()
                w.writerows([{"artist":"Gallus"},{"artist":"The Delines"},{"artist":"A Certain Ratio"}])
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url","status","price","ticket_status"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-20","venue":"Venue A","event_title":"Gallus live","artist":"Gallus","source_url":"https://venue.example/gallus","status":"candidate","price":"£15"})
                w.writerow({"event_date":"2026-10-14","venue":"Venue A","event_title":"Old Delines show","artist":"The Delines","source_url":"https://venue.example/old"})
                w.writerow({"event_date":"2026-10-22","venue":"Venue B","event_title":"Thee Galluses","artist":"Thee Galluses","source_url":"https://venue.example/other"})
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status","price","availability"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-24","venue":"Venue C","event_title":"A Certain Ratio","performer_names":"A Certain Ratio; Support Act","page_url":"https://venue.example/acr","status":"visible_event_candidate_needs_review","price":"£20"})
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),"--inspected",str(inspected),"--start","2026-10-15","--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f: matches=list(csv.DictReader(f))
            self.assertEqual({r["artist_pool_name"] for r in matches},{"Gallus","A Certain Ratio"})
            self.assertTrue(all(r["verified"]=="false" for r in matches))
            with (d/"artist_window_event_coverage.csv").open(newline="",encoding="utf-8") as f: coverage={r["artist"]:r for r in csv.DictReader(f)}
            self.assertEqual(coverage["Gallus"]["candidate_count"],"1")
            self.assertEqual(coverage["The Delines"]["candidate_count"],"0")
            self.assertEqual(coverage["A Certain Ratio"]["candidate_count"],"1")
            summary=json.loads(out.with_suffix(".summary.json").read_text())
            self.assertEqual(summary["status"],"PARTIAL_CANDIDATE_MATCH")
            self.assertEqual(summary["verified_event_rows"],0)

if __name__=="__main__": unittest.main()
