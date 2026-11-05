"""The claims ledger: every number and product claim a design makes, with its source and a check.

A page that says "decisions in 24 hours" is making a promise. The ledger in
.design/brief/claims.json holds each claim with where it came from and, where it can be
checked by a program, the command that checks it. `ddr claims check` runs those commands
from the project root (no shell, 60 s each): exit 0 marks the claim verified with the last
line of output as its evidence; anything else is a finding. A claim checked by reading
something needs status `verified` and the read recorded as evidence. A claim marked
`removed` must not still be on the page: its text in any `--src` file is an error.

    ddr claims add --text "Decisions in 24 hours" --source "ops sheet 2026-10-30" \\
        --check "python3 .design/brief/claims_check.py C1"
    ddr claims set C2 --status verified --evidence "read the rate card PDF, page 2, on 2026-11-05"
    ddr claims set C3 --status removed
    ddr claims list
    ddr claims check --src src/ [--json]      # exit 0 pass, 1 findings, 2 could not run

The ledger follows the claims table of LangChain's design agent content brief
(skills/content-brief, Apache 2.0), made executable.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

STATUSES = ("unverified", "verified", "removed")
MIN_EVIDENCE = 12
TIMEOUT = 60
ID = re.compile(r"C[1-9]\d*")
EXTS = {".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte", ".astro",
        ".svg", ".md", ".mdx", ".json", ".txt"}
SKIP = {"node_modules", ".git", ".next", "dist", "build", ".design"}


def path(project) -> pathlib.Path:
    return pathlib.Path(project) / ".design" / "brief" / "claims.json"


def load(project) -> dict | None:
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
    fd, tmp = tempfile.mkstemp(dir=str(f.parent), prefix="claims.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        h.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, str(f))


def _f(rule, message, cid="", severity="error") -> dict:
    return {"severity": severity, "rule": rule, "message": (f"{cid}: " if cid else "") + message,
            "file": ".design/brief/claims.json", "line": 0}


def _squash(s: str) -> str:
    return " ".join(s.split()).lower()


def _texts(src_paths):
    """(path, squashed text, squashed text without tags) for every source file."""
    for p in map(pathlib.Path, src_paths):
        files = [p] if p.is_file() else [f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in EXTS
                                         and not (set(f.relative_to(p).parts[:-1]) & SKIP)]
        for f in files:
            raw = f.read_text(encoding="utf-8", errors="replace")
            yield f, _squash(raw), _squash(re.sub(r"<[^>]+>", " ", raw))


def _split(cmd: str, windows=None) -> list:
    """Split a check command. POSIX rules treat backslashes as escapes, which mangles a Windows path
    (C:\\Brain\\check.py), so on Windows split without them and strip the quotes."""
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return shlex.split(cmd)
    return [a[1:-1] if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'" else a for a in shlex.split(cmd, posix=False)]


def _argv(cmd: str, windows=None):
    """What subprocess runs: on Windows the command line itself, which CreateProcess parses with the
    Windows rules (quotes inside a token, backslashes in paths); elsewhere the POSIX split."""
    if windows is None:
        windows = os.name == "nt"
    return cmd if windows else _split(cmd, windows=False)


def _run(cmd: str, cwd, timeout):
    argv = _argv(cmd)
    if not argv:
        raise ValueError("empty check command")
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def check(project, src_paths=(), timeout: float = TIMEOUT) -> dict:
    """Run every claim's check and look for removed claims in the source. Tool "claims"."""
    project = pathlib.Path(project)
    out, rows = [], []
    try:
        data = load(project)
    except ValueError as e:
        return _report([_f("tool.could-not-run", str(e))], rows)
    if data is None:
        return _report([_f("tool.could-not-run", f"no claims ledger at {path(project)}: `ddr claims add`")], rows)
    for p in src_paths:
        if not pathlib.Path(p).exists():
            out.append(_f("tool.could-not-run", f"--src {p} does not exist"))
    if data.get("version") != 1:
        out.append(_f("claim.version", "version must be 1"))
    claims = data.get("claims")
    if not isinstance(claims, list):
        return _report(out + [_f("claim.schema", "claims must be a list")], rows)
    texts = None
    seen, changed = set(), False
    for c in claims:
        if not isinstance(c, dict):
            out.append(_f("claim.schema", "a claim is not an object"))
            continue
        cid = str(c.get("id", ""))
        if not ID.fullmatch(cid):
            out.append(_f("claim.id", "ids are C1, C2 and so on", cid or "?"))
        if cid in seen:
            out.append(_f("claim.duplicate-id", "id used twice", cid))
        seen.add(cid)
        text = str(c.get("text") or "").strip()
        if not text:
            out.append(_f("claim.no-text", "a claim needs its text, as it appears on the page", cid))
        st = c.get("status", "unverified")
        if st not in STATUSES:
            out.append(_f("claim.status", f"status must be one of {STATUSES}", cid))
            continue
        if st == "removed":
            rows.append({"id": cid, "status": "removed", "text": text})
            if text and src_paths:
                if texts is None:
                    try:
                        texts = list(_texts([p for p in src_paths if pathlib.Path(p).exists()]))
                    except OSError as e:
                        out.append(_f("tool.could-not-run", f"could not read the source: {e}"))
                        texts = []
                needle = _squash(text)
                for f, raw, plain in texts:
                    if needle in raw or needle in plain:
                        out.append({**_f("claim.removed-but-present", f"removed claim \"{text}\" is still in the source", cid),
                                    "file": str(f)})
            continue
        cmd = str(c.get("check") or "").strip()
        if cmd:
            try:
                res = _run(cmd, project, timeout)
            except subprocess.TimeoutExpired:
                out.append(_f("tool.could-not-run", f"check timed out after {timeout:g} s: {cmd}", cid))
                rows.append({"id": cid, "status": "not checked", "text": text})
                continue
            except (OSError, ValueError) as e:
                out.append(_f("tool.could-not-run", f"check could not start ({type(e).__name__}: {e}): {cmd}", cid))
                rows.append({"id": cid, "status": "not checked", "text": text})
                continue
            if res.returncode == 0:
                lines = [l for l in res.stdout.splitlines() if l.strip()]
                ev = lines[-1].strip() if lines else f"`{cmd}` exited 0"
                if c.get("status") != "verified" or c.get("evidence") != ev:
                    c["status"], c["evidence"] = "verified", ev
                    changed = True
                rows.append({"id": cid, "status": "verified", "text": text, "evidence": ev})
            else:
                tail = " | ".join(l.strip() for l in (res.stderr + "\n" + res.stdout).splitlines() if l.strip())[-300:]
                out.append(_f("claim.check-failed", f"\"{text}\" failed its check (exit {res.returncode}): {tail}", cid))
                if c.get("status") == "verified":
                    c["status"] = "unverified"
                    changed = True
                rows.append({"id": cid, "status": "failed", "text": text})
            continue
        ev = str(c.get("evidence") or "").strip()
        if st != "verified" or len(ev) < MIN_EVIDENCE:
            out.append(_f("claim.unverified", f"\"{text}\" has no check and no recorded read: add --check, or "
                          f"`ddr claims set {cid} --status verified --evidence \"what you read, where, when\"`, "
                          f"or remove it from the page and mark it removed", cid))
            rows.append({"id": cid, "status": "unverified", "text": text})
        else:
            rows.append({"id": cid, "status": "verified", "text": text, "evidence": ev})
    if changed:
        save(project, data)
    return _report(out, rows)


