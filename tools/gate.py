"""ddr gate: the checks that must pass before design work ships, in an order fixed in code.

    ddr gate run --src src/ --file index.html [--copy copy.txt] [--brand acme]
    ddr gate run --src src/ --url http://localhost:3000 [--viewports mac-1512x820,phone-390x844]
    ddr gate run --src print/ --no-render --why "a PDF, not a web page"
    ddr gate verify [--require-review] [--files src/a.css ...]     # the deploy hook calls this
    ddr gate waive --reason "<why>" [--src ...]                    # honest, visible, logged

Seven steps run every time, in this order, and each runs even when an earlier one failed:
contract, claims, lint, brand, render, fidelity, load. Each exits 0 (pass, warnings
allowed), 1 (findings) or 2 (could not run). The gate exits 1 if any step found something,
otherwise 2 if any step could not run, otherwise 0. A check that could not look is not a
check that found nothing, so exit 2 is never a pass.

The receipt (.design/gate/receipt.json) hashes every input, so `verify` can tell when the
work changed after it was checked. The exit-code convention follows LangChain's open-source
design agent (Apache 2.0), workspace/tools/README.md.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import time

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

STEPS = ("contract", "claims", "lint", "brand", "render", "fidelity", "load")
DEFAULT_VIEWPORTS = ["mac-1512x820", "mac-1440x780", "desktop-1440x900", "monitor-1920x1080", "phone-390x844",
                     "phone-landscape-844x390", "small-320x568"]
DESIGN_EXTS = {".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte",
               ".astro", ".svg", ".md", ".mdx", ".json",
               # assets: a picture or a font swapped after review must make the receipt stale
               ".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
               ".mp4", ".webm", ".mov", ".lottie"}
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".design"}
RENDER_TIMEOUT = 900   # seconds for the whole shots run

# Load thresholds. The text-size ones come from SPEC.md; the others are prompts to look, so warn only.
TEXT_ERROR_PX = 12
TEXT_WARN_PX = 14
WORDS_WARN = 400
TEXT_RUN_WARN = 1
FONT_SIZES_WARN = 8


# ---------------------------------------------------------------- small helpers

def _finding(severity, rule, message, file=None, line=None, **extra):
    f = {"severity": severity, "rule": rule, "message": message}
    if file is not None:
        f["file"] = file
    if line is not None:
        f["line"] = line
    f.update(extra)
    return f


def _step(name, exit_code=0, skipped=None, findings=(), **extra):
    findings = list(findings)
    s = {"name": name, "exit": exit_code, "skipped": skipped,
         "errors": sum(1 for f in findings if f.get("severity") == "error" and f.get("rule") != "tool.could-not-run"),
         "warnings": sum(1 for f in findings if f.get("severity") == "warn"),
         "findings": findings}
    s.update(extra)
    return s


def _skip(name, why):
    return _step(name, 0, skipped=why)


def _cannot(name, why):
    return _step(name, 2, findings=[_finding("error", "tool.could-not-run", why)])


def _from_report(name, rep):
    """Turn a tool's JSON report into a step, trusting its exit but never a malformed one."""
    if not isinstance(rep, dict) or rep.get("exit") not in (0, 1, 2):
        return _cannot(name, f"could not run: {name} returned no valid report")
    findings = [f for f in rep.get("findings", []) if isinstance(f, dict)]
    return _step(name, rep["exit"], findings=findings)


def _lazy(module):
    """Import a sibling module only when its step needs it. None when it is not there."""
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


def _rel(path, project):
    p = pathlib.Path(path).resolve()
    try:
        return p.relative_to(project).as_posix()
    except ValueError:
        return p.as_posix()


def _abs(rel, project):
    p = pathlib.Path(rel)
    return p if p.is_absolute() else project / p


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_design(path):
    """Every design file under a --src path. A named file always counts."""
    p = pathlib.Path(path)
    if p.is_file():
        yield p
        return
    if not p.is_dir():
        return
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix.lower() in DESIGN_EXTS and not (set(f.relative_to(p).parts[:-1]) & SKIP_DIRS):
            yield f


