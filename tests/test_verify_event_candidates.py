import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_event_candidates import main


class VerifyEventCandidatesTests(unittest.TestCase):
    def write_csv(self, path, fields, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_official_evidence_verifies_and_explicit_seed_alone_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matches = root / "matches.csv"
            events = root / "events.csv"
            inspected = root / "inspected.csv"
            primary = root / "primary.csv"
            secondary = root / "secondary.csv"
            natural = root / "natural.csv"
            out = root / "verified.csv"

            self.write_csv(matches, [
                "artist_pool_name", "event_date", "venue", "event_title", "matched_performer",
                "source_url", "source_kind", "match_basis", "candidate_status", "price",
                "ticket_status", "verified", "notes",
            ], [
                {"artist_pool_name": "Heaven 17", "event_date": "2026-10-15", "venue": "Boiler Shop",
                 "event_title": "Heaven 17 @ Boiler Shop", "matched_performer": "Heaven 17"},
                {"artist_pool_name": "Ye Gods", "event_date": "2026-10-16", "venue": "The Lubber Fiend",
                 "event_title": "Byker Grave: Ye Gods + Pale World + Y Gwacter + Depletion",
                 "matched_performer": "Ye Gods"},
                {"artist_pool_name": "Dexys Midnight Runners", "event_date": "2026-10-21",
                 "venue": "O2 City Hall Newcastle", "event_title": "Dexys Midnight Runners @ O2 City Hall",
                 "matched_performer": "Dexys Midnight Runners"},
                {"artist_pool_name": "Dexys Midnight Runners", "event_date": "2026-10-20",
                 "venue": "O2 City Hall Newcastle", "event_title": "Dexys Midnight Runners",
                 "matched_performer": "Dexys Midnight Runners"},
            ])
            self.write_csv(events, [
                "event_date", "venue", "event_title", "artist", "source_url", "notes",
            ], [
                {"event_date": "2026-10-15", "venue": "Boiler Shop", "event_title": "Heaven 17",
                 "artist": "Heaven 17", "source_url": "https://www.boilershop.net/events/heaven-17"},
                {"event_date": "2026-10-16", "venue": "The Lubber Fiend",
                 "event_title": "Byker Grave: Ye Gods + Pale World + Y Gwacter + Depletion",
                 "artist": "Ye Gods", "source_url": "https://soundbitenortheast.com/newcastle-gigs/"},
                {"event_date": "2026-10-21", "venue": "O2 City Hall Newcastle",
                 "event_title": "Dexys Midnight Runners @ O2 City Hall", "artist": "Dexys Midnight Runners",
                 "source_url": "https://www.songkick.com/concerts/43121168-dexys-midnight-runners-at-o2-city-hall"},
                {"event_date": "2026-10-20", "venue": "O2 City Hall Newcastle",
                 "event_title": "Dexys Midnight Runners", "artist": "Dexys Midnight Runners",
                 "source_url": "https://www.academymusicgroup.com/o2cityhallnewcastle"},
                {"event_date": "2026-10-21", "venue": "O2 City Hall Newcastle",
                 "event_title": "Dexys Midnight Runners @ O2 City Hall", "artist": "Dexys Midnight Runners",
                 "source_url": "https://www.axs.com/events/123456/dexys-midnight-runners-tickets"},
            ])
            self.write_csv(inspected, [
                "venue", "page_url", "event_title", "event_date", "performer_names", "status", "notes",
            ], [
                {"venue": "The Lubber Fiend",
                 "page_url": "https://www.ents24.com/newcastle-events/the-lubber-fiend/ye-gods/7515428",
                 "event_title": "Byker Grave: Ye Gods + Pale World + Y Gwacter + Depletion",
                 "event_date": "2026-10-16", "performer_names": "Ye Gods; Pale World; Y Gwacter; Depletion",
                 "status": "visible_event_candidate_needs_review", "notes": "Explicit regression seed page"},
            ])
            self.write_csv(primary, ["venue", "source_url", "source_status"], [
                {"venue": "Boiler Shop", "source_url": "https://www.boilershop.net/events",
                 "source_status": "configured_official_calendar"},
                {"venue": "The Lubber Fiend", "source_url": "https://www.thelubberfiend.com/venue",
                 "source_status": "configured_official_site"},
                {"venue": "O2 City Hall Newcastle", "source_url": "https://www.academymusicgroup.com/o2cityhallnewcastle/events",
                 "source_type": "configured_official_calendar"},
            ])
            self.write_csv(secondary, ["venue", "source_url", "source_status"], [
                {"venue": "The Lubber Fiend", "source_url": "https://soundbitenortheast.com/newcastle-gigs/",
                 "source_status": "secondary_citywide_gig_guide"},
                {"venue": "O2 City Hall Newcastle", "source_url": "https://www.songkick.com/venues/885211-o2-city-hall/calendar",
                 "source_status": "secondary_venue_calendar"},
                {"venue": "Cobalt Studios", "source_url": "https://www.axs.com/uk/venues/2301/o2-city-hall-newcastle-upon-tyne-tickets",
                 "source_status": "secondary_ticketing_calendar"},
            ])
            self.write_csv(natural, ["candidate_url", "source_page_url"], [
                {"candidate_url": "https://www.boilershop.net/events/heaven-17", "source_page_url": "https://www.boilershop.net/events"},
                {"candidate_url": "https://soundbitenortheast.com/newcastle-gigs/", "source_page_url": "https://soundbitenortheast.com/newcastle-gigs/"},
                {"candidate_url": "https://www.songkick.com/concerts/43121168-dexys-midnight-runners-at-o2-city-hall", "source_page_url": "https://www.songkick.com/venues/885211-o2-city-hall/calendar"},
                {"candidate_url": "https://www.academymusicgroup.com/o2cityhallnewcastle/events/dexys-midnight-runners-tickets-ae1342102", "source_page_url": "https://www.academymusicgroup.com/o2cityhallnewcastle/events"},
                {"candidate_url": "https://www.axs.com/events/123456/dexys-midnight-runners-tickets", "source_page_url": "https://www.axs.com/uk/venues/2301/o2-city-hall-newcastle-upon-tyne-tickets"},
            ])

            with patch("sys.argv", [
                "verify_event_candidates.py", "--matches", str(matches), "--events", str(events),
                "--inspected", str(inspected), "--primary-sources", str(primary),
                "--secondary-sources", str(secondary), "--natural-links", str(natural),
                "--out", str(out),
            ]):
                self.assertEqual(main(), 0)

            with out.open(encoding="utf-8", newline="") as stream:
                output_rows = list(csv.DictReader(stream))
            rows = {row["artist_pool_name"]: row for row in output_rows if row["event_date"] != "2026-10-20"}
            self.assertEqual(rows["Heaven 17"]["verification_status"], "verified_official_source")
            self.assertEqual(rows["Dexys Midnight Runners"]["verification_status"], "verified_cross_source")
            dexys_wrong_date=next(row for row in output_rows if row["event_date"]=="2026-10-20")
            self.assertEqual(dexys_wrong_date["verification_status"], "candidate_needs_manual_review")
            self.assertEqual(rows["Ye Gods"]["verification_status"], "candidate_needs_manual_review")
            summary = json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["verified_events"], 2)
            self.assertEqual(summary["unverified_candidate_match_rows"], 1)
            self.assertEqual(summary["status"], "LIMITED")


    def test_listing_source_url_does_not_verify_an_explicit_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matches = root / "matches.csv"
            events = root / "events.csv"
            inspected = root / "inspected.csv"
            primary = root / "primary.csv"
            secondary = root / "secondary.csv"
            natural = root / "natural.csv"
            out = root / "verified.csv"
            seeded_url = "https://venue.example/events/the-wedding-present"

            self.write_csv(matches, [
                "artist_pool_name", "event_date", "venue", "event_title", "matched_performer",
                "source_url", "notes",
            ], [{
                "artist_pool_name": "The Wedding Present", "event_date": "2026-10-23",
                "venue": "Boiler Shop", "event_title": "The Wedding Present",
                "matched_performer": "The Wedding Present",
            }])
            self.write_csv(events, [
                "event_date", "venue", "event_title", "artist", "source_url", "notes",
            ], [])
            self.write_csv(inspected, [
                "venue", "page_url", "event_title", "event_date", "performer_names", "notes",
            ], [{
                "venue": "Boiler Shop", "page_url": seeded_url,
                "event_title": "The Wedding Present", "event_date": "2026-10-23",
                "performer_names": "The Wedding Present",
                "notes": "Explicit regression seed page; parser coverage only.",
            }])
            self.write_csv(primary, ["venue", "source_url", "source_type"], [{
                "venue": "Boiler Shop", "source_url": "https://venue.example/events",
                "source_type": "configured_official_calendar",
            }])
            self.write_csv(secondary, ["venue", "source_url", "source_type"], [])
            # The seeded event URL appears only as the source page for a
            # different candidate, not as a naturally discovered event URL.
            self.write_csv(natural, ["candidate_url", "source_page_url"], [{
                "candidate_url": "https://venue.example/events/another-act",
                "source_page_url": seeded_url,
            }])

            with patch("sys.argv", [
                "verify_event_candidates.py", "--matches", str(matches), "--events", str(events),
                "--inspected", str(inspected), "--primary-sources", str(primary),
                "--secondary-sources", str(secondary), "--natural-links", str(natural),
                "--out", str(out),
            ]):
                self.assertEqual(main(), 0)

            with out.open(encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["verification_status"], "candidate_needs_manual_review")
            self.assertEqual(row["verified"], "false")
            summary = json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["verified_events"], 0)


if __name__ == "__main__":
    unittest.main()
