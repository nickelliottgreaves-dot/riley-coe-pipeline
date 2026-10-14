import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_event_links import is_aggregate_calendar_url, apply_shared_calendar_attribution
ROOT=Path(__file__).resolve().parents[1]

class EventPageCrawlerTests(unittest.TestCase):
    def test_crawler_preserves_unverified_status_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); links=d/"links.csv"
            with links.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","candidate_url"]);w.writeheader();w.writerow({"venue":"Test","candidate_url":"https://example.invalid/event"})
            sources=d/"sources.csv"
            with sources.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]);w.writeheader()
                w.writerow({"venue":"Test","source_url":"https://example.invalid"})
                w.writerow({"venue":"Empty venue","source_url":"https://example.org"})
            # Invalid domain proves errors are captured rather than silently treated as a successful sweep.
            p=subprocess.run([sys.executable,str(ROOT/"scripts/inspect_event_links.py"),"--links",str(links),"--sources",str(sources),"--out-dir",str(d/"out"),"--max-pages-per-venue","1"],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            audit=json.loads((d/"out/event_page_crawl_summary.json").read_text())
            self.assertEqual(audit["status"],"PARTIAL")
            with (d/"out/event_page_inspection.csv").open(newline="") as f: rows=list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(r["verified"]=="false" for r in rows))
            with (d/"out/event_page_crawl_audit.csv").open(newline="") as f: venue_audit=list(csv.DictReader(f))
            self.assertEqual({r["venue"] for r in venue_audit},{"Test","Empty venue"})
            empty=next(r for r in venue_audit if r["venue"]=="Empty venue")
            self.assertEqual(empty["status"],"PARTIAL")
            self.assertEqual(empty["seed_candidate_links"],"0")
            self.assertEqual(empty["pages_fetched"],"1")
            self.assertIn("source calendar",empty["notes"])

    def test_shared_parent_calendar_does_not_claim_a_room_without_evidence(self):
        rows=[
            {"venue":"The Cluny","page_url":"https://thecluny.com/listing/example","page_title":"Live music","event_title":"Example band","event_date":"2026-10-20","performer_names":"Example band","status":"page_text_needs_review","notes":"candidate"},
            {"venue":"Cluny 2","page_url":"https://thecluny.com/listing/example","page_title":"Live music","event_title":"Example band","event_date":"2026-10-20","performer_names":"Example band","status":"page_text_needs_review","notes":"candidate"},
        ]
        result=apply_shared_calendar_attribution(rows,{"thecluny.com":{"The Cluny","Cluny 2"}})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["venue"],"Unresolved shared calendar: Cluny 2 / The Cluny")
        self.assertEqual(result[0]["status"],"shared_calendar_attribution_unresolved")
        self.assertIn("Do not attribute",result[0]["notes"])

    def test_shared_calendar_can_resolve_explicit_room_in_page_title(self):
        rows=[{"venue":"The Cluny","page_url":"https://thecluny.com/listing/example","page_title":"Cluny 2: Example band","event_title":"Example band","event_date":"2026-10-20","performer_names":"Example band","status":"page_text_needs_review","notes":"candidate"}]
        result=apply_shared_calendar_attribution(rows,{"thecluny.com":{"The Cluny","Cluny 2"}})
        self.assertEqual(result[0]["venue"],"Cluny 2")
        self.assertNotEqual(result[0]["status"],"shared_calendar_attribution_unresolved")

    def test_aggregate_songkick_pages_are_excluded(self):
        self.assertTrue(is_aggregate_calendar_url("https://www.songkick.com/metro-areas/24577-uk-newcastle-upon-tyne"))
        self.assertTrue(is_aggregate_calendar_url("https://www.songkick.com/live-stream-concerts"))
        self.assertFalse(is_aggregate_calendar_url("https://www.songkick.com/venues/4426128-lubber-fiend/calendar"))
        self.assertFalse(is_aggregate_calendar_url("https://www.boilershop.net/events/"))

if __name__=="__main__": unittest.main()
