import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import gate  # noqa: E402
import taste  # noqa: E402

LAZY = ("contract", "claims", "brandpack")


def fake_report(tool, findings=(), exit_code=None):
    findings = list(findings)
    if exit_code is None:
        exit_code = 1 if any(f["severity"] == "error" for f in findings) else 0
    return {"ok": exit_code == 0, "exit": exit_code, "tool": tool, "findings": findings, "summary": ""}


def render_report(text="Hello there\nBook a sauna", smallest=16, sizes=4, words=120, runs=0, viewports=None):
    viewports = viewports or gate.DEFAULT_VIEWPORTS
    results = []
    for vp in viewports:
        for motion in ("no-preference", "reduce"):
            results.append({"url": "file:///x/index.html", "viewport": vp, "motion": motion, "status": 200,
                            "text": text, "words": words, "screens": 2.5, "maxConsecutiveTextOnly": runs,
                            "fontSizes": [16.0, 24.0, 40.0, 12.0][:sizes] + [float(20 + i) for i in range(max(0, sizes - 4))],
                            "smallestTextPx": smallest})
    return {"ok": True, "exit": 0, "tool": "shots", "findings": [], "summary": "", "results": results}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = pathlib.Path(self.tmp.name) / "proj"
        (self.proj / "src").mkdir(parents=True)
        (self.proj / "src" / "app.css").write_text("body { color: #111; }\n", encoding="utf-8")
        (self.proj / "index.html").write_text("<main><h1>Hello there</h1></main>\n", encoding="utf-8")
        self.home = pathlib.Path(self.tmp.name) / "ddrhome"
        self.env = mock.patch.dict(os.environ, {"DDR_HOME": str(self.home)})
        self.env.start()
        os.environ.pop("DD_TASTE", None)
        self.saved = {k: sys.modules.get(k) for k in LAZY}
        self.shots = mock.patch.object(gate, "_run_shots", side_effect=self.fake_shots)
        self.shots.start()
        self.render = render_report()
        self.render_rc = 0

    def tearDown(self):
        self.shots.stop()
        self.env.stop()
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        self.tmp.cleanup()

    def fake_shots(self, ctx, targets, json_out):
        pathlib.Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(json_out).write_text(json.dumps(self.render), encoding="utf-8")
        return self.render_rc, ""

    def stub(self, name, **funcs):
        mod = types.ModuleType(name)
        for k, v in funcs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        return mod

    def missing(self, name):
        sys.modules[name] = None   # makes `import name` raise ImportError

    def run_gate(self, *extra, src=True, target=True):
        argv = ["run", "--project", str(self.proj)]
        if src:
            argv += ["--src", str(self.proj / "src")]
        if target:
            argv += ["--file", str(self.proj / "index.html")]
        argv += list(extra)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gate.main(argv)
        receipt = json.loads((self.proj / ".design" / "gate" / "receipt.json").read_text(encoding="utf-8"))
        return rc, receipt, buf.getvalue()

    def step(self, receipt, name):
        return next(s for s in receipt["steps"] if s["name"] == name)

    def call(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gate.main(list(argv))
        return rc, buf.getvalue()


class Order(Base):
    def test_seven_steps_in_fixed_order_and_pass(self):
        rc, r, out = self.run_gate()
        self.assertEqual([s["name"] for s in r["steps"]],
                         ["contract", "claims", "lint", "brand", "render", "fidelity", "load"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual(self.step(r, "contract")["skipped"], "no contract")
        self.assertEqual(self.step(r, "claims")["skipped"], "no claims")
        self.assertEqual(self.step(r, "brand")["skipped"], "no brand")
        self.assertTrue(r["rendered"])

    def test_every_step_runs_after_a_failure(self):
        (self.proj / "src" / "bad.css").write_text("a{background:linear-gradient(90deg,#7c3aed,#2563eb)}\n")
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "lint")["exit"], 1)
        self.assertEqual(rc, 1)
        self.assertEqual(r["verdict"], "findings")
        self.assertEqual(self.step(r, "load")["exit"], 0)
        self.assertEqual(self.step(r, "render")["exit"], 0)

    def test_findings_beat_could_not_run(self):
        (self.proj / "src" / "bad.css").write_text("a{background:linear-gradient(90deg,#7c3aed,#2563eb)}\n")
        self.render_rc = 2
        self.render = {"ok": False, "exit": 2, "tool": "shots", "findings": [
            {"severity": "error", "rule": "tool.could-not-run", "message": "no playwright"}], "summary": "", "results": []}
        rc, r, _ = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertEqual(self.step(r, "render")["exit"], 2)
        self.assertEqual(self.step(r, "fidelity")["exit"], 2)
        self.assertEqual(self.step(r, "load")["exit"], 2)

    def test_could_not_run_is_never_a_pass(self):
        self.render_rc = 2
        self.render = {"ok": False, "exit": 2, "tool": "shots", "findings": [], "summary": "", "results": []}
        rc, r, _ = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertEqual(r["verdict"], "could-not-run")
        self.assertFalse(r["rendered"])

    def test_step_report_files_written(self):
        rc, r, _ = self.run_gate()
        run_dir = self.proj / ".design" / "gate" / r["run_id"]
        self.assertTrue((run_dir / "receipt.json").exists())
        self.assertTrue((run_dir / "report.json").exists())
        self.assertTrue((run_dir / "report.md").exists())
        for s in r["steps"]:
            self.assertTrue((self.proj / s["report"]).exists(), s["name"])
        self.assertEqual(r["shots_dir"], f".design/gate/{r['run_id']}/shots")

    def test_json_output_is_one_object(self):
        rc, r, out = self.run_gate("--json")
        data = json.loads(out)
        self.assertEqual(data["tool"], "gate")
        self.assertEqual(data["exit"], rc)
        self.assertEqual(data["ok"], rc == 0)
        self.assertEqual(data["receipt"]["run_id"], r["run_id"])


class LazySteps(Base):
    def write_contract(self):
        d = self.proj / ".design" / "brief"
        d.mkdir(parents=True, exist_ok=True)
        (d / "contract.json").write_text(json.dumps({"version": 1, "requirements": []}))

    def write_claims(self):
        d = self.proj / ".design" / "brief"
        d.mkdir(parents=True, exist_ok=True)
        (d / "claims.json").write_text(json.dumps({"version": 1, "claims": []}))

    def test_contract_checked_at_final_phase(self):
        self.write_contract()
        seen = {}

        def check(project, phase):
            seen["phase"] = phase
            return fake_report("contract", [{"severity": "error", "rule": "req.open", "message": "R1 open"}])
        self.stub("contract", check=check, exact_copy=lambda p: [])
        rc, r, _ = self.run_gate()
        self.assertEqual(seen["phase"], "final")
        self.assertEqual(self.step(r, "contract")["exit"], 1)
        self.assertEqual(self.step(r, "contract")["errors"], 1)
        self.assertEqual(rc, 1)

    def test_contract_module_missing_with_input_is_exit_2(self):
        self.write_contract()
        self.missing("contract")
        rc, r, _ = self.run_gate()
        s = self.step(r, "contract")
        self.assertEqual(s["exit"], 2)
        self.assertIsNone(s["skipped"])
        self.assertEqual(rc, 2)
        rep = json.loads((self.proj / s["report"]).read_text())
        self.assertIn("could not run: contract missing", rep["findings"][0]["message"])
        self.assertEqual(rep["findings"][0]["rule"], "tool.could-not-run")

    def test_contract_module_missing_without_input_is_skipped(self):
        self.missing("contract")
        self.missing("claims")
        self.missing("brandpack")
        rc, r, _ = self.run_gate()
        for name in ("contract", "claims", "brand"):
            self.assertIsNotNone(self.step(r, name)["skipped"], name)
            self.assertEqual(self.step(r, name)["exit"], 0)
        self.assertEqual(rc, 0)

    def test_claims_get_src_paths(self):
        self.write_claims()
        seen = {}

        def check(project, src_paths=()):
            seen["src"] = [str(p) for p in src_paths]
            return fake_report("claims")
        self.stub("claims", check=check)
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "claims")["exit"], 0)
        self.assertIn(str((self.proj / "src").resolve()), seen["src"])

    def test_claims_module_missing_with_input_is_exit_2(self):
        self.write_claims()
        self.missing("claims")
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "claims")["exit"], 2)

    def test_brand_from_flag(self):
        seen = {}

        def lint(paths, slug):
            seen["slug"] = slug
            return fake_report("brand-lint", [{"severity": "warn", "rule": "color.extended", "message": "x"}])
        self.stub("brandpack", lint=lint)
        rc, r, _ = self.run_gate("--brand", "draft")
        self.assertEqual(seen["slug"], "draft")
        self.assertEqual(self.step(r, "brand")["warnings"], 1)
        self.assertEqual(r["brand"], "draft")
        self.assertEqual(rc, 0)

    def test_brand_from_project_file(self):
        (self.proj / ".design").mkdir(exist_ok=True)
        (self.proj / ".design" / "brand").write_text("house\n")
        seen = {}
        self.stub("brandpack", lint=lambda paths, slug: seen.setdefault("slug", slug) and fake_report("brand-lint"))
        rc, r, _ = self.run_gate()
        self.assertEqual(seen["slug"], "house")

    def test_brand_pack_missing_is_exit_2(self):
        def lint(paths, slug):
            raise KeyError(slug)
        self.stub("brandpack", lint=lint)
        rc, r, _ = self.run_gate("--brand", "nope")
        self.assertEqual(self.step(r, "brand")["exit"], 2)

    def test_brandpack_module_missing_with_brand_is_exit_2(self):
        self.missing("brandpack")
        rc, r, _ = self.run_gate("--brand", "draft")
        self.assertEqual(self.step(r, "brand")["exit"], 2)


