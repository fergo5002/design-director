import sys, unittest, pathlib, tempfile, textwrap
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import sources

SAMPLE = textwrap.dedent('''
    # a comment
    [[source]]
    id = "mobbin"
    name = "Mobbin"
    url = "https://mobbin.com"
    kind = "site"
    category = "product-ui"
    best_for = "Shipped app screens, searchable by \\"pattern\\""
    cost = "freemium"
    agent_access = "mcp"
    signal = 5
    tags = ["flows", "mobile"]
    verified = "2026-11-01"
    evidence = "visited"

    [[source]]
    id = "fonts-in-use"
    name = "Fonts In Use"
    url = "https://fontsinuse.com"
    kind = "site"
    category = "typography-inspo"
    best_for = "Real-world type pairings, indexed by face"
    cost = "free"
    agent_access = "rss"
    signal = 5
    verified = "2026-11-01"
    evidence = "visited"
''')

class ParserTests(unittest.TestCase):
    def test_minimal_parser_matches_tomllib(self):
        mine = sources.parse_toml_subset(SAMPLE)
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib unavailable")
        self.assertEqual(mine, tomllib.loads(SAMPLE))

    def test_roundtrip_emit_then_parse(self):
        data = sources.parse_toml_subset(SAMPLE)["source"]
        again = sources.parse_toml_subset(sources.emit(data))["source"]
        self.assertEqual(data, again)

    def test_escapes_and_newlines_survive(self):
        e = [{"id": "x", "name": 'A "quoted"\nline \\ slash', "signal": 3, "tags": ["a", "b"]}]
        self.assertEqual(sources.parse_toml_subset(sources.emit(e))["source"], e)

class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.entries = sources.parse_toml_subset(SAMPLE)["source"]

    def test_valid_sample_has_no_errors(self):
        self.assertEqual(sources.validate(self.entries), [])

    def test_duplicate_id_and_bad_values_are_errors(self):
        bad = self.entries + [dict(self.entries[0])]
        bad[-1]["signal"] = 9
        bad[-1]["kind"] = "website"
        errs = "\n".join(sources.validate(bad))
        self.assertIn("duplicate id", errs)
        self.assertIn("signal", errs)
        self.assertIn("kind", errs)

    def test_missing_required_field(self):
        e = dict(self.entries[0]); del e["url"]
        self.assertTrue(any("url" in m for m in sources.validate([e])))

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.entries = sources.parse_toml_subset(SAMPLE)["source"]

    def test_query_ranks_relevant_first(self):
        hits = sources.search(self.entries, "type pairings")
        self.assertEqual(hits[0]["id"], "fonts-in-use")

    def test_filters(self):
        self.assertEqual([e["id"] for e in sources.search(self.entries, "", category="product-ui")], ["mobbin"])
        self.assertEqual(sources.search(self.entries, "", kind="mcp"), [])

    def test_shuffle_is_reproducible_and_spans_categories(self):
        a = sources.shuffle(self.entries, n=2, seed=7)
        b = sources.shuffle(self.entries, n=2, seed=7)
        self.assertEqual([e["id"] for e in a], [e["id"] for e in b])
        self.assertEqual(len({e["category"] for e in a}), 2)

class StaleTests(unittest.TestCase):
    def test_stale_flags_old_verification(self):
        entries = sources.parse_toml_subset(SAMPLE)["source"]
        entries[0]["verified"] = "2025-01-01"
        stale = sources.stale(entries, today="2026-11-01", days=180)
        self.assertEqual([e["id"] for e in stale], ["mobbin"])

class LoadTests(unittest.TestCase):
    def test_load_reads_every_toml_in_dir(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.toml").write_text(SAMPLE)
            self.assertEqual(len(sources.load(d)), 2)

if __name__ == "__main__":
    unittest.main()
