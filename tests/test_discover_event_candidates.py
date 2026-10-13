import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from discover_event_candidates import event_objects, date_part, likely_event_link, PageParser

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

if __name__=="__main__": unittest.main()
