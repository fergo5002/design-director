"""--storage-state: a page behind a sign-in renders as the signed-in person in shots, audit, motion and the gate.

A local server stands in for an app: /dash answers only with a session cookie and sends everyone else to /login,
as Draft's app does. Real Chromium; skipped cleanly when Node, `npm install` or Chromium is missing (as in CI).
"""
import contextlib
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest

try:
    from test_shots import READY, node
except ImportError:  # run as tests.test_signed_in
    from tests.test_shots import READY, node

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gate  # noqa: E402

PAGE = (b'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
        b'initial-scale=1"><title>%s</title><style>body{font:18px/1.5 Arial,sans-serif;margin:0;padding:16px}</style>'
        b'</head><body><main><h1>%s</h1></main></body></html>')


class App(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/dash"):
            if "session=signed-in" not in (self.headers.get("Cookie") or ""):
                self.send_response(303)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            body = PAGE % (b"Dashboard", b"Your dashboard")
        else:
            body = PAGE % (b"Sign in", b"Sign in")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@unittest.skipUnless(READY, "needs node, npm install and a playwright chromium")
class SignedIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), App)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = pathlib.Path(cls.tmp.name) / "state.json"
        cls.state.write_text(json.dumps({"cookies": [{"name": "session", "value": "signed-in", "domain": "127.0.0.1",
                                                      "path": "/", "expires": -1, "httpOnly": True, "secure": False,
                                                      "sameSite": "Lax"}], "origins": []}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def audit(self, *extra):
        out = pathlib.Path(self.tmp.name) / "a.json"
        node(ROOT / "tools" / "audit.mjs", "--url", f"{self.base}/dash", "--viewports", "phone-390x844",
             "--json-out", out, *extra)
        return json.loads(out.read_text())["viewports"][0]

    def test_audit_without_state_lands_on_the_sign_in(self):
        self.assertTrue(self.audit()["finalUrl"].endswith("/login"))

    def test_audit_with_state_measures_the_dashboard(self):
        self.assertTrue(self.audit("--storage-state", self.state)["finalUrl"].endswith("/dash"))

    def test_motion_with_state(self):
        out = pathlib.Path(self.tmp.name) / "m.json"
        node(ROOT / "tools" / "motion.mjs", "--url", f"{self.base}/dash", "--idle", "300", "--storage-state", self.state,
             "--json-out", out)
        self.assertTrue(json.loads(out.read_text())["finalUrl"].endswith("/dash"))

    def test_gate_run_renders_the_signed_in_page(self):
        proj = pathlib.Path(self.tmp.name) / "proj"
        (proj / "src").mkdir(parents=True, exist_ok=True)
        (proj / "src" / "app.css").write_text("body{}\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gate.main(["run", "--project", str(proj), "--src", str(proj / "src"), "--url", f"{self.base}/dash",
                       "--viewports", "mac-1512x820", "--storage-state", str(self.state)])
        r = json.loads((proj / ".design" / "gate" / "receipt.json").read_text())
        texts = list((proj / r["shots_dir"]).glob("*__text.txt"))
        self.assertTrue(texts, buf.getvalue())
        self.assertIn("Your dashboard", texts[0].read_text())
        self.assertEqual(r["measured"]["audit"]["exit"], 0, r["measured"])


if __name__ == "__main__":
    unittest.main()
