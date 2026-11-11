"""shots.mjs, sheet.mjs and crop.mjs against real pages in a real Chromium.

Skipped cleanly when Node, `npm install` or a Playwright Chromium is missing (as in CI).
"""
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def _ready():
    if not shutil.which("node") or not (ROOT / "node_modules" / "playwright").exists():
        return False
    try:
        out = subprocess.run(["node", "-e", "import('playwright').then(p=>console.log("
                              "require('fs').existsSync(p.chromium.executablePath())?'yes':'no'))"],
                             cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip() == "yes"


READY = _ready()


def node(*args, timeout=300):
    return subprocess.run(["node", *map(str, args)], cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class Shots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name) / "shots"
        cls.json = pathlib.Path(cls.tmp.name) / "render.json"
        cls.proc = node(ROOT / "tools" / "shots.mjs", "--file", FIX / "shots" / "measure.html", "--out", cls.out,
                        "--flat", "--json-out", cls.json, "--viewports", "desktop-1440x900,phone-390x844", "--no-axe")
        cls.rep = json.loads(cls.json.read_text()) if cls.json.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def row(self, vp, motion="no-preference"):
        return next(r for r in self.rep["results"] if r["viewport"] == vp and r["motion"] == motion)

    def test_json_shape(self):
        self.assertIsNotNone(self.rep, self.proc.stderr + self.proc.stdout)
        for k in ("ok", "exit", "tool", "findings", "summary", "results"):
            self.assertIn(k, self.rep)
        self.assertEqual(self.rep["tool"], "shots")
        self.assertEqual(self.rep["exit"], self.proc.returncode)
        self.assertIn(self.rep["exit"], (0, 1))

    def test_flat_out_holds_the_folds(self):
        names = {p.name for p in self.out.glob("*.png")}
        self.assertIn("measure__phone-390x844__motion__fold.png", names)
        self.assertIn("measure__desktop-1440x900__reduced__fold.png", names)
        self.assertTrue((self.out / "report.json").exists())

    def test_text_dump_after_css_transform(self):
        text = self.row("desktop-1440x900")["text"]
        self.assertIn("MEASURED HEADING", text)
        self.assertNotIn("Hidden", text)

    def test_smallest_text_ignores_visually_hidden(self):
        self.assertEqual(self.row("phone-390x844")["smallestTextPx"], 10)

    def test_distinct_font_sizes(self):
        self.assertEqual(sorted(self.row("phone-390x844")["fontSizes"]), [10, 16, 40])

    def test_consecutive_text_only_sections(self):
        self.assertEqual(self.row("desktop-1440x900")["maxConsecutiveTextOnly"], 3)

    def test_words_and_screens(self):
        r = self.row("desktop-1440x900")
        self.assertGreater(r["words"], 250)
        self.assertGreater(r["screens"], 0)

    def test_font_paint_check_catches_undeclared_and_unloaded_faces(self):
        fb = self.row("desktop-1440x900")["fontsFallingBack"]
        self.assertIn("Nowhere Sans Zzz", fb)
        self.assertIn("Ghost Face", fb)
        self.assertTrue(any(f["rule"] == "render.font-fallback" for f in self.rep["findings"]))

    def test_tap_targets_under_44_warn_on_touch_viewports_only(self):
        phone = self.row("phone-390x844")
        self.assertEqual(phone["tapTargetsUnder24px"], [])
        self.assertTrue(any('"Go" 32x32' in t for t in phone["tapTargetsUnder44px"]), phone["tapTargetsUnder44px"])
        t44 = [f for f in self.rep["findings"] if f["rule"] == "render.tap-target-44"]
        self.assertTrue(t44)
        self.assertTrue(all(f["severity"] == "warn" for f in t44))
        self.assertTrue(all("phone-390x844" in f["message"] for f in t44))
        self.assertFalse(any(f["rule"] == "render.tap-target" for f in self.rep["findings"]))

    def test_painted_report_names_platform_fonts(self):
        painted = self.row("desktop-1440x900")["fontsPainted"]
        self.assertIn("Nowhere Sans Zzz", painted)
        self.assertTrue(painted["Nowhere Sans Zzz"])   # something did paint it, just not that face


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class ShotsEdges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_files_with_one_name_never_share_shots(self):
        # review finding 8: site/index.html and site/pricing/index.html overwrote each other
        (self.dir / "site" / "pricing").mkdir(parents=True)
        (self.dir / "site" / "index.html").write_text("<!doctype html><title>a</title><h1>Home</h1>")
        (self.dir / "site" / "pricing" / "index.html").write_text("<!doctype html><title>b</title><h1>Pricing</h1>")
        out = self.dir / "shots"
        node(ROOT / "tools" / "shots.mjs", "--file", self.dir / "site" / "index.html",
             "--file", self.dir / "site" / "pricing" / "index.html", "--out", out, "--flat",
             "--viewports", "desktop-1440x900", "--no-axe")
        names = {p.name for p in out.rglob("*motion__fold.png")}
        self.assertEqual(names, {"index__desktop-1440x900__motion__fold.png",
                                 "pricing-index__desktop-1440x900__motion__fold.png"})

    def test_same_named_files_with_only_the_root_in_common_do_not_hang(self):
        # second review: the common-folder walk never ended once it reached the root
        a = pathlib.Path(tempfile.mkdtemp(dir="/tmp")); b = pathlib.Path(tempfile.mkdtemp(dir="/var/tmp"))
        try:
            for d in (a, b):
                (d / "index.html").write_text("<!doctype html><title>x</title><h1>x</h1>")
            out = self.dir / "shots"
            node(ROOT / "tools" / "shots.mjs", "--file", a / "index.html", "--file", b / "index.html", "--out", out,
                 "--flat", "--viewports", "desktop-1440x900", "--no-axe", timeout=90)
            names = {p.name for p in out.rglob("*motion__fold.png")}
            self.assertEqual(len(names), 2, names)
        finally:
            import shutil
            shutil.rmtree(a, ignore_errors=True); shutil.rmtree(b, ignore_errors=True)

    def test_authored_text_keeps_words_whole_and_ignores_text_transform(self):
        page = self.dir / "t.html"
        page.write_text('<!doctype html><title>t</title><h1 style="text-transform:uppercase">Book<em>ing</em> at <strong>4.2%</strong>.</h1>')
        out = self.dir / "r.json"
        node(ROOT / "tools" / "shots.mjs", "--file", page, "--out", self.dir / "s", "--flat",
             "--viewports", "desktop-1440x900", "--no-axe", "--json-out", out)
        row = next(r for r in json.loads(out.read_text())["results"] if r["motion"] == "no-preference")
        self.assertIn("BOOKING AT 4.2%.", row["text"])
        self.assertIn("Booking at 4.2%.", row["textAuthored"])

    def test_phone_overflow_is_measured_against_the_screen_not_the_stretched_window(self):
        # Under mobile emulation innerWidth grows to fit wide content, so measuring against it never fails.
        p = node(ROOT / "tools" / "shots.mjs", "--file", FIX / "shots" / "wide.html", "--out", self.dir / "wide",
                 "--flat", "--json-out", self.dir / "wide.json", "--viewports", "phone-390x844,desktop-1440x900",
                 "--no-axe")
        rep = json.loads((self.dir / "wide.json").read_text())
        phone = next(r for r in rep["results"] if r["viewport"] == "phone-390x844")
        desk = next(r for r in rep["results"] if r["viewport"] == "desktop-1440x900")
        self.assertGreater(phone["horizontalOverflow"], 700, p.stderr)
        self.assertEqual(desk["horizontalOverflow"], 0, p.stderr)
        # innerHeight stretches the same way, which made a long wide page count as about one screen.
        self.assertGreater(phone["screens"], 3.4, p.stderr)

    def test_old_viewport_names_still_work(self):
        p = node(ROOT / "tools" / "shots.mjs", "--file", FIX / "gate" / "index.html", "--out", self.dir, "--flat",
                 "--json-out", self.dir / "r.json", "--viewports", "desktop,phone", "--no-axe")
        rep = json.loads((self.dir / "r.json").read_text())
        self.assertEqual(sorted({r["viewport"] for r in rep["results"]}), ["desktop", "phone"], p.stderr)

    def test_every_navigation_failing_is_exit_2(self):
        p = node(ROOT / "tools" / "shots.mjs", "http://127.0.0.1:9/", "--out", self.dir, "--flat",
                 "--json-out", self.dir / "r.json", "--viewports", "phone", "--no-axe")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        rep = json.loads((self.dir / "r.json").read_text())
        self.assertEqual(rep["exit"], 2)
        self.assertTrue(any(f["rule"] == "tool.could-not-run" for f in rep["findings"]))

    def test_missing_file_is_exit_2(self):
        p = node(ROOT / "tools" / "shots.mjs", "--file", self.dir / "gone.html", "--out", self.dir,
                 "--json-out", self.dir / "r.json")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads((self.dir / "r.json").read_text())["exit"], 2)

    def test_unknown_viewport_is_exit_2(self):
        p = node(ROOT / "tools" / "shots.mjs", "--file", FIX / "gate" / "index.html", "--viewports", "watch")
        self.assertEqual(p.returncode, 2)


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class SheetAndCrop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = pathlib.Path(cls.tmp.name)
        node(ROOT / "tools" / "shots.mjs", "--file", FIX / "gate" / "index.html", "--out", cls.dir / "a", "--flat",
             "--viewports", "phone-390x844", "--no-axe")
        cls.a = cls.dir / "a" / "index__phone-390x844__motion__fold.png"
        cls.b = cls.dir / "a" / "index__phone-390x844__reduced__fold.png"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sheet_with_images_flag(self):
        out = self.dir / "sheet.png"
        p = node(ROOT / "tools" / "sheet.mjs", "--images", self.a, self.b, "--labels", "Motion,Reduced",
                 "--cols", "2", "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        w, h = png_size(out)
        self.assertGreater(w, 900)   # two 480px cells and the gutters

    def test_sheet_missing_image_is_exit_2(self):
        p = node(ROOT / "tools" / "sheet.mjs", "--images", self.a, self.dir / "nope.png", "--out", self.dir / "s.png")
        self.assertEqual(p.returncode, 2)

    def test_crop_pair(self):
        out = self.dir / "pair.png"
        p = node(ROOT / "tools" / "crop.mjs", self.a, self.b, "--box", "0,0,200,100", "--scale", "2", "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        w, h = png_size(out)
        self.assertGreaterEqual(w, 800)    # two 400px crops side by side
        self.assertGreaterEqual(h, 200)

    def test_crop_box_outside_image_is_exit_2(self):
        p = node(ROOT / "tools" / "crop.mjs", self.a, self.b, "--box", "0,0,99999,10", "--out", self.dir / "x.png")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_crop_bad_box_is_exit_2(self):
        p = node(ROOT / "tools" / "crop.mjs", self.a, self.b, "--box", "zero", "--out", self.dir / "x.png")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
