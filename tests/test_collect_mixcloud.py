import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from scripts.collect_mixcloud import episode_date_from_text, inventory_item, parse_date, resolve_cloudcasts_endpoint

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

    def test_cloudcasts_endpoint_uses_api_metadata_connection(self):
        profile = {"metadata": {"connections": {
            "cloudcasts": "https://api.mixcloud.com/canonical-user/cloudcasts/"
        }}}
        with patch("scripts.collect_mixcloud.get_json", return_value=profile) as get_json:
            endpoint = resolve_cloudcasts_endpoint("Canonical-User")
        self.assertEqual(endpoint, "https://api.mixcloud.com/canonical-user/cloudcasts/")
        get_json.assert_called_once_with("https://api.mixcloud.com/Canonical-User/?metadata=1")

    def test_cloudcasts_endpoint_uses_user_search_when_profile_key_is_unresolved(self):
        def fake_get_json(url):
            if "/search/?" in url:
                return {"data": [{
                    "key": "/SixMusicAlternative/",
                    "name": "The 6 Music Archive",
                    "url": "https://www.mixcloud.com/SixMusicAlternative/"
                }]}
            raise HTTPError(url, 404, "Not Found", None, None)

        with patch("scripts.collect_mixcloud.get_json", side_effect=fake_get_json):
            endpoint = resolve_cloudcasts_endpoint("SixMusicAlternative")
        self.assertEqual(endpoint, "https://api.mixcloud.com/SixMusicAlternative/cloudcasts/")

    def test_episode_date_from_mixcloud_title_or_slug(self):
        self.assertEqual(episode_date_from_text("riley-coe-tuesday-6th-october-2026").isoformat(), "2026-10-06")
        self.assertEqual(episode_date_from_text("Riley & Coe Monday 5th October 2026").isoformat(), "2026-10-05")
        self.assertEqual(episode_date_from_text("riley-coe-2026-10-06").isoformat(), "2026-10-06")
        self.assertEqual(episode_date_from_text("Riley & Coe October 6, 2026").isoformat(), "2026-10-06")
        self.assertIsNone(episode_date_from_text("Riley & Coe - no date"))

    def test_date_parser(self):
        self.assertEqual(parse_date("2026-10-01T20:00:00Z").isoformat(), "2026-10-01")
        self.assertIsNone(parse_date("not-a-date"))

if __name__ == "__main__":
    unittest.main()
