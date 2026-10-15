import csv, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_known_gig_regressions import main


class KnownGigRegressionTests(unittest.TestCase):
    def test_requires_performer_evidence_on_the_specific_event_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures.csv"
            with fixtures.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["fixture_id", "event_date", "venue", "event_title", "performer", "source_url"])
                w.writeheader()
                w.writerow({"fixture_id": "1", "event_date": "2026-10-15", "venue": "Boiler Shop",
                            "event_title": "Heaven 17", "performer": "Heaven 17"})
                w.writerow({"fixture_id": "2", "event_date": "2026-10-16", "venue": "The Lubber Fiend",
                            "event_title": "Another Act", "performer": "Ye Gods"})
            events = root / "events.csv"
            with events.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "artist", "source_url"])
                w.writeheader()
                w.writerow({"event_date": "2026-10-15", "venue": "Boiler Shop", "event_title": "Heaven 17",
                            "artist": "Heaven 17", "source_url": "https://venue.example/heaven"})
            inspected = root / "inspected.csv"
            with inspected.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "performer_names", "page_url",
                                                  "visible_text_snapshot", "status"])
                w.writeheader()
                w.writerow({"event_date": "2026-10-16", "venue": "The Lubber Fiend", "event_title": "Another Act",
                            "performer_names": "Another Act", "page_url": "https://venue.example/another",
                            "visible_text_snapshot": "snapshots/page.txt", "status": "visible_event_candidate_needs_review"})
            (root / "snapshots").mkdir()
            (root / "snapshots/page.txt").write_text("Ye Gods\nFri 16 Oct 2026", encoding="utf-8")
            out = root / "regressions.csv"
            with patch("sys.argv", ["check_known_gig_regressions.py", "--fixtures", str(fixtures),
                                    "--events", str(events), "--inspected", str(inspected),
                                    "--inspection-dir", str(root), "--out", str(out)]):
                self.assertEqual(main(), 1)
            with out.open(encoding="utf-8", newline="") as f:
                rows = {r["fixture_id"]: r for r in csv.DictReader(f)}
            self.assertEqual(rows["1"]["result"], "recovered")
            self.assertEqual(rows["2"]["result"], "not_recovered")
            summary = json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["recovered"], 1)
            self.assertEqual(summary["not_recovered"], 1)


    def test_seeded_parser_recovery_does_not_pass_natural_discovery_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures.csv"
            with fixtures.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["fixture_id", "event_date", "venue", "event_title", "performer"])
                w.writeheader()
                w.writerow({"fixture_id": "1", "event_date": "2026-10-15", "venue": "Boiler Shop",
                            "event_title": "Heaven 17", "performer": "Heaven 17"})
            events = root / "events.csv"
            with events.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "artist", "source_url", "notes"])
                w.writeheader()
                w.writerow({"event_date": "2026-10-15", "venue": "Boiler Shop", "event_title": "Heaven 17",
                            "artist": "Heaven 17", "source_url": "https://venue.example/heaven",
                            "notes": "Explicit regression seed page; parser coverage only."})
            inspected = root / "inspected.csv"
            with inspected.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "performer_names", "page_url", "notes"])
                w.writeheader()
            out = root / "regressions.csv"
            with patch("sys.argv", ["check_known_gig_regressions.py", "--fixtures", str(fixtures),
                                    "--events", str(events), "--inspected", str(inspected),
                                    "--inspection-dir", str(root), "--out", str(out)]):
                self.assertEqual(main(), 1)
            summary = json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["parser_status"], "PASS")
            self.assertEqual(summary["natural_discovery_status"], "INCOMPLETE")
            self.assertEqual(summary["status"], "PARSER_PASS_NATURAL_DISCOVERY_INCOMPLETE")


    def test_listing_source_url_does_not_turn_an_explicit_seed_into_natural_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures.csv"
            with fixtures.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["fixture_id", "event_date", "venue", "event_title", "performer"])
                w.writeheader()
                w.writerow({"fixture_id": "1", "event_date": "2026-10-23", "venue": "Boiler Shop",
                            "event_title": "The Wedding Present", "performer": "The Wedding Present"})
            events = root / "events.csv"
            with events.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "artist", "source_url", "notes"])
                w.writeheader()
            inspected = root / "inspected.csv"
            with inspected.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event_date", "venue", "event_title", "page_url", "notes"])
                w.writeheader()
                w.writerow({"event_date": "2026-10-23", "venue": "Boiler Shop", "event_title": "The Wedding Present",
                            "page_url": "https://venue.example/wedding-present",
                            "notes": "Explicit regression seed page; parser coverage only."})
            natural_links = root / "natural_links.csv"
            with natural_links.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["candidate_url", "source_page_url"])
                w.writeheader()
                # The event page appears only as a source/listing URL, not as a
                # naturally discovered event candidate.
                w.writerow({"candidate_url": "https://venue.example/other-event",
                            "source_page_url": "https://venue.example/wedding-present"})
            out = root / "regressions.csv"
            with patch("sys.argv", ["check_known_gig_regressions.py", "--fixtures", str(fixtures),
                                    "--events", str(events), "--inspected", str(inspected),
                                    "--inspection-dir", str(root), "--natural-links", str(natural_links),
                                    "--out", str(out)]):
                self.assertEqual(main(), 1)
            with out.open(encoding="utf-8", newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["result"], "recovered")
            self.assertEqual(row["natural_result"], "not_naturally_recovered")
            self.assertEqual(row["explicit_seed_recovered"], "true")


if __name__ == "__main__":
    unittest.main()