class Lint(Base):
    def test_missing_src_is_exit_2(self):
        rc, r, _ = self.run_gate("--src", str(self.proj / "nope"))
        self.assertEqual(self.step(r, "lint")["exit"], 2)

    def test_no_src_uses_file_targets(self):
        rc, r, _ = self.run_gate(src=False)
        self.assertEqual(self.step(r, "lint")["exit"], 0)
        self.assertIn("index.html", r["inputs"])

    def test_nothing_to_lint_is_exit_2(self):
        rc, r, _ = self.run_gate("--url", "http://localhost:1", src=False, target=False)
        self.assertEqual(self.step(r, "lint")["exit"], 2)

    def test_project_lint_config_is_used(self):
        (self.proj / ".design").mkdir(exist_ok=True)
        (self.proj / ".design" / "lint.toml").write_text('disable = ["purple-blue-gradient"]\n')
        (self.proj / "src" / "bad.css").write_text("a{background:linear-gradient(90deg,#7c3aed,#2563eb)}\n")
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "lint")["exit"], 0)


class Render(Base):
    def test_no_target_is_exit_2_for_render_fidelity_load(self):
        rc, r, _ = self.run_gate(target=False)
        for name in ("render", "fidelity", "load"):
            s = self.step(r, name)
            self.assertEqual(s["exit"], 2, name)
        self.assertEqual(rc, 2)

    def test_no_render_with_why_skips(self):
        rc, r, _ = self.run_gate("--no-render", "--why", "a PDF, checked by hand", target=False)
        for name in ("render", "fidelity", "load"):
            s = self.step(r, name)
            self.assertEqual(s["exit"], 0)
            self.assertIn("a PDF", s["skipped"])
        self.assertEqual(rc, 0)
        self.assertFalse(r["rendered"])

    def test_no_render_needs_why(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = gate.main(["run", "--project", str(self.proj), "--src", str(self.proj / "src"), "--no-render"])
        self.assertEqual(rc, 2)

    def test_missing_file_target_is_exit_2(self):
        rc, r, _ = self.run_gate("--file", str(self.proj / "gone.html"), target=False)
        self.assertEqual(self.step(r, "render")["exit"], 2)

    def test_render_findings_count(self):
        self.render_rc = 1
        self.render["exit"] = 1
        self.render["findings"] = [{"severity": "error", "rule": "render.overflow", "message": "scrolls sideways"}]
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "render")["exit"], 1)
        self.assertEqual(self.step(r, "render")["errors"], 1)
        self.assertTrue(r["rendered"])

    def test_render_warnings_and_errors_keep_their_severity(self):
        self.render_rc = 1
        self.render["exit"] = 1
        self.render["findings"] = [
            {"severity": "error", "rule": "render.tap-target", "message": "2+ tap targets under 24px"},
            {"severity": "warn", "rule": "render.tap-target-44", "message": "3+ tap targets under 44px"}]
        rc, r, _ = self.run_gate()
        s = self.step(r, "render")
        self.assertEqual((s["errors"], s["warnings"]), (1, 1))
        rep = json.loads((self.proj / s["report"]).read_text())
        self.assertEqual({f["rule"]: f["severity"] for f in rep["findings"]},
                         {"render.tap-target": "error", "render.tap-target-44": "warn"})

    def test_render_warnings_alone_pass(self):
        self.render["findings"] = [{"severity": "warn", "rule": "render.tap-target-44", "message": "under 44px"}]
        rc, r, _ = self.run_gate()
        s = self.step(r, "render")
        self.assertEqual((s["exit"], s["warnings"]), (0, 1))
        self.assertEqual(rc, 0)

    def test_viewports_flag(self):
        self.render = render_report(viewports=["desktop", "phone"])
        rc, r, _ = self.run_gate("--viewports", "desktop,phone")
        self.assertEqual(r["viewports"], ["desktop", "phone"])
        self.assertEqual(rc, 0)


