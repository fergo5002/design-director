"""Looks: record which rough direction the person picked, and why, so the choice teaches something.

    ddr looks pick --look b --why "the ledger reads calm and the rate leads" --others a,c \\
        --domain fintech --tags type:grotesk,layout:ledger --values "Sohne 15/1.5"

A pick writes a taste `win` ("picked look b over a, c", with the reason) to the global
ledger at $DDR_HOME/taste.jsonl, and, with --domain, a note in the person's own words in
that domain's notes, which starts kept because the person said it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def pick(look: str, why: str, others=(), domain: str = "", tags=(), values: str = "", project=None) -> dict:
    import taste
    import notes
    import domains
    if not look.strip() or not why.strip():
        raise ValueError("a pick needs --look and --why (the person's reason, in their words)")
    dom = None
    if domain:
        dom = domains.load(domain)
        if dom is None:
            raise ValueError(f"no domain {domain!r} (`ddr domain list`)")
    others = [o.strip() for o in others if o.strip()]
    what = f"picked look {look}" + (f" over {', '.join(others)}" if others else "")
    project = str(project or pathlib.Path.cwd())
    ev = taste.append(taste.default_path(True), "win", what, list(tags), why=why.strip(), values=values or None,
                      project=project, domain=dom["slug"] if dom else None)
    out = {"taste": ev, "note": None}
    if dom is not None:
        day = _dt.date.today().isoformat()
        note, _ = notes.add(dom["slug"], f"{what[0].upper()}{what[1:]}: {why.strip()}",
                            [f"{day}: {what} in {project}" + (f" ({values})" if values else "")], project, person=True)
        out["note"] = note
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr looks", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("pick", help="record the look the person chose and their reason")
    k.add_argument("--look", default=""); k.add_argument("--why", default="")
    k.add_argument("--others", default="", help="the looks not chosen, comma separated")
    k.add_argument("--domain", default=""); k.add_argument("--tags", default="", help="axis:value tags, comma separated")
    k.add_argument("--values", default="", help="the measured values of the chosen look")
    a = p.parse_args(argv)
    if a.cmd == "pick":
        try:
            res = pick(a.look, a.why, a.others.split(","), a.domain, [t for t in a.tags.split(",") if t.strip()], a.values)
        except ValueError as e:
            print(f"not recorded: {e}", file=sys.stderr)
            return 2
        print(f"logged a taste win: {res['taste']['what']}")
        if res["note"]:
            print(f"and a note in {a.domain}: {res['note']['id']} ({res['note']['status']})")
        else:
            print("no --domain, so no note; add one so the next job in that domain can weigh the pick")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
