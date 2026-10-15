import csv, json, subprocess, sys, tempfile, unittest
from datetime import date
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import inspect_event_links as crawler
from inspect_event_links import calendar_target_in_window, canonicalize_url, event_link_matches, event_performer_candidate, extract_visible_event, extract_visible_listing_events, is_calendar_navigation, is_event_object, is_plausible_event_page_url, likely, main

class EventPageCrawlerTests(unittest.TestCase):
    def test_calendar_date_filters_stay_inside_requested_window(self):
        start=date(2026,10,15); end=date(2026,10,28)
        self.assertTrue(calendar_target_in_window("https://thecluny.com/gigs/date/2026/10",start,end))
        self.assertFalse(calendar_target_in_window("https://thecluny.com/gigs/date/2026/11",start,end))
        self.assertTrue(calendar_target_in_window("https://cobaltstudios.co.uk/whats-on/?date=23-10-2026",start,end))
        self.assertFalse(calendar_target_in_window("https://cobaltstudios.co.uk/whats-on/?date=30-10-2026",start,end))

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

    def test_plausible_event_url_filter_blocks_artist_and_metro_pages(self):
        source="https://www.songkick.com/venues/2716778-boiler-shop/calendar"
        self.assertTrue(is_plausible_event_page_url("https://www.songkick.com/concerts/43180861-heaven-17-at-boiler-shop",source))
        self.assertTrue(is_plausible_event_page_url("https://www.songkick.com/venues/2716778-boiler-shop/calendar?page=2",source))
        self.assertFalse(is_plausible_event_page_url("https://www.songkick.com/en/metro-areas/24577-uk-newcastle-upon-tyne",source))
        self.assertFalse(is_plausible_event_page_url("https://www.songkick.com/artists/525074-heaven-17",source))
        ents_source="https://www.ents24.com/newcastle-events/the-lubber-fiend"
        self.assertTrue(is_plausible_event_page_url("https://www.ents24.com/newcastle-events/the-lubber-fiend/ye-gods/7515428",ents_source))

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

    def test_event_slug_date_conflict_prefers_visible_date_for_review(self):
        visible = """Heaven 17
Date:
Thu 15 Oct 2026
Venue:
Boiler Shop
Peter Coyle
Tickets
Sold Out"""
        row=extract_visible_event("Heaven 17 - Boiler Shop",visible,"Boiler Shop",
            "https://www.boilershop.net/events/heaven-17-15-11-26")
        self.assertIsNotNone(row)
        self.assertEqual(row["event_date"],"2026-10-15")
        self.assertIn("URL date conflicts with visible date; visible date preferred",row["notes"])

    def test_category_first_cards_use_default_venue_and_extract_price(self):
        visible = """AUTUMN PROGRAMME 2026
Featured Events:
17 Oct 2026
Club Night
L.A.D's presents: Marion Hawkes + Sami J
11pm
£9-14
17 Oct 2026
Club Night
Some Like It Early Presents: Colleen 'Cosmo' Murphy
7pm
£10-15
16 Oct 2026
Live Music
Mercury Prize Fringe: Ancient Infinity Orchestra + Weston (DJ)
7pm
£0-12"""
        rows = extract_visible_listing_events(visible, "Cobalt Studios")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["event_date"], "2026-10-17")
        self.assertEqual(rows[0]["venue"], "Cobalt Studios")
        self.assertEqual(rows[0]["price"], "£9-14")
        self.assertEqual(rows[0]["performer_names"], "Marion Hawkes; Sami J")
        self.assertEqual(rows[1]["performer_names"], "Colleen 'Cosmo' Murphy")
        self.assertEqual(rows[2]["performer_names"], "Ancient Infinity Orchestra; Weston (DJ)")
        self.assertEqual(rows[2]["price"], "£0-12")

    def test_venue_homepage_title_is_not_misclassified_as_an_event(self):
        visible = """SOURCE: https://www.boilershop.net/
VENUE: Boiler Shop
Boiler Shop
Events
The Wedding Present
Fri
23 Oct
'
26
7:00 pm"""
        self.assertIsNone(extract_visible_event("Boiler Shop", visible, "Boiler Shop"))

    def test_conflicting_url_and_visible_dates_keep_visible_date(self):
        visible = """SOURCE: https://www.boilershop.net/events/heaven-17-15-11-26
VENUE: Boiler Shop
Heaven 17 - performing 'Penthouse and Pavement' at Boiler Shop Newcastle
Heaven 17 - performing 'Penthouse and Pavement'
+ Peter Coyle
Thu
15 Oct
'
26
7:00 pm
BUY TICKETS
SOLD OUT"""
        row = extract_visible_event("Heaven 17 - performing 'Penthouse and Pavement' at Boiler Shop Newcastle",
            visible,"Boiler Shop","https://www.boilershop.net/events/heaven-17-15-11-26")
        self.assertIsNotNone(row)
        self.assertEqual(row["event_date"],"2026-10-15")
        self.assertIn("URL date conflicts with visible date; visible date preferred",row["notes"])

    def test_cobalt_detail_uses_main_ordinal_date_price_and_billed_acts(self):
        visible = """SOURCE: https://cobaltstudios.co.uk/events/l-a-ds-presents-marion-hawkes/
VENUE: Cobalt Studios
L.A.D’s presents: Marion Hawkes + Sami J - Cobalt Studios
Club Night
Sat 17th October 2026
11pm
9-14
Location:
Venue Space, Cobalt Studios, Newcastle
Marion Hawkes
Support from L.A.Ds and Slack’s Radio resident
Sami J
—
You may also like...
15 Oct 2026
Live Music
Fresh Thursday // Right of Way + James Leonard Hewitson
7pm
£8-16
SOLD OUT"""
        row = extract_visible_event("L.A.D’s presents: Marion Hawkes + Sami J - Cobalt Studios", visible, "Cobalt Studios")
        self.assertIsNotNone(row)
        self.assertEqual(row["event_date"], "2026-10-17")
        self.assertEqual(row["price"], "£9-14")
        self.assertEqual(row["performer_names"], "Marion Hawkes; Sami J")
        self.assertEqual(row["availability"], "not_checked")

    def test_extracts_unlabelled_boiler_shop_date_and_support_billing(self):
        visible = """SOURCE: https://www.boilershop.net/events/the-wedding-present-23-10-26
VENUE: Boiler Shop
The Wedding Present at Boiler Shop Newcastle
JS Promotions presents
The Wedding Present
+ Radhika
Fri
23 Oct
'
26
7:00 pm
BUY TICKETS
SOLD OUT"""
        row = extract_visible_event("The Wedding Present at Boiler Shop Newcastle", visible, "Boiler Shop")
        self.assertIsNotNone(row)
        self.assertEqual(row["event_date"], "2026-10-23")
        self.assertEqual(row["venue"], "Boiler Shop")
        self.assertEqual(row["event_title"], "The Wedding Present")
        self.assertEqual(row["performer_names"], "The Wedding Present; Radhika")
        self.assertEqual(row["availability"], "SoldOut")

    def test_extracts_lead_artist_from_tour_title(self):
        visible = """VENUE: Boiler Shop
Cabaret Voltaire: Final UK Tour
Sat
17 Oct
'
26
7:00 pm
+ Gazelle Twin
SOLD OUT"""
        row = extract_visible_event("Cabaret Voltaire: Final UK Tour at Boiler Shop Newcastle", visible, "Boiler Shop")
        self.assertEqual(row["event_date"], "2026-10-17")
        self.assertEqual(row["event_title"], "Cabaret Voltaire: Final UK Tour")
        self.assertEqual(row["performer_names"], "Cabaret Voltaire; Gazelle Twin")

    def test_detail_page_with_generic_page_title_is_not_promoted_as_an_event(self):
        visible = """Jack Savoretti
Date:
Sun 25 Oct 2026
Venue:
Sage One
Advance tickets:
£42.50"""
        self.assertIsNone(extract_visible_event("Limited Availability - The Glasshouse", visible))
        self.assertIsNone(extract_visible_event("Access Info - The Glasshouse", visible))
        self.assertIsNone(extract_visible_event("7:00pm - The Glasshouse", visible))
        self.assertIsNone(extract_visible_event("Live Events Archives - NX Newcastle", visible))
        self.assertIsNone(extract_visible_event("Events Archive - NX Newcastle", visible))

    def test_glasshouse_detail_page_uses_explicit_room_not_crawl_seed(self):
        visible = """Friday 16 October 2026 |
7:30pm
Book Now
Sheku Kanneh-Mason plays Saint-Saëns
Part of
Classical 26/27
Sage One
Book Now
Tickets – £5.00 to £53.00
Who's playing it
Dinis Sousa
conductor
Sheku Kanneh-Mason
cello
Royal Northern Sinfonia
This event takes place at:
Sage One
St Mary's Square
Gateshead
Tickets
Friday 16 October 2026
From: £5.00 - £53.00
Sage One
What's happening in the music?
Saint-Saëns' packs energy into his concerto."""
        row=extract_visible_event("Sheku Kanneh-Mason plays Saint-Saëns | The Glasshouse",visible,"Sage Two")
        self.assertIsNotNone(row)
        self.assertEqual(row["event_date"],"2026-10-16")
        self.assertEqual(row["venue"],"Sage One")
        self.assertEqual(row["price"],"£5.00 to £53.00")
        self.assertEqual(row["performer_names"],"Sheku Kanneh-Mason; Dinis Sousa; Royal Northern Sinfonia")

    def test_detail_page_metadata_and_timing_lines_are_not_performers(self):
        visible="""Friday 16 October 2026
        Sage One
        Who's playing it
        Sheku Kanneh-Mason
        Violin
        Dinis Sousa
        Conductor
        With support from
        Support Act
        8.30pm -9pm
        Timings are approximate and subject to change
        Interval
        Age: Under 14s must be accompanied by an adult.
        What they say
        The Guardian
        Your visit
        Plan your journey
        Parking
        Eat and Drink
        Access Info
        Take a listen
        About Samling Academy"""
        row=extract_visible_event("Sheku Kanneh-Mason plays Saint-Saëns | The Glasshouse",visible,"Sage Two")
        self.assertIsNotNone(row)
        self.assertEqual(row["performer_names"],"Sheku Kanneh-Mason; Support Act; Dinis Sousa")

    def test_listing_parser_rejects_timing_and_access_labels_as_event_titles(self):
        visible="""8.30pm - 9pm
        Fri 16 Oct 2026
        Live Music
        Sage Two
        Access Info
        Sat 17 Oct 2026
        Live Music
        Sage Two"""
        rows=extract_visible_listing_events(visible,"Sage Two")
        self.assertEqual(rows,[])

    def test_glasshouse_detail_page_at_external_touring_venue_is_excluded(self):
        visible = """Thursday 15 October 2026 |
7:30pm
Book Now
Sheku Kanneh-Mason plays Saint-Saëns
Part of
Classical 26/27
Middlesbrough Town Hall
Book Now
Tickets – £5.00 to £53.00
Who’s on stage
Sheku Kanneh-Mason"""
        row=extract_visible_event("Sheku Kanneh-Mason plays Saint-Saëns | The Glasshouse",visible,"Sage Two")
        self.assertIsNone(row)

    def test_glasshouse_regional_tour_location_with_city_suffix_is_excluded(self):
        visible = """Sunday 25 October 2026 |
3:00pm
Book Now
Vivaldi's Four Seasons
Part of
Royal Northern Sinfonia: Out and about
Who’s on stage
Royal Northern Sinfonia
Who's playing it
Maria Włoszczowska
director/violin
Royal Northern Sinfonia
This event takes place at:
Kings Place
90 York Way
London
N1 9AG
Website:
Kings Place – The Cultural Pulse of King's Cross
Tickets
Sunday 25 October 2026
From: £28.00 - £35.00
Kings Place, London"""
        row=extract_visible_event("Vivaldi's Four Seasons | The Glasshouse",visible,"Sage Two")
        self.assertIsNone(row)

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

    def test_listing_parser_skips_generic_cta_and_availability_labels(self):
        visible = """Allie X
More Info
Mon 26 Oct 2026
Sage Two
Tickets
The Strokes
Limited Availability
Sun 25 Oct 2026
Utilita Arena Newcastle
Tickets"""
        rows = extract_visible_listing_events(visible)
        self.assertEqual([r["event_title"] for r in rows], ["Allie X", "The Strokes"])
        self.assertNotIn("More Info", [r["event_title"] for r in rows])
        self.assertNotIn("Limited Availability", [r["event_title"] for r in rows])

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

    def test_explicit_regression_seed_is_fetched_and_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            links=root/"links.csv"; sources=root/"sources.csv"; extra=root/"extra.csv"
            with links.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","candidate_url","link_text"]); w.writeheader()
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/gigs/"})
            with extra.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/events/skating-polly/"})
            calendar="<title>Gigs</title><p>No current listings on the landing page.</p>"
            detail="<title>Skating Polly - The Cluny</title><p>Date:</p><p>Thu 15 Oct 2026</p><p>Venue:</p><p>The Cluny</p><p>Advance tickets:</p><p>£17.50</p>"
            fetched=[]
            def fake_fetch(url):
                fetched.append(url)
                if url=="https://thecluny.com/gigs/": return 200,"text/html",calendar,False
                if url=="https://thecluny.com/events/skating-polly/": return 200,"text/html",detail,False
                raise AssertionError("Unexpected crawl URL: "+url)
            with patch("inspect_event_links.fetch",side_effect=fake_fetch):
                with patch("sys.argv",["inspect_event_links.py","--links",str(links),"--sources",str(sources),
                    "--extra-seeds",str(extra),"--out-dir",str(root/"out"),"--start","2026-10-15","--end","2026-10-28","--delay","0"]):
                    self.assertEqual(main(),0)
            self.assertEqual(fetched,["https://thecluny.com/gigs/","https://thecluny.com/events/skating-polly/"])
            with (root/"out"/"event_page_inspection.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(any(r["event_title"]=="Skating Polly" and "Explicit regression seed page" in r["notes"] for r in rows))
            summary=json.loads((root/"out"/"event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["explicit_regression_seed_pages"],1)

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

    def test_partial_page_failures_keep_successful_crawl_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); links=root/"links.csv"; sources=root/"sources.csv"
            with links.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["venue","candidate_url"]); w.writeheader()
                w.writerow({"venue":"Test Venue","candidate_url":"https://venue.example/events/good"})
                w.writerow({"venue":"Test Venue","candidate_url":"https://venue.example/events/broken"})
            with sources.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"Test Venue","source_url":"https://venue.example/whats-on"})
            def fake_fetch(url, *args, **kwargs):
                if "broken" in url:
                    return 503,"text/plain","",False
                return 200,"text/html","<html><head><title>Test Venue gigs</title></head><body>Nothing else listed</body></html>",False
            with patch.object(crawler,"fetch",side_effect=fake_fetch):
                with patch("sys.argv",["inspect_event_links.py","--links",str(links),"--sources",str(sources),
                    "--out-dir",str(root/"out"),"--start","2026-10-15","--end","2026-10-28","--delay","0"]):
                    self.assertEqual(main(),0)
            summary=json.loads((root/"out"/"event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["status"],"PARTIAL")
            self.assertGreater(summary["pages_failed"],0)
            self.assertGreater(summary["pages_inspected"]-summary["pages_failed"],0)

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
            # The crawl may be able to fetch one seed despite the deliberately
            # invalid host (depending on the runner's network resolver); the
            # authoritative assertion is that the output remains PARTIAL and
            # every event remains unverified.
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
