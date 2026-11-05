"""Regression tests for the code review of the v2 branch (2026-11-05), one per finding."""
import sys, os, unittest, pathlib, tempfile, importlib, json, concurrent.futures
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = str(self.root / "home")
        import domains, brandpack, notes, taste
        for m in (domains, brandpack, notes, taste):
            importlib.reload(m)
        domains.SEEDS = self.root / "seeds"
        domains.SEEDS.mkdir()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        self.tmp.cleanup()


class AssetsAreHashed(Home):
    """Finding 1: images, fonts and video are inputs the receipt covers."""
    def test_assets_under_src_are_hashed(self):
        import gate
        src = self.root.resolve() / "proj" / "src"
        src.mkdir(parents=True)
        for name in ("hero.jpg", "mark.png", "face.woff2", "loop.mp4", "app.css"):
            (src / name).write_bytes(b"x")
        got = gate.hash_inputs(self.root.resolve() / "proj", src=[str(src)])
        for name in ("hero.jpg", "mark.png", "face.woff2", "loop.mp4", "app.css"):
            self.assertIn(f"src/{name}", got)


class MultiLineCopy(Home):
    """Finding 3: copy rules see text nodes that span lines."""
    def test_text_on_its_own_line_is_checked(self):
        import brandpack
        d = self.root / "home" / "brands" / "acme"
        d.mkdir(parents=True)
        (d / "brand.toml").write_text('slug = "acme"\nname = "Acme"\nstatus = "active"\ntheme = "light-only"\n')
        (d / "tokens.json").write_text(json.dumps({"colors": {"allowed": {}}, "fonts": {},
                                                   "copy": {"banned_phrases": ["seamless"], "banned_chars": ["\u2014"]}}))
        page = self.root / "page.html"
        page.write_text("<p>\n  A seamless way to book \u2014 today.\n</p>\n<script>\nconst s = 'seamless';\n</script>\n")
        rep = brandpack.lint([str(page)], "acme")
        rules = sorted(f["rule"] for f in rep["findings"])
        self.assertEqual(rules, ["copy.banned-char", "copy.banned-phrase"])
        self.assertEqual({f["line"] for f in rep["findings"]}, {2})


class LookPicks(Home):
    """Finding 5: two picks with different reasons are two notes."""
    def test_opposite_picks_do_not_merge(self):
        import domains, looks, notes
        domains.create("fintech", "Fintech", "sector")
        looks.pick("b", "the rate table reads calm", others=["a", "c"], domain="fintech", project="p1")
        looks.pick("c", "the rate table reads loud", others=["a", "b"], domain="fintech", project="p2")
        texts = [n["text"] for n in notes.all_notes("fintech")]
        self.assertEqual(len(texts), 2, texts)


class Contradictions(Home):
    """Finding 6: a note that contradicts another is not counted as a sighting of it."""
    def test_negation_does_not_merge(self):
        import notes
        notes.add("house", "Do use serif headings on the hero", ["job 1"], "j1")
        n, merged = notes.add("house", "Do not use serif headings on the hero", ["job 2"], "j2")
        self.assertFalse(merged)
        self.assertEqual(len(notes.all_notes("house")), 2)

    def test_same_meaning_still_merges(self):
        import notes
        notes.add("house", "Fergus asked for more air around the rate table", ["round 1"], "j1")
        n, merged = notes.add("house", "Fergus asked for more air around the rate table again", ["round 2"], "j2")
        self.assertTrue(merged)


class WindowsChecks(unittest.TestCase):
    """Finding 7: a Windows path in a claim check keeps its backslashes."""
    def test_windows_split_keeps_backslashes(self):
        import claims
        self.assertEqual(claims._split(r"python C:\Brain\check.py C1", windows=True),
                         ["python", r"C:\Brain\check.py", "C1"])
        self.assertEqual(claims._split(r'python "C:\My Brain\check.py" C1', windows=True),
                         ["python", r"C:\My Brain\check.py", "C1"])
        self.assertEqual(claims._split("python3 check.py 'C 1'", windows=False), ["python3", "check.py", "C 1"])


class Waivers(unittest.TestCase):
    """Finding 10: a waiver names who waived it and why, as two things."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = pathlib.Path(self.tmp.name)
        (self.p / ".design" / "brief").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, req):
        base = {"id": "R1", "kind": "change", "text": "x", "source": "Fergus 2026-11-05", "status": "waived",
                "superseded_by": None, "exact": None}
        base.update(req)
        (self.p / ".design" / "brief" / "contract.json").write_text(json.dumps(
            {"version": 1, "job": "new", "brief": "b", "created": "2026-11-05", "requirements": [base]}))

    def rules(self):
        import contract
        return {f["rule"] for f in contract.check(self.p, "final")["findings"]}

    def test_the_word_by_inside_a_reason_is_not_a_name(self):
        self.write({"evidence": "replaced by the new hero section"})
        self.assertIn("contract.waiver-unnamed", self.rules())

    def test_a_name_without_a_reason_is_thin(self):
        self.write({"evidence": "waived by Fergus", "waived_by": "Fergus"})
        self.assertIn("contract.thin-evidence", self.rules())

    def test_name_and_reason_pass(self):
        self.write({"evidence": "keep the old size on the phone", "waived_by": "Fergus"})
        self.assertEqual(self.rules(), set())


class EvalRunSurvivesACrash(Home):
    """Finding 9: one run that raises becomes an error row; the run still finishes."""
    def test_a_raising_case_is_recorded(self):
        import evals
        def boom(*a, **k):
            raise OSError("fixture copy failed")
        with mock.patch.object(evals, "run_one", boom):
            row = evals._safe_run_one(({"id": "c1"}, "after", "/x"), (self.root, "claude", None, True))
        self.assertEqual((row["case"], row["arm"], row["status"]), ("c1", "after", "error"))
        self.assertIn("fixture copy failed", row["reason"])


if __name__ == "__main__":
    unittest.main()
