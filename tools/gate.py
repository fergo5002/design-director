"""ddr gate: the checks that must pass before design work ships, in an order fixed in code.

    ddr gate run --src src/ --file index.html [--copy copy.txt] [--brand draft]
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

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

STEPS = ("contract", "claims", "lint", "brand", "render", "fidelity", "load")
DEFAULT_VIEWPORTS = ["mac-1512x820", "mac-1440x780", "desktop-1440x900", "phone-390x844",
                     "phone-landscape-844x390", "small-320x568"]
DESIGN_EXTS = {".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte",
               ".astro", ".svg", ".md", ".mdx", ".json"}
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


def _run_shots(ctx, targets, json_out):
    """Run tools/shots.mjs and return (exit code, stderr tail). Tests replace this."""
    node = shutil.which("node")
    if not node:
        return 2, "node is not installed"
    argv = [node, str(TOOLS / "shots.mjs")]
    for kind, t in targets:
        argv += ["--file", t] if kind == "file" else [t]
    argv += ["--out", str(ctx["run_dir"] / "shots"), "--flat", "--json-out", str(json_out),
             "--viewports", ",".join(ctx["viewports"])]
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
    texts = [_collapse(r.get("text", "")) for r in results if r["viewport"] == desk]
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


# ---------------------------------------------------------------- run

def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
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
          "look at the shots, then score it with the design-review rubric and `ddr review record`.", ""]
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
    ctx = {"project": project, "src": src, "urls": list(args.url), "files": files,
           "brand": args.brand or _project_brand(project), "copy": args.copy, "viewports": viewports,
           "no_render": bool(args.no_render), "why": args.why, "run_dir": run_dir}
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
        print("Next: open the phone and desktop folds, score them (design-review skill), then "
              f"`ddr review record --run {run_id} --json <file>`.")
    elif code == 1:
        print("Next: fix the findings and run the gate again.")
    else:
        print("Next: a step could not run. Fix the tooling (or say why with --no-render --why); exit 2 is never a pass.")
    return code


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
                                         "Score it, then `ddr review record --run latest --json <file>`"))
            else:
                try:
                    rv = json.loads(rp.read_text(encoding="utf-8")).get("verdict")
                except (OSError, ValueError, AttributeError):
                    rv = None
                if rv != "ship":
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
        print("Next: run `ddr gate run` again on the current work.")
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
