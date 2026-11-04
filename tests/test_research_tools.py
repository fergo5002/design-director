import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib, shutil, json
from unittest import mock
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import history


class History(unittest.TestCase):
    ROWS = [["20201128192146", "A", "200"], ["20210307053927", "B", "200"], ["20210616105916", "C", "200"],
            ["20250101000000", "D", "200"]]

    def test_summarises_by_year_with_archive_links(self):
        s = history.summarise("example.com", self.ROWS)
        self.assertEqual(s["versions"], 4)
        self.assertEqual([y["year"] for y in s["years"]], ["2020", "2021", "2025"])
        self.assertEqual(s["years"][1]["versions"], 2)
        self.assertEqual(s["years"][1]["archive"], "https://web.archive.org/web/20210307053927/https://example.com")

    def test_empty_archive_says_so(self):
        self.assertIn("no archived captures", history.render(history.summarise("x.example", [])))

    def test_network_failure_blames_the_instrument(self):
        err = io.StringIO()
        with mock.patch.object(history, "fetch", side_effect=OSError("timed out")), contextlib.redirect_stderr(err):
            self.assertEqual(history.main(["example.com"]), 2)
        self.assertIn("instrument", err.getvalue())

    def test_header_row_is_dropped(self):
        body = json.dumps([["timestamp", "digest", "statuscode"]] + self.ROWS).encode()
        resp = mock.MagicMock(); resp.read.return_value = body
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(len(history.fetch("example.com")), 4)


class Wrappers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = self.tmp.name
        import domains, ddr
        importlib.reload(domains)
        domains.SEEDS = pathlib.Path(self.tmp.name) / "no-seeds"
        self.domains, self.ddr = domains, ddr
        domains.create("stays", "Stays", "sector", keywords=["cottage", "guesthouse", "b&b"])

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        self.tmp.cleanup()

    def test_teardown_into_a_domain_writes_to_its_shots_folder(self):
        with mock.patch.object(self.ddr, "_which", return_value=True), \
             mock.patch.object(self.ddr.subprocess, "call", return_value=0) as call, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            rc = self.ddr.teardown(["https://www.example.com/stay/", "--into", "stays", "--frames", "3"])
        self.assertEqual(rc, 0)
        argv = call.call_args[0][0]
        self.assertIn("--out", argv)
        self.assertEqual(argv[argv.index("--out") + 1], str(pathlib.Path(self.tmp.name) / "domains" / "stays" / "shots"))
        self.assertNotIn("--into", argv)
        self.assertIn("--shots shots/example.com-stay", out.getvalue())
        self.assertNotIn("--url 3", out.getvalue(), "option values must not be mistaken for urls")

    def test_teardown_into_unknown_domain_refuses(self):
        with mock.patch.object(self.ddr, "_which", return_value=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.ddr.teardown(["https://x.example", "--into", "nope"]), 2)

    def test_sheet_for_a_domain_finds_exemplar_shots_best_first(self):
        base = pathlib.Path(self.tmp.name) / "domains" / "stays" / "shots"
        for host in ("good.example", "best.example"):
            (base / host).mkdir(parents=True)
            (base / host / "desktop__fold.png").write_bytes(b"png")
        self.domains.add_ref("stays", name="Good", url="https://good.example", verdict="exemplar", angle="direct",
                             evidence="screenshot", take="t", score=3)
        self.domains.add_ref("stays", name="Best", url="https://best.example", verdict="exemplar", angle="direct",
                             evidence="screenshot", take="t", score=5, shots="shots/best.example")
        self.domains.add_ref("stays", name="NoShots", url="https://none.example", verdict="exemplar", angle="direct",
                             evidence="visited", take="t", score=4)
        mine = pathlib.Path(self.tmp.name) / "mine.png"; mine.write_bytes(b"png")
        with mock.patch.object(self.ddr, "_which", return_value=True), \
             mock.patch.object(self.ddr.subprocess, "call", return_value=0) as call:
            rc = self.ddr.sheet(["--domain", "stays", "--with", str(mine)])
        self.assertEqual(rc, 0)
        argv = call.call_args[0][0]
        pngs = [a for a in argv if a.endswith(".png") and "sheet-" not in a]
        self.assertEqual(pngs[0], str(mine))
        self.assertTrue(pngs[1].endswith("best.example/desktop__fold.png"))
        self.assertTrue(pngs[2].endswith("good.example/desktop__fold.png"))
        self.assertEqual(argv[argv.index("--labels") + 1], "Yours,Best,Good")

    def test_mcp_research_filter(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.ddr.mcp(["--research"])
        text = out.getvalue()
        self.assertIn("Exa", text)
        self.assertIn("Playwright", text)
        self.assertNotIn("Canva", text)


@unittest.skipUnless(shutil.which("node") and (pathlib.Path(__file__).resolve().parents[1] / "node_modules" / "playwright").exists(),
                     "needs node and npm install")
class TeardownLive(unittest.TestCase):
    """Proves the instrument on a page with known values before it is trusted on real sites."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        cls.out = tempfile.mkdtemp()
        fixture = pathlib.Path(__file__).resolve().parent / "fixtures" / "teardown.html"
        cls.proc = subprocess.run(["node", str(TOOLS / "teardown.mjs"), fixture.as_uri(), "--out", cls.out,
                                   "--frames", "2", "--walk", "See prices>Submit booking"],
                                  capture_output=True, text=True, timeout=180)
        folder = next(pathlib.Path(cls.out).iterdir())
        cls.rec = json.loads((folder / "teardown.json").read_text())
        cls.d = cls.rec["viewports"]["desktop"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_type_roles(self):
        h1 = self.d["type"]["roles"]["h1"]
        self.assertEqual(h1["family"], "Georgia")
        self.assertEqual(h1["size"], "64px")
        self.assertEqual(self.d["type"]["families"][0]["value"], "Georgia")

    def test_palette_by_area_and_controls(self):
        self.assertEqual(self.d["colour"]["backgrounds"][0]["value"], "#f6f1e8")
        self.assertEqual(self.d["colour"]["accents"][0]["value"], "#1f4d3a")

    def test_structure_and_stack(self):
        self.assertIn("Check availability", " ".join(self.d["structure"]["ctas"]))
        self.assertTrue(self.d["structure"]["phoneInHeader"])
        self.assertIn("generator: FixtureBuilder 1.0", self.d["stack"])

    def test_slop_signals(self):
        s = self.d["slop"]
        self.assertIn("seamless", s["words"])
        self.assertEqual(s["eyebrows"], 1)
        self.assertGreaterEqual(s["gradientText"], 1)
        self.assertEqual(s["iconCardTriads"], 1)

    def test_walk_clicks_safe_controls_and_refuses_submit(self):
        walk = self.rec["walk"]
        self.assertTrue(walk[0]["ok"], walk)
        self.assertIn("refused", walk[1]["note"])

    def test_frames_and_folds_saved(self):
        names = {pathlib.Path(f).name for f in self.rec["files"]}
        self.assertTrue({"desktop__fold.png", "phone__fold.png", "desktop__full.png"} <= names)
        self.assertTrue(any(n.startswith("desktop__frame-") for n in names))
        for f in self.rec["files"]:
            self.assertTrue(pathlib.Path(f).stat().st_size > 1000, f)


if __name__ == "__main__":
    unittest.main()
