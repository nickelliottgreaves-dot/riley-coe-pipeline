import csv, json, sys, tempfile, unittest
from urllib.error import HTTPError
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from discover_event_candidates import event_objects, date_part, likely_event_link, PageParser, main

class EventCandidateTests(unittest.TestCase):
    def test_extracts_schema_event_from_graph(self):
        data={"@graph":[{"@type":"MusicEvent","name":"Example gig","startDate":"2026-10-18T19:00:00+01:00","performer":{"@type":"MusicGroup","name":"Example Artist"}}]}
        events=list(event_objects(data))
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["name"],"Example gig")
        self.assertEqual(date_part(events[0]["startDate"]),"2026-10-18")

    def test_nested_event_not_duplicated_by_parser(self):
        data={"@type":"Event","name":"Outer","startDate":"2026-10-18","subEvent":{"@type":"Event","name":"Inner","startDate":"2026-10-19"}}
        self.assertEqual([e["name"] for e in event_objects(data)],["Outer","Inner"])

    def test_likely_calendar_link(self):
        self.assertTrue(likely_event_link("/whats-on/live-music","What's On"))
        self.assertFalse(likely_event_link("/about-us","About us"))

    def test_parser_captures_links_and_jsonld(self):
        p=PageParser()
        p.feed('<title>Venue</title><a href="/events/abc">Artist live</a><script type="application/ld+json">{"@type":"Event"}</script>')
        self.assertEqual(p.title,["Venue"])
        self.assertEqual(p.links,[("/events/abc","Artist live")])
        self.assertEqual(len(p.scripts),1)


    def test_partial_source_failures_keep_a_limited_result_and_exit_successfully(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html; charset=UTF-8"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n=-1): return b"<title>One usable calendar</title><a href='/events/act'>Act</a>"
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); sources=root/"sources.csv"; out=root/"out"
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url","source_status","notes"]); w.writeheader()
                w.writerow({"venue":"Usable Venue","source_url":"https://usable.example/events","source_status":"configured_official_calendar"})
                w.writerow({"venue":"Blocked Venue","source_url":"https://blocked.example/events","source_status":"configured_official_calendar"})
            error=HTTPError("https://blocked.example/events",403,"Forbidden",None,None)
            with patch("discover_event_candidates.urlopen",side_effect=[Response(),error]):
                with patch("sys.argv",["discover_event_candidates.py","--sources",str(sources),"--start","2026-10-15","--end","2026-10-28","--out-dir",str(out)]):
                    self.assertEqual(main(),0)
            summary=json.loads((out/"event_discovery_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sources_fetched"],1)
            self.assertEqual(summary["sources_failed"],1)
            self.assertEqual(summary["status"],"PARTIAL")

    def test_all_source_failures_return_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); sources=root/"sources.csv"; out=root/"out"
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url","source_status","notes"]); w.writeheader()
                w.writerow({"venue":"Blocked Venue","source_url":"https://blocked.example/events","source_status":"configured_official_calendar"})
            error=HTTPError("https://blocked.example/events",403,"Forbidden",None,None)
            with patch("discover_event_candidates.urlopen",side_effect=error):
                with patch("sys.argv",["discover_event_candidates.py","--sources",str(sources),"--start","2026-10-15","--end","2026-10-28","--out-dir",str(out)]):
                    self.assertEqual(main(),1)
            summary=json.loads((out/"event_discovery_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sources_fetched"],0)
            self.assertEqual(summary["sources_failed"],1)
            self.assertEqual(summary["status"],"FAILED")

    def test_shared_official_calendar_url_is_fetched_once(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html; charset=UTF-8"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b"<title>Shared Calendar</title><a href='/events/act'>Act</a>"
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); sources=root/"sources.csv"; out=root/"out"
            with sources.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["venue","source_url","source_status","notes"]); w.writeheader()
                w.writerow({"venue":"The Cluny","source_url":"https://thecluny.com/gigs/","source_status":"verified_official_calendar"})
                w.writerow({"venue":"Cluny 2","source_url":"https://thecluny.com/gigs/","source_status":"verified_official_calendar"})
            with patch("discover_event_candidates.urlopen",return_value=Response()) as mocked:
                with patch("sys.argv",["discover_event_candidates.py","--sources",str(sources),"--start","2026-10-15","--end","2026-10-28","--out-dir",str(out)]):
                    self.assertEqual(main(),0)
            self.assertEqual(mocked.call_count,1)
            with (out/"event_discovery_audit.csv").open(encoding="utf-8",newline="") as f:
                audit=list(csv.DictReader(f))
            self.assertEqual(len(audit),2)
            self.assertTrue(all(r["http_status"]=="200" for r in audit))
            self.assertTrue(all("Response reused" in r["notes"] or "Fetch success" in r["notes"] for r in audit))

if __name__=="__main__": unittest.main()
