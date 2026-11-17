"""ddr audit against a page holding every fault it measures (faulty.html) and its clean twin (clean.html).

Real Chromium; skipped cleanly when Node, `npm install` or a Playwright Chromium is missing (as in CI).
"""
import json
import pathlib
import subprocess
import sys
import unittest

try:
    from test_shots import READY
except ImportError:  # run as tests.test_audit
    from tests.test_shots import READY

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "audit"
VPS = "mac-1512x820,phone-390x844"


def audit(*args, timeout=300):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "ddr.py"), "audit", *map(str, args)],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


def report(page, *extra):
    p = audit("--file", FIX / page, "--viewports", VPS, "--json", *extra)
    try:
        return p, json.loads(p.stdout)
    except ValueError:
        raise AssertionError(f"no JSON from ddr audit (exit {p.returncode}): {p.stderr[-800:]} {p.stdout[-400:]}")


def items(rep, vp, check):
    v = next(v for v in rep["viewports"] if v["viewport"] == vp)
    return v["checks"].get(check, {}).get("items", [])


def vp_of(rep, vp):
    return next(v for v in rep["viewports"] if v["viewport"] == vp)


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class Audit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bad_proc, cls.bad = report("faulty.html")
        cls.good_proc, cls.good = report("clean.html")

    def test_shape(self):
        self.assertEqual(self.bad["tool"], "audit")
        self.assertEqual([v["viewport"] for v in self.bad["viewports"]], VPS.split(","))
        for it in items(self.bad, "mac-1512x820", "clip.text"):
            for k in ("selector", "text", "rect", "stop"):
                self.assertIn(k, it)
            self.assertEqual(len(it["rect"]), 4)

    def test_reports_by_default_and_exits_0(self):
        self.assertEqual(self.bad_proc.returncode, 0, self.bad_proc.stderr)
        self.assertGreater(self.bad["total"], 0)

    # (a) clipped text
    def test_descender_cut_by_a_tight_mask(self):
        hits = [i for i in items(self.bad, "mac-1512x820", "clip.text") if "July" in i["text"]]
        self.assertTrue(hits, items(self.bad, "mac-1512x820", "clip.text"))
        self.assertIn("span.word", hits[0]["selector"])
        self.assertIn("mask", hits[0]["clipper"])
        self.assertGreaterEqual(hits[0]["cut"]["bottom"], 10)

    def test_caps_in_the_same_tight_mask_are_not_cut(self):
        # A content-box check would flag MAIN too: its line box is 0.9em in a 1.12em font box. Only ink counts.
        self.assertEqual(items(self.good, "mac-1512x820", "clip.text"), [])
        self.assertEqual(items(self.good, "phone-390x844", "clip.text"), [])

    def test_card_too_short_for_its_words(self):
        hits = items(self.bad, "mac-1512x820", "clip.box")
        self.assertTrue(any("div.card" in i["selector"] for i in hits), hits)

    # (b) off the viewport
    def test_heading_cut_at_the_phone_edge_with_sideways_scroll_hidden(self):
        hits = items(self.bad, "phone-390x844", "offscreen")
        self.assertTrue(any("h2.wide" in i["selector"] and "Inventory" in i["text"] for i in hits), hits)
        self.assertFalse(any("h2.wide" in i["selector"] for i in items(self.bad, "mac-1512x820", "offscreen")))

    def test_sideways_page_scroll(self):
        p = audit("--file", ROOT / "tests" / "fixtures" / "shots" / "wide.html", "--viewports", "phone-390x844", "--json")
        rep = json.loads(p.stdout)
        hits = items(rep, "phone-390x844", "page.sideways")
        self.assertTrue(hits, rep)
        self.assertGreater(hits[0]["px"], 700)

    # (c) overlapping text, found below the first screen
    def test_overlap_found_at_a_later_scroll_stop(self):
        hits = items(self.bad, "mac-1512x820", "overlap")
        hit = next((i for i in hits if "Cash for stock" in i["text"]), None)
        self.assertIsNotNone(hit, hits)
        self.assertIn("Paid back", hit["other"]["text"])
        self.assertGreater(hit["stop"], 0)

    # (d) tap targets, phone only
    def test_small_and_crowded_tap_targets_on_the_phone(self):
        small = items(self.bad, "phone-390x844", "tap.small")
        self.assertTrue(any('aria-label="Menu"' in i["selector"] or "Menu" in i["text"] for i in small), small)
        close = items(self.bad, "phone-390x844", "tap.close")
        self.assertTrue(close, close)
        self.assertLess(close[0]["gap"], 8)

    def test_no_tap_checks_on_a_laptop(self):
        self.assertEqual(items(self.bad, "mac-1512x820", "tap.small"), [])
        self.assertEqual(items(self.bad, "mac-1512x820", "tap.close"), [])

    # (e) contrast on the pixels
    def test_contrast_measured_on_pixels_not_tokens(self):
        hits = {i["text"]: i for i in items(self.bad, "mac-1512x820", "contrast")}
        over = next((i for t, i in hits.items() if "Apply in minutes" in t), None)
        self.assertIsNotNone(over, hits)   # its tokens say white on black, 21:1
        self.assertLess(over["ratio"], 2)
        self.assertEqual(over["needs"], 4.5)
        faint = next((i for t, i in hits.items() if "Indicative" in t), None)
        self.assertIsNotNone(faint, hits)
        self.assertLess(faint["ratio"], 2.5)

    # (f) line length and small text on the phone
    def test_line_too_long_on_a_laptop(self):
        hits = items(self.bad, "mac-1512x820", "line.length")
        self.assertTrue(any("p.long" in i["selector"] and i["chars"] > 85 for i in hits), hits)

    def test_text_under_16px_on_the_phone(self):
        hits = items(self.bad, "phone-390x844", "text.small")
        self.assertTrue(any("p.tiny" in i["selector"] and i["px"] == 12 for i in hits), hits)
        self.assertEqual(items(self.bad, "mac-1512x820", "text.small"), [])

    # (g) the first screen
    def test_first_screen_counts(self):
        bad, good = vp_of(self.bad, "mac-1512x820")["fold"], vp_of(self.good, "mac-1512x820")["fold"]
        self.assertEqual(bad["headings"], 2)
        self.assertEqual(bad["primaryActions"], 3)
        self.assertEqual(good["headings"], 1)
        self.assertEqual(good["primaryActions"], 1)
        self.assertEqual(bad["largest"]["px"], 240)
        self.assertGreater(good["words"], 5)

    def test_every_scroll_stop_is_walked(self):
        self.assertGreaterEqual(vp_of(self.bad, "mac-1512x820")["stops"], 3)

    # the twin
    def test_clean_twin_has_no_findings(self):
        found = {(v["viewport"], k): c["items"] for v in self.good["viewports"] for k, c in v["checks"].items() if c["count"]}
        self.assertEqual(found, {})
        self.assertEqual(self.good["total"], 0)


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class AuditCli(unittest.TestCase):
    def test_items_are_capped_and_the_cut_is_counted(self):
        p, rep = report("faulty.html", "--max-items", "1")
        for v in rep["viewports"]:
            for name, c in v["checks"].items():
                self.assertLessEqual(len(c["items"]), 1, name)
                self.assertEqual(c["cut"], c["count"] - len(c["items"]), name)

    def test_strict_exits_1_on_findings(self):
        p = audit("--file", FIX / "faulty.html", "--viewports", "phone-390x844", "--strict")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("tap.small", p.stdout)

    def test_strict_clean_exits_0(self):
        p = audit("--file", FIX / "clean.html", "--viewports", "phone-390x844", "--strict")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_missing_file_is_exit_2(self):
        p = audit("--file", FIX / "nope.html")
        self.assertEqual(p.returncode, 2)

    def test_unknown_viewport_is_exit_2(self):
        p = audit("--file", FIX / "clean.html", "--viewports", "fridge-1x1")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
