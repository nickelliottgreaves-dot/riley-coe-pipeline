import unittest
from datetime import date
from urllib.error import HTTPError
from unittest.mock import patch
from scripts.collect_mixcloud import inventory_item, parse_date, parse_title_date, fetch_cloudcasts

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


    def test_title_date_prefers_broadcast_date_over_later_upload_date(self):
        self.assertEqual(parse_title_date("Riley & Coe Tuesday 6th October 2026").isoformat(), "2026-10-06")
        self.assertEqual(parse_title_date("Riley & Coe - 12/10/2026 - BBC Mirror").isoformat(), "2026-10-12")
        self.assertIsNone(parse_title_date("Steve Lamacq Monday 5th October 2026"))

    @patch("scripts.collect_mixcloud.get_json")
    def test_uses_documented_search_when_account_cloudcasts_endpoint_is_404(self, get_json):
        get_json.side_effect = [
            HTTPError("https://api.mixcloud.com/SixMusicAlternative/cloudcasts/", 404, "Not Found", {}, None),
            {"data": [
                {"name": "Riley & Coe Tuesday 6th October 2026", "url": "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/", "created_time": "2026-10-14T00:00:00Z"},
                {"name": "Riley & Coe Tuesday 6th October 2026", "url": "https://www.mixcloud.com/OtherUser/riley-coe-copy/", "created_time": "2026-10-06T00:00:00Z"},
                {"name": "Steve Lamacq Monday 5th October 2026", "url": "https://www.mixcloud.com/SixMusicAlternative/steve-lamacq/", "created_time": "2026-10-05T00:00:00Z"}
            ], "paging": {}}
        ]
        items, errors = fetch_cloudcasts("SixMusicAlternative", date(2026, 10, 5), date(2026, 10, 10))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["episode_date"], "2026-10-06")
        self.assertTrue(items[0]["_search_fallback"])
        self.assertTrue(any("HTTP Error 404" in error for error in errors))
        ep, tracks = inventory_item(items[0])
        self.assertEqual(ep["episode_date"], "2026-10-06")
        self.assertEqual(ep["tracklist_status"], "unavailable")
        self.assertEqual(tracks, [])

    def test_date_parser(self):
        self.assertEqual(parse_date("2026-10-01T20:00:00Z").isoformat(), "2026-10-01")
        self.assertIsNone(parse_date("not-a-date"))

if __name__ == "__main__":
    unittest.main()
