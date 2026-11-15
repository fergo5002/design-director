"""ddr review: store one critic's read of a gate run, with the verdict computed in code.

    ddr review record --run latest --json critic.json   # validate and store .design/review/<run_id>.json
    ddr review resolve --from <run> --evidence "1=<where the fix shows>" [--to latest]
    ddr review show [--run latest]

A critic record has no scores. It holds a cold read of the first screen written before the
critic saw the ask (what it is, who it is for, what to do next), whether that read matches
what the thing is meant to be, each separate thing the owner asked for marked yes, no or
cannot-tell with the shot that shows it, and at most ten defects, worst first, each must-fix
or nice-to-have. It names the shots the critic opened: at least one phone fold and one
desktop or mac fold from that gate run. The verdict is the rule: rework if the cold read
misses what the thing is for; fix-then-ship while an ask is unmet or a must-fix is open;
otherwise ship. An ask only the deploy can meet ("post it to /v10") is marked after-ship.

Why no scores: across 150 scored reviews of real work, 80% of 1,350 scores were exactly the
pass mark and none said rework, while the reviewers' written notes did find the real faults.

`resolve` closes must-fixes and unmet asks on evidence instead of a second review: after the
fixes and a fresh gate run, it carries the critic's record onto the new run with each one
marked by where the fix shows (`--evidence 2=...` for defect 2, `--evidence a1=...` for ask
1). A rework never carries; it needs a fresh look.

A record with `scores` is the older nine-area review and is still accepted: rework if idea
is 2 or less or any score is 1; ship if every score is 4 or more and no note is must-fix;
otherwise fix-then-ship (after the rubric in LangChain's open-source design agent, Apache 2.0).
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
MAX_DEFECTS = 10
MET = ("yes", "no", "cannot-tell", "after-ship")   # after-ship: only the deploy can meet it ("post it to /v10")
COLD = ("what_it_is", "who_for", "next_action")


def verdict_for(scores: dict, notes) -> str:
    """The rule. `scores` maps area to [score, evidence] (or a bare score)."""
    vals = {a: (v[0] if isinstance(v, (list, tuple)) else v) for a, v in scores.items()}
    if vals.get("idea", 0) <= 2 or any(v == 1 for v in vals.values()):
        return "rework"
    if all(v >= 4 for v in vals.values()) and not any((n or {}).get("severity") == "must-fix" for n in notes or []):
        return "ship"
    return "fix-then-ship"


def is_critic(rec) -> bool:
    return isinstance(rec, dict) and "scores" not in rec


def _severity(d) -> str:
    sev = (d or {}).get("severity")
    return "nice-to-have" if sev == "nice" else sev


def critic_verdict(rec) -> str:
    """The rule for a critic record.

    Rework is a cold read that missed what the thing is for: the one fault no fix list repairs.
    An unmet ask and a must-fix defect are fixes, and either stops holding once `resolved`
    carries the evidence. (Measured: in 18 critic passes on real work the cold read always
    matched, all 14 reworks came from an ask marked no, and the owner approved four of the
    five pages they held up as they stood.)
    """
    if rec.get("cold_read_matches") is False:
        return "rework"
    if any((x or {}).get("met") == "no" and not (x or {}).get("resolved") for x in rec.get("ask") or []):
        return "fix-then-ship"
    if any(_severity(d) == "must-fix" and not (d or {}).get("resolved") for d in rec.get("defects") or []):
        return "fix-then-ship"
    return "ship"


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
    if not isinstance(rec, dict):
        return [_err("the review must be a JSON object")]
    out = []
    if rec.get("run_id") not in (None, run_id):
        out.append(_err(f"run_id {rec.get('run_id')!r} does not match the run being recorded ({run_id})"))
    if rec.get("reviewer") not in REVIEWERS:
        out.append(_err(f"reviewer must be one of {', '.join(REVIEWERS)}"))
    out += _validate_critic(rec, fresh=True) if is_critic(rec) else _validate_scored(rec)
    out += _validate_viewed(rec, project, run_id)
    return out


def _validate_critic(rec, fresh=False) -> list:
    """The shape of a critic's read. `fresh` is a read being recorded: it cannot arrive with items
    already closed, because only `resolve` closes them, onto a later gate run."""
    out = []
    if fresh and "resolved_from" in rec:
        out.append(_err("resolved_from is written by `ddr review resolve`, never by the critic"))
    cold = rec.get("cold_read")
    if not isinstance(cold, dict):
        out.append(_err("cold_read must be an object: what_it_is, who_for, next_action, first_noticed, confusing"))
        cold = {}
    for k in COLD:
        if not isinstance(cold.get(k), str) or not cold[k].strip():
            out.append(_err(f"cold_read.{k} is empty: the cold read, written before seeing the ask, is the point"))
    if not isinstance(rec.get("cold_read_matches"), bool):
        out.append(_err("cold_read_matches must be true or false"))
    ask = rec.get("ask")
    if not isinstance(ask, list) or not ask:
        out.append(_err("ask is empty: every separate thing the owner asked for gets a line, in their words"))
        ask = []
    for i, x in enumerate(ask, 1):
        if not isinstance(x, dict):
            out.append(_err(f"ask {i} must be an object"))
            continue
        if not isinstance(x.get("item"), str) or not x["item"].strip():
            out.append(_err(f"ask {i} needs item: the owner's own words"))
        if x.get("met") not in MET:
            out.append(_err(f"ask {i}: met must be one of {', '.join(MET)}"))
        if fresh and "resolved" in x:
            out.append(_err(f"ask {i} arrives resolved: a fresh read closes nothing. Fix it, gate again, then "
                            "`ddr review resolve`"))
        if not isinstance(x.get("evidence"), str) or not x["evidence"].strip():
            out.append(_err(f"ask {i} needs evidence: the shot and region that shows it"))
    defects = rec.get("defects", [])
    if not isinstance(defects, list):
        out.append(_err("defects must be a list"))
        defects = []
    if len(defects) > MAX_DEFECTS:
        out.append(_err(f"{len(defects)} defects: at most ten, worst first. Cut the weakest"))
    for i, d in enumerate(defects, 1):
        if not isinstance(d, dict):
            out.append(_err(f"defect {i} must be an object"))
            continue
        for field in ("where", "what", "fix"):
            if not isinstance(d.get(field), str) or not d[field].strip():
                out.append(_err(f"defect {i} needs {field}"))
        if _severity(d) not in SEVERITIES:
            out.append(_err(f"defect {i} severity must be must-fix or nice-to-have"))
        if fresh and "resolved" in d:
            out.append(_err(f"defect {i} arrives resolved: a fresh read closes nothing. Fix it, gate again, then "
                            "`ddr review resolve`"))
    if not out and "verdict" in rec:
        rule = critic_verdict(rec)
        if rec["verdict"] != rule:
            out.append(_err(f"verdict {rec['verdict']!r} does not follow the rule: this read makes it {rule!r}. "
                            "Leave verdict out and it is computed", rule="review.verdict"))
    return out


def _validate_scored(rec) -> list:
    out = []
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
    if len(good_scores) == len(AREAS):
        rule = verdict_for(good_scores, [n for n in notes if isinstance(n, dict)])
        if rec.get("verdict") != rule:
            out.append(_err(f"verdict {rec.get('verdict')!r} does not follow the rule: these scores and notes make it "
                            f"{rule!r}", rule="review.verdict"))
    elif rec.get("verdict") not in VERDICTS:
        out.append(_err(f"verdict must be one of {', '.join(VERDICTS)}"))
    return out


def _validate_viewed(rec, project, run_id) -> list:
    out = []
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
    if is_critic(rec):
        rec = dict(rec, kind="critic", verdict=critic_verdict(rec))
    out = _store(project, run_id, rec)
    print(f"recorded {out.relative_to(project)}: {rec['verdict']}")
    if rec["verdict"] == "rework":
        print("Next: the cold read missed what it is for. Rethink it, gate it again, and get a fresh critic.")
    elif rec["verdict"] != "ship":
        print("Next: fix the must-fix defects and unmet asks, run `ddr gate run` again, then "
              + (f"`ddr review resolve --from {run_id} --evidence \"<n>=<where the fix shows>\"` (a<n> for an ask)."
                 if is_critic(rec) else "review the new run."))
    return 0


def _now():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(project, run_id, rec):
    rec = dict(rec, run_id=run_id, recorded_at=_now())
    out = project / ".design" / "review" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return out


def resolve(a):
    """Carry a critic's record onto a later gate run, each open must-fix closed by the evidence given."""
    project = pathlib.Path(a.project).resolve()
    src_run, err = _resolve_run(project, a.source)
    if not err:
        dst_run, err = _resolve_run(project, a.to)
    if err:
        print(f"could not resolve: {err}")
        return 2
    if src_run == dst_run:
        print(f"not resolved: --to is the run the critic read ({src_run}). Fix, run `ddr gate run` again, "
              "then resolve onto the new run.")
        return 1
    if dst_run < src_run:                       # run ids start with their UTC time
        print(f"not resolved: {dst_run} is older than {src_run}; carry a read only onto a later gate run")
        return 1
    try:
        dst_verdict = json.loads((project / ".design" / "gate" / dst_run / "receipt.json").read_text(encoding="utf-8"))["verdict"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"could not resolve: cannot read the gate verdict of {dst_run} ({e})")
        return 2
    if dst_verdict != "pass":
        print(f"not resolved: gate run {dst_run} says {dst_verdict!r}. Fix its findings and gate to a pass first.")
        return 1
    # A read carries forward only across runs nobody else has read: no review may exist for any run
    # after the one the critic saw, up to and including the target. That keeps a later fresh read
    # from being overwritten, and stops one read being carried onto run after run.
    between = sorted(f.stem for f in (project / ".design" / "review").glob("*.json") if src_run < f.stem <= dst_run)
    if between:
        print(f"not resolved: run {between[0]} has its own review, which is the latest read of this work. Resolve "
              f"from that one, or get a fresh critic.")
        return 1
    path = project / ".design" / "review" / f"{src_run}.json"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"could not resolve: no readable review for run {src_run} ({e})")
        return 2
    if not is_critic(rec):
        print("not resolved: that is a scored review. Only a critic's must-fixes close on evidence; review the new run.")
        return 1
    if critic_verdict(rec) == "rework":
        print("not resolved: the critic read rework, a cold read that missed what the thing is for. That needs a fresh "
              "look, not evidence.")
        return 1
    given = {}
    for e in a.evidence or []:
        key, sep, text = e.partition("=")
        key = key.strip().lower()
        kind, num = ("ask", key[1:]) if key.startswith("a") else ("defect", key)
        if not sep or not num.isdigit() or not text.strip():
            print(f"not resolved: --evidence {e!r} must be <defect number>=<where the fix shows>, or a<ask number>=...")
            return 1
        if (kind, int(num)) in given:
            print(f"not resolved: {key} is given twice; one --evidence per item")
            return 1
        given[(kind, int(num))] = text.strip()
    defects = [dict(d) for d in rec.get("defects") or []]
    asks = [dict(x) for x in rec.get("ask") or []]
    open_ = [("defect", i) for i, d in enumerate(defects, 1) if _severity(d) == "must-fix" and not d.get("resolved")]
    open_ += [("ask", i) for i, x in enumerate(asks, 1) if x.get("met") == "no" and not x.get("resolved")]
    name = lambda k: f"a{k[1]}" if k[0] == "ask" else str(k[1])
    if not open_:
        print(f"not resolved: the read of {src_run} has nothing open, and it covers only the run it saw. A new "
              "gate run of changed work needs a fresh critic.")
        return 1
    stray = [k for k in given if k not in open_]
    if stray:
        print(f"not resolved: {', '.join(map(name, stray))} is not an open must-fix or unmet ask "
              f"(open: {', '.join(map(name, open_)) or 'none'})")
        return 1
    missing = [k for k in open_ if k not in given]
    if missing:
        print(f"not resolved: {', '.join(('must-fix ' + name(k)) if k[0] == 'defect' else ('unmet ask ' + name(k)) for k in missing)}"
              " has no evidence. Fix it and say where the fix shows in the new run, or get a fresh critic.")
        return 1
    for (kind, i), text in given.items():
        (defects if kind == "defect" else asks)[i - 1]["resolved"] = f"{dst_run}: {text}"
    new = dict(rec, defects=defects, ask=asks, resolved_from=src_run)
    new["verdict"] = critic_verdict(new)
    out = _store(project, dst_run, new)
    print(f"recorded {out.relative_to(project)}: {new['verdict']} ({len(given)} closed on evidence from "
          f"run {src_run})")
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
    if is_critic(rec):
        cold = rec.get("cold_read") or {}
        print(f"  cold read: {cold.get('what_it_is')}; for {cold.get('who_for')}; next: {cold.get('next_action')}"
              f" ({'matches' if rec.get('cold_read_matches') else 'does not match'} what it is meant to be)")
        for i, x in enumerate(rec.get("ask") or [], 1):
            done = f"  [resolved {x['resolved']}]" if x.get("resolved") else ""
            print(f"  a{i:<2} {x.get('met'):11} {x.get('item')}  ({x.get('evidence')}){done}")
        for i, d in enumerate(rec.get("defects") or [], 1):
            done = f"  [resolved {d['resolved']}]" if d.get("resolved") else ""
            print(f"  {i:2}. {_severity(d):12} {d.get('where')}: {d.get('what')} -> {d.get('fix')}{done}")
        return 0
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
    r.add_argument("--json", required=True, help="the critic's record to validate and store")
    v = sub.add_parser("resolve", help="close a critic's must-fixes on evidence, onto a later gate run")
    v.add_argument("--project", default=".")
    v.add_argument("--from", dest="source", required=True, help="the gate run the critic read")
    v.add_argument("--to", default="latest", help="the later gate run (default: latest)")
    v.add_argument("--evidence", action="append", help="<defect number>=<where the fix shows>; once per must-fix")
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
    if a.cmd == "resolve":
        return resolve(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