class Fidelity(Base):
    def test_copy_file_lines_must_appear(self):
        (self.proj / "copy.txt").write_text("Hello there\nBook   a sauna\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        self.assertEqual(self.step(r, "fidelity")["exit"], 0)
        self.assertIn("copy.txt", r["inputs"])

    def test_missing_line_is_error(self):
        (self.proj / "copy.txt").write_text("Hello there\nDecisions in 24 hours\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        s = self.step(r, "fidelity")
        self.assertEqual(s["exit"], 1)
        self.assertEqual(s["errors"], 1)

    def test_recased_line_is_error(self):
        self.render = render_report(text="HELLO THERE")
        (self.proj / "copy.txt").write_text("Hello there\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        s = self.step(r, "fidelity")
        self.assertEqual(s["exit"], 1)
        rep = json.loads((self.proj / s["report"]).read_text())
        self.assertIn("re-cased", rep["findings"][0]["message"])

    def test_contract_exact_copy_is_checked(self):
        d = self.proj / ".design" / "brief"
        d.mkdir(parents=True)
        (d / "contract.json").write_text("{}")
        self.stub("contract", check=lambda p, phase: fake_report("contract"),
                  exact_copy=lambda p: ["Book a sauna", "Not on the page"])
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "fidelity")["errors"], 1)

    def test_only_desktop_text_counts(self):
        rep = render_report(text="nothing")
        for row in rep["results"]:
            if row["viewport"] == "phone-390x844":
                row["text"] = "Hello there"
        self.render = rep
        (self.proj / "copy.txt").write_text("Hello there\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        self.assertEqual(self.step(r, "fidelity")["exit"], 1)

    def test_missing_copy_file_is_exit_2(self):
        rc, r, _ = self.run_gate("--copy", str(self.proj / "nope.txt"))
        self.assertEqual(self.step(r, "fidelity")["exit"], 2)

    def test_no_lines_skips(self):
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "fidelity")["skipped"], "no copy to check")


