import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"check_regression_artists.py"

class RegressionArtistSearchTests(unittest.TestCase):
    def test_writes_a_search_row_for_every_seed_and_labels_bounded_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); seeds=root/"seeds.csv"; venues=root/"venues.csv"
            venue_snaps=root/"venue-pages"; event_snaps=root/"event-pages"; out=root/"regression_artist_checks.csv"
            venue_snaps.mkdir(); event_snaps.mkdir()
            with seeds.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["artist"]); w.writeheader()
                w.writerow({"artist":"Delines"}); w.writerow({"artist":"Gallus"})
            with venues.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url"]); w.writeheader()
                w.writerow({"venue":"Test Venue","source_url":"https://venue.example/calendar"})
            (venue_snaps/"page.txt").write_text("SOURCE: https://venue.example/calendar\nThe Delines are listed on this page.\n")
            (event_snaps/"detail.txt").write_text("SOURCE: https://venue.example/event\nA local event page.\n")
            subprocess.run([sys.executable,str(SCRIPT),"--seeds",str(seeds),"--venue-snapshots",str(venue_snaps),
                "--event-snapshots",str(event_snaps),"--venues",str(venues),"--out",str(out)],
                check=True,capture_output=True,text=True)
            with out.open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            by_artist={r["artist"]:r for r in rows}
            self.assertEqual(set(by_artist),{"Delines","Gallus"})
            self.assertEqual(by_artist["Delines"]["result"],"found_in_collected_pages")
            self.assertIn("The Delines are listed on this page",by_artist["Delines"]["notes"])
            self.assertIn("Matching text (context only",by_artist["Delines"]["notes"])
            self.assertEqual(by_artist["Gallus"]["result"],"not_found_in_collected_pages")
            self.assertEqual(by_artist["Gallus"]["searched"],"true")
            self.assertIn("bounded corpus",by_artist["Gallus"]["notes"])
            summary=json.loads(out.with_suffix(".summary.json").read_text())
            self.assertEqual(summary["snapshots_searched"],2)

if __name__=="__main__":
    unittest.main()
