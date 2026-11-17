"""ddr motion: a smooth page passes, the same page with a 150 ms stall fails, layout animation and shifts are named,
and a page whose requestAnimationFrame never fires returns a degraded verdict instead of hanging.

Real Chromium; skipped cleanly when Node, `npm install` or a Playwright Chromium is missing (as in CI).
"""
import json
import pathlib
import subprocess
import sys
import time
import unittest

try:
    from test_shots import READY, node
except ImportError:  # run as tests.test_motion
    from tests.test_shots import READY, node

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "motion"


def motion(*args, timeout=300):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "ddr.py"), "motion", *map(str, args)],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


def report(page, *extra):
    p = motion("--file", FIX / page, "--scroll", "--idle", "1500", "--json", *extra)
    try:
        return p, json.loads(p.stdout)
    except ValueError:
        raise AssertionError(f"no JSON from ddr motion (exit {p.returncode}): {p.stderr[-800:]} {p.stdout[-400:]}")


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class Motion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smooth_proc, cls.smooth = report("smooth.html")
        cls.stall_proc, cls.stall = report("stall.html")
        cls.layout_proc, cls.layout = report("layout.html")

    def test_shape(self):
        r = self.smooth["result"]
        for k in ("verdict", "refreshMs", "phases", "sections", "longTasks", "layoutShift", "layoutAnimations"):
            self.assertIn(k, r)
        for phase in ("idle", "scroll"):
            for k in ("frames", "p50", "p95", "p99", "worst", "dropped"):
                self.assertIn(k, r["phases"][phase])

    def test_smooth_page_passes(self):
        r = self.smooth["result"]
        self.assertEqual(r["verdict"], "SMOOTH", r)
        self.assertGreater(r["phases"]["scroll"]["frames"], 30)
        self.assertEqual(r["layoutAnimations"], [])
        self.assertEqual(self.smooth_proc.returncode, 0)

    def test_injected_150ms_stall_fails(self):
        r = self.stall["result"]
        self.assertEqual(r["verdict"], "NOT SMOOTH", r)
        self.assertGreaterEqual(r["phases"]["scroll"]["worst"], 140)
        self.assertTrue(any(t["ms"] >= 140 for t in r["longTasks"]["items"]), r["longTasks"])
        self.assertEqual(self.stall_proc.returncode, 0)   # it reports; --strict decides

    def test_strict_exits_1_on_a_stall(self):
        p = motion("--file", FIX / "stall.html", "--scroll", "--idle", "500", "--strict")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("NOT SMOOTH", p.stdout)

    def test_layout_properties_named_with_their_element(self):
        anims = {(a["selector"], p) for a in self.layout["result"]["layoutAnimations"] for p in a["props"]}
        self.assertIn(("#slider", "left"), anims)
        self.assertIn(("#grow", "width"), anims)
        self.assertNotIn("#slider", {a["selector"] for a in self.smooth["result"]["layoutAnimations"]})

    def test_layout_shift_measured_with_its_source(self):
        ls = self.layout["result"]["layoutShift"]
        self.assertGreater(ls["total"], 0.01)
        self.assertTrue(ls["sources"], ls)
        self.assertEqual(self.smooth["result"]["layoutShift"]["total"], 0)


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class MotionScroll(unittest.TestCase):
    def test_a_page_that_scrolls_inside_a_container_is_scrolled(self):
        # html and body hide overflow and #app scrolls; each scroll event blocks the main thread for 120 ms
        p = motion("--file", ROOT / "tests" / "fixtures" / "audit" / "inner-scroll.html", "--scroll", "--idle", "500", "--json")
        r = json.loads(p.stdout)["result"]
        self.assertTrue(r["scrolled"]["measured"], r["scrolled"])
        self.assertEqual(r["scrolled"]["target"], "#app")
        self.assertEqual(r["verdict"], "NOT SMOOTH", r)
        # the refresh interval comes from the idle frames, so a stall on every scroll frame counts as dropped frames
        self.assertLess(r["refreshMs"], 40, r)
        self.assertGreater(r["phases"]["scroll"]["dropped"], 50, r["phases"]["scroll"])

    def test_smooth_scroll_behaviour_does_not_hide_the_page(self):
        p = motion("--file", ROOT / "tests" / "fixtures" / "audit" / "smooth-scroll.html", "--scroll", "--idle", "500", "--json")
        r = json.loads(p.stdout)["result"]
        self.assertTrue(r["scrolled"]["measured"], r["scrolled"])
        self.assertEqual(r["scrolled"]["target"], "window")
        self.assertGreater(r["phases"]["scroll"]["frames"], 100)

    def test_scroll_asked_for_on_a_page_that_cannot_scroll_says_not_measured(self):
        short = ROOT / "tests" / "fixtures" / "gate" / "index.html"
        p = motion("--file", short, "--scroll", "--idle", "500", "--json")
        r = json.loads(p.stdout)["result"]
        self.assertFalse(r["scrolled"]["measured"], r["scrolled"])
        text = motion("--file", short, "--scroll", "--idle", "500").stdout
        self.assertIn("scroll not measured", text)
        self.assertNotIn("None", text)


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class MotionInstrument(unittest.TestCase):
    def test_a_page_without_animation_frames_does_not_hang(self):
        # A hidden tab never runs requestAnimationFrame. Stub it out and the probe must still come back, degraded.
        probe = (ROOT / "tools" / "motion-probe.js").read_text()
        expr = f"window.requestAnimationFrame = () => 0; ({probe})({{ idleMs: 800, scroll: true, maxScrollMs: 800 }})"
        t = time.monotonic()
        p = node(ROOT / "tools" / "eval_render.mjs", "probe", "--file", FIX / "smooth.html", "--viewport", "1512x820",
                 "--expr", expr, timeout=60)
        took = time.monotonic() - t
        value = json.loads(p.stdout.strip().splitlines()[-1])["value"]
        self.assertEqual(value["verdict"], "INSTRUMENT DEGRADED", value)
        self.assertLess(took, 30)

    def test_missing_file_is_exit_2(self):
        self.assertEqual(motion("--file", FIX / "nope.html").returncode, 2)


if __name__ == "__main__":
    unittest.main()