class Load(Base):
    def test_small_text_is_error(self):
        self.render = render_report(smallest=11)
        rc, r, _ = self.run_gate()
        self.assertEqual(self.step(r, "load")["exit"], 1)

    def test_text_under_14_is_warning(self):
        self.render = render_report(smallest=13)
        rc, r, _ = self.run_gate()
        s = self.step(r, "load")
        self.assertEqual(s["exit"], 0)
        self.assertGreaterEqual(s["warnings"], 1)

    def test_metrics_recorded(self):
        self.render = render_report(words=640, runs=3, sizes=6)
        rc, r, _ = self.run_gate()
        s = self.step(r, "load")
        rep = json.loads((self.proj / s["report"]).read_text())
        m = rep["metrics"]
        self.assertEqual(m["words_main"], 640)
        self.assertEqual(m["consecutive_text_only"], 3)
        self.assertEqual(m["phone_font_sizes"], 6)
        self.assertEqual(m["phone_smallest_px"], 16)
        self.assertIn("phone-390x844", m["screens"])
        self.assertGreaterEqual(s["warnings"], 2)   # long page and a wall of text sections


class Inputs(Base):
    def test_hashes_design_files_and_skips_build_dirs(self):
        (self.proj / "src" / "node_modules").mkdir()
        (self.proj / "src" / "node_modules" / "x.css").write_text("x")
        (self.proj / "src" / "notes.py").write_text("print(1)")
        rc, r, _ = self.run_gate()
        self.assertIn("src/app.css", r["inputs"])
        self.assertIn("index.html", r["inputs"])
        self.assertNotIn("src/node_modules/x.css", r["inputs"])
        self.assertNotIn("src/notes.py", r["inputs"])
        self.assertEqual(len(r["inputs"]["src/app.css"]), 64)

    def test_contract_and_claims_hashed(self):
        d = self.proj / ".design" / "brief"
        d.mkdir(parents=True)
        (d / "claims.json").write_text('{"version": 1, "claims": []}')
        self.stub("claims", check=lambda project, src_paths=(): fake_report("claims"))
        rc, r, _ = self.run_gate()
        self.assertIn(".design/brief/claims.json", r["inputs"])