def _report(findings, rows) -> dict:
    if any(f["rule"] == "tool.could-not-run" for f in findings):
        code = 2
    else:
        code = 1 if any(f["severity"] == "error" for f in findings) else 0
    n = sum(1 for f in findings if f["severity"] == "error")
    summary = {0: f"{sum(1 for r in rows if r['status'] == 'verified')} claims verified, "
                  f"{sum(1 for r in rows if r['status'] == 'removed')} removed",
               1: f"{n} claims not proven", 2: "could not run: " + "; ".join(
                   f["message"] for f in findings if f["rule"] == "tool.could-not-run")}[code]
    return {"ok": code == 0, "exit": code, "tool": "claims", "findings": findings, "summary": summary, "claims": rows}


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS)
    p = argparse.ArgumentParser(prog="ddr claims", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add", parents=[common]); a_.add_argument("--text", required=True)
    a_.add_argument("--source", required=True); a_.add_argument("--check", default="")
    a_.add_argument("--status", default="unverified"); a_.add_argument("--evidence", default="")
    s = sub.add_parser("set", parents=[common]); s.add_argument("id")
    for k in ("text", "source", "check", "status", "evidence"):
        s.add_argument(f"--{k}")
    sub.add_parser("list", parents=[common])
    c = sub.add_parser("check", parents=[common]); c.add_argument("--src", nargs="*", default=[])
    c.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    proj = pathlib.Path(a.project)
    try:
        if a.cmd == "add":
            if a.status not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            if not a.text.strip() or not a.source.strip():
                raise ValueError("a claim needs --text (as it appears) and --source (where it comes from)")
            data = load(proj) or {"version": 1, "claims": []}
            data.setdefault("claims", [])
            nums = [int(x["id"][1:]) for x in data["claims"] if ID.fullmatch(str(x.get("id", "")))]
            row = {"id": f"C{max(nums, default=0) + 1}", "text": a.text.strip(), "source": a.source.strip(),
                   "check": a.check.strip(), "status": a.status, "evidence": a.evidence.strip()}
            data["claims"].append(row)
            save(proj, data)
            print(f"added {row['id']}" + ("" if row["check"] else ": no --check, so record what you read with "
                                          f"`ddr claims set {row['id']} --status verified --evidence ...`"))
            return 0
        if a.cmd == "set":
            data = load(proj)
            row = next((x for x in (data or {}).get("claims", []) if x.get("id") == a.id), None)
            if row is None:
                raise ValueError(f"no claim {a.id}: `ddr claims list`")
            if a.status is not None and a.status not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            for k in ("text", "source", "check", "status", "evidence"):
                if getattr(a, k) is not None:
                    row[k] = getattr(a, k)
            save(proj, data)
            print(f"{row['id']} {row.get('status')}")
            return 0
        if a.cmd == "list":
            data = load(proj)
            for x in (data or {}).get("claims", []):
                print(f"  {x.get('id'):4} {x.get('status', ''):10} {x.get('text', '')}  ({x.get('source', '')})")
                if x.get("check"):
                    print(f"  {'':15} check: {x['check']}")
                if x.get("evidence"):
                    print(f"  {'':15} evidence: {x['evidence']}")
            if not data:
                print(f"no claims ledger at {path(proj)}")
            return 0
        if a.cmd == "check":
            res = check(proj, a.src)
            if a.json:
                print(json.dumps(res, ensure_ascii=False))
            else:
                for f in res["findings"]:
                    print(f"  {f['severity']:5} {f['rule']:26} {f['message']}")
                print(res["summary"])
            return res["exit"]
    except ValueError as e:
        print(f"not done: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
