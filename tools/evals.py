"""ddr eval: run a design skill headless on real briefs, grade what it made and how, compare arms.

    ddr eval list [--cases DIR]
    ddr eval run --arm v1=~/skills/old/design-director --arm v2=skills/design-director \\
                 [--case ID ...] [--jobs 2] [--model opus] [--dry-run] [--max-total-usd 25]
    ddr eval report <run_id|latest> [--regrade] [--json]
    ddr eval sheet <run_id|latest>

Cases live in $DDR_HOME/evals/cases/<id>/case.toml (Fergus's, private). Each run writes
$DDR_HOME/evals/runs/<run_id>/<case>/<arm>/ (workdir, transcript.jsonl, stderr.txt,
grades.json) and results.json plus report.md at the run root. docs/evals.md has the case
format, the graders and what the harness cannot see.

Every grade is pass, fail or error. Fail means the output or the transcript broke the rule.
Error means the grader could not look (no Chromium, no brandpack, no transcript, a bad
regex), and an error is never counted as a pass. No model judges taste here: the graders
count what can be counted and a person reviews the contact sheets.

The grading ideas (trace order, questions before acting, exact copy, cost) are ported and
simplified from LangChain's design-agent (Apache License 2.0), src/design_agent/evals/
graders.py and trace.py.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as _dt
import hashlib
import html.parser
import json
import os
import pathlib
import re
import secrets
import io
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict, dataclass, field

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

# What a run may use. --tools limits what exists, --allowedTools approves it without a prompt
# (print mode cannot ask anyone), --disallowedTools denies the rest even inside Bash.
ALLOWED = "Read,Write,Edit,Glob,Grep,Bash,Skill"
DENIED = [
    "Bash(git push:*)", "Bash(git commit:*)", "Bash(brain:*)",
    "Bash(vercel:*)", "Bash(npx vercel:*)", "Bash(wrangler:*)", "Bash(npx wrangler:*)",
    "Bash(railway:*)", "Bash(netlify:*)", "Bash(npx netlify:*)", "Bash(gh:*)",
    "mcp__*", "mcp__whatsapp", "mcp__workspace-mcp-personal", "mcp__workspace-mcp-arbourvilla",
    "mcp__workspace-mcp-tighsauna", "mcp__workspace-mcp-tcd", "mcp__claude_ai_Gmail", "mcp__claude_ai_Slack",
    "WebFetch", "WebSearch",
]
# The probe in docs/evals.md showed that --setting-sources does not stop the user CLAUDE.md
# loading; these settings do, and they keep auto-memory out of the run.
RUN_SETTINGS = {"claudeMdExcludes": [str(pathlib.Path.home() / ".claude" / "CLAUDE.md"), "**/CLAUDE.md",
                                     "**/CLAUDE.local.md", "**/AGENTS.md"],
                "autoMemoryEnabled": False}
PLUGIN = "dd"                       # every arm gets the same plugin name, so a run cannot tell arms apart
SKILL = "design-director"
WRITES = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SKIP = {".git", "node_modules"}
MAX_JOBS = 3
# Put in front of every prompt unless the case says `preamble = false` or run gets --no-preamble.
PREAMBLE = ("This is an evaluation run in an isolated folder. Fergus is not available: do not ask questions, "
            "decide and say what you decided. Do not write to the vault or the brain, do not commit, push, "
            "deploy or publish. Save every deliverable under ./out/.")
# What a run's private copy of $DDR_HOME carries. evals/ and every shots/ folder stay behind.
HOME_COPY = ("domains", "brands", "notes", "taste.jsonl")
GIT_ARM = re.compile(r"git:(?P<repo>.+?)@(?P<ref>[^:@\s]+):(?P<path>.*)")

GRADERS = ("file-exists", "text-present", "text-absent", "max-count", "lint-clean", "brand-lint-clean",
           "unchanged", "dom-probe", "trace-order", "trace-present", "trace-absent", "questions-max",
           "cost-max", "isolation")


def home() -> pathlib.Path:
    env = os.environ.get("DDR_HOME")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".design-director"


def runs_dir() -> pathlib.Path:
    return home() / "evals" / "runs"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ cases

def _toml(text: str) -> dict:
    import sources
    return sources.loads(text)


def load_case(path: pathlib.Path) -> dict:
    """Read and check one case directory. Raises ValueError listing every problem."""
    toml = path / "case.toml"
    try:
        data = _toml(toml.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read {toml}: {e}") from None
    problems = []
    if data.get("id") != path.name:
        problems.append(f"id {data.get('id')!r} must match its directory name {path.name!r}")
    for key in ("title", "origin"):
        if not str(data.get(key) or "").strip():
            problems.append(f"needs {key}")
    if data.get("prompt_file"):
        pf = path / data["prompt_file"]
        if pf.is_file():
            data["prompt"] = pf.read_text(encoding="utf-8")
        else:
            problems.append(f"prompt_file {data['prompt_file']} not found")
    if not str(data.get("prompt") or "").strip():
        problems.append("needs prompt (or prompt_file)")
    if data.get("fixture") and not (path / data["fixture"]).is_dir():
        problems.append(f"fixture {data['fixture']} is not a directory beside case.toml")
    if data.get("append_system_prompt_file") and not (path / data["append_system_prompt_file"]).is_file():
        problems.append(f"append_system_prompt_file {data['append_system_prompt_file']} not found")
    try:
        data["budget_usd"] = float(data.get("budget_usd", 4))
        data["timeout_min"] = float(data.get("timeout_min", 25))
    except (TypeError, ValueError):
        problems.append("budget_usd and timeout_min must be numbers")
    graders = data.get("grader", [])
    if not isinstance(graders, list):
        problems.append("graders are [[grader]] tables")
        graders = []
    for i, g in enumerate(graders, 1):
        if g.get("type") not in GRADERS:
            problems.append(f"grader {i}: unknown type {g.get('type')!r} (one of {', '.join(GRADERS)})")
    if problems:
        raise ValueError("; ".join(problems))
    data["grader"] = graders
    data["preamble"] = bool(data.get("preamble", True))
    data["dir"] = str(path)
    return data


def load_cases(directory: pathlib.Path) -> tuple:
    """(valid cases sorted by id, ["<dir>: problem", ...])."""
    cases, problems = [], []
    if not directory.is_dir():
        return [], [f"{directory}: no cases directory"]
    for d in sorted(p for p in directory.iterdir() if (p / "case.toml").is_file()):
        try:
            cases.append(load_case(d))
        except ValueError as e:
            problems.append(f"{d.name}: {e}")
    return cases, problems


# ------------------------------------------------------------------ trace

@dataclass
class Call:
    index: int
    name: str
    input: dict
    ok: bool = True
    result: str = ""

    def blob(self) -> str:
        return json.dumps(self.input, sort_keys=True, ensure_ascii=False)


@dataclass
class Trace:
    calls: list = field(default_factory=list)
    texts: list = field(default_factory=list)      # (calls made before this text, text)
    init: dict = None
    result: dict = None
    hooks: list = field(default_factory=list)
    events: int = 0
    bad_lines: int = 0

    @classmethod
    def from_events(cls, events) -> "Trace":
        t = cls()
        by_id = {}
        for e in events:
            t.events += 1
            kind = e.get("type")
            if kind == "system" and e.get("subtype") == "init":
                t.init = e
            elif kind == "system" and e.get("subtype") == "hook_started":
                t.hooks.append(str(e.get("hook_name") or e.get("hook_event") or "?"))
            elif kind == "result":
                t.result = e
            elif kind in ("assistant", "user"):
                content = (e.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if kind == "assistant" and c.get("type") == "tool_use":
                        call = Call(len(t.calls), str(c.get("name")), dict(c.get("input") or {}))
                        t.calls.append(call)
                        by_id[c.get("id")] = call
                    elif kind == "assistant" and c.get("type") == "text":
                        t.texts.append((len(t.calls), str(c.get("text") or "")))
                    elif kind == "user" and c.get("type") == "tool_result":
                        call = by_id.get(c.get("tool_use_id"))
                        if call is not None:
                            call.ok = not c.get("is_error")
                            body = c.get("content")
                            call.result = body if isinstance(body, str) else json.dumps(body)[:2000]
        return t

    @classmethod
    def from_jsonl(cls, path: pathlib.Path) -> "Trace":
        events, bad = [], 0
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    bad += 1
        t = cls.from_events(events)
        t.bad_lines = bad
        return t

    def first_write(self):
        return next((c.index for c in self.calls if c.name in WRITES), None)

    def text_before_first_write(self) -> str:
        cut = self.first_write()
        return "\n".join(text for before, text in self.texts if cut is None or before <= cut).strip()

    def first(self, tool: str, match: str = ""):
        rx_tool, rx = re.compile(tool or ".*"), re.compile(match) if match else None
        return next((c.index for c in self.calls if rx_tool.fullmatch(c.name) and (rx is None or rx.search(c.blob()))), None)

    def count(self, tool: str, match: str = "") -> int:
        rx_tool, rx = re.compile(tool or ".*"), re.compile(match) if match else None
        return sum(1 for c in self.calls if rx_tool.fullmatch(c.name) and (rx is None or rx.search(c.blob())))


_EMPHASIS = re.compile(r"[*_`]+")


def questions_in(text: str) -> int:
    """Sentences or list lines that end with a question mark (port of the reference's count)."""
    plain = _EMPHASIS.sub("", text or "")
    return sum(1 for s in re.split(r"(?<=[.?!])\s+|\n+", plain) if s.strip().endswith("?"))


# ------------------------------------------------------------------ graders

@dataclass
class Grade:
    type: str
    name: str
    status: str           # pass | fail | error
    reason: str = ""


@dataclass
class Context:
    workdir: pathlib.Path
    fixture: pathlib.Path = None
    trace: Trace = None
    case: dict = None
    ddr_home: pathlib.Path = None     # the run's private copy of $DDR_HOME


def _base(spec: dict, ctx: Context) -> pathlib.Path:
    """Where a file grader looks: the workdir, or with root = "ddr_home" the run's copy of $DDR_HOME."""
    root = spec.get("root", "workdir")
    if root == "workdir":
        return ctx.workdir
    if root == "ddr_home":
        if ctx.ddr_home is None:
            raise _CouldNotRun("this run has no copy of DDR_HOME")
        return ctx.ddr_home
    raise _CouldNotRun(f"root must be workdir or ddr_home, not {root!r}")


def _files(base: pathlib.Path, pattern: str) -> list:
    if base is None or not base.is_dir():
        return []
    return sorted(p for p in base.glob(pattern)
                  if p.is_file() and not (set(p.relative_to(base).parts) & SKIP))


def main_html(workdir: pathlib.Path, named: str = "") -> pathlib.Path:
    if named:
        p = workdir / named
        return p if p.is_file() else None
    found = _files(workdir, "**/*.html") + _files(workdir, "**/*.htm")
    found.sort(key=lambda p: (p.relative_to(workdir).parts[0] != "out", len(p.relative_to(workdir).parts),
                              p.name != "index.html", str(p)))
    return found[0] if found else None


def _rel(p: pathlib.Path, base: pathlib.Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def _regex(spec: dict, key: str = "pattern"):
    flags = 0
    for ch in str(spec.get("flags", "")):
        flags |= {"i": re.I, "m": re.M, "s": re.S}.get(ch, 0)
    return re.compile(str(spec.get(key, "")), flags)


class _Tags(html.parser.HTMLParser):
    def __init__(self, names):
        super().__init__(convert_charrefs=True)
        self.names, self.n = names, 0

    def handle_starttag(self, tag, attrs):
        self.n += tag.lower() in self.names

    handle_startendtag = handle_starttag


SIMPLE_SELECTOR = re.compile(r"\s*[A-Za-z][A-Za-z0-9-]*(\s*,\s*[A-Za-z][A-Za-z0-9-]*)*\s*")


def _node(verb: str, *args, timeout: int = 120) -> dict:
    """Run tools/eval_render.mjs. Returns its JSON; {"ok": False, "error": ...} when it could not look."""
    node = os.environ.get("DDR_EVAL_NODE") or shutil.which("node")
    if not node or not pathlib.Path(node).exists():
        return {"ok": False, "error": "Node.js not found (needs Node 18+ and `npm install` in the design-director repo)"}
    try:
        p = subprocess.run([node, str(TOOLS / "eval_render.mjs"), verb, *args], capture_output=True,
                           text=True, timeout=timeout, cwd=str(ROOT))
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"eval_render.mjs did not finish: {e}"}
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": (p.stderr or p.stdout or "no output").strip()[:300]}


def _need_trace(ctx: Context):
    if ctx.trace is None or ctx.trace.events == 0:
        raise _CouldNotRun("no transcript to read")


class _CouldNotRun(Exception):
    pass


def g_file_exists(spec, ctx):
    base = _base(spec, ctx)
    found = _files(base, spec.get("glob", "**/*"))
    need = int(spec.get("min", 1))
    ok = len(found) >= need
    return ok, f"{len(found)} file(s) match {spec.get('glob')} (need {need})" + (
        "" if ok or not found else f": {', '.join(_rel(p, base) for p in found[:5])}")


def _text_hits(spec, ctx):
    base = _base(spec, ctx)
    files = _files(base, spec.get("glob", "**/*"))
    if not files:
        return None, files
    try:
        rx = _regex(spec)
    except re.error as e:
        raise _CouldNotRun(f"bad pattern: {e}")
    hits = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise _CouldNotRun(f"cannot read {_rel(f, base)}: {e}")
        for m in rx.finditer(text):
            hits.append(f"{_rel(f, base)}:{text.count(chr(10), 0, m.start()) + 1} {m.group(0)[:60]!r}")
    return hits, files


def g_text_present(spec, ctx):
    hits, files = _text_hits(spec, ctx)
    if hits is None:
        return False, f"no file matches {spec.get('glob')}"
    return bool(hits), (f"found at {hits[0]}" if hits else f"/{spec.get('pattern')}/ not in {len(files)} file(s)")


def g_text_absent(spec, ctx):
    hits, files = _text_hits(spec, ctx)
    if hits is None:
        return False, f"no file matches {spec.get('glob')}, so nothing was checked"
    return not hits, (f"{len(hits)} hit(s): {'; '.join(hits[:5])}" if hits else f"absent from {len(files)} file(s)")


def g_max_count(spec, ctx):
    page = main_html(ctx.workdir, spec.get("file", ""))
    if page is None:
        return False, f"no page {spec.get('file') or '*.html'} in the workdir"
    sel, limit = str(spec.get("selector", "")), int(spec.get("max", 0))
    if SIMPLE_SELECTOR.fullmatch(sel):
        parser = _Tags({s.strip().lower() for s in sel.split(",")})
        parser.feed(page.read_text(encoding="utf-8", errors="replace"))
        n, how = parser.n, "in the source"
    else:
        r = _node("count", "--file", str(page), "--selector", sel)
        if not r.get("ok"):
            raise _CouldNotRun(r.get("error", "count failed"))
        n, how = int(r["count"]), "in Chromium"
    return n <= limit, f"{n} x {sel!r} {how} in {_rel(page, ctx.workdir)} (max {limit})"


def g_lint_clean(spec, ctx):
    base = _base(spec, ctx)
    import slop_lint
    files = _files(base, spec.get("glob", "**/*"))
    files = [f for f in files if f.suffix.lower() in slop_lint.EXTS | slop_lint.MD_EXTS]
    if not files:
        return False, f"no lintable file matches {spec.get('glob', '**/*')}"
    rules = list(spec.get("rules", []))
    found = slop_lint.lint_paths([str(f) for f in files], enable=rules, md=bool(spec.get("md")))
    bad = [f for f in found if (f.rule in rules if rules else f.level == "error")]
    return not bad, ("; ".join(f"{_rel(pathlib.Path(f.file), base)}:{f.line} {f.rule}" for f in bad[:6])
                     if bad else f"{len(files)} file(s) clean of {', '.join(rules) or 'error-level rules'}")


def g_brand_lint_clean(spec, ctx):
    base = _base(spec, ctx)
    try:
        import brandpack
        lint = brandpack.lint
    except (ImportError, AttributeError) as e:
        raise _CouldNotRun(f"brandpack.lint is not available: {e}")
    files = _files(base, spec.get("glob", "**/*"))
    if not files:
        return False, f"no file matches {spec.get('glob', '**/*')}"
    try:
        r = lint([str(f) for f in files], spec.get("brand", ""))
    except KeyError as e:
        raise _CouldNotRun(f"no brand pack {e}")
    code = int(r.get("exit", 2))
    errors = [f for f in r.get("findings", []) if f.get("severity") == "error"]
    if code == 2:
        raise _CouldNotRun("; ".join(f.get("message", "") for f in errors[:3]) or "brand lint could not run")
    return code == 0, ("; ".join(f"{f.get('rule')} {f.get('file', '')}:{f.get('line', '')} {f.get('message', '')[:60]}"
                                 for f in errors[:5]) if code else r.get("summary") or "clean")


_PROP = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}]+)")