class Verify(Base):
    def test_no_receipt_is_exit_2(self):
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 2)

    def test_fresh_pass_is_ok(self):
        self.run_gate()
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 0, out)

    def test_changed_input_is_stale(self):
        self.run_gate()
        (self.proj / "src" / "app.css").write_text("body { color: #222; }\n")
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 1)
        self.assertIn("src/app.css", out)
        self.assertIn("changed", out)

    def test_vanished_input_is_stale(self):
        self.run_gate()
        (self.proj / "src" / "app.css").unlink()
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 1)
        self.assertIn("vanished", out)

    def test_new_file_under_src_is_stale(self):
        self.run_gate()
        (self.proj / "src" / "new.css").write_text("a{}")
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 1)
        self.assertIn("src/new.css", out)

    def test_failed_verdict_is_1(self):
        (self.proj / "src" / "bad.css").write_text("a{background:linear-gradient(90deg,#7c3aed,#2563eb)}\n")
        self.run_gate()
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 1)

    def test_uncovered_file_is_1(self):
        self.run_gate()
        (self.proj / "other.css").write_text("a{}")
        rc, out = self.call("verify", "--project", str(self.proj), "--files", str(self.proj / "other.css"))
        self.assertEqual(rc, 1)
        self.assertIn("other.css", out)
        rc, out = self.call("verify", "--project", str(self.proj), "--files", "src/app.css")
        self.assertEqual(rc, 0, out)

    def test_require_review(self):
        rc0, r, _ = self.run_gate()
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 1)
        self.assertIn("review", out)
        rdir = self.proj / ".design" / "review"
        rdir.mkdir(parents=True)
        (rdir / f"{r['run_id']}.json").write_text(json.dumps({"verdict": "fix-then-ship"}))
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 1)
        (rdir / f"{r['run_id']}.json").write_text(json.dumps({"verdict": "ship"}))
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 0, out)

    def test_json(self):
        self.run_gate()
        (self.proj / "src" / "app.css").write_text("changed")
        rc, out = self.call("verify", "--project", str(self.proj), "--json")
        data = json.loads(out)
        self.assertEqual(data["tool"], "gate-verify")
        self.assertEqual(data["exit"], 1)
        self.assertTrue(any("src/app.css" in f["message"] for f in data["findings"]))


