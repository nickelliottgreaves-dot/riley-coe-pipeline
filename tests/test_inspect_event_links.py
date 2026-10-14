import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_event_links import is_aggregate_calendar_url
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
            self.assertEqual(empty["seed_candidate_links"],"1")
            self.assertEqual(empty["pages_failed"],"1")
            self.assertIn("source calendar",empty["notes"])

    def test_aggregate_songkick_pages_are_excluded(self):
        self.assertTrue(is_aggregate_calendar_url("https://www.songkick.com/metro-areas/24577-uk-newcastle-upon-tyne"))
        self.assertTrue(is_aggregate_calendar_url("https://www.songkick.com/live-stream-concerts"))
        self.assertFalse(is_aggregate_calendar_url("https://www.songkick.com/venues/4426128-lubber-fiend/calendar"))
        self.assertFalse(is_aggregate_calendar_url("https://www.boilershop.net/events/"))

if __name__=="__main__": unittest.main()