def _props(files, names):
    out = {n: set() for n in names}
    for f in files:
        for m in _PROP.finditer(f.read_text(encoding="utf-8", errors="replace")):
            if m.group(1) in out:
                out[m.group(1)].add(" ".join(m.group(2).split()).lower())
    return out


def g_unchanged(spec, ctx):
    if ctx.fixture is None or not ctx.fixture.is_dir():
        raise _CouldNotRun("the case has no fixture to compare with")
    problems, checked = [], 0
    for rel in spec.get("files", []):
        src, dst = ctx.fixture / rel, ctx.workdir / rel
        if not src.is_file():
            raise _CouldNotRun(f"{rel} is not in the fixture")
        checked += 1
        if not dst.is_file():
            problems.append(f"{rel} missing")
        elif src.read_bytes() != dst.read_bytes():
            problems.append(f"{rel} changed")
    names = list(spec.get("properties", []))
    if names:
        pattern = spec.get("glob", "**/*.css")
        before = _props(_files(ctx.fixture, pattern), names)
        after = _props(_files(ctx.workdir, pattern), names)
        for n in names:
            if not before[n]:
                raise _CouldNotRun(f"{n} is not defined in the fixture's {pattern}")
            checked += 1
            if after[n] != before[n]:
                problems.append(f"{n} was {sorted(before[n])}, now {sorted(after[n]) or 'gone'}")
    if not checked:
        raise _CouldNotRun("name files or properties to keep")
    return not problems, "; ".join(problems) if problems else f"{checked} item(s) unchanged"


