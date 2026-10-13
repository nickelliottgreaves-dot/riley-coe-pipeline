import unittest
from scripts.collect_venue_pages import VisibleText

class VenuePageParserTests(unittest.TestCase):
    def test_visible_text_excludes_scripts_and_extracts_title(self):
        parser=VisibleText()
        parser.feed("<html><head><title>Official Gigs</title><script>fake event</script></head><body><h1>Upcoming shows</h1><p>Artist A</p></body></html>")
        self.assertEqual(" ".join(parser.title),"Official Gigs")
        visible=" ".join(parser.text)
        self.assertIn("Upcoming shows",visible)
        self.assertIn("Artist A",visible)
        self.assertNotIn("fake event",visible)

if __name__=="__main__": unittest.main()
