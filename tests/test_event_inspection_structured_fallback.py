import csv, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_event_links import main


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


if __name__ == "__main__":
    unittest.main()
