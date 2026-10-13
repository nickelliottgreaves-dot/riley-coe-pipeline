import unittest
from datetime import date
from unittest.mock import patch
from io import BytesIO
from scripts.collect_mixcloud import inventory_item, parse_date, parse_mixcloud_title_date, fetch_cloudcasts, fetch_cloudcasts_html, fetch_show_page_tracks, fetch_cloudcasts_search

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

    def test_public_search_fallback_filters_account_and_date(self):
        payload = {"data": [
            {"name": "Riley & Coe Tuesday 6th October 2026", "url": "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/", "created_time": "2026-10-06T20:00:00Z"},
            {"name": "Other account", "url": "https://www.mixcloud.com/anotheruser/other-show/", "created_time": "2026-10-07T20:00:00Z"}
        ], "paging": {}}
        with patch("scripts.collect_mixcloud.get_json", return_value=payload):
            items, errors = fetch_cloudcasts_search("sixmusicalternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertIn("SixMusicAlternative", items[0]["url"])
        self.assertEqual(errors, [])

    def test_html_fallback_discovers_dated_profile_links(self):
        html = b'<a href="/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/">Play</a>'
        response = type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
            "read": lambda self, n: html})()
        with patch("scripts.collect_mixcloud.urlopen", return_value=response):
            items, errors = fetch_cloudcasts_html("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["_html_fallback"])
        self.assertEqual(items[0]["created_time"], "2026-10-06")
        self.assertEqual(errors, [])

    def test_html_fallback_tries_uploads_page_after_empty_profile(self):
        html_empty = b'<html><body><a href="/help/">Help</a></body></html>'
        html_uploads = b'<a href="/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/">Play</a>'
        def response(html, url):
            return type("Response", (), {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
                "read": lambda self, n: html,
                "geturl": lambda self: url
            })()
        with patch("scripts.collect_mixcloud.urlopen", side_effect=[
            response(html_empty, "https://www.mixcloud.com/SixMusicAlternative/"),
            response(html_uploads, "https://www.mixcloud.com/SixMusicAlternative/uploads/"),
            response(b'<a href="/help/">Help</a>', "https://www.mixcloud.com/search/?q=Riley%20%26%20Coe"),
            response(b'<a href="/help/">Help</a>', "https://html.duckduckgo.com/html/?q=Riley"),
            response(b'<a href="/help/">Help</a>', "https://www.google.com/search?q=Riley")
        ]):
            items, errors = fetch_cloudcasts_html("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["created_time"], "2026-10-06")
        self.assertEqual(errors, [])

    def test_html_fallback_discovers_shows_from_search_page(self):
        html = b'<a href="/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/">Riley &amp; Coe Tuesday 6th October 2026</a>'
        response = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self, n: html,
            "geturl": lambda self: "https://www.mixcloud.com/search/?q=Riley%20%26%20Coe"
        })()
        with patch("scripts.collect_mixcloud.urlopen", side_effect=[
            type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
                "read": lambda self, n: b'<a href="/help/">Help</a>', "geturl": lambda self: "https://www.mixcloud.com/SixMusicAlternative/"})(),
            type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
                "read": lambda self, n: b'<a href="/help/">Help</a>', "geturl": lambda self: "https://www.mixcloud.com/SixMusicAlternative/uploads/"})(),
            response,
            type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
                "read": lambda self, n: b'<a href="/help/">Help</a>', "geturl": lambda self: "https://html.duckduckgo.com/html/?q=Riley"})(),
            type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
                "read": lambda self, n: b'<a href="/help/">Help</a>', "geturl": lambda self: "https://www.google.com/search?q=Riley"})()
        ]):
            items, errors = fetch_cloudcasts_html("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertIn("6th-october-2026", items[0]["url"])
        self.assertEqual(errors, [])


    def test_html_fallback_unwraps_search_engine_result_links(self):
        def response(html, url):
            return type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
                "read": lambda self, n: html, "geturl": lambda self: url})()
        result = b'<a href="/l/?uddg=https%3A%2F%2Fwww.mixcloud.com%2FSixMusicAlternative%2Friley-coe-tuesday-6th-october-2026%2F">Riley &amp; Coe Tuesday 6th October 2026</a>'
        with patch("scripts.collect_mixcloud.urlopen", side_effect=[
            response(b'<a href="/help/">Help</a>', "https://www.mixcloud.com/SixMusicAlternative/"),
            response(b'<a href="/help/">Help</a>', "https://www.mixcloud.com/SixMusicAlternative/uploads/"),
            response(b'<a href="/help/">Help</a>', "https://www.mixcloud.com/"),
            response(result, "https://html.duckduckgo.com/html/?q=Riley"),
            response(b'<a href="/help/">Help</a>', "https://www.google.com/search?q=Riley")
        ]):
            items, errors = fetch_cloudcasts_html("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertIn("6th-october-2026", items[0]["url"])
        self.assertEqual(errors, [])

    def test_show_page_parser_reads_numbered_creator_comment_tracklist(self):
        html = b'<div>Comments</div><div>The 6 Music Archive</div><div>Creator</div><div>Button: 00:00</div><div>1.</div><div>Threadbare</div><div>Lande Hekt</div><div>2.</div><div>New York No Wave</div><div>Ill Ease</div><div>Reply</div>'
        response = type("Response", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None,
            "read": lambda self, n: html})()
        item = {"name": "Riley & Coe Wednesday 30th September 2026",
            "url": "https://www.mixcloud.com/SixMusicAlternative/riley-coe-wednesday-30th-september-2026/",
            "created_time": "2026-09-30"}
        with patch("scripts.collect_mixcloud.urlopen", return_value=response):
            episode, tracks = fetch_show_page_tracks(item)
        self.assertEqual([(x["track_title"], x["artist"]) for x in tracks],
            [("Threadbare", "Lande Hekt"), ("New York No Wave", "Ill Ease")])
        self.assertEqual(episode["tracklist_status"], "incomplete")

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

    def test_api_falls_back_to_lowercase_account_key_after_404(self):
        from urllib.error import HTTPError
        payload = {"data": [
            {"name": "Riley & Coe Tuesday 6th October 2026",
             "url": "https://www.mixcloud.com/SixMusicAlternative/riley-coe-tuesday-6th-october-2026/",
             "created_time": "2026-10-06T20:00:00Z", "sections": [{"artist": "British Birds", "song": "Stuck In A Room"}]}
        ], "paging": {}}
        with patch("scripts.collect_mixcloud.get_json", side_effect=[
            HTTPError("https://api.mixcloud.com/SixMusicAlternative/cloudcasts/", 404, "Not Found", {}, None),
            payload
        ]) as mock_get:
            items, errors = fetch_cloudcasts("SixMusicAlternative", date(2026, 10, 6), date(2026, 10, 13))
        self.assertEqual(len(items), 1)
        self.assertIn("/sixmusicalternative/cloudcasts/", mock_get.call_args_list[1].args[0])
        self.assertEqual(errors, [])

    def test_date_parser(self):
        self.assertEqual(parse_date("2026-10-01T20:00:00Z").isoformat(), "2026-10-01")
        self.assertIsNone(parse_date("not-a-date"))

if __name__ == "__main__":
    unittest.main()
