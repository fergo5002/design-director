import sys, unittest, pathlib, tempfile, io, contextlib, json, shlex
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import claims

PY = shlex.quote(sys.executable)
SCRIPT = """import sys, time
c = sys.argv[1]
if c == "C1":
    print("reading the ops sheet")
    print("ops sheet row 4: median decision 19 hours")
    sys.exit(0)
if c == "SLOW":
    time.sleep(5)
print("rate is 7.9 not 6.9", file=sys.stderr)
sys.exit(1)
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = pathlib.Path(self.tmp.name)
        (self.p / ".design" / "brief").mkdir(parents=True)
        (self.p / ".design" / "brief" / "claims_check.py").write_text(SCRIPT)
        (self.p / "src").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        (self.p / ".design" / "brief" / "claims.json").write_text(json.dumps({"version": 1, "claims": rows}))

    def claim(self, cid="C1", **kw):
        c = {"id": cid, "text": "Decisions in 24 hours", "source": "ops sheet 2026-10-30", "check": "",
             "status": "unverified", "evidence": ""}
        c.update(kw)
        return c

    def check_cmd(self, arg):
        return f"{PY} .design/brief/claims_check.py {arg}"

    def rules(self, res):
        return [f["rule"] for f in res["findings"]]

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = claims.main(["--project", str(self.p)] + list(argv))
        return rc, out.getvalue()


class Check(Base):
    def test_missing_file_could_not_run(self):
        (self.p / ".design" / "brief" / "claims_check.py").unlink()
        res = claims.check(self.p)
        self.assertEqual(res["exit"], 2)
        self.assertEqual(res["tool"], "claims")
        self.assertIsNone(claims.load(self.p))

    def test_a_passing_check_marks_it_verified_with_the_last_line(self):
        self.write([self.claim(check=self.check_cmd("C1"))])
        res = claims.check(self.p)
        self.assertEqual(res["exit"], 0, res)
        c = claims.load(self.p)["claims"][0]
        self.assertEqual(c["status"], "verified")
        self.assertEqual(c["evidence"], "ops sheet row 4: median decision 19 hours")

    def test_a_failing_check_is_an_error(self):
        self.write([self.claim(check=self.check_cmd("C2"))])
        res = claims.check(self.p)
        self.assertEqual(res["exit"], 1)
        self.assertEqual(self.rules(res), ["claim.check-failed"])
        self.assertIn("7.9 not 6.9", res["findings"][0]["message"])
        self.assertEqual(claims.load(self.p)["claims"][0]["status"], "unverified")

    def test_a_check_that_hangs_could_not_run(self):
        self.write([self.claim(check=self.check_cmd("SLOW"))])
        res = claims.check(self.p, timeout=0.5)
        self.assertEqual(res["exit"], 2)
        self.assertEqual(self.rules(res), ["tool.could-not-run"])
        self.assertIn("timed out", res["findings"][0]["message"])

    def test_a_missing_program_could_not_run(self):
        self.write([self.claim(check="no-such-program-ddr-test --x")])
        self.assertEqual(claims.check(self.p)["exit"], 2)

    def test_runs_from_the_project_root_without_a_shell(self):
        self.write([self.claim(check=self.check_cmd("C1") + " ; echo pwned > pwned.txt")])
        claims.check(self.p)
        self.assertFalse((self.p / "pwned.txt").exists())

    def test_without_a_check_it_needs_a_recorded_read(self):
        self.write([self.claim()])
        self.assertEqual(self.rules(claims.check(self.p)), ["claim.unverified"])
        self.write([self.claim(status="verified", evidence="short")])
        self.assertEqual(self.rules(claims.check(self.p)), ["claim.unverified"])
        self.write([self.claim(status="verified", evidence="read the ops sheet row 4 on 2026-11-05")])
        self.assertEqual(claims.check(self.p)["exit"], 0)

    def test_removed_claim_must_not_appear_in_the_source(self):
        (self.p / "src" / "index.html").write_text("<h1>Decisions   in 24\n hours</h1>")
        self.write([self.claim(status="removed")])
        res = claims.check(self.p, [str(self.p / "src")])
        self.assertEqual(self.rules(res), ["claim.removed-but-present"])
        (self.p / "src" / "index.html").write_text("<h1>Decisions the same week</h1>")
        res = claims.check(self.p, [str(self.p / "src")])
        self.assertEqual(res["exit"], 0)
        self.assertEqual(res["claims"][0]["status"], "removed")

    def test_missing_src_could_not_run(self):
        self.write([self.claim(status="removed")])
        self.assertEqual(claims.check(self.p, [str(self.p / "gone")])["exit"], 2)

    def test_bad_schema(self):
        self.write([self.claim(status="probably"), self.claim("C1"), self.claim("C3", text="")])
        rules = set(self.rules(claims.check(self.p)))
        for r in ("claim.status", "claim.duplicate-id", "claim.no-text"):
            self.assertIn(r, rules)


class Cli(Base):
    def test_add_set_list_check(self):
        rc, out = self.cli("add", "--text", "Decisions in 24 hours", "--source", "ops sheet", "--check", self.check_cmd("C1"))
        self.assertEqual(rc, 0, out)
        rc, out = self.cli("add", "--text", "Rates from 6.9%", "--source", "rate card")
        self.assertEqual([c["id"] for c in claims.load(self.p)["claims"]], ["C1", "C2"])
        self.assertEqual(self.cli("set", "C2", "--status", "removed")[0], 0)
        self.assertEqual(self.cli("set", "C9", "--status", "removed")[0], 2)
        self.assertEqual(self.cli("set", "C2", "--status", "maybe")[0], 2)
        rc, out = self.cli("list")
        self.assertIn("C2", out)
        (self.p / "src" / "a.html").write_text("<p>Rates from 6.9%</p>")
        rc, out = self.cli("check", "--src", str(self.p / "src"), "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["findings"][0]["rule"], "claim.removed-but-present")
        (self.p / "src" / "a.html").write_text("<p>Rates on the rate card</p>")
        self.assertEqual(self.cli("check", "--src", str(self.p / "src"))[0], 0)


if __name__ == "__main__":
    unittest.main()
