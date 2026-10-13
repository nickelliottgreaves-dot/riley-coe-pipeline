import unittest
from datetime import date
from unittest.mock import patch
from io import BytesIO
from scripts.collect_mixcloud import inventory_item, parse_date, parse_mixcloud_title_date, fetch_cloudcasts_html, fetch_show_page_tracks

class MixcloudInventoryTests(unittest.TestCase):
    def test_no_sections_is_unavailable_not_complete(self):
        ep, tracks = inventory_item({"name":"Riley & Coe example","url":"https://www.mixcloud.com/SixMusicAlternative/example/","created_time":"2026-10-01T20:00:00Z"})
        self.assertEqual(ep["tracklist_status"], "unavailable")
        self.assertEqual(tracks, [])

    def test_sections_are_candidates_not_proof_of_completeness(self):
        ep, tracks = inventory_item({"name":"Riley & Coe example","url":"https://www.mixcloud.com/SixMusicAlternative/example/","created_time":"2026-10-01T20:00:00Z","sections":[{"artist":"A Certain Ratio","song":"Example track"},{"chapter":"Interview"},{"artist":"Robyn Hitchcock","song":"Another track"}]})
        self.assertEqual(ep["tracklist_status"], "incomplete")
        self.assertEqual(ep["tracks_extracted"], "2")
        self.assertEqual([x["artist"] for x in tracks], ["A Certain Ratio","Robyn Hitchcock"])
        self.assertTrue(all(x["verification_status"] == "needs_visible_page_verification" for x in tracks))

    def test_parse_mixcloud_title_date_with_ordinal(self):
        self.assertEqual(parse_mixcloud_title_date("Riley & Coe Tuesday 6th October 2026"), date(2026, 10, 6))
        self.assertIsNone(parse_mixcloud_title_date("Riley & Coe no date"))

    def test_html_fallback_discovers_dated_profile_links(self):
        html = b'<a href="/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/">Riley &amp; Coe Tuesday 6th October 2026</a>'
        response = type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
            "read": lambda self, n: html})()
        with patch("scripts.collect_mixcloud.urlopen", return_value=response):
            items, errors = fetch_cloudcasts_html("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["_html_fallback"])
        self.assertEqual(items[0]["created_time"], "2026-10-06")
        self.assertEqual(errors, [])

    def test_html_show_page_extracts_visible_track_rows_as_unverified(self):
        html = b'<h2>Tracklist</h2><div>1.</div><div>Song One</div><div>Artist One</div><div>2.</div><div>Song Two</div><div>Artist Two</div><div>Show more</div>'
        response = type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
            "read": lambda self, n: html})()
        item = {"name": "Riley & Coe Tuesday 6th October 2026", "url": "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/", "created_time": "2026-10-06"}
        with patch("scripts.collect_mixcloud.urlopen", return_value=response):
            episode, tracks = fetch_show_page_tracks(item)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["artist"], "Artist One")
        self.assertEqual(episode["tracklist_status"], "incomplete")
        self.assertTrue(all(t["verification_status"] == "needs_complete_visible_page_verification" for t in tracks))

    def test_date_parser(self):
        self.assertEqual(parse_date("2026-10-01T20:00:00Z").isoformat(), "2026-10-01")
        self.assertIsNone(parse_date("not-a-date"))

if __name__ == "__main__":
    unittest.main()
