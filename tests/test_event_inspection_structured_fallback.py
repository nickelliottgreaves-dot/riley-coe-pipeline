import csv, json, sys, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_event_links import main, extract_visible_listing_events


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


if __name__ == "__main__":
    unittest.main()
