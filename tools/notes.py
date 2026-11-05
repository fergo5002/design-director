"""Notes: what past jobs showed, with evidence and counts, read by the next job and weighed.

After a job, up to five observations are written down, each with its evidence: "the client
asked for larger type on the phone fold twice", with where each time shows. The next job in
the same domain or brand reads them as untrusted notes and weighs them itself. They are
observations, not rules: nothing here says "always" or "never", and nothing acts on them
but the agent reading them.

How the list stays useful as it grows:

- Changed one note at a time by code, never rewritten wholesale, so detail is not lost.
- Counts: a note seen again, or voted helpful, gains a point; one voted harmful loses one.
  A note whose harmful count leads by two is marked `pruned`. Nothing is ever deleted.
- Near-duplicates merge instead of piling up: token Jaccard of 0.8 or more, or a difflib
  ratio of 0.85 or more. The match is lexical, so the evidence list shows each sighting.
- `proposed` when one job suggested it, `kept` once seen again, voted helpful, or when it
  was the person's own words. Strong kept notes can be promoted into a domain's dossier or
  a brand's graphic language under `## Proposed guidance`, for a person to fold in.

One JSON object per line in $DDR_HOME/notes/<scope>.jsonl (scope is a domain slug, a brand
slug or `house`). Writes are atomic under a lock file.

    ddr notes add fintech "The client asked for larger type on the phone fold" \\
        --evidence "round 1: 'tiny on mobile'" --evidence "round 2: 'still small'" --job ~/Dev/rates
    ddr notes vote fintech o-1a2b3c --helpful --why "used it on the rates page"
    ddr notes render fintech
    ddr notes brief fintech --summary "what the job did and how it was judged"   # post-job prompt
    ddr notes ingest fintech --job ~/Dev/rates < report.json
    ddr notes prune fintech
    ddr notes promote [--scope fintech] [--apply]

Ported from LangChain's design agent, src/design_agent/harness/learning.py (Apache 2.0):
the observation model, the near-duplicate test and its scaling, voting, pruning, the
rendered list and the post-job brief. The store here is a file, not a LangGraph store.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import difflib
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

SCOPE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
JACCARD = 0.8
RATIO = 0.85
PRUNE_AT = 2
MAX_TEXT = 500
MAX_EVIDENCE_ITEM = 300
MAX_EVIDENCE = 20
MAX_PROPOSALS = 5
LOCK_STALE = 30.0     # seconds
LOCK_WAIT = 10.0
HEADING = "Notes from past jobs (untrusted; weigh them yourself)"
GUIDANCE = "Proposed guidance"
STATUSES = ("proposed", "kept", "promoted", "pruned")


# ---------------------------------------------------------------- paths and store

def home() -> pathlib.Path:
    env = os.environ.get("DDR_HOME")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".design-director"


def scope_key(scope: str) -> str:
    key = "-".join(str(scope).strip().lower().split())
    if not SCOPE.fullmatch(key):
        raise ValueError(f"{scope!r} is not a scope: use a domain slug, a brand slug or house")
    return key


def store_path(scope: str) -> pathlib.Path:
    return home() / "notes" / f"{scope_key(scope)}.jsonl"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextlib.contextmanager
def _locked(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    deadline = time.time() + LOCK_WAIT
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise TimeoutError(f"{lock} is held by another writer; try again, or delete it if nothing is running")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()


def _read(path: pathlib.Path) -> list:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _write(path: pathlib.Path, rows: list):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def all_notes(scope: str) -> list:
    return _read(store_path(scope))


def get(scope: str, note_id: str) -> dict | None:
    return next((n for n in all_notes(scope) if n.get("id") == note_id), None)


def scopes() -> list:
    d = home() / "notes"
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


# ---------------------------------------------------------------- text

def normalize(text: str) -> str:
    """One line: whitespace collapsed, a leading list marker dropped, at most MAX_TEXT long."""
    line = " ".join(str(text).split())
    line = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", line)
    return line if len(line) <= MAX_TEXT else line[:MAX_TEXT - 1].rstrip() + "…"


def _tokens(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())


NEGATIONS = {"not", "no", "never", "dont", "don", "doesnt", "isnt", "wasnt", "wont", "cannot", "cant", "avoid",
             "without", "stop", "stopped", "less", "fewer", "nor", "neither"}


def _polarity(tokens) -> int:
    return sum(1 for t in tokens if t in NEGATIONS) % 2


def similarity(a: str, b: str) -> float:
    """The higher of token Jaccard and difflib's ratio, each scaled so that its threshold is 1.0.
    Two notes of opposite polarity ("do use serif" and "do not use serif") are never near-duplicates:
    a contradiction is a counter-observation, not another sighting (review, 2026-11-05)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if a.strip().lower() == b.strip().lower() else 0.0
    if _polarity(ta) != _polarity(tb):
        return 0.0
    sa, sb = set(ta), set(tb)
    jaccard = len(sa & sb) / len(sa | sb)
    ratio = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return max(jaccard / JACCARD, ratio / RATIO)


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _evidence(items) -> list:
    if items is None:
        return []
    if isinstance(items, (str, int, float)):
        items = [items]
    out = []
    for item in items:
        line = _short(" ".join(str(item).split()), MAX_EVIDENCE_ITEM)
        if line and line not in out:
            out.append(line)
    return out


