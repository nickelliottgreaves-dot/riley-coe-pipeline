import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from collect_bbc_sounds import episode_id,find_episodes,parse_date,TextParser

class BBCCollectorTests(unittest.TestCase):
    def test_episode_id(self):
        self.assertEqual(episode_id("https://www.bbc.co.uk/programmes/m0031tk4"),"m0031tk4")
        self.assertEqual(episode_id("https://www.bbc.co.uk/sounds/play/m0031tk4"),"m0031tk4")
    def test_finds_episode_links(self):
        html='<a href="/programmes/m0031tk4">Gideon reigns supreme</a><a href="/about">About</a>'
        self.assertEqual(find_episodes(html,"https://www.bbc.co.uk/programmes/m001mf2c/episodes")[0]["title"],"Gideon reigns supreme")
    def test_parse_date(self):
        self.assertEqual(parse_date("Radio 6 Music 01 Oct 2026 120 mins"),"2026-10-01")
    def test_text_parser_skips_scripts(self):
        p=TextParser();p.feed('<p>Tracklist</p><script>secret text</script><a href="/programmes/m0031tk4">Episode</a>')
        self.assertIn("Tracklist",p.text);self.assertNotIn("secret text",p.text)
        self.assertEqual(len(p.links),1)
if __name__=="__main__":unittest.main()
