import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from inspect_event_links import canonicalize_url, event_link_matches, extract_visible_event, extract_visible_listing_events, is_calendar_navigation, is_event_object, likely

class EventPageCrawlerTests(unittest.TestCase):
    def test_canonical_url_removes_tracking_but_preserves_pagination(self):
        self.assertEqual(
            canonicalize_url("https://thecluny.com/gigs/page/2/?utm_source=mail&ref=abc"),
            "https://thecluny.com/gigs/page/2/"
        )
        self.assertEqual(
            canonicalize_url("https://example.com/events/?page=3&utm_campaign=x"),
            "https://example.com/events/?page=3"
        )

    def test_only_schema_event_types_are_event_objects(self):
        self.assertTrue(is_event_object({"@type":"MusicEvent","name":"A concert"}))
        self.assertTrue(is_event_object({"@type":["Thing","Event"],"name":"A concert"}))
        self.assertFalse(is_event_object({"@type":"Organization","name":"Venue"}))
        self.assertFalse(is_event_object({"@type":"BreadcrumbList","name":"Breadcrumbs"}))
        self.assertTrue(event_link_matches({"event_title":"Skating Polly"},"/listing/skating-polly/","Tickets"))
        self.assertFalse(event_link_matches({"event_title":"Skating Polly"},"/listing/another-act/","Another Act"))

    def test_likely_filter_keeps_event_and_ticket_links(self):
        self.assertTrue(likely("/listing/artist-name/", "Artist"))
        self.assertTrue(likely("/tickets/", "Buy tickets"))
        self.assertFalse(likely("/about-us/", "About us"))

    def test_calendar_pagination_is_prioritized_over_detail_pages(self):
        self.assertTrue(is_calendar_navigation("/gigs/page/2/", "Next"))
        self.assertTrue(is_calendar_navigation("/events/?page=3", "3", "https://example.com/events/?page=2"))
        self.assertFalse(is_calendar_navigation("/listing/ben-quad/", "Ben Quad"))
        self.assertFalse(is_calendar_navigation("/events/ben-quad/", "Ben Quad"))

    def test_extracts_review_only_candidate_from_visible_event_detail(self):
        visible = """Gigs
eastside events presents:
Skating Polly
Buy Tickets
With support from
Lord Friday The 13th
Details
Date:
Thu 15 Oct 2026
Venue:
The Cluny
Advance tickets:
£17.50 + fees
Doors:
7:30pm"""
        row = extract_visible_event("Skating Polly - The Cluny", visible)
        self.assertIsNotNone(row)
        self.assertEqual(row["event_title"], "Skating Polly")
        self.assertEqual(row["event_date"], "2026-10-15")
        self.assertEqual(row["venue"], "The Cluny")
        self.assertEqual(row["price"], "£17.50")
        self.assertEqual(row["performer_names"], "Skating Polly; Lord Friday The 13th")
        self.assertIn("independently verify", row["notes"])

    def test_extracts_multiple_dated_cards_from_cluny_calendar(self):
        visible = """Gigs
October 2026
Skating Polly
Thu 15 Oct 2026
/
The Cluny
With support from
Lord Friday The 13th
Info
Tickets
Florentenes
Thu 15 Oct 2026
/
Cluny 2
Info
Tickets
Discharge
Fri 16 Oct 2026
/
The Cluny
Info
Tickets
Audition for the Newcastle University Symphony Orchestra!
Sat 17 Oct 2026
Audition for the Newcastle University Symphony Orchestra!"""
        rows = extract_visible_listing_events(visible)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["event_title"], "Skating Polly")
        self.assertEqual(rows[0]["event_date"], "2026-10-15")
        self.assertEqual(rows[0]["venue"], "The Cluny")
        self.assertEqual(rows[0]["performer_names"], "Skating Polly; Lord Friday The 13th")
        self.assertEqual(rows[1]["venue"], "Cluny 2")
        self.assertEqual(rows[2]["event_title"], "Discharge")

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
            self.assertEqual(empty["seed_candidate_links"],"1")
            self.assertIn("Bounded crawl",empty["notes"])

if __name__=="__main__": unittest.main()
