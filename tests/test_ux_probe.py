"""tools/ux-probe.js against a known-good and a known-bad page in a real Chromium.

Skipped cleanly when Node, `npm install` or a Playwright Chromium is missing (as in CI).
"""
import json
import pathlib
import unittest

from test_shots import READY, node

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "ux"
PROBE = (ROOT / "tools" / "ux-probe.js").read_text()


def probe(page, viewport):
    p = node(ROOT / "tools" / "eval_render.mjs", "probe", "--file", page, "--viewport", viewport, "--expr", PROBE)
    return json.loads(p.stdout.strip().splitlines()[-1])["value"]


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class UxProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good_phone = probe(FIX / "good.html", "390x844")
        cls.good_desk = probe(FIX / "good.html", "1440x900")
        cls.bad_phone = probe(FIX / "bad.html", "390x844")
        cls.bad_rules = {f["rule"] for f in cls.bad_phone["findings"]}

    def test_good_page_is_clean_on_phone_and_desktop(self):
        # The spaced footer links pass WCAG 2.5.8 by its spacing exception; on touch they still get the 44px advice.
        self.assertEqual(self.good_phone["fails"], 0, self.good_phone["findings"])
        self.assertEqual({f["where"].split('"')[1] for f in self.good_phone["findings"]}, {"Privacy", "Cookies"})
        self.assertEqual({f["rule"] for f in self.good_phone["findings"]}, {"target.under-44-touch"})
        self.assertEqual(self.good_desk["findings"], [])

    def test_default_submit_label_is_vague(self):
        self.assertTrue(any(f["rule"] == "action.vague-label" and f["where"].startswith("input") for f in self.bad_phone["findings"]))

    def test_measures_against_the_phone_not_the_stretched_window(self):
        self.assertEqual(self.bad_phone["viewport"], "390x844")
        self.assertIn("layout.sideways-scroll", self.bad_rules)

    def test_bad_page_findings(self):
        for rule in ("field.no-label", "field.placeholder-as-label", "field.wrong-type", "field.zooms-on-focus",
                     "field.no-autocomplete", "dark.pre-ticked", "form.browser-bubbles-only", "action.vague-label",
                     "action.no-name", "action.clickable-div", "page.h1-count", "page.no-lang", "page.zoom-blocked",
                     "nav.no-skip-link", "nav.no-current", "img.no-alt", "table.numbers-not-right-aligned",
                     "table.numbers-not-tabular"):
            self.assertIn(rule, self.bad_rules, rule)

    def test_clipped_overflow_is_still_caught(self):
        # overflow-x: hidden on html and body keeps scrollWidth at the viewport, so measure the boxes too.
        rules = {f["rule"] for f in probe(FIX / "clipped.html", "390x844")["findings"]}
        self.assertIn("layout.cut-off", rules)

    def test_clipping_on_purpose_is_not_cut_off(self):
        # aria-hidden decoration may bleed and an off-canvas fixed drawer may wait past the edge.
        self.assertEqual(probe(FIX / "good-clipped.html", "390x844")["findings"], [])

    def test_missing_viewport_meta_fails(self):
        rules = {f["rule"] for f in probe(FIX / "no-viewport.html", "390x844")["findings"]}
        self.assertIn("page.no-viewport-meta", rules)

    def test_failures_counted(self):
        self.assertGreater(self.bad_phone["fails"], 5)
        self.assertEqual(self.bad_phone["fails"], sum(f["severity"] == "fail" for f in self.bad_phone["findings"]))


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class UxCommand(unittest.TestCase):
    def ddr(self, *args):
        import subprocess
        import sys
        return subprocess.run([sys.executable, str(ROOT / "tools" / "ddr.py"), "ux", *map(str, args)],
                              capture_output=True, text=True, timeout=300)

    def test_exit_codes(self):
        self.assertEqual(self.ddr("--file", FIX / "good.html").returncode, 0)
        bad = self.ddr("--file", FIX / "bad.html", "--json")
        self.assertEqual(bad.returncode, 1, bad.stderr)
        self.assertGreater(json.loads(bad.stdout)["fails"], 0)
        self.assertEqual(self.ddr("--file", FIX / "missing.html").returncode, 2)
        self.assertEqual(self.ddr("--file", FIX / "good.html", "--viewports", "").returncode, 2)
        self.assertEqual(self.ddr("--url", "localhost:3000/").returncode, 2)

    def test_url_is_probed_as_served(self):
        import http.server
        import threading
        handler = lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(FIX))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/bad.html"
            p = self.ddr("--url", url, "--json")
            self.assertEqual(p.returncode, 1, p.stderr)
            self.assertEqual(json.loads(p.stdout)["target"], url)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