def _merge_list(old, new, cap=None):
    merged = list(old) + [x for x in new if x not in old]
    return merged[-cap:] if cap else merged


def score(n: dict) -> int:
    return int(n.get("helpful", 0)) - int(n.get("harmful", 0))


# ---------------------------------------------------------------- operations

def add(scope: str, text: str, evidence=(), job: str = "", person: bool = False):
    """Save one observation, or merge it into a near-duplicate (helpful +1, evidence and jobs
    merged, kept). Returns (note, merged)."""
    key = scope_key(scope)
    line = normalize(text)
    if not line:
        raise ValueError("a note needs text")
    found = _evidence(evidence)
    path = store_path(key)
    with _locked(path):
        rows = _read(path)
        now = _now()
        # A person's own words (a reason given for a pick) are a fact each time: they merge only with the
        # same words. Lexical similarity merged "the rate table reads calm" into "... reads loud" (review).
        sim = (lambda a, b: 1.0 if normalize(a).lower() == normalize(b).lower() else 0.0) if person else similarity
        best = max(((sim(line, r.get("text", "")), r) for r in rows), key=lambda p: p[0], default=(0.0, None))
        if best[1] is not None and best[0] >= 1.0:
            n = best[1]
            n["helpful"] = int(n.get("helpful", 0)) + 1
            n["evidence"] = _merge_list(n.get("evidence", []), found, MAX_EVIDENCE)
            n["jobs"] = _merge_list(n.get("jobs", []), [job] if job else [])
            n["person"] = bool(n.get("person")) or person
            n["updated"] = now
            if n.get("status") in ("proposed", None):
                n["status"] = "kept"
            elif n.get("status") == "pruned" and int(n.get("harmful", 0)) - n["helpful"] < PRUNE_AT:
                n["status"] = "kept"
            _write(path, rows)
            return n, True
        n = {"id": f"o-{uuid.uuid4().hex[:6]}", "scope": key, "text": line, "evidence": found[-MAX_EVIDENCE:],
             "jobs": [job] if job else [], "helpful": 0, "harmful": 0,
             "status": "kept" if person else "proposed", "person": bool(person),
             "created": now, "updated": now, "promoted_to": None}
        while any(r.get("id") == n["id"] for r in rows):
            n["id"] = f"o-{uuid.uuid4().hex[:6]}"
        rows.append(n)
        _write(path, rows)
        return n, False


def vote(scope: str, note_id: str, helpful: bool, why: str = "") -> dict:
    """Count one rating. Helpful also keeps a proposed note. KeyError when there is no such note."""
    path = store_path(scope)
    with _locked(path):
        rows = _read(path)
        n = next((r for r in rows if r.get("id") == note_id), None)
        if n is None:
            raise KeyError(note_id)
        if helpful:
            n["helpful"] = int(n.get("helpful", 0)) + 1
            if n.get("status") == "proposed":
                n["status"] = "kept"
        else:
            n["harmful"] = int(n.get("harmful", 0)) + 1
        if why.strip():
            n["evidence"] = _merge_list(n.get("evidence", []),
                                        _evidence([f"voted {'helpful' if helpful else 'harmful'}: {why}"]), MAX_EVIDENCE)
        n["updated"] = _now()
        _write(path, rows)
        return n