def g_dom_probe(spec, ctx):
    page = main_html(ctx.workdir, spec.get("file", ""))
    if page is None:
        return False, f"no page {spec.get('file') or '*.html'} in the workdir"
    vp = str(spec.get("viewport", "1440x900"))
    r = _node("probe", "--file", str(page), "--viewport", vp, "--motion", str(spec.get("motion", "reduce")),
              "--expr", str(spec.get("expr", "")))
    if not r.get("ok"):
        raise _CouldNotRun(r.get("error", "probe failed"))
    return r.get("value") is True, f"{spec.get('expr')!r} at {vp} returned {json.dumps(r.get('value'))[:80]}"


def g_trace_order(spec, ctx):
    _need_trace(ctx)
    a = ctx.trace.first(spec.get("before_tool", ""), spec.get("before_match", ""))
    b = ctx.trace.first(spec.get("after_tool", ""), spec.get("after_match", ""))
    da = f"{spec.get('before_tool')}{' /' + spec['before_match'] + '/' if spec.get('before_match') else ''}"
    db = f"{spec.get('after_tool')}{' /' + spec['after_match'] + '/' if spec.get('after_match') else ''}"
    if a is None:
        return False, f"{da} never called"
    if b is None:
        return False, f"{db} never called, so the order could not hold"
    return a < b, f"{da} at call {a}, {db} at call {b}"


