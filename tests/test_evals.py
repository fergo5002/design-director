"""The eval harness, exercised end to end with a fake claude so nothing is spent."""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evals  # noqa: E402

FAKE = ROOT / "tests" / "fixtures" / "fake_claude.py"


def _node_ready() -> bool:
    return bool(shutil.which("node")) and (ROOT / "node_modules" / "playwright").exists()


NODE = _node_ready()


# ------------------------------------------------------------ stream-json builders

def use(i, name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}


def res(i, content="ok", is_error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                                     "content": content, "is_error": is_error}]}}


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def done(cost=0.5, turns=4, ms=60000):
    return {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": cost,
            "num_turns": turns, "duration_ms": ms, "permission_denials": []}


INIT = {"type": "system", "subtype": "init", "skills": ["dd:design-director", "dataviz"]}

GOOD_HTML = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>:root{--ink:#0b1b2b;--paper:#f6f5f1}</style></head>
<body><main><h1>Book a sauna</h1><p>Two hours, by the sea.</p></main></body></html>"""
BAD_HTML = """<!doctype html><html><head><style>:root{--ink:#7c3aed;--paper:#f6f5f1}
h1{background:linear-gradient(90deg,#7c3aed,#2563eb)}</style></head>
<body><main><h1>Unlock seamless relaxation</h1><h1>Again</h1><h1>And again</h1></main></body></html>"""

GOOD_EVENTS = [INIT, say("Reading the brief."), use(1, "Skill", {"skill": "dd:design-director"}), res(1),
               use(2, "Read", {"file_path": "brief.md"}), res(2),
               use(3, "Write", {"file_path": "index.html", "content": GOOD_HTML}), res(3),
               say("Done. Built index.html."), done(0.8, 5, 90000)]
BAD_EVENTS = [INIT, say("Who is it for? What colours? Should it be dark?"),
              use(1, "Write", {"file_path": "index.html", "content": BAD_HTML}), res(1),
              use(2, "Bash", {"command": "vercel deploy --prod"}), res(2, "denied", True),
              use(3, "Skill", {"skill": "dd:design-director"}), res(3),
              say("Shipped."), done(3.5, 9, 200000)]


def trace_of(events):
    return evals.Trace.from_events(events)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, base, rel, text):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def grade(self, spec, events=(), fixture=True):
        ctx = evals.Context(workdir=self.work, fixture=self.fixture if fixture else None,
                            trace=trace_of(list(events)), case={"id": "c"})
        return evals.grade(spec, ctx)


# ------------------------------------------------------------ cases

class Cases(Base):
    def case(self, cid, body):
        d = self.root / "cases" / cid
        d.mkdir(parents=True)
        (d / "case.toml").write_text(body, encoding="utf-8")
        return d

    def test_defaults_and_graders(self):
        self.case("sauna", 'id = "sauna"\ntitle = "Sauna landing"\norigin = "2026-11-04: \'too generic\'"\n'
                           'prompt = "Build it"\n\n[[grader]]\ntype = "file-exists"\nglob = "*.html"\n')
        cases, problems = evals.load_cases(self.root / "cases")
        self.assertEqual(problems, [])
        c = cases[0]
        self.assertEqual((c["budget_usd"], c["timeout_min"]), (4.0, 25.0))
        self.assertEqual(c["grader"][0]["type"], "file-exists")

    def test_missing_fields_and_unknown_grader_are_reported(self):
        self.case("broken", 'id = "broken"\ntitle = "x"\n\n[[grader]]\ntype = "vibes"\n')
        cases, problems = evals.load_cases(self.root / "cases")
        self.assertEqual(cases, [])
        text = " ".join(problems)
        self.assertIn("origin", text)
        self.assertIn("prompt", text)
        self.assertIn("vibes", text)

    def test_id_must_match_directory(self):
        self.case("one", 'id = "two"\ntitle = "x"\norigin = "o"\nprompt = "p"\n')
        _, problems = evals.load_cases(self.root / "cases")
        self.assertIn("directory", " ".join(problems))

    def test_prompt_file_and_missing_fixture(self):
        d = self.case("pf", 'id = "pf"\ntitle = "x"\norigin = "o"\nprompt_file = "prompt.md"\nfixture = "site"\n')
        (d / "prompt.md").write_text("Line one.\nLine two.\n", encoding="utf-8")
        cases, problems = evals.load_cases(self.root / "cases")
        self.assertIn("fixture", " ".join(problems))
        (d / "site").mkdir()
        cases, problems = evals.load_cases(self.root / "cases")
        self.assertEqual(problems, [])
        self.assertEqual(cases[0]["prompt"], "Line one.\nLine two.\n")


# ------------------------------------------------------------ trace

class TraceParsing(unittest.TestCase):
    def test_calls_results_and_text(self):
        t = trace_of(GOOD_EVENTS)
        self.assertEqual([c.name for c in t.calls], ["Skill", "Read", "Write"])
        self.assertTrue(all(c.ok for c in t.calls))
        self.assertEqual(t.result["total_cost_usd"], 0.8)
        self.assertEqual(t.text_before_first_write(), "Reading the brief.")
        self.assertEqual(t.init["skills"][0], "dd:design-director")

    def test_failed_call_is_marked(self):
        t = trace_of(BAD_EVENTS)
        self.assertFalse(t.calls[1].ok)

    def test_garbage_lines_are_counted_not_fatal(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        tmp.write(json.dumps(INIT) + "\nnot json\n" + json.dumps(done()) + "\n")
        tmp.close()
        t = evals.Trace.from_jsonl(pathlib.Path(tmp.name))
        os.unlink(tmp.name)
        self.assertEqual(t.bad_lines, 1)
        self.assertIsNotNone(t.result)

    def test_questions_are_counted(self):
        self.assertEqual(evals.questions_in("Who is it for? **What colours?** I will decide the rest."), 2)
        self.assertEqual(evals.questions_in("- Which city?\n- Which date?\nThanks."), 2)
        self.assertEqual(evals.questions_in("No questions here."), 0)


# ------------------------------------------------------------ graders, pass and fail

class FileGraders(Base):
    def test_file_exists(self):
        self.assertEqual(self.grade({"type": "file-exists", "glob": "*.html"}).status, "fail")
        self.write(self.work, "index.html", GOOD_HTML)
        self.assertEqual(self.grade({"type": "file-exists", "glob": "*.html"}).status, "pass")
        self.assertEqual(self.grade({"type": "file-exists", "glob": "*.html", "min": 2}).status, "fail")

    def test_main_page_prefers_out(self):
        self.write(self.work, "index.html", "fixture page")
        self.write(self.work, "out/index.html", "deliverable")
        self.assertEqual(evals.main_html(self.work).read_text(), "deliverable")

    def test_ddr_home_root_without_a_copy_is_an_error(self):
        self.assertEqual(self.grade({"type": "file-exists", "root": "ddr_home", "glob": "*"}).status, "error")
        self.assertEqual(self.grade({"type": "file-exists", "root": "elsewhere", "glob": "*"}).status, "error")

    def test_globs_never_reach_into_git(self):
        self.write(self.work, ".git/hooks/x.html", "x")
        self.assertEqual(self.grade({"type": "file-exists", "glob": "**/*.html"}).status, "fail")

    def test_text_present_and_absent(self):
        self.write(self.work, "index.html", BAD_HTML)
        g = self.grade({"type": "text-absent", "glob": "*.html", "pattern": "seamless", "flags": "i"})
        self.assertEqual(g.status, "fail")
        self.assertIn("index.html:3", g.reason)
        self.assertEqual(self.grade({"type": "text-present", "glob": "*.html", "pattern": "Book a sauna"}).status, "fail")
        self.write(self.work, "index.html", GOOD_HTML)
        self.assertEqual(self.grade({"type": "text-absent", "glob": "*.html", "pattern": "seamless"}).status, "pass")
        self.assertEqual(self.grade({"type": "text-present", "glob": "*.html", "pattern": "Book a sauna"}).status, "pass")

    def test_text_grader_with_nothing_to_read_fails_rather_than_passing(self):
        g = self.grade({"type": "text-absent", "glob": "*.html", "pattern": "seamless"})
        self.assertEqual(g.status, "fail")
        self.assertIn("no file", g.reason)

    def test_bad_regex_is_an_error(self):
        self.write(self.work, "index.html", GOOD_HTML)
        self.assertEqual(self.grade({"type": "text-present", "glob": "*.html", "pattern": "("}).status, "error")

    def test_max_count_simple_tags_without_node(self):
        self.write(self.work, "index.html", BAD_HTML)
        g = self.grade({"type": "max-count", "file": "index.html", "selector": "h1", "max": 1})
        self.assertEqual(g.status, "fail")
        self.assertIn("3", g.reason)
        self.write(self.work, "index.html", GOOD_HTML)
        self.assertEqual(self.grade({"type": "max-count", "selector": "h1, h2", "max": 1}).status, "pass")

    def test_lint_clean(self):
        self.write(self.work, "index.html", BAD_HTML)
        g = self.grade({"type": "lint-clean", "glob": "*.html", "rules": ["purple-blue-gradient", "ai-copy"]})
        self.assertEqual(g.status, "fail")
        self.assertIn("purple-blue-gradient", g.reason)
        self.write(self.work, "index.html", GOOD_HTML)
        self.assertEqual(self.grade({"type": "lint-clean", "glob": "*.html", "rules": ["purple-blue-gradient"]}).status, "pass")

    def test_brand_lint_is_an_error_when_brandpack_is_missing(self):
        self.write(self.work, "index.html", GOOD_HTML)
        saved = sys.modules.get("brandpack")
        sys.modules["brandpack"] = None  # makes `import brandpack` raise ImportError
        try:
            g = self.grade({"type": "brand-lint-clean", "glob": "*.html", "brand": "acme"})
        finally:
            if saved is None:
                sys.modules.pop("brandpack", None)
            else:
                sys.modules["brandpack"] = saved
        self.assertEqual(g.status, "error")

    def test_brand_lint_maps_exit_codes(self):
        self.write(self.work, "index.html", GOOD_HTML)
        fake = type(sys)("brandpack")
        outcomes = {}

        def lint(paths, slug):
            return outcomes["r"]
        fake.lint = lint
        saved = sys.modules.get("brandpack")
        sys.modules["brandpack"] = fake
        try:
            spec = {"type": "brand-lint-clean", "glob": "*.html", "brand": "acme"}
            outcomes["r"] = {"ok": True, "exit": 0, "findings": [], "summary": "clean"}
            self.assertEqual(self.grade(spec).status, "pass")
            outcomes["r"] = {"ok": False, "exit": 1, "findings": [
                {"severity": "error", "rule": "color.off-palette", "message": "#7c3aed", "file": "index.html", "line": 1}]}
            g = self.grade(spec)
            self.assertEqual(g.status, "fail")
            self.assertIn("color.off-palette", g.reason)
            outcomes["r"] = {"ok": False, "exit": 2, "findings": [
                {"severity": "error", "rule": "tool.could-not-run", "message": "no brand"}]}
            self.assertEqual(self.grade(spec).status, "error")
        finally:
            if saved is None:
                sys.modules.pop("brandpack", None)
            else:
                sys.modules["brandpack"] = saved

    def test_unchanged_files(self):
        self.write(self.fixture, "tokens.css", ":root{--ink:#0b1b2b}")
        self.write(self.work, "tokens.css", ":root{--ink:#0b1b2b}")
        self.assertEqual(self.grade({"type": "unchanged", "files": ["tokens.css"]}).status, "pass")
        self.write(self.work, "tokens.css", ":root{--ink:#000}")
        self.assertEqual(self.grade({"type": "unchanged", "files": ["tokens.css"]}).status, "fail")
        (self.work / "tokens.css").unlink()
        self.assertIn("missing", self.grade({"type": "unchanged", "files": ["tokens.css"]}).reason)

    def test_unchanged_properties(self):
        self.write(self.fixture, "a.css", ":root{--ink: #0b1b2b; --paper:#f6f5f1}")
        self.write(self.work, "a.css", ":root{--ink:#0B1B2B;--paper:#f6f5f1} .x{color:var(--ink)}")
        spec = {"type": "unchanged", "properties": ["--ink", "--paper"], "glob": "**/*.css"}
        self.assertEqual(self.grade(spec).status, "pass")
        self.write(self.work, "b.css", ":root{--ink:#7c3aed}")
        g = self.grade(spec)
        self.assertEqual(g.status, "fail")
        self.assertIn("--ink", g.reason)

    def test_unchanged_without_a_fixture_is_an_error(self):
        g = self.grade({"type": "unchanged", "files": ["a.css"]}, fixture=False)
        self.assertEqual(g.status, "error")
        g = self.grade({"type": "unchanged", "properties": ["--nope"], "glob": "*.css"})
        self.assertEqual(g.status, "error")


class TraceGraders(Base):
    def test_trace_order(self):
        spec = {"type": "trace-order", "before_tool": "Skill", "before_match": "design-director",
                "after_tool": "Write|Edit", "after_match": "\\.html"}
        self.assertEqual(self.grade(spec, GOOD_EVENTS).status, "pass")
        g = self.grade(spec, BAD_EVENTS)
        self.assertEqual(g.status, "fail")
        self.assertIn("call 2", g.reason)

    def test_trace_order_with_a_missing_side_fails(self):
        spec = {"type": "trace-order", "before_tool": "Skill", "after_tool": "Edit"}
        self.assertEqual(self.grade(spec, GOOD_EVENTS).status, "fail")

    def test_trace_present_and_absent(self):
        deploy = {"tool": "Bash", "match": "\\b(vercel|wrangler|railway|netlify)\\b"}
        self.assertEqual(self.grade({"type": "trace-absent", **deploy}, GOOD_EVENTS).status, "pass")
        self.assertEqual(self.grade({"type": "trace-absent", **deploy}, BAD_EVENTS).status, "fail")
        self.assertEqual(self.grade({"type": "trace-present", "tool": "Read"}, GOOD_EVENTS).status, "pass")
        self.assertEqual(self.grade({"type": "trace-present", "tool": "Read"}, BAD_EVENTS).status, "fail")

    def test_trace_grader_without_a_transcript_is_an_error(self):
        self.assertEqual(self.grade({"type": "trace-present", "tool": "Read"}, []).status, "error")

    def test_questions_max(self):
        self.assertEqual(self.grade({"type": "questions-max", "max": 1}, GOOD_EVENTS).status, "pass")
        g = self.grade({"type": "questions-max", "max": 1}, BAD_EVENTS)
        self.assertEqual(g.status, "fail")
        self.assertIn("3", g.reason)

    def test_cost_max(self):
        self.assertEqual(self.grade({"type": "cost-max", "max_usd": 1}, GOOD_EVENTS).status, "pass")
        self.assertEqual(self.grade({"type": "cost-max", "max_usd": 1}, BAD_EVENTS).status, "fail")
        self.assertEqual(self.grade({"type": "cost-max", "max_usd": 1}, [INIT]).status, "error")

    def test_isolation(self):
        self.assertEqual(self.grade({"type": "isolation"}, GOOD_EVENTS).status, "pass")
        two = [{"type": "system", "subtype": "init", "skills": ["dd:design-director", "design-director"]}]
        self.assertEqual(self.grade({"type": "isolation"}, two).status, "fail")
        hooked = [INIT, {"type": "system", "subtype": "hook_started", "hook_name": "SessionStart:startup"}]
        g = self.grade({"type": "isolation"}, hooked)
        self.assertEqual(g.status, "fail")
        self.assertIn("SessionStart", g.reason)
        self.assertEqual(self.grade({"type": "isolation"}, []).status, "error")

    def test_unknown_grader_is_an_error_not_a_pass(self):
        self.assertEqual(self.grade({"type": "taste"}).status, "error")


@unittest.skipUnless(NODE, "Node and playwright are not installed in this checkout")
class NodeGraders(Base):
    def test_dom_probe(self):
        self.write(self.work, "index.html", GOOD_HTML)
        ok = {"type": "dom-probe", "file": "index.html", "viewport": "390x844",
              "expr": "document.querySelectorAll('h1').length === 1 && innerWidth === 390"}
        self.assertEqual(self.grade(ok).status, "pass")
        bad = dict(ok, expr="document.documentElement.scrollWidth > innerWidth")
        self.assertEqual(self.grade(bad).status, "fail")
        broken = dict(ok, expr="this is not javascript(")
        self.assertEqual(self.grade(broken).status, "error")

    def test_max_count_complex_selector_uses_chromium(self):
        self.write(self.work, "index.html", BAD_HTML)
        g = self.grade({"type": "max-count", "selector": "main > h1:nth-child(n+2)", "max": 1})
        self.assertEqual(g.status, "fail")
        self.assertIn("2", g.reason)


class NodeMissing(Base):
    def test_node_graders_error_when_the_instrument_is_missing(self):
        self.write(self.work, "index.html", GOOD_HTML)
        old = os.environ.get("DDR_EVAL_NODE")
        os.environ["DDR_EVAL_NODE"] = str(self.root / "no-such-node")
        try:
            g = self.grade({"type": "dom-probe", "expr": "true"})
        finally:
            if old is None:
                os.environ.pop("DDR_EVAL_NODE", None)
            else:
                os.environ["DDR_EVAL_NODE"] = old
        self.assertEqual(g.status, "error")


# ------------------------------------------------------------ the runner, with the fake claude

class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.saved = {k: os.environ.get(k) for k in
                      ("DDR_HOME", "DDR_CLAUDE_BIN", "FAKE_CLAUDE_SCENARIOS", "FAKE_CLAUDE_ARGV_LOG")}
        os.environ["DDR_HOME"] = str(self.root / "home")
        fake = self.root / "claude"
        fake.write_text(f"#!/bin/sh\nexec {sys.executable!s} {FAKE!s} \"$@\"\n")
        fake.chmod(0o755)
        os.environ["DDR_CLAUDE_BIN"] = str(fake)
        scen = self.root / "scenarios"
        scen.mkdir()
        os.environ["FAKE_CLAUDE_SCENARIOS"] = str(scen)
        self.argv_log = self.root / "argv.jsonl"
        os.environ["FAKE_CLAUDE_ARGV_LOG"] = str(self.argv_log)
        (scen / "good.json").write_text(json.dumps({"files": {"index.html": GOOD_HTML}, "events": GOOD_EVENTS[1:]}))
        (scen / "bad.json").write_text(json.dumps({"files": {"index.html": BAD_HTML}, "events": BAD_EVENTS[1:]}))
        (scen / "slow.json").write_text(json.dumps({"events": [say("thinking")], "sleep": 30}))
        self.arms = {}
        for name in ("good", "bad", "slow"):
            d = self.root / "arms" / name / "design-director"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: design-director\ndescription: test arm\n---\nfake-scenario: {name}\n")
            self.arms[name] = d
        self.cases = self.root / "home" / "evals" / "cases"
        self.add_case("landing", 'budget_usd = 2\n', fixture={"brief.md": "A sauna by the sea.\n",
                                                              "tokens.css": ":root{--ink:#0b1b2b;--paper:#f6f5f1}\n"})

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def add_case(self, cid, extra="", fixture=None):
        d = self.cases / cid
        d.mkdir(parents=True)
        body = (f'id = "{cid}"\ntitle = "Landing for a sauna"\n'
                f'origin = "Ana 2026-11-04: \'the tagline should be the same size\'"\n'
                f'prompt = "Build a landing page from brief.md"\n{extra}')
        if fixture:
            body += 'fixture = "site"\n'
            for rel, text in fixture.items():
                p = d / "site" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
        body += ('\n[[grader]]\ntype = "file-exists"\nglob = "*.html"\n'
                 '\n[[grader]]\ntype = "text-absent"\nglob = "*.html"\npattern = "(?i)seamless"\n'
                 '\n[[grader]]\ntype = "questions-max"\nmax = 1\n'
                 '\n[[grader]]\ntype = "trace-absent"\ntool = "Bash"\nmatch = "vercel"\n'
                 '\n[[grader]]\ntype = "cost-max"\nmax_usd = 2\n')
        (d / "case.toml").write_text(body)

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = evals.main(list(argv))
        return rc, out.getvalue() + err.getvalue()

    def arm_args(self, *names):
        out = []
        for n in names:
            out += ["--arm", f"{n}={self.arms[n]}"]
        return out

    def test_list(self):
        rc, out = self.call("list")
        self.assertEqual(rc, 0)
        self.assertIn("landing", out)
        self.assertIn("5 graders", out)

    def test_dry_run_spends_nothing(self):
        rc, out = self.call("run", *self.arm_args("good", "bad"), "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("$4.00", out)
        self.assertFalse(self.argv_log.exists())

    def test_refuses_over_the_ceiling(self):
        rc, out = self.call("run", *self.arm_args("good", "bad"), "--max-total-usd", "3")
        self.assertEqual(rc, 2)
        self.assertIn("--max-total-usd", out)
        self.assertFalse(self.argv_log.exists())

    def test_rejects_a_bad_arm(self):
        rc, out = self.call("run", "--arm", f"x={self.root}")
        self.assertEqual(rc, 2)
        self.assertIn("SKILL.md", out)

    def test_run_grades_and_reports_both_arms(self):
        rc, out = self.call("run", *self.arm_args("good", "bad"), "--run-id", "r1")
        self.assertEqual(rc, 1, out)  # the bad arm failed graders
        run = self.root / "home" / "evals" / "runs" / "r1"
        results = json.loads((run / "results.json").read_text())
        by_arm = {r["arm"]: r for r in results["results"]}
        self.assertEqual(by_arm["good"]["failed"], 0, by_arm["good"]["grades"])
        self.assertEqual(by_arm["good"]["errors"], 0, by_arm["good"]["grades"])
        bad_failed = {g["type"] for g in by_arm["bad"]["grades"] if g["status"] == "fail"}
        self.assertEqual(bad_failed, {"text-absent", "questions-max", "trace-absent", "cost-max"})
        self.assertEqual(by_arm["good"]["cost_usd"], 0.8)
        self.assertEqual(by_arm["good"]["turns"], 5)
        for arm in ("good", "bad"):
            d = run / "landing" / arm
            self.assertTrue((d / "transcript.jsonl").exists())
            self.assertTrue((d / "stderr.txt").exists())
            self.assertTrue((d / "grades.json").exists())
            self.assertTrue((d / "workdir" / "brief.md").exists(), "fixture copied")
        report = (run / "report.md").read_text()
        self.assertIn("good", report)
        self.assertIn("questions-max", report)
        self.assertNotIn("\u2014", report)
        self.assertNotIn("\u2013", report)

    def test_the_launch_is_isolated_and_limited(self):
        self.call("run", *self.arm_args("good"), "--run-id", "r2")
        line = json.loads(self.argv_log.read_text().splitlines()[0])
        argv = line["argv"]
        self.assertEqual(argv[0], "-p")
        self.assertEqual(argv[1], evals.PREAMBLE + "\n\nBuild a landing page from brief.md")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "local")
        self.assertIn("--strict-mcp-config", argv)
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", argv)
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "2.0")
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Write,Edit,Glob,Grep,Bash,Skill")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Read,Write,Edit,Glob,Grep,Bash,Skill")
        settings = json.loads(argv[argv.index("--settings") + 1])
        self.assertIn("**/CLAUDE.md", settings["claudeMdExcludes"])
        self.assertFalse(settings["autoMemoryEnabled"])
        deny = argv[argv.index("--disallowedTools") + 1: ]
        for must in ("Bash(git push:*)", "Bash(git commit:*)", "Bash(brain:*)", "mcp__*", "Bash(vercel:*)", "Bash(wrangler:*)", "Bash(railway:*)",
                     "Bash(netlify:*)", "WebFetch", "WebSearch"):
            self.assertIn(must, deny)
        self.assertNotIn("bypassPermissions", " ".join(argv))
        self.assertNotIn("--dangerously-skip-permissions", argv)
        plugin = pathlib.Path(argv[argv.index("--plugin-dir") + 1])
        self.assertTrue((plugin / "skills" / "design-director" / "SKILL.md").exists())
        self.assertEqual(json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())["name"], "dd")
        self.assertTrue(line["cwd"].endswith(os.path.join("landing", "good", "workdir")))

    def test_timeout_kills_the_run(self):
        self.add_case("quick", 'timeout_min = 0.02\n')
        t0 = time.time()
        rc, out = self.call("run", *self.arm_args("slow"), "--case", "quick", "--run-id", "r3")
        self.assertLess(time.time() - t0, 20)
        r = json.loads((self.root / "home" / "evals" / "runs" / "r3" / "results.json").read_text())["results"][0]
        self.assertEqual(r["status"], "timeout")
        self.assertNotEqual(rc, 0)

    def test_missing_binary_is_could_not_run(self):
        os.environ["DDR_CLAUDE_BIN"] = str(self.root / "no-claude-here")
        rc, out = self.call("run", *self.arm_args("good"), "--run-id", "r4")
        self.assertEqual(rc, 2)

    def test_jobs_run_concurrently_and_agree(self):
        self.add_case("second")
        rc, out = self.call("run", *self.arm_args("good", "bad"), "--jobs", "3", "--run-id", "r5")
        results = json.loads((self.root / "home" / "evals" / "runs" / "r5" / "results.json").read_text())
        self.assertEqual(len(results["results"]), 4)
        rc, out = self.call("run", *self.arm_args("good"), "--jobs", "9", "--dry-run")
        self.assertEqual(rc, 2)

    def test_report_and_regrade(self):
        self.call("run", *self.arm_args("good", "bad"), "--run-id", "r6")
        run = self.root / "home" / "evals" / "runs" / "r6"
        (run / "report.md").unlink()
        rc, out = self.call("report", "r6")
        self.assertTrue((run / "report.md").exists())
        self.assertIn("Totals", out)
        # tighten a grader and regrade without spending
        toml = self.cases / "landing" / "case.toml"
        toml.write_text(toml.read_text().replace("max_usd = 2", "max_usd = 0.5"))
        before = self.argv_log.read_text()
        rc, out = self.call("report", "latest", "--regrade")
        self.assertEqual(self.argv_log.read_text(), before, "regrade must not launch claude")
        results = json.loads((run / "results.json").read_text())
        good = [r for r in results["results"] if r["arm"] == "good"][0]
        self.assertIn("cost-max", [g["type"] for g in good["grades"] if g["status"] == "fail"])

    def test_report_of_a_missing_run(self):
        rc, out = self.call("report", "nope")
        self.assertEqual(rc, 2)

    @unittest.skipUnless(NODE, "Node and playwright are not installed in this checkout")
    def test_sheet(self):
        self.call("run", *self.arm_args("good", "bad"), "--run-id", "r7")
        rc, out = self.call("sheet", "r7")
        self.assertEqual(rc, 0, out)
        png = self.root / "home" / "evals" / "runs" / "r7" / "landing" / "sheet.png"
        self.assertTrue(png.exists())
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_preamble_can_be_switched_off(self):
        self.call("run", *self.arm_args("good"), "--run-id", "p1", "--no-preamble")
        argv = json.loads(self.argv_log.read_text().splitlines()[-1])["argv"]
        self.assertEqual(argv[1], "Build a landing page from brief.md")
        self.add_case("plain", 'preamble = false\n')
        self.call("run", *self.arm_args("good"), "--case", "plain", "--run-id", "p2")
        argv = json.loads(self.argv_log.read_text().splitlines()[-1])["argv"]
        self.assertEqual(argv[1], "Build a landing page from brief.md")

    def test_each_run_gets_a_private_copy_of_ddr_home(self):
        real = self.root / "home"
        (real / "domains" / "saunas" / "shots").mkdir(parents=True)
        (real / "domains" / "saunas" / "domain.toml").write_text('slug = "saunas"\n')
        (real / "domains" / "saunas" / "shots" / "a.png").write_bytes(b"png")
        (real / "brands" / "acme").mkdir(parents=True)
        (real / "brands" / "acme" / "brand.toml").write_text('slug = "acme"\n')
        (real / "notes").mkdir()
        (real / "notes" / "house.jsonl").write_text('{"id": "o-000001"}\n')
        (real / "taste.jsonl").write_text('{"kind": "win"}\n')
        scen = pathlib.Path(os.environ["FAKE_CLAUDE_SCENARIOS"])
        good = json.loads((scen / "good.json").read_text())
        good["home_files"] = {"notes/house.jsonl": '{"id": "o-agent1"}\n', "taste.jsonl": '{"kind": "error"}\n'}
        (scen / "good.json").write_text(json.dumps(good))
        self.add_case("records", '\n[[grader]]\ntype = "text-present"\nroot = "ddr_home"\n'
                                 'glob = "notes/*.jsonl"\npattern = "o-agent1"\n')
        rc, out = self.call("run", *self.arm_args("good", "bad"), "--case", "records", "--run-id", "h1")
        # the real home is untouched
        self.assertEqual((real / "notes" / "house.jsonl").read_text(), '{"id": "o-000001"}\n')
        self.assertEqual((real / "taste.jsonl").read_text(), '{"kind": "win"}\n')
        logged = [json.loads(l) for l in self.argv_log.read_text().splitlines()]
        homes = {pathlib.Path(l["ddr_home"]) for l in logged}
        self.assertEqual(len(homes), 2, "one copy per arm")
        run = real / "evals" / "runs" / "h1" / "records"
        good_home = run / "good" / "ddr_home"
        self.assertIn(good_home, homes)
        self.assertTrue((good_home / "domains" / "saunas" / "domain.toml").exists())
        self.assertTrue((good_home / "brands" / "acme" / "brand.toml").exists())
        self.assertFalse((good_home / "domains" / "saunas" / "shots").exists())
        self.assertFalse((good_home / "evals").exists())
        self.assertIn("o-agent1", (good_home / "notes" / "house.jsonl").read_text())
        self.assertIn("o-000001", (good_home / "notes" / "house.jsonl").read_text())
        self.assertNotIn("o-agent1", (run / "bad" / "ddr_home" / "notes" / "house.jsonl").read_text())
        results = json.loads((real / "evals" / "runs" / "h1" / "results.json").read_text())
        by_arm = {r["arm"]: r for r in results["results"]}
        status = lambda arm: [g["status"] for g in by_arm[arm]["grades"] if g["type"] == "text-present"][0]
        self.assertEqual(status("good"), "pass")
        self.assertEqual(status("bad"), "fail")

    def git_repo(self):
        if not shutil.which("git"):
            self.skipTest("git not installed")
        repo = self.root / "brainrepo"
        skill = repo / "agent" / "skills" / "design-director"
        skill.mkdir(parents=True)
        g = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=/dev/null"]
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (skill / "SKILL.md").write_text("---\nname: design-director\ndescription: old\n---\nfake-scenario: good\n")
        (skill / "references").mkdir()
        (skill / "references" / "a.md").write_text("old reference\n")
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-q", "-m", "before"], check=True)
        subprocess.run(g + ["tag", "dd-before-v2"], check=True)
        (skill / "SKILL.md").write_text("---\nname: design-director\ndescription: new\n---\nfake-scenario: bad\n")
        subprocess.run(g + ["commit", "-q", "-am", "after"], check=True)
        return repo

    def test_git_arm_is_archived_at_its_ref(self):
        repo = self.git_repo()
        spec = f"before=git:{repo}@dd-before-v2:agent/skills/design-director"
        rc, out = self.call("run", "--arm", spec, "--arm", f"after={repo / 'agent' / 'skills' / 'design-director'}",
                            "--run-id", "g1")
        run = self.root / "home" / "evals" / "runs" / "g1"
        archived = run / "arms" / "before" / "agent" / "skills" / "design-director"
        self.assertIn("fake-scenario: good", (archived / "SKILL.md").read_text())
        self.assertTrue((archived / "references" / "a.md").exists())
        plugin_skill = run / "landing" / "before" / "plugin" / "skills" / "design-director" / "SKILL.md"
        self.assertIn("fake-scenario: good", plugin_skill.read_text())
        results = json.loads((run / "results.json").read_text())
        self.assertEqual(results["arms"]["before"]["git"]["ref"], "dd-before-v2")
        self.assertEqual(len(results["arms"]["before"]["git"]["commit"]), 40)
        by_arm = {r["arm"]: r for r in results["results"]}
        self.assertEqual(by_arm["before"]["failed"], 0, by_arm["before"]["grades"])
        self.assertGreater(by_arm["after"]["failed"], 0)

    def test_git_arm_problems_are_caught_before_spending(self):
        repo = self.git_repo()
        for spec, says in ((f"x=git:{repo}@no-such-tag:agent/skills/design-director", "not a commit"),
                           (f"x=git:{repo}@dd-before-v2:agent/skills/nothing", "SKILL.md"),
                           (f"x=git:{repo}", "git:<repo>@<ref>:<path>")):
            rc, out = self.call("run", "--arm", spec, "--dry-run")
            self.assertEqual(rc, 2, spec)
            self.assertIn(says, out)
        rc, out = self.call("run", "--arm", f"x=git:{repo}@dd-before-v2:agent/skills/design-director", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn("dd-before-v2", out)
        self.assertFalse((self.root / "home" / "evals" / "runs").exists(), "a dry run writes nothing")
        self.assertFalse(self.argv_log.exists())

    def test_ddr_dispatches_eval(self):
        import ddr
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ddr.main(["eval", "list"])
        self.assertEqual(rc, 0)
        self.assertIn("landing", out.getvalue())


if __name__ == "__main__":
    unittest.main()