def prune(scope: str) -> list:
    """Mark every note whose harmful count leads by PRUNE_AT or more as pruned. Nothing is deleted."""
    path = store_path(scope)
    if not path.exists():
        return []
    with _locked(path):
        rows = _read(path)
        hit = [r for r in rows if r.get("status") != "pruned" and -score(r) >= PRUNE_AT]
        for r in hit:
            r["status"] = "pruned"
            r["updated"] = _now()
        if hit:
            _write(path, rows)
        return hit


def ranked(scope: str) -> list:
    """Kept and proposed notes, best score first, kept before proposed, newest touched first."""
    live = [n for n in all_notes(scope) if n.get("status") in ("kept", "proposed")]
    live.sort(key=lambda n: n.get("updated", ""), reverse=True)
    return sorted(live, key=lambda n: (-score(n), n.get("status") != "kept"))


def render_line(n: dict) -> str:
    ev = n.get("evidence", [])
    newest = ev[-2:]
    if newest:
        shown = "; ".join(_short(x, 140) for x in reversed(newest))
        extra = len(ev) - len(newest)
        shown += f"; +{extra} more" if extra else ""
    else:
        shown = "none recorded"
    return f"- {n['text']} (+{n.get('helpful', 0)}/-{n.get('harmful', 0)}, {n.get('status')}; evidence: {shown}) [{n['id']}]"


def render(scope: str, limit: int = 12) -> str:
    try:
        shown = ranked(scope)
    except ValueError:
        return ""
    if not shown:
        return ""
    lines = [HEADING] + [render_line(n) for n in shown[:limit]]
    if len(shown) > limit:
        lines.append(f"({len(shown) - limit} more with lower scores are not shown: `ddr notes list {scope_key(scope)}`)")
    return "\n".join(lines)


POST_JOB = """\
ROLE
You read one finished design job in {scope} and write down what it showed, for whoever runs the
next job there. You change nothing and start nothing.

THE JOB
{summary}

ALREADY NOTED FOR {scope}
{existing}

WHAT TO WRITE
Up to five observations. An observation is something that happened in this job, with where it
shows: "Fergus asked for more air around the rate table twice", with the evidence ["round 1:
'it is cramped'", "round 2: 'still tight on the phone'"]. Useful ones are specific to this kind
of work, point at what happened (quote the person, name the file, the screenshot or the
viewport) and could change what the next job does. Write what happened and how often,
never a rule: whether and how to act on it is the next job's call.
If a note above says the same thing and this job shows it again, repeat that note's words
exactly, so it is counted again. If this job went against one, write what happened instead.
Fewer is fine, and so is none.

OUTPUT
Your final message is this JSON and nothing else:
{{"scope": "{scope}", "observations": [{{"text": "...", "evidence": ["...", "..."]}}]}}
"""


