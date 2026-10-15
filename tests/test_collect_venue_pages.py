import csv, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.collect_venue_pages import VisibleText, main

class VenuePageParserTests(unittest.TestCase):
    def test_visible_text_excludes_scripts_and_extracts_title(self):
        parser=VisibleText()
        parser.feed("<html><head><title>Official Gigs</title><script>fake event</script></head><body><h1>Upcoming shows</h1><p>Artist A</p></body></html>")
        self.assertEqual(" ".join(parser.title),"Official Gigs")
        visible=" ".join(parser.text)
        self.assertIn("Upcoming shows",visible)
        self.assertIn("Artist A",visible)
        self.assertNotIn("fake event",visible)


    def test_identical_official_source_url_is_fetched_once_for_shared_rooms(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html; charset=UTF-8"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b"<title>Shared Calendar</title><p>Upcoming gigs</p>"
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); sources=root/"sources.csv"; out=root/"out"
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url","source_status"]); w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/gigs/","source_status":"verified_official_calendar"})
                w.writerow({"venue":"Cluny 2","source_url":"https://thecluny.com/gigs/","source_status":"verified_official_calendar"})
            with patch("scripts.collect_venue_pages.urlopen",return_value=Response()) as mocked:
                with patch("sys.argv",["collect_venue_pages.py","--sources",str(sources),"--out-dir",str(out)]):
                    self.assertEqual(main(),0)
            self.assertEqual(mocked.call_count,1)
            with (out/"venue_page_access_audit.csv").open(encoding="utf-8",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r["text_file"] for r in rows))
            self.assertTrue(all(r["calendar_coverage_status"]=="not_checked" for r in rows))

if __name__=="__main__": unittest.main()
