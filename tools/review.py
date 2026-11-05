"""ddr review: store a scored design review against a gate run, with the verdict computed in code.

    ddr review record --run latest --json review.json   # validate and store .design/review/<run_id>.json
    ddr review show [--run latest]

The record scores nine areas 1 to 5 with evidence (the anchors live in the design-review
skill), lists at most 12 ranked notes, and names the shots the reviewer actually opened:
at least one phone fold and one desktop or mac fold from that gate run. The verdict must
equal the rule: rework if idea is 2 or less or any score is 1; ship if every score is 4 or
more and no note is must-fix; otherwise fix-then-ship. The rule follows the review rubric
in LangChain's open-source design agent (Apache 2.0).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

AREAS = ("idea", "hierarchy", "copy", "craft", "brand", "fit", "truth", "distinctiveness", "load")
SEVERITIES = ("must-fix", "nice-to-have")
REVIEWERS = ("self", "independent")
VERDICTS = ("ship", "fix-then-ship", "rework")
MAX_NOTES = 12


def verdict_for(scores: dict, notes) -> str:
    """The rule. `scores` maps area to [score, evidence] (or a bare score)."""
    vals = {a: (v[0] if isinstance(v, (list, tuple)) else v) for a, v in scores.items()}
    if vals.get("idea", 0) <= 2 or any(v == 1 for v in vals.values()):
        return "rework"
    if all(v >= 4 for v in vals.values()) and not any((n or {}).get("severity") == "must-fix" for n in notes or []):
        return "ship"
    return "fix-then-ship"


def _err(msg, **extra):
    f = {"severity": "error", "rule": "review.invalid", "message": msg}
    f.update(extra)
    return f


def _fold(path: str, run_id: str):
    """The viewport name of a fold shot from this run, or None."""
    p = pathlib.PurePosixPath(path.replace(os.sep, "/"))
    if f"gate/{run_id}/shots" not in p.parent.as_posix():
        return None
    parts = p.name.split("__")
    if len(parts) < 4 or parts[-1] != "fold.png":
        return None
    return parts[-3]


def _is_phone(vp):
    return bool(vp) and vp.startswith("phone") and "landscape" not in vp


def _is_desktop(vp):
    return bool(vp) and vp.startswith(("desktop", "mac"))


def validate(rec, project: pathlib.Path, run_id: str) -> list:
    out = []
    if not isinstance(rec, dict):
        return [_err("the review must be a JSON object")]
    if rec.get("run_id") not in (None, run_id):
        out.append(_err(f"run_id {rec.get('run_id')!r} does not match the run being recorded ({run_id})"))
    if rec.get("reviewer") not in REVIEWERS:
        out.append(_err(f"reviewer must be one of {', '.join(REVIEWERS)}"))
    scores = rec.get("scores")
    good_scores = {}
    if not isinstance(scores, dict):
        out.append(_err("scores must be an object with all nine areas"))
        scores = {}
    for a in AREAS:
        v = scores.get(a)
        if v is None:
            out.append(_err(f"scores.{a} is missing: score all nine areas ({', '.join(AREAS)})"))
            continue
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            out.append(_err(f"scores.{a} must be [score, evidence]"))
            continue
        n, ev = v
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 5:
            out.append(_err(f"scores.{a} must be a whole number from 1 to 5, got {n!r}"))
        elif not isinstance(ev, str) or not ev.strip():
            out.append(_err(f"scores.{a} needs evidence: the crop, size or number behind the score"))
        else:
            good_scores[a] = n
    extra = sorted(set(scores) - set(AREAS))
    if extra:
        out.append(_err(f"unknown score areas: {', '.join(extra)}"))
    notes = rec.get("notes", [])
    if not isinstance(notes, list):
        out.append(_err("notes must be a list"))
        notes = []
    if len(notes) > MAX_NOTES:
        out.append(_err(f"{len(notes)} notes: at most {MAX_NOTES}, ranked by impact. Cut the weakest"))
    for i, n in enumerate(notes, 1):
        if not isinstance(n, dict):
            out.append(_err(f"note {i} must be an object"))
            continue
        for field in ("where", "what", "why", "fix"):
            if not isinstance(n.get(field), str) or not n[field].strip():
                out.append(_err(f"note {i} needs {field}"))
        if n.get("severity") not in SEVERITIES:
            out.append(_err(f"note {i} severity must be must-fix or nice-to-have"))
    for field in ("strengths", "compared_with"):
        if not isinstance(rec.get(field, []), list):
            out.append(_err(f"{field} must be a list"))
    viewed = rec.get("viewed")
    if not isinstance(viewed, list) or not viewed:
        out.append(_err("viewed must list the shots you opened, from this gate run"))
        viewed = []
    folds = []
    for v in viewed:
        if not isinstance(v, str):
            out.append(_err(f"viewed entry {v!r} is not a path"))
            continue
        p = pathlib.Path(v)
        if not (p if p.is_absolute() else project / p).is_file():
            out.append(_err(f"viewed {v} does not exist"))
            continue
        folds.append(_fold(v, run_id))
    if not any(_is_phone(f) for f in folds):
        out.append(_err(f"no phone fold from run {run_id} in viewed: open the phone fold and list it"))
    if not any(_is_desktop(f) for f in folds):
        out.append(_err(f"no desktop or mac fold from run {run_id} in viewed: open one and list it"))
    if len(good_scores) == len(AREAS):
        rule = verdict_for(good_scores, [n for n in notes if isinstance(n, dict)])
        if rec.get("verdict") != rule:
            out.append(_err(f"verdict {rec.get('verdict')!r} does not follow the rule: these scores and notes make it "
                            f"{rule!r}", rule="review.verdict"))
    elif rec.get("verdict") not in VERDICTS:
        out.append(_err(f"verdict must be one of {', '.join(VERDICTS)}"))
    return out


def _resolve_run(project, run):
    gate = project / ".design" / "gate"
    if run in (None, "latest"):
        rp = gate / "receipt.json"
        if not rp.is_file():
            return None, f"no gate receipt at {rp}: run `ddr gate run` first"
        try:
            run = json.loads(rp.read_text(encoding="utf-8"))["run_id"]
        except (OSError, ValueError, KeyError) as e:
            return None, f"cannot read the run id from {rp} ({e})"
    if not (gate / run).is_dir():
        return None, f"no gate run {run} under {gate}"
    return run, None


def record(a):
    project = pathlib.Path(a.project).resolve()
    run_id, err = _resolve_run(project, a.run)
    if err:
        print(f"could not record: {err}")
        return 2
    try:
        rec = json.loads(pathlib.Path(a.json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"could not record: cannot read {a.json} ({e})")
        return 2
    problems = validate(rec, project, run_id)
    if problems:
        for p in problems:
            print(f"  error  {p['message']}")
        print(f"\n{len(problems)} problems: fix the review and record it again. Nothing was stored.")
        return 1
    rec = dict(rec, run_id=run_id,
               recorded_at=_dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"))
    out = project / ".design" / "review" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    print(f"recorded {out.relative_to(project)}: {rec['verdict']}")
    if rec["verdict"] != "ship":
        print("Next: fix the must-fix notes, run `ddr gate run` again, and review the new run.")
    return 0


def show(a):
    project = pathlib.Path(a.project).resolve()
    run_id, err = _resolve_run(project, a.run)
    if err:
        print(err)
        return 2
    path = project / ".design" / "review" / f"{run_id}.json"
    if not path.is_file():
        print(f"no review recorded for run {run_id}. `ddr review record --run {run_id} --json <file>`")
        return 1
    rec = json.loads(path.read_text(encoding="utf-8"))
    print(f"review of {run_id} ({rec.get('reviewer')}): {rec.get('verdict')}")
    for area in AREAS:
        s = rec.get("scores", {}).get(area, [None, ""])
        print(f"  {area:16} {s[0]}  {s[1]}")
    for i, n in enumerate(rec.get("notes", []), 1):
        print(f"  {i:2}. {n.get('severity'):12} {n.get('where')}: {n.get('what')} -> {n.get('fix')}")
    for s in rec.get("strengths", []):
        print(f"  protect: {s}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="ddr review", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("record")
    r.add_argument("--project", default=".")
    r.add_argument("--run", default="latest")
    r.add_argument("--json", required=True, help="the review record to validate and store")
    s = sub.add_parser("show")
    s.add_argument("--project", default=".")
    s.add_argument("--run", default="latest")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if a.cmd == "record":
        return record(a)
    if a.cmd == "show":
        return show(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