def g_trace_present(spec, ctx):
    _need_trace(ctx)
    n, need = ctx.trace.count(spec.get("tool", ""), spec.get("match", "")), int(spec.get("min", 1))
    return n >= need, f"{n} matching call(s) to {spec.get('tool')} (need {need})"


def g_trace_absent(spec, ctx):
    _need_trace(ctx)
    i = ctx.trace.first(spec.get("tool", ""), spec.get("match", ""))
    if i is None:
        return True, f"no call to {spec.get('tool')} matching /{spec.get('match', '')}/"
    return False, f"call {i}: {ctx.trace.calls[i].name} {ctx.trace.calls[i].blob()[:120]}"


def g_questions_max(spec, ctx):
    _need_trace(ctx)
    n, limit = questions_in(ctx.trace.text_before_first_write()), int(spec.get("max", 0))
    where = "before the first write" if ctx.trace.first_write() is not None else "in the whole run (it never wrote)"
    return n <= limit, f"{n} question(s) {where} (max {limit})"


def g_cost_max(spec, ctx):
    _need_trace(ctx)
    if not ctx.trace.result or ctx.trace.result.get("total_cost_usd") is None:
        raise _CouldNotRun("no result event with total_cost_usd (the run did not finish)")
    cost, limit = float(ctx.trace.result["total_cost_usd"]), float(spec.get("max_usd", 0))
    return cost <= limit, f"{_money(cost)} (max {_money(limit)})"


def g_isolation(spec, ctx):
    """The run saw exactly one design-director, the arm's, and no hook fired."""
    _need_trace(ctx)
    if not ctx.trace.init:
        raise _CouldNotRun("no init event in the transcript")
    want = f"{PLUGIN}:{SKILL}"
    seen = [s for s in ctx.trace.init.get("skills", []) if SKILL in str(s)]
    problems = []
    if seen != [want]:
        problems.append(f"design-director skills seen: {seen or 'none'} (want only {want})")
    if ctx.trace.hooks:
        problems.append(f"hooks ran: {', '.join(sorted(set(ctx.trace.hooks)))}")
    return not problems, "; ".join(problems) or f"only {want}, no hooks"


