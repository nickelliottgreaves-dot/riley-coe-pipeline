import csv, json, subprocess, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from inspect_event_links import canonicalize_url, event_link_matches, event_performer_candidate, extract_visible_event, extract_visible_listing_events, is_calendar_navigation, is_event_object, likely, main

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

    def test_missing_structured_performer_uses_title_as_review_candidate(self):
        performer, fallback = event_performer_candidate({"name":"The Strokes"})
        self.assertEqual(performer,"The Strokes")
        self.assertTrue(fallback)
        performer, fallback = event_performer_candidate({"name":"The Strokes","performer":{"name":"The Strokes"}})
        self.assertEqual(performer,"The Strokes")
        self.assertFalse(fallback)

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

    def test_crawl_prioritizes_official_calendar_and_only_in_window_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            links=root/"links.csv"
            sources=root/"sources.csv"
            with links.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","candidate_url","link_text"]); w.writeheader()
                w.writerow({"venue":"The Cluny","candidate_url":"https://thecluny.com/listing/unrelated-candidate/","link_text":"Unrelated"})
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/gigs/"})
            calendar="""<title>Gigs - The Cluny</title>
<script type="application/ld+json">{"@type":"Event","name":"JSONLD placeholder"}</script>
<a href="/events/skating-polly/">Skating Polly</a>
<a href="/events/old-act/">Old Act</a>
<p>Skating Polly</p><p>Thu 15 Oct 2026</p><p>/</p><p>The Cluny</p><p>With support from</p><p>Lord Friday The 13th</p><p>Info</p>
<p>Old Act</p><p>Thu 10 Dec 2026</p><p>/</p><p>The Cluny</p>"""
            detail="""<title>Skating Polly - The Cluny</title><p>Date:</p><p>Thu 15 Oct 2026</p><p>Venue:</p><p>The Cluny</p><p>Advance tickets:</p><p>£17.50 + fees</p>"""
            fetched=[]
            def fake_fetch(url):
                fetched.append(url)
                if url=="https://thecluny.com/gigs/":
                    return 200,"text/html",calendar,False
                if url=="https://thecluny.com/events/skating-polly/":
                    return 200,"text/html",detail,False
                raise AssertionError("Unexpected crawl URL: "+url)
            with patch("inspect_event_links.fetch",side_effect=fake_fetch):
                with patch("sys.argv",["inspect_event_links.py","--links",str(links),"--sources",str(sources),"--out-dir",str(root/"out"),"--start","2026-10-15","--end","2026-10-28","--delay","0"]):
                    self.assertEqual(main(),0)
            self.assertEqual(fetched,["https://thecluny.com/gigs/","https://thecluny.com/events/skating-polly/"])
            summary=json.loads((root/"out"/"event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["pages_inspected"],2)
            with (root/"out"/"event_page_inspection.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(any(r["event_title"]=="Skating Polly" and r["status"]=="visible_event_candidate_needs_review" for r in rows))

    def test_external_ticket_hosts_are_not_crawled_as_venue_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); links=root/"links.csv"; sources=root/"sources.csv"
            with links.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","candidate_url","link_text"]); w.writeheader()
                w.writerow({"venue":"Test Venue","candidate_url":"https://tickets.example/event/123","link_text":"Tickets"})
                w.writerow({"venue":"Test Venue","candidate_url":"https://venue.example/events/act","link_text":"Act"})
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"Test Venue","source_url":"https://venue.example/whats-on"})
            fetched=[]
            calendar='<title>Whats On</title><a href="/events/act">Act</a>'
            detail='<title>Act - Test Venue</title><p>Date:</p><p>Thu 15 Oct 2026</p><p>Venue:</p><p>Test Venue</p>'
            def fake_fetch(url):
                fetched.append(url)
                if url=="https://venue.example/whats-on": return 200,"text/html",calendar,False
                if url=="https://venue.example/events/act": return 200,"text/html",detail,False
                raise AssertionError("External URL must not be fetched: "+url)
            with patch("inspect_event_links.fetch",side_effect=fake_fetch):
                with patch("sys.argv",["inspect_event_links.py","--links",str(links),"--sources",str(sources),"--out-dir",str(root/"out"),"--start","2026-10-15","--end","2026-10-28","--delay","0"]):
                    self.assertEqual(main(),0)
            self.assertNotIn("https://tickets.example/event/123",fetched)
            with (root/"out"/"event_page_crawl_audit.csv").open(newline="",encoding="utf-8") as f:
                audit=list(csv.DictReader(f))[0]
            self.assertEqual(audit["external_seed_links_skipped"],"1")
            self.assertIn("External ticketing hosts are not crawled",audit["notes"])

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
