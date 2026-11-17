import contextlib
import io
import json
import re
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


def audit_report(items=None, exit_code=0):
    """What tools/audit.mjs writes: one viewport here, with the checks given as {check: [items]}."""
    items = items if items is not None else {
        "clip.text": [{"selector": "main > span.word", "text": "July", "rect": [16, 344, 427, 222], "stop": 0,
                       "score": 26, "detail": "descenders cut by 26px by main > div.mask"}],
        "tap.small": [{"selector": "button.ic", "text": "Menu", "rect": [16, 8, 30, 30], "stop": 0, "score": 14,
                       "detail": "30x30px, under 44x44"}] * 2,
        "contrast": [{"selector": "p.faint", "text": "Indicative", "rect": [16, 638, 177, 20], "stop": 0,
                      "score": 2.8, "detail": "1.67:1 on the pixels behind it (needs 4.5:1)"}]}
    checks = {k: {"count": len(v), "cut": 0, "items": v} for k, v in items.items()}
    total = sum(c["count"] for c in checks.values())
    return {"ok": exit_code == 0, "exit": exit_code, "tool": "audit", "target": "file:///x/index.html", "total": total,
            "summary": f"{total} measured problems",
            "viewports": [{"viewport": "mac-1512x820", "stops": 4, "checks": checks,
                           "fold": {"headings": 1, "primaryActions": 1, "words": 40,
                                    "largest": {"px": 56, "selector": "h1", "text": "Draft"}}}]}


def motion_report(verdict="NOT SMOOTH", exit_code=0):
    return {"ok": exit_code == 0, "exit": exit_code, "tool": "motion", "target": "file:///x/index.html",
            "viewport": "mac-1512x820", "summary": verdict,
            "result": {"verdict": verdict, "refreshMs": 16.7, "headless": True,
                       "phases": {"idle": {"frames": 90, "p50": 16.7, "p95": 16.8, "p99": 16.8, "worst": 16.8, "dropped": 0, "ok": True},
                                  "scroll": {"frames": 134, "p50": 16.7, "p95": 16.8, "p99": 16.8, "worst": 150, "dropped": 8, "ok": False}},
                       "sections": {"middle": {"frames": 65, "p95": 16.8, "worst": 150, "ok": False}},
                       "longTasks": {"count": 1, "over100": 1, "items": [{"at": 2500, "ms": 150}]},
                       "layoutShift": {"total": 0, "count": 0, "sources": []}, "layoutAnimations": []}}


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
        self.measured = {"audit": audit_report(), "motion": motion_report()}
        self.measure_calls = []
        self.measure = mock.patch.object(gate, "_run_measure", side_effect=self.fake_measure)
        self.measure.start()

    def tearDown(self):
        self.measure.stop()
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

    def fake_measure(self, ctx, kind, target, json_out):
        self.measure_calls.append((kind, target))
        rep = self.measured.get(kind)
        if rep is not None:
            pathlib.Path(json_out).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(json_out).write_text(json.dumps(rep), encoding="utf-8")
        return (rep or {}).get("exit", 2), ""

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

    def test_a_pass_hands_over_to_the_critic(self):
        rc, r, out = self.run_gate()
        self.assertEqual(rc, 0, out)
        md = (self.proj / ".design" / "gate" / r["run_id"] / "report.md").read_text()
        for text in (out, md):
            self.assertIn("critic", text)
            self.assertNotIn("score", text.lower())

    def test_step_report_files_written(self):
        rc, r, _ = self.run_gate()
        run_dir = self.proj / ".design" / "gate" / r["run_id"]
        self.assertTrue((run_dir / "receipt.json").exists())
        self.assertTrue((run_dir / "report.json").exists())
        self.assertTrue((run_dir / "report.md").exists())
        for s in r["steps"]:
            self.assertTrue((self.proj / s["report"]).exists(), s["name"])
        shots = json.loads((run_dir / "shots.json").read_text())
        self.assertEqual(shots["tool"], "shots")   # the step report must not overwrite the raw render report
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
        rc, r, _ = self.run_gate("--brand", "acme")
        self.assertEqual(seen["slug"], "acme")
        self.assertEqual(self.step(r, "brand")["warnings"], 1)
        self.assertEqual(r["brand"], "acme")
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
        rc, r, _ = self.run_gate("--brand", "acme")
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