def post_job_brief(scope: str, summary: str) -> str:
    key = scope_key(scope)
    return POST_JOB.format(scope=key, summary=(summary or "").strip() or "(no summary given)",
                           existing=render(key, limit=30) or "Nothing yet.")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _json_in(report: str):
    text = (report or "").strip()
    candidates = [text] + _FENCE.findall(text)
    for o, c in (("{", "}"), ("[", "]")):
        s, e = text.find(o), text.rfind(c)
        if 0 <= s < e:
            candidates.append(text[s:e + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except ValueError:
            continue
    return None


def parse(report: str) -> list:
    value = _json_in(report)
    items = value.get("observations") if isinstance(value, dict) else value
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            text, ev = item, None
        elif isinstance(item, dict):
            text, ev = item.get("text"), item.get("evidence")
        else:
            continue
        line = normalize(str(text or ""))
        if line:
            out.append({"text": line, "evidence": _evidence(ev)})
    return out[:MAX_PROPOSALS]


def ingest(scope: str, report_text: str, job: str) -> list:
    """Add the observations in a post-job report (at most five). Returns [(note, merged)]."""
    return [add(scope, p["text"], p["evidence"], job) for p in parse(report_text)]


# ---------------------------------------------------------------- promotion

def _target(scope: str):
    """(path to write, why not) for a scope: a domain's dossier, else a brand's graphic language."""
    import domains
    import brandpack
    try:
        if domains.load(scope) is not None:
            return domains.path_for_write(domains.load(scope)["slug"]) / "dossier.md", ""
    except ValueError as e:
        return None, str(e)
    folder, layer = brandpack.find(scope)
    if folder is not None:
        if layer != "home":
            return None, f"brand {scope!r} is a read-only template; `ddr brand init {scope}` first"
        return folder / "graphic-language.md", ""
    return None, f"no domain or brand called {scope!r}"


def _append_guidance(path: pathlib.Path, line: str, marker: str) -> bool:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in text:
        return False
    lines = text.splitlines()
    head = next((i for i, l in enumerate(lines) if re.match(rf"^##\s+{re.escape(GUIDANCE)}\s*$", l)), None)
    if head is None:
        new = text.rstrip() + ("\n\n" if text.strip() else "") + f"## {GUIDANCE}\n\n{line}\n"
    else:
        end = next((i for i in range(head + 1, len(lines)) if re.match(r"^#{1,2}\s", lines[i])), len(lines))
        last = end
        while last > head + 1 and not lines[last - 1].strip():
            last -= 1
        insert = [line] if last > head + 1 else ["", line]
        tail = [""] if end < len(lines) else []
        new_lines = lines[:last] + insert + tail + lines[end:]
        new = "\n".join(new_lines).rstrip() + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, str(path))
    return True


def promote(scope=None, min_score=3, min_jobs=2, apply=False, today=None) -> list:
    """Kept notes with score >= min_score and either a person's words or min_jobs distinct jobs.
    With apply, each is appended under ## Proposed guidance and marked promoted."""
    day = str(today or _dt.date.today().isoformat())
    out = []
    for s in ([scope_key(scope)] if scope else scopes()):
        cands = [n for n in all_notes(s) if n.get("status") == "kept" and score(n) >= min_score
                 and (n.get("person") or len(set(n.get("jobs", []))) >= min_jobs)]
        if not cands:
            continue
        target, why = _target(s) if apply else _target_dry(s)
        for n in cands:
            row = {"scope": s, "id": n["id"], "text": n["text"], "score": score(n),
                   "jobs": len(set(n.get("jobs", []))), "person": bool(n.get("person")),
                   "target": str(target) if target else None, "why_not": why, "applied": False}
            if apply and target is not None:
                line = f"- {n['text']} (note [{n['id']}], +{n.get('helpful', 0)}/-{n.get('harmful', 0)}, promoted {day})"
                _append_guidance(target, line, f"note [{n['id']}]")
                _mark_promoted(s, n["id"], str(target))
                row["applied"] = True
            out.append(row)
    return out


def _target_dry(scope: str):
    """Where promotion would write, without creating a domain layer."""
    import domains
    import brandpack
    dom = domains.load(scope)
    if dom is not None:
        return domains.home_domains() / dom["slug"] / "dossier.md", ""
    folder, layer = brandpack.find(scope)
    if folder is not None:
        return (folder / "graphic-language.md", "") if layer == "home" else \
            (None, f"brand {scope!r} is a read-only template; `ddr brand init {scope}` first")
    return None, f"no domain or brand called {scope!r}"


def _mark_promoted(scope: str, note_id: str, target: str):
    path = store_path(scope)
    with _locked(path):
        rows = _read(path)
        for r in rows:
            if r.get("id") == note_id:
                r["status"] = "promoted"
                r["promoted_to"] = target
                r["updated"] = _now()
        _write(path, rows)


# ---------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr notes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add"); a_.add_argument("scope"); a_.add_argument("text")
    a_.add_argument("--evidence", action="append", default=[], help="what happened and where it shows; repeat for more")
    a_.add_argument("--job", default="", help="a label for the job: the project path or the brief's slug (default: here)")
    a_.add_argument("--person", action="store_true", help="the person's own words (a reason given for a pick)")
    v = sub.add_parser("vote"); v.add_argument("scope"); v.add_argument("id")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--helpful", action="store_true"); g.add_argument("--harmful", action="store_true")
    v.add_argument("--why", default="")
    sub.add_parser("prune").add_argument("scope")
    li = sub.add_parser("list"); li.add_argument("scope"); li.add_argument("--all", action="store_true")
    li.add_argument("--json", action="store_true")
    r = sub.add_parser("render"); r.add_argument("scope"); r.add_argument("--limit", type=int, default=12)
    b = sub.add_parser("brief"); b.add_argument("scope"); b.add_argument("--summary", default="")
    b.add_argument("--summary-file")
    ig = sub.add_parser("ingest"); ig.add_argument("scope"); ig.add_argument("--job", default="")
    ig.add_argument("--file", help="the post-job report (default: read stdin)")
    pr = sub.add_parser("promote"); pr.add_argument("--scope"); pr.add_argument("--min-score", type=int, default=3)
    pr.add_argument("--min-jobs", type=int, default=2); pr.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.cmd == "add":
            ev = [e for e in a.evidence if e.strip()]
            if not ev:
                print("not added: a note needs --evidence (what happened and where it shows)", file=sys.stderr)
                return 2
            n, merged = add(a.scope, a.text, ev, a.job or str(pathlib.Path.cwd()), a.person)
            print(f"{'merged into' if merged else 'added'} {n['id']} ({n['status']}, +{n['helpful']}/-{n['harmful']})")
            return 0
        if a.cmd == "vote":
            try:
                n = vote(a.scope, a.id, a.helpful, a.why)
            except KeyError:
                print(f"no note {a.id} in {a.scope}: `ddr notes list {a.scope}`", file=sys.stderr)
                return 2
            print(f"{n['id']} now +{n['helpful']}/-{n['harmful']}, {n['status']}")
            return 0
        if a.cmd == "prune":
            hit = prune(a.scope)
            print(f"pruned {len(hit)}" + "".join(f"\n  {n['id']} {n['text']}" for n in hit))
            return 0
        if a.cmd == "list":
            rows = all_notes(a.scope) if a.all else ranked(a.scope)
            if a.json:
                print(json.dumps(rows, ensure_ascii=False, indent=1))
            else:
                for n in rows:
                    print(f"  {n['id']} {n['status']:8} +{n.get('helpful', 0)}/-{n.get('harmful', 0)} "
                          f"jobs {len(set(n.get('jobs', [])))}  {n['text']}")
                if not rows:
                    print(f"no notes in {a.scope}")
            return 0
        if a.cmd == "render":
            print(render(a.scope, a.limit))
            return 0
        if a.cmd == "brief":
            summary = pathlib.Path(a.summary_file).read_text(encoding="utf-8") if a.summary_file else a.summary
            print(post_job_brief(a.scope, summary))
            return 0
        if a.cmd == "ingest":
            text = pathlib.Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
            got = ingest(a.scope, text, a.job or str(pathlib.Path.cwd()))
            if not got and parse(text) == [] and _json_in(text) is None:
                print("no JSON found in the report; nothing added", file=sys.stderr)
            for n, merged in got:
                print(f"{'merged into' if merged else 'added'} {n['id']}: {n['text']}")
            return 0
        if a.cmd == "promote":
            rows = promote(a.scope, a.min_score, a.min_jobs, a.apply)
            for row in rows:
                state = "promoted" if row["applied"] else ("would promote" if row["target"] else "cannot promote")
                print(f"  {state:14} {row['scope']}/{row['id']} (+{row['score']}, {row['jobs']} jobs"
                      f"{', person' if row['person'] else ''}) {row['text']}")
                print(f"  {'':14} -> {row['target'] or row['why_not']}")
            if not rows:
                print("no note is strong enough to promote yet")
            elif not a.apply:
                print("dry run: add --apply to write them under ## Proposed guidance")
            return 0
    except (ValueError, OSError, TimeoutError) as e:
        print(f"not done: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