GRADE_FNS = {
    "file-exists": g_file_exists, "text-present": g_text_present, "text-absent": g_text_absent,
    "max-count": g_max_count, "lint-clean": g_lint_clean, "brand-lint-clean": g_brand_lint_clean,
    "unchanged": g_unchanged, "dom-probe": g_dom_probe, "trace-order": g_trace_order,
    "trace-present": g_trace_present, "trace-absent": g_trace_absent, "questions-max": g_questions_max,
    "cost-max": g_cost_max, "isolation": g_isolation,
}


def grade(spec: dict, ctx: Context) -> Grade:
    kind = str(spec.get("type", ""))
    name = str(spec.get("name") or kind)
    fn = GRADE_FNS.get(kind)
    if fn is None:
        return Grade(kind, name, "error", f"unknown grader {kind!r}")
    try:
        ok, reason = fn(spec, ctx)
    except _CouldNotRun as e:
        return Grade(kind, name, "error", f"could not run: {e}")
    except Exception as e:  # a grader that crashes has not looked
        return Grade(kind, name, "error", f"could not run: {type(e).__name__}: {e}")
    return Grade(kind, name, "pass" if ok else "fail", reason)


def grade_case(case: dict, ctx: Context) -> list:
    specs = list(case.get("grader", []))
    if not any(s.get("type") == "isolation" for s in specs):
        specs.insert(0, {"type": "isolation"})
    return [grade(s, ctx) for s in specs]


# ------------------------------------------------------------------ running

def _claude_bin() -> str:
    return os.environ.get("DDR_CLAUDE_BIN") or "claude"


def _resolve(binary: str):
    if os.sep in binary or (os.altsep and os.altsep in binary):
        p = pathlib.Path(binary).expanduser()
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    return shutil.which(binary)


def _tree_hash(d: pathlib.Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file() and not (set(x.relative_to(d).parts) & SKIP)):
        h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def build_plugin(arm_path: pathlib.Path, dest: pathlib.Path) -> pathlib.Path:
    """Wrap the arm in a session-only plugin, a frozen copy outside the workdir."""
    if dest.exists():
        shutil.rmtree(dest)
    (dest / ".claude-plugin").mkdir(parents=True)
    (dest / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": PLUGIN, "version": "0.0.0", "description": "design-director eval arm"}, indent=1), encoding="utf-8")
    shutil.copytree(arm_path, dest / "skills" / SKILL, ignore_dangling_symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".DS_Store"))
    return dest


def build_prompt(case: dict, preamble: bool = True) -> str:
    if preamble and case.get("preamble", True):
        return PREAMBLE + "\n\n" + case["prompt"]
    return case["prompt"]


def build_argv(binary: str, case: dict, plugin: pathlib.Path, model: str = "", preamble: bool = True) -> list:
    argv = [binary, "-p", build_prompt(case, preamble),
            "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--max-budget-usd", str(float(case["budget_usd"])),
            "--setting-sources", "local", "--plugin-dir", str(plugin),
            "--settings", json.dumps(RUN_SETTINGS), "--strict-mcp-config", "--no-session-persistence",
            "--tools", ALLOWED, "--allowedTools", ALLOWED]
    model = model or case.get("model")
    if model:
        argv += ["--model", str(model)]
    if case.get("append_system_prompt_file"):
        extra = (pathlib.Path(case["dir"]) / case["append_system_prompt_file"]).read_text(encoding="utf-8")
        argv += ["--append-system-prompt", extra]
    return argv + ["--disallowedTools", *DENIED]