def _now():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _new_run_id(now):
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def _collapse(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _brief(project):
    return project / ".design" / "brief"


def _gate_dir(project):
    return project / ".design" / "gate"


def _project_brand(project):
    f = project / ".design" / "brand"
    if not f.is_file():
        return None
    try:
        line = f.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    return line[0].strip() if line and line[0].strip() else None


def hash_inputs(project, src=(), files=(), copy=None):
    """{relative path: sha256} for everything the gate looked at."""
    out = {}
    paths = []
    for s in src:
        paths += list(_walk_design(s))
    paths += [pathlib.Path(f) for f in files]
    if copy:
        paths.append(pathlib.Path(copy))
    paths += [_brief(project) / "contract.json", _brief(project) / "claims.json"]
    for p in paths:
        if p.is_file():
            try:
                out[_rel(p, project)] = _sha(p)
            except OSError:
                pass
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- the seven steps

def step_contract(ctx):
    path = _brief(ctx["project"]) / "contract.json"
    if not path.exists():
        return _skip("contract", "no contract")
    mod = _lazy("contract")
    if mod is None:
        return _cannot("contract", "could not run: contract missing")
    try:
        return _from_report("contract", mod.check(ctx["project"], "final"))
    except Exception as e:  # a crash in a check is a check that did not run
        return _cannot("contract", f"could not run: contract crashed ({type(e).__name__}: {e})")


def step_claims(ctx):
    path = _brief(ctx["project"]) / "claims.json"
    if not path.exists():
        return _skip("claims", "no claims")
    mod = _lazy("claims")
    if mod is None:
        return _cannot("claims", "could not run: claims missing")
    try:
        return _from_report("claims", mod.check(ctx["project"], [str(p) for p in ctx["src"]]))
    except Exception as e:
        return _cannot("claims", f"could not run: claims crashed ({type(e).__name__}: {e})")


def step_lint(ctx):
    import slop_lint
    src = ctx["src"]
    if not src:
        return _cannot("lint", "could not run: nothing to lint. Pass --src (or --file) with the source paths")
    gone = [str(p) for p in src if not pathlib.Path(p).exists()]
    if gone:
        return _cannot("lint", f"could not run: {', '.join(gone)} does not exist")
    enable, disable = slop_lint._project_config(ctx["project"])
    problems = []
    found = slop_lint.lint_paths([str(p) for p in src], enable, disable, problems=problems)
    findings = [_finding("error" if f.level == "error" else "warn", f.rule, f.message,
                         _rel(f.file, ctx["project"]), f.line) for f in found]
    if problems:
        findings += [_finding("error", "tool.could-not-run", f"could not read {p}") for p in problems]
        return _step("lint", 2, findings=findings)
    return _step("lint", 1 if any(f["severity"] == "error" for f in findings) else 0, findings=findings)


def step_brand(ctx):
    slug = ctx["brand"]
    if not slug:
        return _skip("brand", "no brand")
    mod = _lazy("brandpack")
    if mod is None:
        return _cannot("brand", "could not run: brandpack missing")
    if not ctx["src"]:
        return _cannot("brand", "could not run: nothing to lint. Pass --src (or --file)")
    try:
        return _from_report("brand", mod.lint([str(p) for p in ctx["src"]], slug))
    except KeyError:
        return _cannot("brand", f"could not run: no brand pack {slug!r}. `ddr brand list` shows the packs")
    except Exception as e:
        return _cannot("brand", f"could not run: brand lint crashed ({type(e).__name__}: {e})")


def _shots_argv(ctx, targets, json_out):
    argv = [shutil.which("node") or "node", str(TOOLS / "shots.mjs")]
    for kind, t in targets:
        argv += ["--file", t] if kind == "file" else [t]
    argv += ["--out", str(ctx["run_dir"] / "shots"), "--flat", "--json-out", str(json_out),
             "--viewports", ",".join(ctx["viewports"])]
    if ctx.get("storage_state"):
        argv += ["--storage-state", str(ctx["storage_state"])]
    return argv


def _run_shots(ctx, targets, json_out):
    """Run tools/shots.mjs and return (exit code, stderr tail). Tests replace this."""
    if not shutil.which("node"):
        return 2, "node is not installed"
    argv = _shots_argv(ctx, targets, json_out)
    try:
        p = subprocess.run(argv, cwd=str(ctx["project"]), capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        return 2, f"shots took longer than {RENDER_TIMEOUT}s"
    except OSError as e:
        return 2, str(e)
    return p.returncode, (p.stderr or "")[-600:]


def step_render(ctx):
    if ctx["no_render"]:
        return _skip("render", f"--no-render: {ctx['why']}")
    targets = [("url", u) for u in ctx["urls"]] + [("file", str(f)) for f in ctx["files"]]
    if not targets:
        return _cannot("render", "could not run: nothing to render. Pass --url or --file, "
                                 "or --no-render --why for a non-web artefact")
    gone = [str(f) for f in ctx["files"] if not pathlib.Path(f).is_file()]
    if gone:
        return _cannot("render", f"could not run: {', '.join(gone)} does not exist")
    if ctx.get("storage_state") and not pathlib.Path(ctx["storage_state"]).is_file():
        return _cannot("render", f"could not run: no storage state at {ctx['storage_state']}")
    json_out = ctx["run_dir"] / "shots.json"
    rc, err = _run_shots(ctx, targets, json_out)
    rep = None
    if json_out.is_file():
        try:
            rep = json.loads(json_out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rep = None
    if rep is None:
        return _cannot("render", f"could not run: shots wrote no report (exit {rc}). {err.strip()}".strip())
    exit_code = rc if rc in (0, 1, 2) else 2
    if exit_code != 2:
        ctx["render"] = rep
    findings = [f for f in rep.get("findings", []) if isinstance(f, dict)]
    if exit_code == 2 and not any(f.get("rule") == "tool.could-not-run" for f in findings):
        findings.append(_finding("error", "tool.could-not-run", f"could not run: shots exit {rc}. {err.strip()}"))
    return _step("render", exit_code, findings=findings)


def _results(ctx):
    rep = ctx.get("render")
    if not rep:
        return None
    return [r for r in rep.get("results", []) if r.get("motion", "no-preference") == "no-preference"]


def _pick(viewports, prefer, test):
    for name in prefer:
        if name in viewports:
            return name
    for name in viewports:
        if test(name):
            return name
    return None


def desktop_viewport(viewports):
    return _pick(viewports, ("desktop-1440x900", "desktop", "mac-1440x780", "mac-1512x820"),
                 lambda n: n.startswith(("desktop", "mac", "laptop")))


def phone_viewport(viewports):
    return _pick(viewports, ("phone-390x844", "phone"),
                 lambda n: n.startswith("phone") and "landscape" not in n)


def _render_unavailable(name, ctx):
    if ctx["no_render"]:
        return _skip(name, f"--no-render: {ctx['why']}")
    return None


def step_fidelity(ctx):
    early = _render_unavailable("fidelity", ctx)
    if early:
        return early
    lines = []
    if ctx["copy"]:
        cp = pathlib.Path(ctx["copy"])
        if not cp.is_file():
            return _cannot("fidelity", f"could not run: copy file {cp} does not exist")
        try:
            lines += [l.strip() for l in cp.read_text(encoding="utf-8").splitlines() if l.strip()]
        except (OSError, UnicodeDecodeError) as e:
            return _cannot("fidelity", f"could not run: cannot read {cp} ({e})")
    if (_brief(ctx["project"]) / "contract.json").exists():
        mod = _lazy("contract")
        if mod is None:
            return _cannot("fidelity", "could not run: contract missing (needed for its exact copy)")
        try:
            lines += [l for l in mod.exact_copy(ctx["project"]) if l and l.strip()]
        except Exception as e:
            return _cannot("fidelity", f"could not run: contract.exact_copy crashed ({type(e).__name__})")
    results = _results(ctx)
    if results is None:
        return _cannot("fidelity", "could not run: render did not run, so there is no rendered text")
    if not lines:
        return _skip("fidelity", "no copy to check")
    desk = desktop_viewport([r["viewport"] for r in results])
    # textAuthored is the text as written, before CSS text-transform; innerText (text) applies it, so
    # copy styled uppercase would read as re-cased. Older reports only have text.
    texts = []
    for r in results:
        if r["viewport"] == desk:
            texts += [_collapse(r.get("text", "")), _collapse(r.get("textAuthored", ""))]
    texts = [t for t in texts if t]
    if desk is None or not any(texts):
        return _cannot("fidelity", "could not run: no desktop render with text to check against")
    findings = []
    for line in lines:
        want = _collapse(line)
        if any(want in t for t in texts):
            continue
        low = want.lower()
        if any(low in t.lower() for t in texts):
            msg = f'"{line}" is on the page but re-cased. Ship the words exactly as given'
        else:
            msg = f'"{line}" is not in the rendered text at {desk}'
        findings.append(_finding("error", "copy.fidelity", msg))
    return _step("fidelity", 1 if findings else 0, findings=findings, checked=len(lines), viewport=desk)


def step_load(ctx):
    early = _render_unavailable("load", ctx)
    if early:
        return early
    results = _results(ctx)
    if not results:
        return _cannot("load", "could not run: render did not run, so there is nothing to measure")
    names = [r["viewport"] for r in results]
    desk, phone = desktop_viewport(names), phone_viewport(names)
    findings, metrics = [], {"screens": {}}
    for r in results:
        metrics["screens"].setdefault(r["viewport"], r.get("screens"))
    d = next((r for r in results if r["viewport"] == desk), results[0])
    metrics["words_main"] = d.get("words")
    metrics["consecutive_text_only"] = max((r.get("maxConsecutiveTextOnly") or 0) for r in results)
    if isinstance(metrics["words_main"], int) and metrics["words_main"] > WORDS_WARN:
        findings.append(_finding("warn", "load.words", f"{metrics['words_main']} words in main at {d['viewport']}. "
                                 f"Over about {WORDS_WARN} words of prose reads as a wall on a marketing page"))
    if metrics["consecutive_text_only"] > TEXT_RUN_WARN:
        findings.append(_finding("warn", "load.text-run", f"{metrics['consecutive_text_only']} text-only sections in a row. "
                                 "Break the run with a picture, a figure or a change of pace"))
    if phone is None:
        findings.append(_finding("warn", "load.no-phone", "no phone viewport rendered, so text size went unmeasured"))
    else:
        p = next(r for r in results if r["viewport"] == phone)
        sizes = p.get("fontSizes") or []
        metrics["phone_font_sizes"] = len(set(sizes))
        metrics["phone_smallest_px"] = p.get("smallestTextPx")
        small = metrics["phone_smallest_px"]
        if metrics["phone_font_sizes"] > FONT_SIZES_WARN:
            findings.append(_finding("warn", "load.font-sizes", f"{metrics['phone_font_sizes']} distinct text sizes at "
                                     f"{phone}. A tight scale usually needs five or six"))
        if isinstance(small, (int, float)):
            if small < TEXT_ERROR_PX:
                findings.append(_finding("error", "load.text-size", f"smallest visible text at {phone} is {small}px "
                                         f"(under {TEXT_ERROR_PX}px). {p.get('smallestTextAt') or ''}".strip()))
            elif small < TEXT_WARN_PX:
                findings.append(_finding("warn", "load.text-size", f"smallest visible text at {phone} is {small}px "
                                         f"(under {TEXT_WARN_PX}px)"))
    return _step("load", 1 if any(f["severity"] == "error" for f in findings) else 0, findings=findings, metrics=metrics)


STEP_FUNCS = {"contract": step_contract, "claims": step_claims, "lint": step_lint, "brand": step_brand,
              "render": step_render, "fidelity": step_fidelity, "load": step_load}


def overall(steps):
    exits = [s["exit"] for s in steps]
    if 1 in exits:
        return 1
    if 2 in exits:
        return 2
    return 0


VERDICTS = {0: "pass", 1: "findings", 2: "could-not-run"}


# ---------------------------------------------------------------- measured, report only

# ddr audit and ddr motion run after the seven steps. They are saved with the run and summarised, and they never
# change the verdict: what passes or fails is still the seven steps alone.
MEASURE_VIEWPORTS = ["mac-1512x820", "mac-1440x780", "phone-390x844"]
MEASURE_TARGETS = 3          # audit at most this many targets; motion runs on the first
MOTION_IDLE_MS, MOTION_SCROLL_MS = 2000, 8000
MEASURE_BUDGET = 75          # seconds for all measuring in one gate run; past it, what was measured is kept
MOTION_RESERVE = 20         # seconds of the budget kept for motion, so the audit cannot starve it
BUDGET_NOTE = "measuring stopped at the budget"
_clock = time.monotonic


def _remaining(ctx, kind=None):
    """Seconds left of the measuring budget; the audit's share leaves motion its reserve."""
    deadline = ctx.get("measure_deadline")
    left = MEASURE_BUDGET if deadline is None else deadline - _clock()
    return left - MOTION_RESERVE if kind == "audit" else left


def phone_first(viewports):
    """His phone complaints are the commonest, so the phone is measured first and the budget reaches it."""
    return sorted(viewports, key=lambda v: 0 if v.startswith(("phone", "small")) and "landscape" not in v else 1)


def _measure_argv(ctx, kind, target, json_out):
    flag, where = target
    argv = [shutil.which("node") or "node", str(TOOLS / f"{kind}.mjs"), "--file" if flag == "file" else "--url", where,
            "--json-out", str(json_out)]
    if kind == "audit":
        # its own deadline leaves a few seconds to close the browser and write the report inside the budget
        argv += ["--viewports", ",".join(ctx["measure_viewports"]), "--max-items", "5",
                 "--deadline", str(max(0, int(_remaining(ctx, "audit")) - 5))]
    else:
        argv += ["--viewport", desktop_viewport(ctx["measure_viewports"]) or "mac-1512x820", "--scroll",
                 "--idle", str(MOTION_IDLE_MS), "--max-scroll", str(MOTION_SCROLL_MS)]
    if ctx.get("storage_state"):
        argv += ["--storage-state", str(ctx["storage_state"])]
    return argv


def _run_measure(ctx, kind, target, json_out):
    """Run tools/audit.mjs or tools/motion.mjs and return (exit code, stderr tail). Tests replace this."""
    if not shutil.which("node"):
        return 2, "node is not installed"
    try:
        p = subprocess.run(_measure_argv(ctx, kind, target, json_out), cwd=str(ctx["project"]), capture_output=True,
                           text=True, timeout=max(1, _remaining(ctx, kind)))
    except subprocess.TimeoutExpired:
        return 2, f"{BUDGET_NOTE} ({MEASURE_BUDGET}s) during {kind}"
    except OSError as e:
        return 2, str(e)
    return p.returncode, (p.stderr or "")[-400:]


def _read(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def measure(ctx):
    """Run audit on each target and motion on the first; write audit.json and motion.json; return the summary."""
    import audit as audit_mod
    import motion as motion_mod
    targets = [("url", u) for u in ctx["urls"]] + [("file", str(f)) for f in ctx["files"]]
    ctx.setdefault("measure_deadline", _clock() + MEASURE_BUDGET)
    out = {}
    reports = []
    for i, t in enumerate(targets[:MEASURE_TARGETS]):
        part = ctx["run_dir"] / f"audit-{i}.json"
        if _remaining(ctx, "audit") <= 0:
            reports.append(audit_mod._cannot(f"{BUDGET_NOTE} ({MEASURE_BUDGET}s) before this target"))
            continue
        try:
            rc, err = _run_measure(ctx, "audit", t, part)
        except Exception as e:  # a crash here must never touch the verdict
            rc, err = 2, f"{type(e).__name__}: {e}"
        rep = _read(part) or audit_mod._cannot(f"audit wrote no report (exit {rc}). {err.strip()}".strip())
        part.unlink(missing_ok=True)
        reports.append(rep)
    combined = {"tool": "audit", "targets": reports}
    _write_json(ctx["run_dir"] / "audit.json", combined)
    looked = [r for r in reports if r.get("exit") != 2]
    name = lambda r, v: (f"{r.get('target', '')} " if len(looked) > 1 else "") + v["viewport"]
    seen = [(r, v) for r in looked for v in r.get("viewports", [])]
    merged = {"viewports": [dict(v, viewport=name(r, v)) for r, v in seen if not v.get("error") and v.get("stops", 1)]}
    missed = [name(r, v) for r, v in seen if v.get("error") or not v.get("stops", 1)]
    out["audit"] = {"exit": 0 if looked else 2, "total": sum(r.get("total", 0) for r in looked),
                    "counts": audit_mod.counts(merged), "worst": audit_mod.worst(merged, 3),
                    "looked_at": [v["viewport"] for v in merged["viewports"]], "not_looked_at": missed,
                    "report": _rel(ctx["run_dir"] / "audit.json", ctx["project"]),
                    "fold": {v["viewport"]: v.get("fold") for v in merged["viewports"]}}
    if len(targets) > MEASURE_TARGETS:
        out["audit"]["targets_skipped"] = len(targets) - MEASURE_TARGETS
    if not looked:
        out["audit"]["why"] = "; ".join(str(r.get("summary", "")) for r in reports)[:300]
    if any(r.get("stoppedAtDeadline") for r in looked):
        out["audit"]["partial"] = f"{BUDGET_NOTE}: some scroll stops were not looked at"
    mpath = ctx["run_dir"] / "motion.json"
    if _remaining(ctx) <= 0:
        rc, err = 2, f"{BUDGET_NOTE} ({MEASURE_BUDGET}s) before motion"
        mpath.unlink(missing_ok=True)
    else:
        try:
            rc, err = _run_measure(ctx, "motion", targets[0], mpath)
        except Exception as e:
            rc, err = 2, f"{type(e).__name__}: {e}"
    mrep = _read(mpath)
    if mrep is None:
        mrep = motion_mod._cannot(f"motion wrote no report (exit {rc}). {err.strip()}".strip())
        _write_json(mpath, mrep)
    r = mrep.get("result") or {}
    scroll = (r.get("phases") or {}).get("scroll") or {}
    scrolled = r.get("scrolled") or {}
    out["motion"] = {"exit": mrep.get("exit", 2), "verdict": r.get("verdict"), "viewport": mrep.get("viewport"),
                     "scroll_measured": bool(scroll.get("frames")) and scrolled.get("measured", True),
                     "scroll_why": scrolled.get("why"),
                     "scroll_p95": scroll.get("p95"), "worst_ms": scroll.get("worst"),
                     "long_tasks": (r.get("longTasks") or {}).get("count"), "problems": motion_mod.problems(r)[:3] if r else [],
                     "report": _rel(mpath, ctx["project"])}
    if mrep.get("exit") == 2:
        out["motion"]["why"] = str(mrep.get("summary", ""))[:300]
    return out


def measured_lines(m):
    """The short printed summary: counts and the three worst for audit, the verdict and its reasons for motion."""
    if m.get("skipped"):
        return [f"  measured  skipped   {m['skipped']}"]
    L = ["  measured  report only, never changes the verdict"]
    a = m.get("audit") or {}
    if a.get("exit") == 2:
        L.append(f"      audit    could not look: {a.get('why', '')}")
    else:
        counts = ", ".join(f"{k} {v}" for k, v in a.get("counts", {}).items()) or "nothing measured wrong"
        L.append(f"      audit    {a.get('total', 0)} found at {','.join(a.get('looked_at', []))}: {counts}  ({a.get('report')})")
        if a.get("not_looked_at"):
            L.append(f"               not looked at: {', '.join(a['not_looked_at'])}")
        L += [f"               {w}" for w in a.get("worst", [])]
        if a.get("partial"):
            L.append(f"               {a['partial']}")
        first = next(((vp, f) for vp, f in (a.get("fold") or {}).items() if f), None)
        if first:
            vp, f = first
            big = f.get("largest") or {}
            L.append(f"               first screen at {vp}: {f.get('headings')} headings, {f.get('primaryActions')} filled "
                     f"actions, {f.get('words')} words, largest {big.get('px')}px {big.get('selector', '')} \"{big.get('text', '')}\"")
    mo = m.get("motion") or {}
    if mo.get("exit") == 2:
        L.append(f"      motion   could not measure: {mo.get('why', '')}")
    else:
        if mo.get("scroll_measured", True) and mo.get("scroll_p95") is not None:
            how = f"scroll p95 {mo.get('scroll_p95')} ms, worst {mo.get('worst_ms')} ms"
        else:
            how = f"idle only, scroll not measured ({mo.get('scroll_why') or 'no scroll frames'})"
        L.append(f"      motion   {mo.get('verdict')} at {mo.get('viewport')}: {how}, {mo.get('long_tasks')} long tasks  "
                 f"({mo.get('report')})")
        L += [f"               {p}" for p in mo.get("problems", [])]
    return L


# ---------------------------------------------------------------- run

def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # unique per process and write: two gate runs on one project must not share receipt.json.tmp
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _where(f):
    file, line = f.get("file"), f.get("line")
    if file and line:
        return f" {file}:{line}"
    if file and file not in f.get("message", ""):
        return f" {file}"
    return ""


def _report_md(receipt, steps):
    L = [f"# Gate {receipt['run_id']}", "", f"Verdict: **{receipt['verdict']}** (exit {receipt['exit']})", ""]
    for s in steps:
        state = f"skipped ({s['skipped']})" if s["skipped"] else f"exit {s['exit']}, {s['errors']} errors, {s['warnings']} warnings"
        L.append(f"- {s['name']}: {state}")
        for f in s["findings"][:20]:
            where = _where(f)
            L.append(f"  - {f['severity']} {f['rule']}{where}: {f['message']}")
    L += ["", "A pass means these checks found nothing. It says nothing about whether the design is good:",
          "hand the shots to one fresh critic (design-review skill) and `ddr review record` what it read.", ""]
    return "\n".join(L)


def run(args):
    project = pathlib.Path(args.project).resolve()
    now = _now()
    run_id = _new_run_id(now)
    run_dir = _gate_dir(project) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    files = [pathlib.Path(f).resolve() for f in args.file]
    src = [pathlib.Path(s).resolve() for s in args.src] or list(files)
    viewports = [v.strip() for v in (args.viewports or ",".join(DEFAULT_VIEWPORTS)).split(",") if v.strip()]
    state = str(pathlib.Path(args.storage_state).resolve()) if args.storage_state else None
    ctx = {"project": project, "src": src, "urls": list(args.url), "files": files,
           "brand": args.brand or _project_brand(project), "copy": args.copy, "viewports": viewports,
           "no_render": bool(args.no_render), "why": args.why, "run_dir": run_dir, "storage_state": state,
           "measure_viewports": phone_first(viewports if args.viewports else list(MEASURE_VIEWPORTS))}
    steps = []
    for name in STEPS:
        try:
            s = STEP_FUNCS[name](ctx)
        except Exception as e:  # one broken step must not stop the rest
            s = _cannot(name, f"could not run: {name} crashed ({type(e).__name__}: {e})")
        report_path = run_dir / f"{name}.json"
        _write_json(report_path, {"ok": s["exit"] == 0, "exit": s["exit"], "tool": name, "skipped": s["skipped"],
                                  "findings": s["findings"], "metrics": s.get("metrics"),
                                  "summary": f"{s['errors']} errors, {s['warnings']} warnings"})
        s["report"] = _rel(report_path, project)
        steps.append(s)
    code = overall(steps)
    render = next(s for s in steps if s["name"] == "render")
    receipt = {
        "version": 1, "run_id": run_id, "ran_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project.as_posix(), "brand": ctx["brand"],
        "targets": {"urls": list(args.url), "files": [_rel(f, project) for f in files]},
        "src": [_rel(s, project) for s in src],
        "inputs": hash_inputs(project, src, files, args.copy),
        "steps": [{k: s[k] for k in ("name", "exit", "skipped", "errors", "warnings", "report")} for s in steps],
        "viewports": viewports, "shots_dir": _rel(run_dir / "shots", project),
        "rendered": render["skipped"] is None and render["exit"] in (0, 1),
        "verdict": VERDICTS[code], "exit": code, "waived": None,
    }
    _write_json(run_dir / "receipt.json", receipt)
    _write_json(_gate_dir(project) / "receipt.json", receipt)
    all_findings = [dict(f, step=s["name"]) for s in steps for f in s["findings"]]
    summary = f"gate {VERDICTS[code]}: " + ", ".join(
        f"{s['name']} {'skipped' if s['skipped'] else s['exit']}" for s in steps)
    report = {"ok": code == 0, "exit": code, "tool": "gate", "findings": all_findings, "summary": summary,
              "receipt": receipt}
    _write_json(run_dir / "report.json", report)
    (run_dir / "report.md").write_text(_report_md(receipt, steps), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        _trailing_measure(args, ctx, render, sys.stderr)   # stdout stays one JSON object
        return code
    for s in steps:
        if s["skipped"]:
            print(f"  {s['name']:9} skipped   {s['skipped']}")
        else:
            print(f"  {s['name']:9} exit {s['exit']}    {s['errors']} errors, {s['warnings']} warnings")
        for f in s["findings"][:6]:
            where = _where(f)
            print(f"      {f['severity']:5} {f['rule']}{where} {f['message']}")
        if len(s["findings"]) > 6:
            print(f"      ... {len(s['findings']) - 6} more in {s['report']}")
    print(f"\n{summary}\nreceipt: {_rel(_gate_dir(project) / 'receipt.json', project)}  shots: {receipt['shots_dir']}")
    if code == 0:
        print("Next: one fresh critic reads the shots (cold read first, then the ask, then defects; design-review "
              f"skill), then `ddr review record --run {run_id} --json <file>`.")
    elif code == 1:
        print("Next: fix the findings and run the gate again.")
    else:
        print("Next: a step could not run. Fix the tooling (or say why with --no-render --why); exit 2 is never a pass.")
    _trailing_measure(args, ctx, render, sys.stdout)
    return code


def _trailing_measure(args, ctx, render, out):
    """ddr audit and ddr motion, after the gate's run is complete on disk. They write audit.json, motion.json and
    measured.json in the run's folder and print a summary; they never touch receipt.json or report.json, so if this
    is killed, fails or runs out of budget, the saved run and the exit code are the verdict's alone."""
    if args.no_measure:
        measured = {"skipped": "--no-measure"}
    elif render["skipped"] is not None or render["exit"] == 2:
        measured = {"skipped": f"render did not run ({render['skipped'] or 'exit 2'}), so there is no page to measure"}
    else:
        try:
            measured = measure(ctx)
        except Exception as e:  # report only: a broken measure is said, never a changed verdict
            measured = {"skipped": f"could not run: measure crashed ({type(e).__name__}: {e})"}
    try:
        _write_json(ctx["run_dir"] / "measured.json", measured)
    except OSError:
        pass
    for line in measured_lines(measured):
        print(line, file=out)


# ---------------------------------------------------------------- verify

def _load_receipt(project):
    path = _gate_dir(project) / "receipt.json"
    if not path.is_file():
        return None, f"no gate receipt at {path}. Run `ddr gate run` first"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        return None, f"cannot read {path} ({e})"


def verify(args):
    project = pathlib.Path(args.project).resolve()
    receipt, err = _load_receipt(project)
    if receipt is None:
        return _emit_verify(args, 2, [_finding("error", "tool.could-not-run", err)], None)
    findings = []
    verdict = receipt.get("verdict")
    if verdict not in ("pass", "waived"):
        findings.append(_finding("error", "gate.verdict", f"the last gate run ({receipt.get('run_id')}) is "
                                 f"{verdict!r}, not a pass"))
    inputs = receipt.get("inputs") or {}
    for rel, digest in sorted(inputs.items()):
        p = _abs(rel, project)
        if not p.is_file():
            findings.append(_finding("error", "gate.stale", f"{rel} vanished since the gate ran", rel))
        else:
            try:
                same = _sha(p) == digest
            except OSError:
                same = False
            if not same:
                findings.append(_finding("error", "gate.stale", f"{rel} changed since the gate ran", rel))
    for s in receipt.get("src") or []:
        for f in _walk_design(_abs(s, project)):
            rel = _rel(f, project)
            if rel not in inputs:
                findings.append(_finding("error", "gate.stale", f"{rel} is new since the gate ran", rel))
    for f in args.files:
        p = pathlib.Path(f)
        if not p.is_absolute():
            p = (project / p) if (project / p).exists() or not (pathlib.Path.cwd() / p).exists() else pathlib.Path.cwd() / p
        rel = _rel(p, project)
        if rel not in inputs:
            findings.append(_finding("error", "gate.uncovered", f"{rel} is not covered by the gate receipt", rel))
    if args.require_review:
        if verdict == "waived":
            pass   # a waiver stands in for the review, and it is already on the taste ledger
        else:
            rp = project / ".design" / "review" / f"{receipt.get('run_id')}.json"
            if not rp.is_file():
                findings.append(_finding("error", "gate.no-review", f"no review recorded for run {receipt.get('run_id')}. "
                                         "Get one fresh critic's read, then `ddr review record --run latest --json "
                                         "<file>` (or `ddr review resolve` to close an earlier read's must-fixes)"))
            else:
                import review
                try:
                    rec = json.loads(rp.read_text(encoding="utf-8"))
                    rv = rec.get("verdict")
                except (OSError, ValueError, AttributeError):
                    rec, rv = None, None
                bad = []
                if rv == "ship":
                    # a stored review is read, not trusted: its shape, then the rule on what it says
                    bad = review._validate_critic(rec) if review.is_critic(rec) else review._validate_scored(rec)
                if bad:
                    findings.append(_finding("error", "gate.review-invalid", f"the review for {receipt.get('run_id')} "
                                             f"does not stand: {bad[0]['message']}"))
                elif rv != "ship":
                    findings.append(_finding("error", "gate.review-verdict", f"the review for {receipt.get('run_id')} "
                                             f"says {rv!r}, not 'ship'"))
    code = 1 if findings else 0
    return _emit_verify(args, code, findings, receipt)


def _emit_verify(args, code, findings, receipt):
    waived = receipt.get("waived") if receipt else None
    if code == 0:
        summary = f"gate receipt {receipt['run_id']} is current"
        if waived:
            summary += f" (waived: {waived.get('reason')})"
    elif code == 1:
        summary = f"{len(findings)} problems with the gate receipt"
    else:
        summary = findings[0]["message"]
    if args.json:
        print(json.dumps({"ok": code == 0, "exit": code, "tool": "gate-verify", "findings": findings,
                          "summary": summary}, ensure_ascii=False))
        return code
    for f in findings:
        print(f"  {f['rule']:20} {f['message']}")
    print(summary)
    if code == 1:
        print("Next: fix what is listed, run `ddr gate run` on the current work and review that run.")
    return code


# ---------------------------------------------------------------- waive

def waive(args):
    reason = (args.reason or "").strip()
    if not reason:
        print("a waiver needs --reason: say why the gate cannot or should not run", file=sys.stderr)
        return 2
    project = pathlib.Path(args.project).resolve()
    now = _now()
    run_id = _new_run_id(now)
    files = [pathlib.Path(f).resolve() for f in args.file]
    src = [pathlib.Path(s).resolve() for s in args.src] or list(files)
    receipt = {
        "version": 1, "run_id": run_id, "ran_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project.as_posix(), "brand": args.brand or _project_brand(project),
        "targets": {"urls": [], "files": [_rel(f, project) for f in files]},
        "src": [_rel(s, project) for s in src],
        "inputs": hash_inputs(project, src, files, args.copy),
        "steps": [], "viewports": [], "shots_dir": None, "rendered": False,
        "verdict": "waived", "exit": 0,
        "waived": {"reason": reason, "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
    }
    run_dir = _gate_dir(project) / run_id
    _write_json(run_dir / "receipt.json", receipt)
    _write_json(_gate_dir(project) / "receipt.json", receipt)
    import taste
    taste.append(taste.default_path(True), "error", f"gate waived: {reason}", why=reason,
                 project=project.as_posix(), run_id=run_id)
    print(f"gate waived for {project} ({len(receipt['inputs'])} inputs hashed): {reason}\n"
          f"Logged to the taste ledger as an error. It shows in `ddr taste brief`.")
    return 0


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse's own usage errors are exit 2 already; keep the message short
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        raise SystemExit(2)


def _parser():
    p = _Parser(prog="ddr gate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run the seven checks and write a receipt")
    r.add_argument("--project", default=".")
    r.add_argument("--src", nargs="+", default=[], action="extend")
    r.add_argument("--url", nargs="+", default=[], action="extend")
    r.add_argument("--file", nargs="+", default=[], action="extend")
    r.add_argument("--brand")
    r.add_argument("--copy", help="a text file of lines that must ship verbatim")
    r.add_argument("--viewports", help="comma list (default: " + ",".join(DEFAULT_VIEWPORTS) + ")")
    r.add_argument("--no-render", action="store_true")
    r.add_argument("--why", help="with --no-render: why this artefact is not rendered")
    r.add_argument("--storage-state", help="a Playwright storage state (cookies) for pages behind a sign-in; "
                                           "every browser step opens with it")
    r.add_argument("--no-measure", action="store_true", help="skip the report-only ddr audit and ddr motion")
    r.add_argument("--json", action="store_true")
    v = sub.add_parser("verify", help="is the receipt current, passing and (optionally) reviewed")
    v.add_argument("--project", default=".")
    v.add_argument("--require-review", action="store_true")
    v.add_argument("--files", nargs="+", default=[], action="extend")
    v.add_argument("--json", action="store_true")
    w = sub.add_parser("waive", help="record that the gate was skipped, and why")
    w.add_argument("--project", default=".")
    w.add_argument("--reason", required=True)
    w.add_argument("--src", nargs="+", default=[], action="extend")
    w.add_argument("--file", nargs="+", default=[], action="extend")
    w.add_argument("--copy")
    w.add_argument("--brand")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = _parser()
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if a.cmd == "run":
        if a.no_render and not (a.why or "").strip():
            print("--no-render needs --why \"<reason>\": a skipped render must say why", file=sys.stderr)
            return 2
        return run(a)
    if a.cmd == "verify":
        return verify(a)
    if a.cmd == "waive":
        return waive(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
