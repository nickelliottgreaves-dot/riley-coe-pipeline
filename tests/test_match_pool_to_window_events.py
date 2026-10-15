import csv,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from match_pool_to_window_events import is_event_detail_url, main

class PoolWindowEventMatchTests(unittest.TestCase):
    def test_only_individual_event_detail_urls_are_used_for_page_text_joins(self):
        self.assertTrue(is_event_detail_url("https://www.boilershop.net/events/the-wedding-present-23-10-26"))
        self.assertTrue(is_event_detail_url("https://www.utilitaarena.co.uk/events/detail/2026-mercury-prize"))
        self.assertFalse(is_event_detail_url("https://www.boilershop.net/"))
        self.assertFalse(is_event_detail_url("https://www.boilershop.net/events"))
        self.assertFalse(is_event_detail_url("https://thecluny.com/gigs/"))
        self.assertFalse(is_event_detail_url("https://cobaltstudios.co.uk/whats-on/?date=19-10-2026"))
        self.assertFalse(is_event_detail_url("https://theglasshouseicm.org/whats-on/page/2/"))

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
            self.assertIn("verify billing",rows[0]["notes"])

    def test_biography_only_pool_mentions_do_not_become_gig_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]);w.writeheader();w.writerow({"artist":"Al Green"})
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url"]);w.writeheader()
            url="https://venue.example/events/hue-and-cry"
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status"]);w.writeheader()
                w.writerow({"event_date":"2026-10-20","venue":"Venue A","event_title":"Hue and Cry","performer_names":"",
                    "page_url":url,"status":"visible_event_candidate_needs_review"})
            page_hits=d/"page_hits.csv"
            with page_hits.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]);w.writeheader()
                w.writerow({"artist":"Al Green","searched":"true","result":"found_in_collected_pages","evidence_url":url,
                    "notes":"Matching text: Hue and Cry have appeared alongside Al Green in a biography."})
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),
                "--inspected",str(inspected),"--pool-page-matches",str(page_hits),"--start","2026-10-15",
                "--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows,[])
            with out.with_name("artist_window_event_coverage.csv").open(newline="",encoding="utf-8") as f:
                coverage=list(csv.DictReader(f))
            self.assertEqual(coverage[0]["result"],"no_exact_dated_candidate_match")

    def test_short_artist_name_in_parenthetical_country_label_is_not_a_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]);w.writeheader();w.writerow({"artist":"Can"})
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url"]);w.writeheader()
            url="https://venue.example/listing/jake-vaadeland-can"
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status"]);w.writeheader()
                w.writerow({"event_date":"2026-10-20","venue":"Venue A",
                    "event_title":"Jake Vaadeland & The Sturgeon River Boys (Can)","performer_names":"Jake Vaadeland; Rob Heron",
                    "page_url":url,"status":"visible_event_candidate_needs_review"})
            page_hits=d/"page_hits.csv"
            with page_hits.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]);w.writeheader()
                w.writerow({"artist":"Can","searched":"true","result":"found_in_collected_pages","evidence_url":url,
                    "notes":"Matching text: (Can)"})
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),
                "--inspected",str(inspected),"--pool-page-matches",str(page_hits),"--start","2026-10-15",
                "--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows,[])

    def test_composer_mentioned_in_concert_title_is_not_treated_as_billed_artist(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]);w.writeheader();w.writerow({"artist":"Vivaldi"})
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url"]);w.writeheader()
            url="https://venue.example/events/vivaldis-four-seasons"
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status"]);w.writeheader()
                w.writerow({"event_date":"2026-10-22","venue":"Sage One","event_title":"Vivaldi's Four Seasons",
                    "performer_names":"Maria Włoszczowska; Royal Northern Sinfonia","page_url":url,
                    "status":"visible_event_candidate_needs_review"})
            page_hits=d/"page_hits.csv"
            with page_hits.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"]);w.writeheader()
                w.writerow({"artist":"Vivaldi","searched":"true","result":"found_in_collected_pages","evidence_url":url,
                    "notes":"The event is Vivaldi's Four Seasons, performed by Royal Northern Sinfonia."})
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),
                "--inspected",str(inspected),"--pool-page-matches",str(page_hits),"--start","2026-10-15",
                "--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows,[])

    def test_deduplicates_same_performer_event_across_source_title_and_venue_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            pool=d/"pool.csv"
            with pool.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]); w.writeheader()
                w.writerow({"artist":"Dexys Midnight Runners"})
            events=d/"events.csv"
            with events.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","artist","source_url","status"])
                w.writeheader()
                w.writerow({"event_date":"2026-10-21","venue":"O2 City Hall","event_title":"Dexys Midnight Runners @ O2 City Hall",
                            "artist":"Dexys Midnight Runners","source_url":"https://songkick.example/concert/1","status":"candidate"})
                w.writerow({"event_date":"2026-10-21","venue":"O2 City Hall Newcastle","event_title":"Dexys Midnight Runners",
                            "artist":"Dexys Midnight Runners","source_url":"https://songkick.example/venue/calendar","status":"candidate"})
                w.writerow({"event_date":"2026-10-21","venue":"O2 City Hall Newcastle","event_title":"Dexys Midnight Runners @ O2 City Hall",
                            "artist":"Dexys Midnight Runners","source_url":"https://ents24.example/dexys","status":"candidate"})
            inspected=d/"inspected.csv"
            with inspected.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["event_date","venue","event_title","performer_names","page_url","status"])
                w.writeheader()
            out=d/"matches.csv"
            with patch("sys.argv",["match_pool_to_window_events.py","--pool",str(pool),"--events",str(events),
                "--inspected",str(inspected),"--start","2026-10-15","--end","2026-10-28","--out",str(out)]):
                self.assertEqual(main(),0)
            with out.open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["venue"],"O2 City Hall Newcastle")
            self.assertEqual(rows[0]["event_title"],"Dexys Midnight Runners")
            self.assertIn("https://songkick.example/concert/1",rows[0]["source_url"])
            self.assertIn("https://songkick.example/venue/calendar",rows[0]["source_url"])
            self.assertIn("https://ents24.example/dexys",rows[0]["source_url"])
            self.assertEqual(rows[0]["verified"],"false")

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