class Measured(Base):
    """ddr audit and ddr motion run with the gate, report only: saved with the run, summarised, never the verdict."""

    def test_findings_do_not_change_a_pass(self):
        rc, r, out = self.run_gate()
        self.assertEqual(rc, 0, out)
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual([s["name"] for s in r["steps"]], list(gate.STEPS))

    def test_saved_with_the_run(self):
        rc, r, _ = self.run_gate()
        run_dir = self.proj / ".design" / "gate" / r["run_id"]
        self.assertEqual(json.loads((run_dir / "audit.json").read_text())["targets"][0]["tool"], "audit")
        self.assertEqual(json.loads((run_dir / "motion.json").read_text())["tool"], "motion")
        m = r["measured"]
        self.assertEqual(m["audit"]["counts"], {"clip.text": 1, "contrast": 1, "tap.small": 2})
        self.assertEqual(m["audit"]["total"], 4)
        self.assertEqual(m["motion"]["verdict"], "NOT SMOOTH")
        self.assertEqual(m["audit"]["report"], f".design/gate/{r['run_id']}/audit.json")

    def test_summary_names_counts_and_the_three_worst(self):
        rc, r, out = self.run_gate()
        self.assertIn("report only", out)
        self.assertIn("clip.text 1", out)
        worst = r["measured"]["audit"]["worst"]
        self.assertEqual(len(worst), 3)
        self.assertIn("July", worst[0])            # cut words first
        self.assertIn("contrast", worst[1])
        self.assertIn("NOT SMOOTH", out)
        self.assertIn("150", out)
        md = (self.proj / ".design" / "gate" / r["run_id"] / "report.md").read_text()
        self.assertIn("July", md)

    def test_could_not_measure_is_said_but_does_not_fail_the_gate(self):
        self.measured = {"audit": None, "motion": None}
        rc, r, out = self.run_gate()
        self.assertEqual(rc, 0, out)
        self.assertEqual(r["measured"]["audit"]["exit"], 2)
        self.assertIn("could not", out)

    def test_skipped_without_a_render(self):
        rc, r, _ = self.run_gate("--no-render", "--why", "a PDF", target=False)
        self.assertEqual(self.measure_calls, [])
        self.assertIn("render", r["measured"]["skipped"])

    def test_no_measure_flag_skips_them(self):
        rc, r, _ = self.run_gate("--no-measure")
        self.assertEqual(self.measure_calls, [])
        self.assertEqual(r["measured"]["skipped"], "--no-measure")
        self.assertEqual(rc, 0)

    def test_audit_uses_the_gate_viewports_when_named(self):
        captured = {}
        orig = self.fake_measure

        def spy(ctx, kind, target, json_out):
            captured[kind] = ctx["measure_viewports"]
            return orig(ctx, kind, target, json_out)
        self.measure.stop()
        self.measure = mock.patch.object(gate, "_run_measure", side_effect=spy)
        self.measure.start()
        self.render = render_report(viewports=["mac-1512x820", "phone-390x844"])
        self.run_gate("--viewports", "mac-1512x820,phone-390x844")
        self.assertEqual(captured["audit"], ["mac-1512x820", "phone-390x844"])
        self.run_gate()
        self.assertEqual(captured["audit"], ["mac-1512x820", "mac-1440x780", "phone-390x844"])

    def test_json_output_carries_the_summary(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gate.main(["run", "--project", str(self.proj), "--src", str(self.proj / "src"),
                       "--file", str(self.proj / "index.html"), "--json"])
        rep = json.loads(buf.getvalue())
        self.assertEqual(rep["measured"]["motion"]["verdict"], "NOT SMOOTH")

    def test_storage_state_reaches_every_browser_step(self):
        state = self.proj / "state.json"
        state.write_text('{"cookies": [], "origins": []}')
        ctx = {"storage_state": str(state), "run_dir": self.proj, "viewports": ["mac-1512x820"],
               "measure_viewports": ["mac-1512x820"], "project": self.proj}
        self.assertIn(str(state), gate._shots_argv(ctx, [("url", "http://localhost:8000/x")], self.proj / "s.json"))
        for kind in ("audit", "motion"):
            argv = gate._measure_argv(ctx, kind, ("url", "http://localhost:8000/x"), self.proj / "m.json")
            self.assertEqual(argv[argv.index("--storage-state") + 1], str(state))

    def test_missing_storage_state_is_exit_2(self):
        rc, r, _ = self.run_gate("--storage-state", str(self.proj / "nope.json"))
        self.assertEqual(self.step(r, "render")["exit"], 2)
        self.assertEqual(rc, 2)


class Viewports(unittest.TestCase):
    """The gate's default sizes and the renderer's must agree, and a big monitor is one of them."""

    def shots_source(self):
        return (pathlib.Path(gate.__file__).parent / "shots.mjs").read_text(encoding="utf-8")

    def test_defaults_match_the_renderer(self):
        src = self.shots_source()
        default = re.search(r"const DEFAULT = '([^']+)'", src).group(1).split(",")
        self.assertEqual(default, gate.DEFAULT_VIEWPORTS)

    def test_every_default_is_a_known_viewport(self):
        # the table moved to viewports.mjs so shots, audit and motion share one list of sizes
        src = (pathlib.Path(gate.__file__).parent / "viewports.mjs").read_text(encoding="utf-8")
        table = src[src.index("const VIEWPORTS = {"):src.index("};", src.index("const VIEWPORTS = {"))]
        known = set(re.findall(r"^\s*'?([a-z][a-z0-9-]*)'?\s*:", table, re.M))
        for v in gate.DEFAULT_VIEWPORTS + ["monitor-2560x1440", "tablet-820x1180"]:
            self.assertIn(v, known)

    def test_a_monitor_is_rendered_by_default(self):
        self.assertIn("monitor-1920x1080", gate.DEFAULT_VIEWPORTS)

    def test_a_monitor_is_not_picked_as_the_desktop(self):
        self.assertEqual(gate.desktop_viewport(["monitor-1920x1080", "mac-1512x820"]), "mac-1512x820")


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

    def test_css_uppercase_is_not_a_recasing(self):
        # review finding 2: innerText applies text-transform, so the gate reads the authored text
        rep = render_report(text="DECISIONS IN 24 HOURS")
        for row in rep["results"]:
            row["textAuthored"] = "Decisions in 24 hours"
        self.render = rep
        (self.proj / "copy.txt").write_text("Decisions in 24 hours\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        self.assertEqual(self.step(r, "fidelity")["exit"], 0)

    def test_authored_recasing_is_still_an_error(self):
        rep = render_report(text="DECISIONS IN 24 HOURS")
        for row in rep["results"]:
            row["textAuthored"] = "Decisions In 24 Hours"
        self.render = rep
        (self.proj / "copy.txt").write_text("Decisions in 24 hours\n")
        rc, r, _ = self.run_gate("--copy", str(self.proj / "copy.txt"))
        self.assertEqual(self.step(r, "fidelity")["exit"], 1)

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
        good = {"kind": "critic", "verdict": "ship", "cold_read_matches": True,
                "cold_read": {"what_it_is": "a page", "who_for": "people", "next_action": "book"},
                "ask": [{"item": "x", "met": "yes", "evidence": "phone fold"}], "defects": []}
        (rdir / f"{r['run_id']}.json").write_text(json.dumps(good))
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 0, out)

    def test_a_bare_ship_file_is_not_a_review(self):
        rc0, r, _ = self.run_gate()
        rdir = self.proj / ".design" / "review"
        rdir.mkdir(parents=True)
        for bad in ({"verdict": "ship"}, {"verdict": "ship", "ask": "x"}, ["ship"], {"scores": {}, "verdict": "ship"}):
            (rdir / f"{r['run_id']}.json").write_text(json.dumps(bad))
            rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
            self.assertEqual(rc, 1, out)
            self.assertIn("gate.review", out)

    def test_no_review_points_at_the_critic_not_at_scores(self):
        self.run_gate()
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 1)
        self.assertIn("critic", out)
        self.assertNotIn("Score it", out)

    def test_a_critic_record_whose_stored_verdict_breaks_the_rule_does_not_pass(self):
        rc0, r, _ = self.run_gate()
        rdir = self.proj / ".design" / "review"
        rdir.mkdir(parents=True)
        rec = {"kind": "critic", "cold_read_matches": True, "ask": [{"item": "x", "met": "yes", "evidence": "e"}],
               "cold_read": {"what_it_is": "a page", "who_for": "people", "next_action": "book"},
               "defects": [{"where": "a", "what": "b", "fix": "c", "severity": "must-fix"}], "verdict": "ship"}
        (rdir / f"{r['run_id']}.json").write_text(json.dumps(rec))
        rc, out = self.call("verify", "--project", str(self.proj), "--require-review")
        self.assertEqual(rc, 1, out)
        self.assertIn("fix-then-ship", out)
        rec["defects"][0]["resolved"] = "next run: fixed"
        (rdir / f"{r['run_id']}.json").write_text(json.dumps(rec))
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
        # the report-only measures ran for real, on the gate's own viewports, and are saved with the run
        m = r["measured"]
        self.assertEqual(m["audit"]["exit"], 0, m)
        self.assertEqual(m["audit"]["viewports"], ["desktop-1440x900", "phone-390x844"])
        self.assertIn(m["motion"]["verdict"], ("SMOOTH", "NOT SMOOTH"), m)
        self.assertTrue((self.proj / m["audit"]["report"]).is_file())
        self.assertIn("report only", buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["verify", "--project", str(self.proj)]), 0)
        (site / "styles.css").write_text((site / "styles.css").read_text() + "\n/* edited */\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["verify", "--project", str(self.proj)]), 1)


if __name__ == "__main__":
    unittest.main()
