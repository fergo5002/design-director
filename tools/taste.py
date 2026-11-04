"""The taste ledger: what landed, what was rejected, what went wrong, and what keeps getting made.

One JSON line per event in .design/taste.jsonl (the project's own taste), or the file
named by $DD_TASTE, or $DDR_HOME/taste.jsonl (default ~/.design-director) with --global.
Add --domain <slug> to an event and it also counts towards that domain's experience.

    ddr taste win    "Masked text rise, 90ms stagger" --tags motion:masked-rise,type:serif-display \
                    --values "Instrument Serif 96/0.95, -0.02em" --surface landing
    ddr taste miss   "Dashboard of identical KPI cards" --tags layout:card-grid \
                    --why "nothing leads, reads as generated" --rule "DASHBOARDS.md Part 2"
    ddr taste shipped --what "Pricing page v2" --tags type:grotesk,colour:mono,layout:asymmetric
    ddr taste error  "Screenshot hung, blamed the page" --why "hidden tab, rAF never fires" \
                    --rung isolated --prevention "run instrument-check.js first"
    ddr taste brief  [--surface landing]     # read this before designing
    ddr taste export > lesson.md             # anonymised, for a pull request to lessons/

Rewarding good design without converging on it: every win and every shipped piece adds
weight to its tags, weight halves every HALF_LIFE days, and any tag carrying more than
SATURATION of the recent weight is reported as saturated. The brief then demands three
directions: one may use proven moves, one must avoid every saturated tag, one starts
from a random cross-discipline draw from the catalogue.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys
from collections import defaultdict

KINDS = {"win", "miss", "shipped", "error", "note"}
AXES = ("type", "colour", "layout", "motion", "imagery", "density", "mood", "material",
        "interaction", "copy", "surface", "brand", "data", "sound")
RUNGS = ("guessed", "observed", "reproduced", "isolated", "explained", "fixed")
HALF_LIFE = 120          # days
SATURATION = 0.30        # share of recent tag weight
MIN_EVENTS = 3           # need this many weighted events before calling anything saturated
TAG = re.compile(r"[a-z]+:[a-z0-9][a-z0-9.+-]*")


def default_path(global_: bool = False) -> pathlib.Path:
    if os.environ.get("DD_TASTE"):
        return pathlib.Path(os.environ["DD_TASTE"]).expanduser()
    if global_:
        base = os.environ.get("DDR_HOME")
        return (pathlib.Path(base).expanduser() if base else pathlib.Path.home() / ".design-director") / "taste.jsonl"
    return pathlib.Path.cwd() / ".design" / "taste.jsonl"


def append(path, kind, what, tags=(), date=None, **fields) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    if not what or not what.strip():
        raise ValueError("say what it was, specifically")
    tags = [t.strip().lower() for t in tags if t and t.strip()]
    for t in tags:
        if not TAG.fullmatch(t):
            raise ValueError(f"tag {t!r} must look like axis:value, e.g. type:serif-display")
        if t.split(":")[0] not in AXES:
            raise ValueError(f"tag axis {t.split(':')[0]!r} not in {AXES}")
    if kind == "miss" and not fields.get("why"):
        raise ValueError("a miss needs --why, or the same mistake comes back")
    if kind == "error":
        if not fields.get("why"):
            raise ValueError("an error needs --why (the cause, at the rung you actually reached)")
        if fields.get("rung") and fields["rung"] not in RUNGS:
            raise ValueError(f"rung must be one of {RUNGS}")
    ev = {"date": date or _dt.date.today().isoformat(), "kind": kind, "what": what.strip(), "tags": tags}
    ev.update({k: v for k, v in fields.items() if v not in (None, "", [])})
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def read(path) -> list[dict]:
    path = pathlib.Path(path)
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"warning: {path}:{n} is not valid JSON, skipped", file=sys.stderr)
    return out


def _weight(ev, today: _dt.date) -> float:
    try:
        age = (today - _dt.date.fromisoformat(ev["date"])).days
    except (KeyError, ValueError):
        age = HALF_LIFE
    return 0.5 ** (max(age, 0) / HALF_LIFE)


def saturation(events, today=None, threshold=SATURATION):
    """Tags that carry more than `threshold` of the recent weight within their axis."""
    today = _dt.date.fromisoformat(today) if isinstance(today, str) else (today or _dt.date.today())
    by_axis = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    counted = 0.0
    for ev in events:
        if ev.get("kind") not in ("win", "shipped"):
            continue
        w = _weight(ev, today)
        counted += w
        for t in ev.get("tags", []):
            axis = t.split(":")[0]
            by_axis[axis][t] += w
            totals[axis] += w
    if counted < MIN_EVENTS * 0.5:
        return []
    out = []
    for axis, tags in by_axis.items():
        for t, w in tags.items():
            share = w / totals[axis]
            # a tag must be both a large share of its axis and present in a real fraction of the work
            if share > threshold and w / counted > threshold and w >= 1.5:
                out.append((t, round(w / counted, 2)))
    return sorted(out, key=lambda x: -x[1])


def brief(events, surface=None, today=None, draw=None) -> str:
    today_d = _dt.date.fromisoformat(today) if today else _dt.date.today()
    rel = [e for e in events if not surface or e.get("surface") in (None, surface)]
    misses = [e for e in rel if e["kind"] == "miss"]
    wins = sorted((e for e in rel if e["kind"] == "win"), key=lambda e: -_weight(e, today_d))
    errors = [e for e in rel if e["kind"] == "error"]
    sat = saturation(rel, today_d)
    L = [f"# Taste brief{' for ' + surface if surface else ''} ({today_d.isoformat()})", ""]
    if not rel:
        L += ["No taste logged yet. Log wins, misses and what ships as you go (`ddr taste --help`).", ""]
    if misses:
        L += ["## Avoid (rejected before, with the reason)", ""]
        seen = set()
        for e in reversed(misses):
            if e["what"] in seen:
                continue
            seen.add(e["what"])
            rule = f" Rule: {e['rule']}." if e.get("rule") else ""
            L.append(f"- {e['what']}: {e.get('why', '')}.{rule} [{', '.join(e.get('tags', []))}]")
        L.append("")
    if errors:
        L += ["## Process errors not to repeat", ""]
        for e in errors[-8:]:
            prev = f" Prevention: {e['prevention']}." if e.get("prevention") else ""
            L.append(f"- {e['what']} (cause, {e.get('rung', 'guessed')}): {e['why']}.{prev}")
        L.append("")
    if wins:
        L += ["## Proven (landed before; reuse the move, not the look)", ""]
        for e in wins[:10]:
            vals = f" Values: {e['values']}." if e.get("values") else ""
            L.append(f"- {e['what']}.{vals} [{', '.join(e.get('tags', []))}]")
        L.append("")
    L += ["## Saturated (do not open with these)", ""]
    if sat:
        for t, share in sat:
            L.append(f"- {t}: {int(share * 100)}% of recent wins and shipped work")
    else:
        L.append("- Nothing yet. Keep logging `shipped` so this stays honest.")
    L.append("")
    L += [
        "## Directions to make before choosing",
        "",
        "- **Direction A** may lean on the proven moves above.",
        "- **Direction B** must use none of the saturated tags"
        + (f" ({', '.join(t for t, _ in sat)})." if sat else "; pick an axis you have never logged."),
        "- **Direction C** starts from the exploration draw below: take one mechanism from each and combine them.",
        "",
        "Judge the three side by side at real size. Log the pick with `ddr taste shipped`, and the client's verdicts with `win` or `miss`.",
        "",
    ]
    if draw:
        L += ["## Exploration draw", ""]
        for e in draw:
            L.append(f"- {e['name']} ({e.get('category')}): {e.get('take') or e.get('best_for')}  {e['url']}")
        L.append("")
    return "\n".join(L)


def export(events) -> str:
    L = ["# Lessons", "", "Anonymised from a taste ledger. Projects and clients removed.", ""]
    for kind, title in (("miss", "Rejected"), ("error", "Process errors"), ("win", "Landed")):
        group = [e for e in events if e["kind"] == kind]
        if not group:
            continue
        L += [f"## {title}", ""]
        for e in group:
            extra = "; ".join(f"{k}: {e[k]}" for k in ("why", "values", "rule", "prevention", "rung") if e.get(k))
            L.append(f"- {e['date']} {e['what']}" + (f" ({extra})" if extra else "") + f" [{', '.join(e.get('tags', []))}]")
        L.append("")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr taste", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--global", dest="global_", action="store_true", help="use ~/.design-director/taste.jsonl")
    p.add_argument("--file", help="ledger path (overrides everything)")
    # the same two options also work after the subcommand: `ddr taste win --global ...`
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--global", dest="global_", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--file", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    for k in ("win", "miss", "shipped", "error", "note"):
        s = sub.add_parser(k, parents=[common])
        s.add_argument("what", nargs="?")
        s.add_argument("--what", dest="what_opt")
        s.add_argument("--tags", default="")
        s.add_argument("--surface"); s.add_argument("--project"); s.add_argument("--values")
        s.add_argument("--why"); s.add_argument("--rule"); s.add_argument("--by")
        s.add_argument("--rung"); s.add_argument("--prevention"); s.add_argument("--evidence")
        s.add_argument("--domain", help="also record it in this design domain's ledger (ddr domain list)")
    b = sub.add_parser("brief", parents=[common]); b.add_argument("--surface"); b.add_argument("--no-draw", action="store_true")
    b.add_argument("--seed", type=int)
    sub.add_parser("saturation", parents=[common])
    sub.add_parser("export", parents=[common])
    sub.add_parser("path", parents=[common])
    a = p.parse_args(argv)
    path = pathlib.Path(a.file).expanduser() if a.file else default_path(a.global_)

    if a.cmd == "path":
        print(path); return 0
    if a.cmd in KINDS:
        what = a.what or a.what_opt
        dom = None
        if a.domain:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
            import domains
            dom = domains.load(a.domain)
            if dom is None:
                print(f"not logged: no domain {a.domain!r} (`ddr domain list`)", file=sys.stderr); return 2
        try:
            ev = append(path, a.cmd, what, [t for t in a.tags.split(",") if t],
                        surface=a.surface, project=a.project, values=a.values, why=a.why, rule=a.rule,
                        by=a.by, rung=a.rung, prevention=a.prevention, evidence=a.evidence)
        except ValueError as e:
            print(f"not logged: {e}", file=sys.stderr); return 2
        print(f"logged {ev['kind']} to {path}")
        if dom is not None:
            try:
                domains.log(dom["slug"], a.cmd, what, why=a.why or "", rule=a.rule or "",
                            prevention=a.prevention or "", tags=ev.get("tags", []), project=a.project or "")
                print(f"and to the {dom['slug']} domain")
            except ValueError as e:
                print(f"not logged to the domain: {e}", file=sys.stderr); return 2
        if a.cmd == "miss" and not a.rule:
            print("now edit the rule that allowed it, then re-log with --rule so the ledger points at the fix")
        return 0
    events = read(path)
    if a.cmd == "saturation":
        for t, share in saturation(events):
            print(f"{t}\t{share}")
        return 0
    if a.cmd == "export":
        print(export(events)); return 0
    if a.cmd == "brief":
        draw = []
        if not a.no_draw:
            try:
                import sources
                draw = sources.shuffle(sources.load(), n=3, seed=a.seed)
            except Exception as e:  # catalogue missing should never block a brief
                print(f"(no exploration draw: {e})", file=sys.stderr)
        print(brief(events, a.surface, draw=draw))
        return 0


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    sys.exit(main())
