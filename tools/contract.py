"""The contract: every requirement of a job, in the person's words, with its status and evidence.

Exact requirements are lost between rounds when they live only in a conversation: the size
Fergus asked for in round one is gone by round three. The contract keeps them in
.design/brief/contract.json and two checks hold the order: `plan` before building (every
requirement has a source) and `final` before shipping (nothing open, every closed one has
evidence, every supersession points at a real requirement).

    ddr contract init --job new|edit-list|restyle --brief "one line"
    ddr contract add --kind change --text "Make SC the same size as PFOR" --source "Fergus 2026-11-04: '...'"
    ddr contract add --kind copy --text "Hero line" --source "..." --exact "Decisions in 24 hours"
    ddr contract set R2 --status satisfied --evidence "desktop fold shot: SC 48px, PFOR 48px"
    ddr contract set R3 --status superseded --superseded-by R5 --evidence "replaced in round 2"
    ddr contract set R4 --status waived --by Fergus --evidence "keep the old size"
    ddr contract list
    ddr contract check --phase plan|final [--json]     # exit 0 pass, 1 findings, 2 could not run
    ddr contract copy                                   # every line that must ship verbatim

`edit-list` (changes to something that exists) adds a scope requirement on init: only the
listed changes. Kinds: change, copy (with --exact), asset, size, must-not, scope. Statuses:
open, satisfied, superseded (needs --superseded-by), waived (needs evidence naming who).

The plan and final phases follow the intake and completion checks of LangChain's design
agent (workspace/tools/artifact-contract.mjs, Apache 2.0), rewritten for this format.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import tempfile

JOBS = ("new", "edit-list", "restyle")
KINDS = ("change", "copy", "asset", "size", "must-not", "scope")
STATUSES = ("open", "satisfied", "superseded", "waived")
PHASES = ("plan", "final")
MIN_EVIDENCE = 12
SCOPE_TEXT = "Only the listed changes. Palette, layout, structure and components stay unless a requirement names them."
ID = re.compile(r"R[1-9]\d*")


def path(project) -> pathlib.Path:
    return pathlib.Path(project) / ".design" / "brief" / "contract.json"


def load(project) -> dict | None:
    """The contract, or None when there is none. Raises ValueError when it does not parse."""
    f = path(project)
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{f} does not parse: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{f} must hold a JSON object")
    return data


def save(project, data: dict):
    f = path(project)
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(f.parent), prefix="contract.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        h.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, str(f))


def _f(rule, message, rid="", severity="error") -> dict:
    return {"severity": severity, "rule": rule, "message": (f"{rid}: " if rid else "") + message,
            "file": ".design/brief/contract.json", "line": 0}


def _report(findings) -> dict:
    if any(f["rule"] == "tool.could-not-run" for f in findings):
        code = 2
    else:
        code = 1 if any(f["severity"] == "error" for f in findings) else 0
    n = sum(1 for f in findings if f["severity"] == "error")
    summary = {0: "contract holds", 1: f"{n} problems in the contract",
               2: "could not run: " + "; ".join(f["message"] for f in findings)}[code]
    return {"ok": code == 0, "exit": code, "tool": "contract", "findings": findings, "summary": summary}


def _schema(data: dict) -> list:
    out = []
    if data.get("version") != 1:
        out.append(_f("contract.version", "version must be 1"))
    if data.get("job") not in JOBS:
        out.append(_f("contract.job", f"job must be one of {JOBS}"))
    reqs = data.get("requirements")
    if not isinstance(reqs, list):
        return out + [_f("contract.requirements", "requirements must be a list")]
    seen = set()
    for i, r in enumerate(reqs):
        if not isinstance(r, dict):
            out.append(_f("contract.requirements", f"requirement {i + 1} is not an object"))
            continue
        rid = str(r.get("id", ""))
        if not ID.fullmatch(rid):
            out.append(_f("contract.id", "ids are R1, R2 and so on", rid or f"#{i + 1}"))
        if rid in seen:
            out.append(_f("contract.duplicate-id", "id used twice", rid))
        seen.add(rid)
        if r.get("kind") not in KINDS:
            out.append(_f("contract.kind", f"kind must be one of {KINDS}", rid))
        if not str(r.get("text") or "").strip():
            out.append(_f("contract.no-text", "a requirement needs its text", rid))
        if r.get("status") not in STATUSES:
            out.append(_f("contract.status", f"status must be one of {STATUSES}", rid))
        if r.get("kind") == "copy" and not str(r.get("exact") or "").strip():
            out.append(_f("contract.copy-exact", "a copy requirement needs exact: the words that ship verbatim", rid))
    return out


def check(project, phase: str) -> dict:
    """`plan`: valid, at least one requirement, every one sourced. `final`: also nothing open,
    evidence on every closed one, supersessions that point at a real id, waivers that name who."""
    if phase not in PHASES:
        return _report([_f("tool.could-not-run", f"phase must be one of {PHASES}")])
    try:
        data = load(project)
    except ValueError as e:
        return _report([_f("tool.could-not-run", str(e))])
    if data is None:
        return _report([_f("tool.could-not-run", f"no contract at {path(project)}: `ddr contract init`")])
    out = _schema(data)
    reqs = [r for r in data.get("requirements") or [] if isinstance(r, dict)]
    if not reqs:
        out.append(_f("contract.empty", "no requirements: write down what was asked, in the person's words"))
    for r in reqs:
        if not str(r.get("source") or "").strip():
            out.append(_f("contract.no-source", "every requirement needs a source: who asked, when, in their words", r.get("id", "")))
    if data.get("job") == "edit-list" and not any(r.get("kind") == "scope" for r in reqs):
        out.append(_f("contract.scope-missing", "an edit-list job needs its scope requirement: " + SCOPE_TEXT))
    if phase == "final":
        ids = {r.get("id") for r in reqs}
        for r in reqs:
            rid, st, ev = r.get("id", ""), r.get("status"), str(r.get("evidence") or "").strip()
            if st == "open":
                out.append(_f("contract.open", f"still open: {r.get('text', '')}", rid))
                continue
            if st in ("satisfied", "superseded", "waived") and len(ev) < MIN_EVIDENCE:
                out.append(_f("contract.thin-evidence", f"evidence must say where it shows (at least {MIN_EVIDENCE} "
                              "characters): the screenshot, the file, the measured value", rid))
            if st == "superseded":
                to = r.get("superseded_by")
                if not to or to not in ids or to == rid:
                    out.append(_f("contract.superseded-dangling", f"superseded_by must name another requirement, got {to!r}", rid))
            if st == "waived" and not re.search(r"\bby\s+\S+", ev, re.I):
                out.append(_f("contract.waiver-unnamed", "a waiver names who waived it: `--by <name>`", rid))
    return _report(out)


def exact_copy(project) -> list:
    """Every copy requirement's exact text that still has to ship (not superseded or waived)."""
    try:
        data = load(project)
    except ValueError:
        return []
    out = []
    for r in (data or {}).get("requirements") or []:
        if isinstance(r, dict) and r.get("kind") == "copy" and r.get("status") not in ("superseded", "waived"):
            t = str(r.get("exact") or "").strip()
            if t:
                out.append(t)
    return out


