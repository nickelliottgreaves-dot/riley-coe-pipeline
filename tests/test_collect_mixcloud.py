import unittest
from scripts.collect_mixcloud import inventory_item, parse_date

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

    def test_date_parser(self):
        self.assertEqual(parse_date("2026-10-01T20:00:00Z").isoformat(), "2026-10-01")
        self.assertIsNone(parse_date("not-a-date"))

if __name__ == "__main__":
    unittest.main()
