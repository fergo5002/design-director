import sys, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import radar

RSS = """<?xml version="1.0"?><rss><channel><title>Feed</title>
<item><title>Site of the Day: Lumen</title><link>https://x/1</link></item>
<item><title>Older</title><link>https://x/0</link></item></channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Rel</title>
<entry><title>v4.2.0</title><link href="https://g/r/4.2.0"/></entry></feed>"""
GH = '[{"tag_name":"v1.9.0","html_url":"https://g/1.9"},{"tag_name":"v1.8.0"}]'

class Extract(unittest.TestCase):
    def test_rss(self):
        self.assertEqual(radar.latest("application/rss+xml", RSS), "Site of the Day: Lumen")
    def test_atom(self):
        self.assertEqual(radar.latest("application/atom+xml", ATOM), "v4.2.0")
    def test_github_releases_json(self):
        self.assertEqual(radar.latest("application/json", GH), "v1.9.0")
    def test_npm_json(self):
        self.assertEqual(radar.latest("application/json", '{"dist-tags":{"latest":"12.0.1"}}'), "12.0.1")
    def test_html_falls_back_to_hash(self):
        a = radar.latest("text/html", "<html><body>hello</body></html>")
        self.assertTrue(a.startswith("sha:"))

class Diff(unittest.TestCase):
    def test_changes_only_when_value_moves(self):
        old = {"motion": {"latest": "12.0.0"}, "gsap": {"latest": "3.13"}}
        new = {"motion": {"latest": "12.0.1"}, "gsap": {"latest": "3.13"}, "lenis": {"latest": "1.3"}}
        ch = radar.diff(old, new)
        self.assertEqual([c[0] for c in ch], ["lenis", "motion"])

class Candidates(unittest.TestCase):
    def test_filters_known_urls_and_non_design(self):
        known = {"https://github.com/figma/mcp-server"}
        items = [
            {"name": "figma-mcp", "url": "https://github.com/figma/mcp-server/", "description": "Figma MCP"},
            {"name": "penpot-mcp", "url": "https://github.com/penpot/penpot-mcp", "description": "Penpot design MCP server"},
            {"name": "db-mcp", "url": "https://github.com/a/db", "description": "Postgres MCP"},
        ]
        out = radar.candidates(items, known)
        self.assertEqual([c["name"] for c in out], ["penpot-mcp"])

if __name__ == "__main__":
    unittest.main()