class Waive(Base):
    def test_waive_writes_receipt_and_taste_error(self):
        rc, out = self.call("waive", "--project", str(self.proj), "--reason", "client signed off by phone",
                            "--src", str(self.proj / "src"))
        self.assertEqual(rc, 0, out)
        r = json.loads((self.proj / ".design" / "gate" / "receipt.json").read_text())
        self.assertEqual(r["verdict"], "waived")
        self.assertEqual(r["waived"]["reason"], "client signed off by phone")
        self.assertIn("src/app.css", r["inputs"])
        self.assertTrue((self.proj / ".design" / "gate" / r["run_id"] / "receipt.json").exists())
        events = taste.read(self.home / "taste.jsonl")
        self.assertEqual(events[-1]["kind"], "error")
        self.assertEqual(events[-1]["what"], "gate waived: client signed off by phone")

    def test_waived_receipt_verifies_until_inputs_change(self):
        self.call("waive", "--project", str(self.proj), "--reason", "print job, no web render",
                  "--src", str(self.proj / "src"))
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 0, out)
        self.assertIn("waived", out)
        (self.proj / "src" / "app.css").write_text("x")
        rc, out = self.call("verify", "--project", str(self.proj))
        self.assertEqual(rc, 1)

    def test_waive_needs_reason(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc, out = self.call("waive", "--project", str(self.proj), "--reason", "  ")
        self.assertEqual(rc, 2)


def _playwright_ready():
    root = TOOLS.parent
    if not shutil.which("node") or not (root / "node_modules" / "playwright").exists():
        return False
    try:
        out = subprocess.run(["node", "-e", "import('playwright').then(p=>p.chromium.executablePath()).then(x=>"
                              "console.log(require('fs').existsSync(x)?'yes':'no'))"],
                             cwd=str(root), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip() == "yes"


@unittest.skipUnless(_playwright_ready(), "needs node, npm install and a playwright chromium")
class RealRender(unittest.TestCase):
    """The gate against a real page in a real Chromium."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = pathlib.Path(self.tmp.name)
        src = TOOLS.parent / "tests" / "fixtures" / "gate"
        shutil.copytree(src, self.proj / "site")

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_gate_run_and_stale_verify(self):
        site = self.proj / "site"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gate.main(["run", "--project", str(self.proj), "--src", str(site), "--file", str(site / "index.html"),
                            "--copy", str(site / "copy.txt"), "--viewports", "desktop-1440x900,phone-390x844"])
        r = json.loads((self.proj / ".design" / "gate" / "receipt.json").read_text())
        steps = {s["name"]: s for s in r["steps"]}
        self.assertEqual(steps["render"]["exit"], 0, buf.getvalue())
        self.assertEqual(steps["fidelity"]["exit"], 0, buf.getvalue())
        self.assertIn(steps["load"]["exit"], (0, 1))
        self.assertEqual(rc, 0, buf.getvalue())
        shots = list((self.proj / r["shots_dir"]).glob("*__fold.png"))
        self.assertTrue(any("__phone-390x844__" in p.name for p in shots))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["verify", "--project", str(self.proj)]), 0)
        (site / "styles.css").write_text((site / "styles.css").read_text() + "\n/* edited */\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["verify", "--project", str(self.proj)]), 1)


if __name__ == "__main__":
    unittest.main()
