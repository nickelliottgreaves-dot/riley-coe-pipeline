import csv, json, sys, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_event_links import main, extract_visible_listing_events, allowed_source_scoped_url, is_external_event_detail_url


class StructuredDataFallbackTests(unittest.TestCase):
    def test_incomplete_jsonld_does_not_suppress_same_host_event_link_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "candidate_url": "https://venue.example/events/example-artist",
                    "link_text": "Example Artist",
                })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "source_url": "https://venue.example/events/",
                })

            calendar = (
                '<title>Wylam Brewery Events</title>'
                '<script type="application/ld+json">'
                '{"@type":"Event","name":"One structured item","startDate":"2026-10-17"}'
                '</script>'
                '<a href="/events/example-artist">Example Artist</a>'
            )
            detail = (
                '<title>Example Artist - Wylam Brewery</title>'
                '<p>Date:</p><p>Sat 17 Oct 2026</p>'
                '<p>Venue:</p><p>Wylam Brewery</p>'
                '<p>Advance tickets:</p><p>£12.00</p>'
            )
            fetched = []

            def fake_fetch(url):
                fetched.append(url)
                if url == "https://venue.example/events/":
                    return 200, "text/html", calendar, False
                if url == "https://venue.example/events/example-artist":
                    return 200, "text/html", detail, False
                raise AssertionError("Unexpected URL fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            self.assertEqual(fetched, [
                "https://venue.example/events/",
                "https://venue.example/events/example-artist",
            ])
            summary = json.loads((out / "event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["pages_inspected"], 2)
            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(any(
                row["event_title"] == "Example Artist"
                and row["event_date"] == "2026-10-17"
                and row["status"] == "visible_event_candidate_needs_review"
                for row in rows
            ))


    def test_structured_candidates_are_window_filtered_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "candidate_url": "https://venue.example/events/",
                    "link_text": "Wylam Brewery events",
                })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "source_url": "https://venue.example/events/",
                })

            page = (
                '<title>Wylam Brewery Events</title>'
                '<script type="application/ld+json">'
                '{"@graph":['
                '{"@type":"MusicEvent","name":"In Window Act","startDate":"2026-10-17T19:00:00+01:00"},'
                '{"@type":"MusicEvent","name":"In Window Act","startDate":"2026-10-17T19:00:00+01:00"},'
                '{"@type":"MusicEvent","name":"Out of Window Act","startDate":"2027-02-01T19:00:00+00:00"}'
                ']}'
                '</script>'
            )
            with patch("inspect_event_links.fetch", return_value=(200, "text/html", page, False)):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            structured = [row for row in rows if row["status"] == "structured_candidate_needs_review"]
            self.assertEqual(len(structured), 1)
            self.assertEqual(structured[0]["event_title"], "In Window Act")
            self.assertEqual(structured[0]["event_date"], "2026-10-17")

    def test_out_of_window_jsonld_does_not_block_visible_in_window_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "candidate_url": "https://venue.example/events/",
                    "link_text": "Wylam Brewery events",
                })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "Wylam Brewery",
                    "source_url": "https://venue.example/events/",
                })
            page = (
                '<title>Wylam Brewery Events</title>'
                '<script type="application/ld+json">'
                '{"@type":"MusicEvent","name":"Old Event","startDate":"2027-02-01"}'
                '</script>'
                '<p>Sat 17 Oct 2026</p><p>Visible In-Window Act</p>'
                '<p>Wylam Brewery</p>'
            )
            with patch("inspect_event_links.fetch", return_value=(200, "text/html", page, False)):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)
            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(any(
                row["event_title"] == "Visible In-Window Act"
                and row["event_date"] == "2026-10-17"
                and row["status"] == "visible_event_candidate_needs_review"
                for row in rows
            ))
            self.assertFalse(any(row["event_title"] == "Old Event" for row in rows))

    def test_empty_non_200_host_response_uses_only_bounded_fallback_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                for i in range(20):
                    w.writerow({
                        "venue": "The Cluny",
                        "candidate_url": f"https://blocked.example/listing/act-{i}/",
                        "link_text": f"Act {i}",
                    })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "The Cluny",
                    "source_url": "https://blocked.example/gigs/",
                })

            fetched = []
            def fake_fetch(url):
                fetched.append(url)
                return 202, "text/html", "", False

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--max-pages-per-venue", "30", "--delay", "0",
                ]):
                    # With no successful fetches the crawler correctly exits non-zero.
                    self.assertEqual(main(), 1)

            self.assertLessEqual(len(fetched), 4)
            with (out / "event_page_crawl_audit.csv").open(encoding="utf-8", newline="") as f:
                audit = list(csv.DictReader(f))[0]
            self.assertEqual(audit["pages_failed"], "4")
            self.assertEqual(audit["crawl_cap_reached"], "false")
            self.assertEqual(audit["status"], "PARTIAL")


    def test_date_first_cumberland_cards_capture_title_and_support_acts(self):
        visible = """Events
october
Thur 15 October '26 | 19.30
TICKETS
Yotuns + Delphine Joussein ‘Calamity’ + LEDLEY w/ special guest Faye MacCalman
fri 16 October '26 | 19:30
Tickets
f54 x mercury prize fringe 2026
Sin Clair, Nadine Hurley, Crimewavex
"""
        rows = extract_visible_listing_events(
            visible, "Cumberland Arms",
            date.fromisoformat("2026-10-15"), date.fromisoformat("2026-10-28")
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_date"], "2026-10-15")
        self.assertIn("Yotuns", rows[0]["performer_names"])
        self.assertIn("Faye MacCalman", rows[0]["performer_names"])
        self.assertEqual(rows[1]["event_date"], "2026-10-16")
        self.assertIn("Sin Clair", rows[1]["performer_names"])
        self.assertIn("Crimewavex", rows[1]["performer_names"])

    def test_inline_month_day_and_ordinal_dates_are_inferred_from_window(self):
        visible = """Oct 15 – KMP Quintal
Thursday 15 October, 7pm
Tickets: £6-£8
23rd Oct - The Fargo Railroad Co. @ Central Bar
26th Oct - The Klittens
"""
        rows = extract_visible_listing_events(
            visible, "Central Gateshead / Central Bar",
            date.fromisoformat("2026-10-15"), date.fromisoformat("2026-10-28")
        )
        by_title = {row["event_title"]: row for row in rows}
        self.assertEqual(by_title["KMP Quintal"]["event_date"], "2026-10-15")
        self.assertEqual(by_title["KMP Quintal"]["price"], "£6-£8")
        self.assertEqual(by_title["The Fargo Railroad Co."]["event_date"], "2026-10-23")
        self.assertEqual(by_title["The Klittens"]["event_date"], "2026-10-26")

    def test_ordinal_full_year_calendar_dates_parse_for_gigantic_cards(self):
        visible = """Friday 16th October 2026
Smith & Liddle
The Grove, Newcastle upon Tyne
Doors at 19:00
Book Tickets
Saturday 17th October 2026
Northern Hospitality
+ Slate Label & Ben Harwood
The Grove, Newcastle upon Tyne
Doors at 19:00
Book Tickets
"""
        rows = extract_visible_listing_events(
            visible, "The Grove",
            date.fromisoformat("2026-10-15"), date.fromisoformat("2026-10-28")
        )
        self.assertEqual([r["event_date"] for r in rows], ["2026-10-16", "2026-10-17"])
        self.assertEqual(rows[0]["event_title"], "Smith & Liddle")
        self.assertIn("Slate Label & Ben Harwood", rows[1]["performer_names"])


    def test_successful_but_incomplete_jsonld_uses_bounded_fallback_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                for i in range(20):
                    w.writerow({
                        "venue": "Example Venue",
                        "candidate_url": f"https://venue.example/events/act-{i}",
                        "link_text": f"Act {i}",
                    })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "Example Venue",
                    "source_url": "https://venue.example/events/",
                })

            html = (
                '<title>Example Venue Events</title>'
                '<script type="application/ld+json">'
                '{"@type":"Event","name":"One structured item","startDate":"2026-10-17"}'
                '</script>'
            )
            fetched = []
            def fake_fetch(url):
                fetched.append(url)
                return 200, "text/html", html, False

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--max-pages-per-venue", "30", "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            self.assertEqual(len(fetched), 4)
            with (out / "event_page_crawl_audit.csv").open(encoding="utf-8", newline="") as f:
                audit = list(csv.DictReader(f))[0]
            self.assertEqual(audit["pages_fetched"], "4")
            self.assertEqual(audit["pages_failed"], "0")
            self.assertEqual(audit["crawl_cap_reached"], "false")


    def test_complete_in_window_jsonld_avoids_redundant_event_detail_crawl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            event_objects = []
            cards = []
            anchors = []
            for i in range(5):
                event_objects.append({
                    "@type": "MusicEvent",
                    "name": f"Act {i} @ Wylam Brewery",
                    "startDate": "2026-10-17",
                    "performer": {"@type": "MusicGroup", "name": f"Act {i}"},
                    "offers": {"price": "12.00", "priceCurrency": "GBP"},
                })
                cards.append(f"<p>Act {i}</p><p>Sat 17 Oct 2026</p><p>Wylam Brewery</p>")
                anchors.append(f'<a href="/events/act-{i}">Act {i}</a>')
            html = (
                '<title>Wylam Brewery Events</title>'
                '<script type="application/ld+json">' + json.dumps(event_objects) + '</script>'
                + "".join(cards) + "".join(anchors)
            )
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                for i in range(5):
                    w.writerow({
                        "venue": "Wylam Brewery",
                        "candidate_url": f"https://venue.example/events/act-{i}",
                        "link_text": f"Act {i}",
                    })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({"venue": "Wylam Brewery", "source_url": "https://venue.example/events/"})

            fetched = []
            def fake_fetch(url):
                fetched.append(url)
                if url == "https://venue.example/events/":
                    return 200, "text/html", html, False
                raise AssertionError("Redundant detail page fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            self.assertEqual(fetched, ["https://venue.example/events/"])
            summary = json.loads((out / "event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["pages_inspected"], 1)


    def test_songkick_venue_scope_rejects_metro_and_artist_pages(self):
        source = "https://www.songkick.com/venues/17634-cluny/calendar"
        self.assertTrue(allowed_source_scoped_url(source, source, "The Cluny"))
        self.assertTrue(allowed_source_scoped_url(
            source, "https://www.songkick.com/concerts/43399167-barbican-estate-at-cluny", "The Cluny"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.songkick.com/en/metro-areas/24577-uk-newcastle-upon-tyne", "The Cluny"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.songkick.com/artists/1234-example-band", "The Cluny"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.songkick.com/concerts/123-band-at-boiler-shop", "The Cluny"
        ))

    def test_songkick_crawl_does_not_attribute_metro_events_to_cluny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            source = "https://www.songkick.com/venues/17634-cluny/calendar"
            concert = "https://www.songkick.com/concerts/43399167-barbican-estate-at-cluny"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({"venue": "The Cluny", "candidate_url": "https://www.songkick.com/en/metro-areas/24577-uk-newcastle-upon-tyne", "link_text": "Newcastle events"})
                w.writerow({"venue": "The Cluny", "candidate_url": "https://www.songkick.com/artists/1234-example-band", "link_text": "Example Band"})
                w.writerow({"venue": "The Cluny", "candidate_url": concert, "link_text": "Barbican Estate at The Cluny"})
                w.writerow({"venue": "The Cluny", "candidate_url": "https://www.songkick.com/concerts/123-band-at-boiler-shop", "link_text": "Band at Boiler Shop"})
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({"venue": "The Cluny", "source_url": source})

            fetched = []
            calendar = (
                '<title>The Cluny calendar</title>'
                '<a href="/en/metro-areas/24577-uk-newcastle-upon-tyne">Newcastle events</a>'
                '<a href="/artists/1234-example-band">Example Band</a>'
                '<a href="/concerts/43399167-barbican-estate-at-cluny">Barbican Estate at The Cluny</a>'
                '<a href="/concerts/123-band-at-boiler-shop">Band at Boiler Shop</a>'
            )
            detail = '<title>Barbican Estate at The Cluny</title><p>Mon 9 Nov 2026</p><p>The Cluny</p>'

            def fake_fetch(url):
                fetched.append(url)
                if url == source:
                    return 200, "text/html", calendar, False
                if url == concert:
                    return 200, "text/html", detail, False
                raise AssertionError("Out-of-scope Songkick URL fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-11-11",
                    "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            self.assertEqual(set(fetched), {source, concert})
            with (out / "event_page_inspection.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertFalse(any("metro-areas" in row["page_url"] for row in rows))
            self.assertFalse(any("/artists/" in row["page_url"] for row in rows))



    def test_external_ticketing_allowlist_accepts_event_details_not_generic_pages(self):
        self.assertTrue(is_external_event_detail_url(
            "https://www.universe.com/events/example-act-tickets-ABC123"
        ))
        self.assertTrue(is_external_event_detail_url(
            "https://www.seetickets.com/event/example-act/the-cumberland-arms/3726530"
        ))
        self.assertTrue(is_external_event_detail_url(
            "https://www.eventbrite.co.uk/e/example-act-tickets-1984620387002"
        ))
        self.assertFalse(is_external_event_detail_url(
            "https://www.songkick.com/metro-areas/1409-us-washington"
        ))
        self.assertFalse(is_external_event_detail_url(
            "https://www.eventbrite.co.uk/o/cobalt-studios-cic-47234260433"
        ))
        self.assertFalse(is_external_event_detail_url(
            "https://www.ticketmaster.co.uk/the-cluny-tickets-newcastle-upon-tyne/venue/254267?page=1"
        ))

    def test_bounded_allowlisted_external_event_page_is_inspected_without_recursive_external_crawl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({
                    "venue": "Cumberland Arms",
                    "candidate_url": "https://www.universe.com/events/example-act-tickets-ABC123",
                    "link_text": "Example Act tickets",
                })
                w.writerow({
                    "venue": "Cumberland Arms",
                    "candidate_url": "https://www.songkick.com/metro-areas/1409-us-washington",
                    "link_text": "unrelated Songkick city page",
                })
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({
                    "venue": "Cumberland Arms",
                    "source_url": "https://venue.example/events/",
                })
            calendar = '<title>Cumberland Arms Events</title><p>Upcoming live music</p>'
            external = (
                '<title>Example Act at Cumberland Arms</title>'
                '<script type="application/ld+json">'
                '{"@type":"MusicEvent","name":"Example Act","startDate":"2026-10-20T19:00:00+01:00",'
                '"performer":{"@type":"MusicGroup","name":"Example Act"}}'
                '</script>'
                '<a href="https://www.songkick.com/metro-areas/999-us-nowhere">Other events</a>'
            )
            fetched = []
            def fake_fetch(url):
                fetched.append(url)
                if url == "https://venue.example/events/":
                    return 200, "text/html", calendar, False
                if url == "https://www.universe.com/events/example-act-tickets-ABC123":
                    return 200, "text/html", external, False
                raise AssertionError("Unexpected URL fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28",
                    "--delay", "0", "--max-external-event-pages-per-venue", "2",
                ]):
                    self.assertEqual(main(), 0)

            self.assertEqual(fetched, [
                "https://venue.example/events/",
                "https://www.universe.com/events/example-act-tickets-ABC123",
            ])
            summary = json.loads((out / "event_page_crawl_summary.json").read_text())
            self.assertEqual(summary["external_event_pages_inspected"], 1)
            self.assertEqual(summary["external_seed_links_skipped"], 1)
            with (out / "event_page_crawl_audit.csv").open(encoding="utf-8", newline="") as f:
                audit = next(csv.DictReader(f))
            self.assertEqual(audit["external_event_pages_inspected"], "1")
            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(any(
                row["event_title"] == "Example Act"
                and row["event_date"] == "2026-10-20"
                and row["page_url"] == "https://www.universe.com/events/example-act-tickets-ABC123"
                for row in rows
            ))


    def test_skiddle_venue_scope_rejects_other_cities_and_other_venues(self):
        source = "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Lubber-Fiend/"
        self.assertTrue(allowed_source_scoped_url(
            source, "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Lubber-Fiend/#events", "Lubber Fiend"
        ))
        self.assertTrue(allowed_source_scoped_url(
            source, "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Lubber-Fiend/12345-example-event/", "Lubber Fiend"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.skiddle.com/whats-on/Cardiff/", "Lubber Fiend"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.skiddle.com/whats-on/Birmingham/whats-on-in-birmingham-today/", "Lubber Fiend"
        ))
        self.assertFalse(allowed_source_scoped_url(
            source, "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Cluny/", "Lubber Fiend"
        ))

    def test_skiddle_crawl_does_not_attribute_cardiff_events_to_lubber_fiend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            source = "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Lubber-Fiend/"
            local_event = "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Lubber-Fiend/12345-example-event/"
            unrelated = [
                "https://www.skiddle.com/whats-on/Cardiff/",
                "https://www.skiddle.com/whats-on/Newcastle-on-Tyne/The-Cluny/",
            ]
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({"venue": "Lubber Fiend", "candidate_url": unrelated[0], "link_text": "Cardiff events"})
                w.writerow({"venue": "Lubber Fiend", "candidate_url": unrelated[1], "link_text": "The Cluny"})
                w.writerow({"venue": "Lubber Fiend", "candidate_url": local_event, "link_text": "Example event"})
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({"venue": "Lubber Fiend", "source_url": source})
            calendar = (
                '<title>Lubber Fiend events</title>'
                f'<a href="{unrelated[0]}">Cardiff events</a>'
                f'<a href="{unrelated[1]}">The Cluny</a>'
                f'<a href="{local_event}">Example event</a>'
            )
            detail = (
                '<title>Example Act at Lubber Fiend</title>'
                '<script type="application/ld+json">'
                '{"@type":"MusicEvent","name":"Example Act","startDate":"2026-10-20T19:00:00+01:00",'
                '"performer":{"@type":"MusicGroup","name":"Example Act"}}'
                '</script>'
            )
            fetched = []
            def fake_fetch(url):
                fetched.append(url)
                if url == source:
                    return 200, "text/html", calendar, False
                if url == local_event:
                    return 200, "text/html", detail, False
                raise AssertionError("Out-of-scope Skiddle URL fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-10-28", "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)
            self.assertEqual(fetched, [source, local_event])
            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(any(row["event_title"] == "Example Act" and row["venue"] == "Lubber Fiend" for row in rows))
            self.assertFalse(any(row["page_url"] in unrelated for row in rows))


    def test_structured_single_event_uses_visible_price_and_ticket_listing_when_jsonld_omits_offers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            links = root / "links.csv"
            sources = root / "sources.csv"
            out = root / "out"
            event_url = "https://www.dice.fm/event/example-act-at-the-globe"
            with links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "candidate_url", "link_text"])
                w.writeheader()
                w.writerow({"venue": "The Globe", "candidate_url": event_url, "link_text": "Example Act tickets"})
            with sources.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["venue", "source_url"])
                w.writeheader()
                w.writerow({"venue": "The Globe", "source_url": event_url})
            html = (
                "<title>Example Act at The Globe</title>"
                "<h1>Example Act</h1><p>Date</p><p>Tue 27 October 2026</p>"
                "<p>Venue</p><p>The Globe Newcastle</p>"
                "<p>Tickets from £6.00</p><a href='/checkout'>Get tickets</a>"
                '<script type="application/ld+json">'
                '{"@type":"MusicEvent","name":"Example Act","startDate":"2026-10-27T19:00:00+01:00",'
                '"performer":{"@type":"MusicGroup","name":"Example Act"}}'
                "</script>"
            )
            def fake_fetch(url):
                if url == event_url:
                    return 200, "text/html", html, False
                raise AssertionError("Unexpected URL fetched: " + url)

            with patch("inspect_event_links.fetch", side_effect=fake_fetch):
                with patch("sys.argv", [
                    "inspect_event_links.py", "--links", str(links),
                    "--sources", str(sources), "--out-dir", str(out),
                    "--start", "2026-10-15", "--end", "2026-11-11", "--delay", "0",
                ]):
                    self.assertEqual(main(), 0)

            with (out / "event_page_inspection.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            row = next(row for row in rows if row["event_title"] == "Example Act")
            self.assertEqual(row["price"], "6.00")
            self.assertEqual(row["currency"], "GBP")
            self.assertEqual(row["availability"], "listed_for_purchase")
            self.assertIn("Visible text supplied price/status", row["notes"])

if __name__ == "__main__":
    unittest.main()
