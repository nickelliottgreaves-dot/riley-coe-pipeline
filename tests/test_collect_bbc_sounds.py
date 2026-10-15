import sys,unittest, json, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from collect_bbc_sounds import episode_id,find_episodes,parse_date,TextParser,extract_tracklist_candidates,main

class BBCCollectorTests(unittest.TestCase):
    def test_sequential_page_fallback_finds_more_bbc_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing = "https://www.bbc.co.uk/programmes/m001mf2c/episodes"
            def fake_fetch(url):
                if url == listing:
                    return 200, "text/html", '<a href="/programmes/m0031tk4">Episode One</a>'
                if url == listing + "?page=2":
                    return 200, "text/html", '<a href="/programmes/m0031tk5">Episode Two</a>'
                if url == listing + "?page=3":
                    return 200, "text/html", '<p>No more episodes</p>'
                if url.endswith("m0031tk4"):
                    return 200, "text/html", '<p>24 Sep 2026</p><h2>Tracklist</h2><p>Song One - Artist One</p>'
                if url.endswith("m0031tk5"):
                    return 200, "text/html", '<p>25 Sep 2026</p><h2>Tracklist</h2><p>Song Two - Artist Two</p>'
                raise AssertionError("Unexpected URL: " + url)
            with patch("collect_bbc_sounds.fetch", side_effect=fake_fetch), \
                 patch("collect_bbc_sounds.time.sleep"), \
                 patch("sys.argv", ["collect_bbc_sounds.py", "--start", "2026-09-24", "--end", "2026-10-15", "--out-dir", tmp]):
                self.assertEqual(main(), 0)
            summary=json.loads((Path(tmp)/"bbc_collection_audit.json").read_text())
            self.assertEqual(summary["listing_pages_fetched"], 3)
            self.assertEqual(summary["episodes_discovered"], 2)
            self.assertEqual(summary["listing_pagination_status"], "sequential_page_fallback_exhausted")

    def test_episode_id(self):
        self.assertEqual(episode_id("https://www.bbc.co.uk/programmes/m0031tk4"),"m0031tk4")
        self.assertEqual(episode_id("https://www.bbc.co.uk/sounds/play/m0031tk4"),"m0031tk4")
    def test_finds_episode_links(self):
        html='<a href="/programmes/m0031tk4">Gideon reigns supreme</a><a href="/about">About</a>'
        self.assertEqual(find_episodes(html,"https://www.bbc.co.uk/programmes/m001mf2c/episodes")[0]["title"],"Gideon reigns supreme")
    def test_parse_date(self):
        self.assertEqual(parse_date("Radio 6 Music 01 Oct 2026 120 mins"),"2026-10-01")
    def test_extracts_review_only_visible_text_candidates(self):
        p=TextParser()
        p.feed("<h2>Tracklist</h2><p>Artist One - Song One</p><p>Song Two by Artist Two</p>")
        candidates=extract_tracklist_candidates(p,"Tracklist\nArtist One - Song One\nSong Two by Artist Two","https://www.bbc.co.uk/programmes/m0031tk4","Test episode","2026-10-01")
        self.assertEqual(len(candidates),2)
        self.assertEqual(candidates[0]["artist_candidate"],"Artist One")
        self.assertEqual(candidates[0]["track_title"],"Song One")
        self.assertTrue(all(row["review_status"]=="needs_manual_review" for row in candidates))
    def test_extracts_explicitly_labelled_track_artist_pairs(self):
        p=TextParser()
        line_one="Track: Song One | Artist: Artist One"
        line_two="Artist: Artist Two; Title: Song Two"
        p.feed("<h2>Tracklist</h2><p>"+line_one+"</p><p>"+line_two+"</p>")
        candidates=extract_tracklist_candidates(p,"Tracklist\n"+line_one+"\n"+line_two,
            "https://www.bbc.co.uk/programmes/m0031tk4","Test episode","2026-10-01")
        self.assertEqual(len(candidates),2)
        by_artist={row["artist_candidate"]:row for row in candidates}
        self.assertEqual(by_artist["Artist One"]["track_title"],"Song One")
        self.assertEqual(by_artist["Artist Two"]["track_title"],"Song Two")
        self.assertTrue(all(row["review_status"]=="needs_manual_review" for row in candidates))

    def test_extracts_visible_bbc_tracklist_rows_with_repeated_title_nodes(self):
        p=TextParser()
        text="Tracklist\nTrack\nArtist\n1.\nFree Way\nFree Way\nLafayette And The Lasabres\n2.\nThe Swim Thing\nThe Swim Thing\nDave Lewis\nShow more"
        candidates=extract_tracklist_candidates(p,text,"https://www.bbc.co.uk/sounds/play/m0032d2m","Test episode","2026-10-12")
        self.assertEqual(len(candidates),2)
        self.assertEqual(candidates[0]["track_title"],"Free Way")
        self.assertEqual(candidates[0]["artist_candidate"],"Lafayette And The Lasabres")
        self.assertEqual(candidates[1]["track_title"],"The Swim Thing")
        self.assertEqual(candidates[1]["artist_candidate"],"Dave Lewis")
        self.assertTrue(all(row["review_status"]=="needs_manual_review" for row in candidates))

    def test_extracts_jsonld_recording_candidates(self):
        p=TextParser()
        p.feed('<script type="application/ld+json">{"@type":"MusicRecording","name":"Track Name","byArtist":{"@type":"MusicGroup","name":"Artist Name"}}</script>')
        candidates=extract_tracklist_candidates(p,"","https://www.bbc.co.uk/programmes/m0031tk4","Test episode","")
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]["artist_candidate"],"Artist Name")
        self.assertEqual(candidates[0]["extraction_method"],"jsonld_music_recording")
        self.assertEqual(candidates[0]["review_status"],"needs_manual_review")
    def test_text_parser_skips_scripts(self):
        p=TextParser();p.feed('<p>Tracklist</p><script>secret text</script><a href="/programmes/m0031tk4">Episode</a>')
        self.assertIn("Tracklist",p.text);self.assertNotIn("secret text",p.text)
        self.assertEqual(len(p.links),1)
if __name__=="__main__":unittest.main()