def _next_id(reqs) -> str:
    nums = [int(r["id"][1:]) for r in reqs if isinstance(r, dict) and ID.fullmatch(str(r.get("id", "")))]
    return f"R{max(nums, default=0) + 1}"


def _req(rid, kind, text, source, exact=None) -> dict:
    return {"id": rid, "kind": kind, "text": text, "source": source, "status": "open", "evidence": "",
            "superseded_by": None, "exact": exact}


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS)
    p = argparse.ArgumentParser(prog="ddr contract", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", parents=[common]); i.add_argument("--job", default="new", help=f"one of {JOBS}")
    i.add_argument("--brief", default=""); i.add_argument("--force", action="store_true")
    a_ = sub.add_parser("add", parents=[common]); a_.add_argument("--kind", required=True)
    a_.add_argument("--text", required=True); a_.add_argument("--source", required=True); a_.add_argument("--exact")
    s = sub.add_parser("set", parents=[common]); s.add_argument("id"); s.add_argument("--status")
    s.add_argument("--evidence"); s.add_argument("--superseded-by"); s.add_argument("--by")
    s.add_argument("--text"); s.add_argument("--source"); s.add_argument("--exact")
    sub.add_parser("list", parents=[common])
    c = sub.add_parser("check", parents=[common]); c.add_argument("--phase", default="final")
    c.add_argument("--json", action="store_true")
    sub.add_parser("copy", parents=[common])
    a = p.parse_args(argv)
    proj = pathlib.Path(a.project)

    def need():
        data = load(proj)
        if data is None:
            raise ValueError(f"no contract at {path(proj)}: `ddr contract init` first")
        data.setdefault("requirements", [])
        return data

    try:
        if a.cmd == "init":
            if a.job not in JOBS:
                raise ValueError(f"job must be one of {JOBS}: new, edit-list (changes to something that exists) "
                                 "or restyle (a supplied reference is preserved)")
            if path(proj).exists() and not a.force:
                print(f"not done: {path(proj)} exists (use --force to start again)", file=sys.stderr)
                return 2
            data = {"version": 1, "job": a.job, "brief": a.brief, "created": _dt.date.today().isoformat(),
                    "requirements": []}
            if a.job == "edit-list":
                data["requirements"].append(_req("R1", "scope", SCOPE_TEXT, "the job is a list of edits to existing work"))
            save(proj, data)
            print(f"created {path(proj)}\nnext: `ddr contract add --kind ... --text ... --source ...` for each thing asked")
            return 0
        if a.cmd == "add":
            if a.kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}")
            if not a.text.strip() or not a.source.strip():
                raise ValueError("a requirement needs --text and --source")
            if a.kind == "copy" and not (a.exact or "").strip():
                raise ValueError("a copy requirement needs --exact: the words that must ship verbatim")
            data = need()
            r = _req(_next_id(data["requirements"]), a.kind, a.text.strip(), a.source.strip(), a.exact)
            data["requirements"].append(r)
            save(proj, data)
            print(f"added {r['id']} ({r['kind']})")
            return 0
        if a.cmd == "set":
            data = need()
            r = next((x for x in data["requirements"] if isinstance(x, dict) and x.get("id") == a.id), None)
            if r is None:
                raise ValueError(f"no requirement {a.id}: `ddr contract list`")
            if a.status:
                if a.status not in STATUSES:
                    raise ValueError(f"status must be one of {STATUSES}")
                r["status"] = a.status
            if a.superseded_by:
                if not any(x.get("id") == a.superseded_by for x in data["requirements"]) or a.superseded_by == a.id:
                    raise ValueError(f"{a.superseded_by} is not another requirement")
                r["superseded_by"] = a.superseded_by
            if a.evidence is not None or a.by:
                ev = (a.evidence or "").strip()
                r["evidence"] = (f"waived by {a.by}: {ev}" if a.by else ev).strip(": ")
            for k in ("text", "source", "exact"):
                if getattr(a, k) is not None:
                    r[k] = getattr(a, k)
            save(proj, data)
            print(f"{r['id']} {r['status']}")
            return 0
        if a.cmd == "list":
            data = need()
            print(f"{data.get('job')}: {data.get('brief', '')}")
            for r in data["requirements"]:
                extra = f" -> {r['superseded_by']}" if r.get("superseded_by") else ""
                print(f"  {r.get('id'):4} {r.get('status', ''):10} {r.get('kind', ''):8} {r.get('text', '')}{extra}")
                if r.get("exact"):
                    print(f"  {'':24} exact: {r['exact']}")
                if r.get("evidence"):
                    print(f"  {'':24} evidence: {r['evidence']}")
            return 0
        if a.cmd == "check":
            res = check(proj, a.phase)
            if a.json:
                print(json.dumps(res, ensure_ascii=False))
            else:
                for f in res["findings"]:
                    print(f"  {f['severity']:5} {f['rule']:28} {f['message']}")
                print(res["summary"])
            return res["exit"]
        if a.cmd == "copy":
            need()
            for line in exact_copy(proj):
                print(line)
            return 0
    except ValueError as e:
        print(f"not done: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