def _git_baseline(workdir: pathlib.Path):
    """Make the workdir its own repository, so a stray `git commit` lands here and not in
    whatever repository holds $DDR_HOME. Best effort: no git, no baseline."""
    git = shutil.which("git")
    if not git:
        return
    quiet = dict(cwd=str(workdir), capture_output=True, timeout=60)
    ident = ["-c", "user.name=ddr eval", "-c", "user.email=eval@localhost", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=/dev/null"]
    try:
        subprocess.run([git, "init", "-q"], **quiet)
        subprocess.run([git, *ident, "add", "-A"], **quiet)
        subprocess.run([git, *ident, "commit", "-q", "--allow-empty", "-m", "fixture"], **quiet)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _kill(p: subprocess.Popen):
    try:
        if os.name == "posix":
            os.killpg(p.pid, signal.SIGTERM)
        else:
            p.terminate()
        p.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
        try:
            if os.name == "posix":
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
        except (ProcessLookupError, OSError):
            pass
        p.wait()


def copy_home(src: pathlib.Path, dest: pathlib.Path) -> pathlib.Path:
    """A private copy of $DDR_HOME for one run, so whatever the agent records (domain logs,
    notes, taste events, gate waivers) lands in the run folder and never in the real one."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in HOME_COPY:
        p = src / name
        if p.is_dir():
            shutil.copytree(p, dest / name, ignore=shutil.ignore_patterns("shots", ".git"),
                            ignore_dangling_symlinks=True)
        elif p.is_file():
            shutil.copy2(p, dest / name)
    return dest


def run_one(case: dict, arm: str, arm_path: pathlib.Path, run_root: pathlib.Path, binary: str, model: str = "",
            preamble: bool = True) -> dict:
    d = run_root / case["id"] / arm
    if d.exists():
        shutil.rmtree(d)
    workdir = d / "workdir"
    if case.get("fixture"):
        shutil.copytree(pathlib.Path(case["dir"]) / case["fixture"], workdir)
    else:
        workdir.mkdir(parents=True)
    _git_baseline(workdir)
    ddr_home = copy_home(home(), d / "ddr_home")
    env = dict(os.environ, DDR_HOME=str(ddr_home))
    plugin = build_plugin(arm_path, d / "plugin")
    argv = build_argv(binary, case, plugin, model, preamble)
    rec = {"case": case["id"], "arm": arm, "status": "launch-error", "exit_code": None, "reason": "",
           "started": _now(), "argv": argv[1:]}
    t0 = time.time()
    with open(d / "transcript.jsonl", "wb") as out, open(d / "stderr.txt", "wb") as err:
        try:
            p = subprocess.Popen(argv, cwd=str(workdir), stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env,
                                 start_new_session=(os.name == "posix"))
        except OSError as e:
            rec["reason"] = f"could not start {binary}: {e}"
            p = None
        if p is not None:
            try:
                rec["exit_code"] = p.wait(timeout=case["timeout_min"] * 60)
                rec["status"] = "finished"
            except subprocess.TimeoutExpired:
                _kill(p)
                rec["exit_code"] = p.returncode
                rec["status"] = "timeout"
                rec["reason"] = f"killed after {case['timeout_min']:g} min"
    rec["wall_s"] = round(time.time() - t0, 1)
    trace = Trace.from_jsonl(d / "transcript.jsonl")
    if rec["status"] == "finished" and trace.result is None:
        rec["status"], rec["reason"] = "no-result", f"exited {rec['exit_code']} without a result event"
    return _grade_record(rec, case, d, trace)


def _grade_record(rec: dict, case: dict, d: pathlib.Path, trace: Trace = None) -> dict:
    trace = trace or Trace.from_jsonl(d / "transcript.jsonl")
    fixture = pathlib.Path(case["dir"]) / case["fixture"] if case.get("fixture") else None
    ctx = Context(workdir=d / "workdir", fixture=fixture, trace=trace, case=case, ddr_home=d / "ddr_home")
    grades = grade_case(case, ctx)
    res = trace.result or {}
    rec.update({
        "cost_usd": res.get("total_cost_usd"), "turns": res.get("num_turns"), "duration_ms": res.get("duration_ms"),
        "result_subtype": res.get("subtype"), "permission_denials": len(res.get("permission_denials") or []),
        "calls": len(trace.calls), "failed_calls": sum(1 for c in trace.calls if not c.ok),
        "bad_lines": trace.bad_lines, "grades": [asdict(g) for g in grades],
        "passed": sum(g.status == "pass" for g in grades), "failed": sum(g.status == "fail" for g in grades),
        "errors": sum(g.status == "error" for g in grades),
    })
    (d / "grades.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


# ------------------------------------------------------------------ reporting

def _money(x) -> str:
    if x is None:
        return "?"
    return f"${float(x):.4f}" if 0 < float(x) < 0.01 else f"${float(x):.2f}"


def render_report(results: dict) -> str:
    rows = results["results"]
    arms = list(results["arms"])
    out = [f"# Eval run {results['run_id']}", "",
           f"Ran {results.get('started', '?')} to {results.get('finished', '?')} with `{results.get('claude_bin')}` "
           f"({results.get('claude_version') or 'version unknown'}). Arms: "
           + ", ".join(f"`{a}` ({results['arms'][a]['sha256'][:10]})" for a in arms) + ".", "",
           "A pass means the counted things held. It says nothing about taste: look at the sheets (`ddr eval sheet`).", ""]
    for cid in results["cases"]:
        out += [f"## {cid}", "", "| arm | status | passed | failed | errors | cost | turns | minutes |",
                "|---|---|---|---|---|---|---|---|"]
        mine = [r for r in rows if r["case"] == cid]
        for r in sorted(mine, key=lambda r: arms.index(r["arm"]) if r["arm"] in arms else 99):
            out.append(f"| {r['arm']} | {r['status']} | {r['passed']} | {r['failed']} | {r['errors']} | "
                       f"{_money(r.get('cost_usd'))} | {r.get('turns') if r.get('turns') is not None else '?'} | "
                       f"{r.get('wall_s', 0) / 60:.1f} |")
        out.append("")
        for r in mine:
            for g in r["grades"]:
                mark = {"pass": "pass", "fail": "FAIL", "error": "ERROR"}[g["status"]]
                out.append(f"- `{r['arm']}` {mark} `{g['type']}`{'' if g['name'] == g['type'] else ' (' + g['name'] + ')'}: {g['reason']}")
            if r.get("reason"):
                out.append(f"- `{r['arm']}` run: {r['reason']}")
        out.append("")
    out += ["## Totals", "", "| arm | graders passed | failed | errors | cases all green | cost | minutes |",
            "|---|---|---|---|---|---|---|"]
    for a in arms:
        mine = [r for r in rows if r["arm"] == a]
        total = sum(len(r["grades"]) for r in mine)
        green = sum(1 for r in mine if r["failed"] == 0 and r["errors"] == 0 and r["status"] == "finished")
        cost = sum(float(r["cost_usd"]) for r in mine if r.get("cost_usd") is not None)
        unknown = any(r.get("cost_usd") is None for r in mine)
        out.append(f"| {a} | {sum(r['passed'] for r in mine)}/{total} | {sum(r['failed'] for r in mine)} | "
                   f"{sum(r['errors'] for r in mine)} | {green}/{len(mine)} | {_money(cost)}{' + unknown' if unknown else ''} | "
                   f"{sum(r.get('wall_s', 0) for r in mine) / 60:.1f} |")
    return "\n".join(out) + "\n"


def _write(run_root: pathlib.Path, results: dict):
    (run_root / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    (run_root / "report.md").write_text(render_report(results), encoding="utf-8")


def _exit_for(rows) -> int:
    if any(r["failed"] or r["status"] == "timeout" for r in rows):
        return 1
    if any(r["errors"] or r["status"] in ("launch-error", "no-result") for r in rows):
        return 2
    return 0


def _find_run(ref: str):
    base = runs_dir()
    if ref == "latest":
        found = sorted(base.glob("*/results.json"), key=lambda p: p.stat().st_mtime) if base.is_dir() else []
        return found[-1].parent if found else None
    d = base / ref
    return d if (d / "results.json").is_file() else None


# ------------------------------------------------------------------ commands

def cmd_list(a) -> int:
    cases, problems = load_cases(pathlib.Path(a.cases))
    for c in cases:
        print(f"{c['id']:28} {c['title'][:44]:44} ${c['budget_usd']:.2f}  {c['timeout_min']:g} min  "
              f"{len(c['grader'])} graders")
        print(f"{'':28} origin: {c['origin'][:90]}")
    for p in problems:
        print(f"PROBLEM {p}")
    if not cases and not problems:
        print(f"no cases in {a.cases}")
    return 1 if problems else 0


def _git(repo: pathlib.Path, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=120, **kw)


def _check_git_arm(name: str, m) -> tuple:
    """Resolve git:<repo>@<ref>:<path> to a commit without writing anything. (info, problem)."""
    if not shutil.which("git"):
        return None, f"--arm {name}: git is not installed"
    repo = pathlib.Path(m.group("repo")).expanduser().resolve()
    ref, path = m.group("ref"), m.group("path").strip("/")
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", text=True)
    if r.returncode != 0:
        return None, f"--arm {name}: {ref!r} is not a commit in {repo}"
    commit = r.stdout.strip()
    if _git(repo, "cat-file", "-e", f"{commit}:{path + '/' if path else ''}SKILL.md").returncode != 0:
        return None, f"--arm {name}: {path or '.'}/SKILL.md is not in {ref} ({commit[:10]})"
    return {"repo": str(repo), "ref": ref, "commit": commit, "path": path}, None


def materialise_git_arm(info: dict, dest: pathlib.Path) -> pathlib.Path:
    """git archive the arm's path at its commit into dest: the baseline is exactly that commit."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    args = ["archive", "--format=tar", info["commit"]] + ([info["path"]] if info["path"] else [])
    r = _git(pathlib.Path(info["repo"]), *args)
    if r.returncode != 0:
        raise OSError(f"git archive failed: {r.stderr.decode(errors='replace').strip()[:200]}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        safe = [t for t in tar.getmembers()
                if not t.name.startswith("/") and ".." not in pathlib.PurePosixPath(t.name).parts]
        try:
            tar.extractall(dest, members=safe, filter="data")
        except TypeError:  # Python before the extraction filters
            tar.extractall(dest, members=safe)
    return dest / info["path"] if info["path"] else dest


def _parse_arms(specs) -> tuple:
    """{name: {"spec", "path" (a skill dir, or None until a git arm is archived), "git"}}, problems."""
    arms, problems = {}, []
    for s in specs or []:
        name, sep, path = s.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            problems.append(f"--arm {s!r}: write it as name=<skill dir> or name=git:<repo>@<ref>:<path>")
            continue
        if name in arms:
            problems.append(f"--arm {name} given twice")
            continue
        if path.startswith("git:"):
            m = GIT_ARM.fullmatch(path)
            if not m:
                problems.append(f"--arm {name}: write a git arm as git:<repo>@<ref>:<path>")
                continue
            info, problem = _check_git_arm(name, m)
            if problem:
                problems.append(problem)
            else:
                arms[name] = {"spec": path, "path": None, "git": info}
            continue
        p = pathlib.Path(path).expanduser().resolve()
        if not (p / "SKILL.md").is_file():
            problems.append(f"--arm {name}: {p} has no SKILL.md")
        else:
            arms[name] = {"spec": path, "path": p, "git": None}
    if not specs:
        problems.append("give at least one --arm name=<skill dir>")
    return arms, problems


def cmd_run(a) -> int:
    arms, problems = _parse_arms(a.arm)
    if not 1 <= a.jobs <= MAX_JOBS:
        problems.append(f"--jobs must be 1 to {MAX_JOBS}")
    cases, case_problems = load_cases(pathlib.Path(a.cases))
    if a.case:
        known = {c["id"] for c in cases}
        problems += [f"no valid case {c!r}" for c in a.case if c not in known]
        cases = [c for c in cases if c["id"] in set(a.case)]
        case_problems = [p for p in case_problems if p.split(":")[0] in set(a.case)]
    problems += case_problems
    if not cases and not problems:
        problems.append(f"no cases in {a.cases}")
    if problems:
        for p in problems:
            print(f"cannot run: {p}")
        return 2
    ceiling = sum(c["budget_usd"] for c in cases) * len(arms)
    print(f"plan: {len(cases)} case(s) x {len(arms)} arm(s) = {len(cases) * len(arms)} run(s), {a.jobs} at a time")
    for c in cases:
        print(f"  {c['id']:28} ${c['budget_usd']:.2f} each, {c['timeout_min']:g} min cap, {len(c['grader'])} graders")
    for n, arm in arms.items():
        where = f"{arm['git']['repo']} at {arm['git']['ref']} ({arm['git']['commit'][:10]}):{arm['git']['path']}" \
            if arm["git"] else arm["path"]
        print(f"  arm {n} = {where}")
    print(f"budget ceiling: ${ceiling:.2f} (limit ${a.max_total_usd:.2f}, raise with --max-total-usd)")
    if ceiling > a.max_total_usd:
        print(f"refused: the ceiling ${ceiling:.2f} is over --max-total-usd ${a.max_total_usd:.2f}")
        return 2
    if a.dry_run:
        print("dry run: nothing launched, nothing spent")
        return 0
    binary = _claude_bin()
    resolved = _resolve(binary)
    if not resolved:
        print(f"cannot run: {binary!r} not found. Set DDR_CLAUDE_BIN to the claude binary.")
        return 2
    try:
        version = subprocess.run([resolved, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        version = ""
    run_id = a.run_id or _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)
    run_root = runs_dir() / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    for n, arm in arms.items():
        if arm["git"]:
            try:
                arm["path"] = materialise_git_arm(arm["git"], run_root / "arms" / n)
            except (OSError, tarfile.TarError, subprocess.TimeoutExpired) as e:
                print(f"cannot run: --arm {n}: {e}")
                return 2
    results = {"version": 1, "run_id": run_id, "started": _now(), "finished": None, "cases_dir": str(pathlib.Path(a.cases)),
               "claude_bin": binary, "claude_resolved": resolved, "claude_version": version, "model": a.model or None,
               "arms": {n: {"path": str(arm["path"]), "spec": arm["spec"], "git": arm["git"],
                         "sha256": _tree_hash(arm["path"])} for n, arm in arms.items()},
               "preamble": PREAMBLE if a.preamble else None,
               "cases": [c["id"] for c in cases], "budget_ceiling_usd": ceiling, "results": []}
    jobs = [(c, n, arm["path"]) for c in cases for n, arm in arms.items()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = {pool.submit(_safe_run_one, (c, n, p), (run_root, resolved, a.model, a.preamble)): (c["id"], n)
                   for c, n, p in jobs}
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            results["results"].append(r)
            print(f"  {r['case']} / {r['arm']}: {r['status']}, {r['passed']} passed, {r['failed']} failed, "
                  f"{r['errors']} errors, {_money(r.get('cost_usd'))}")
            _write(run_root, results)
    order = {(c["id"], n): i for i, (c, n, _) in enumerate(jobs)}
    results["results"].sort(key=lambda r: order.get((r["case"], r["arm"]), 0))
    results["finished"] = _now()
    _write(run_root, results)
    print(f"\nreport: {run_root / 'report.md'}")
    return _exit_for(results["results"])


def _safe_run_one(job, ctx) -> dict:
    """run_one, but an exception (a fixture that will not copy, an unreadable transcript) becomes an
    error row, so one bad case cannot abort a run whose other paid runs are still going."""
    case, arm, path = job
    run_root, resolved, model, preamble = ctx
    try:
        return run_one(case, arm, path, run_root, resolved, model, preamble)
    except Exception as e:  # recorded, never swallowed: the row says what broke
        return {"case": case.get("id", "?"), "arm": arm, "status": "error", "reason": f"{type(e).__name__}: {e}",
                "passed": 0, "failed": 0, "errors": 1, "cost_usd": None, "grades": []}


def cmd_report(a) -> int:
    run_root = _find_run(a.run)
    if run_root is None:
        print(f"no run {a.run!r} in {runs_dir()}")
        return 2
    results = json.loads((run_root / "results.json").read_text(encoding="utf-8"))
    if a.regrade:
        cases, problems = load_cases(pathlib.Path(a.cases or results.get("cases_dir") or home() / "evals" / "cases"))
        by_id = {c["id"]: c for c in cases}
        for p in problems:
            print(f"PROBLEM {p}")
        for i, r in enumerate(results["results"]):
            if r["case"] in by_id:
                results["results"][i] = _grade_record(dict(r), by_id[r["case"]], run_root / r["case"] / r["arm"])
        results["regraded"] = _now()
    _write(run_root, results)
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        print((run_root / "report.md").read_text(encoding="utf-8"))
    return _exit_for(results["results"])


def cmd_sheet(a) -> int:
    run_root = _find_run(a.run)
    if run_root is None:
        print(f"no run {a.run!r} in {runs_dir()}")
        return 2
    results = json.loads((run_root / "results.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in load_cases(pathlib.Path(results.get("cases_dir") or ""))[0]}
    rc = 0
    for cid in results["cases"]:
        items = []
        for arm in results["arms"]:
            page = main_html(run_root / cid / arm / "workdir", cases.get(cid, {}).get("main_html", ""))
            items += ["--item", f"{arm}::{page or ''}"]
        out = run_root / cid / "sheet.png"
        r = _node("sheet", "--out", str(out), "--title", cid, *items, timeout=300)
        if r.get("ok"):
            print(f"sheet: {out}")
        else:
            print(f"could not draw the sheet for {cid}: {r.get('error')}")
            rc = 2
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ddr eval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    default_cases = str(home() / "evals" / "cases")
    s = sub.add_parser("list")
    s.add_argument("--cases", default=default_cases)
    s = sub.add_parser("run")
    s.add_argument("--arm", action="append", help="name=<path to a skill directory>, repeatable")
    s.add_argument("--cases", default=default_cases)
    s.add_argument("--case", action="append", help="run only this case id, repeatable")
    s.add_argument("--jobs", type=int, default=1)
    s.add_argument("--model", default="")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--max-total-usd", type=float, default=25.0)
    s.add_argument("--run-id", default="")
    s.add_argument("--no-preamble", dest="preamble", action="store_false",
                   help="do not put the isolation preamble in front of each prompt")
    s = sub.add_parser("report")
    s.add_argument("run", nargs="?", default="latest")
    s.add_argument("--regrade", action="store_true", help="grade the stored transcripts and files again, spending nothing")
    s.add_argument("--cases", default="")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("sheet")
    s.add_argument("run", nargs="?", default="latest")
    a = p.parse_args(argv)
    if a.cmd is None:
        p.print_help()
        return 2
    return {"list": cmd_list, "run": cmd_run, "report": cmd_report, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
