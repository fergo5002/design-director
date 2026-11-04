"""The source catalogue: every site, library, MCP, skill and tool worth reaching for.

The catalogue lives in library/*.toml as [[source]] tables. Standard library only;
Python 3.11+ uses tomllib, older Pythons use the small parser below, which reads
exactly the subset `emit` writes (CI checks the two agree).

    python tools/ddr.py sources search "product onboarding flows" -n 8
    python tools/ddr.py sources search "" --kind mcp --min-signal 4
    python tools/ddr.py sources shuffle -n 4            # cross-discipline draw for divergence
    python tools/ddr.py sources validate
    python tools/ddr.py sources stale --days 180
    python tools/ddr.py sources render                  # rewrites library/SOURCES.md
    python tools/ddr.py sources add --id x --name X --url https://... --kind site --category web-gallery ...
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library"

KINDS = {"site", "mcp", "skill", "library", "tool", "ai-tool", "feed", "font-source", "aggregator"}
COSTS = {"free", "freemium", "paid"}
ACCESS = {"none", "rss", "api", "mcp", "cli", "npm", "git", "scrape-ok", "scrape-no"}
EVIDENCE = {"visited", "docs", "search"}
REQUIRED = ("id", "name", "url", "kind", "category", "best_for", "cost", "signal", "verified", "evidence")
FIELD_ORDER = ("id", "name", "url", "kind", "category", "best_for", "cost", "price", "agent_access",
               "agent_notes", "signal", "take", "avoid", "licence", "install", "freshness", "tags",
               "verified", "evidence")
EVIDENCE_WEIGHT = {"visited": 1.0, "docs": 0.9, "search": 0.6}


# ---------------------------------------------------------------- TOML subset

_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'|[^,\s]+')


def _unescape(s: str) -> str:
    return json.loads('"' + s + '"')


def _strip_comment(s: str) -> str:
    """Drop a trailing # comment that sits outside any string."""
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            return s[:i].rstrip()
        i += 1
    return s.rstrip()


def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        m = _STR.fullmatch(raw)
        if not m:
            raise ValueError(f"bad string: {raw[:60]}")
        return _unescape(m.group(1))
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise ValueError(f"bad string: {raw[:60]}")
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"[-+]?\d+", raw):
        return int(raw)
    if re.fullmatch(r"[-+]?\d+\.\d+", raw):
        return float(raw)
    raise ValueError(f"unsupported value: {raw[:60]}")


def _value(raw: str):
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise ValueError(f"unterminated array: {raw[:60]}")
        inner = raw[1:-1].strip()
        return [_scalar(m.group(0)) for m in _TOKEN.finditer(inner)]
    return _scalar(raw)


def _balance(s: str) -> int:
    depth, quote, i = 0, None, 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        i += 1
    return depth


def parse_toml_subset(text: str) -> dict:
    """Parse [[table]] arrays of flat key = value pairs: strings (both quote styles),
    numbers, booleans and arrays (single or multi-line), with # comments. Enough for
    the catalogue and for hand-edited .design/lint.toml; anything else raises ValueError."""
    out: dict = {}
    current = None
    lines = text.splitlines()
    n = 0
    while n < len(lines):
        s = _strip_comment(lines[n].strip())
        n += 1
        if not s:
            continue
        m = re.fullmatch(r"\[\[([A-Za-z0-9_-]+)\]\]", s)
        if m:
            current = {}
            out.setdefault(m.group(1), []).append(current)
            continue
        m = re.fullmatch(r"([A-Za-z0-9_-]+)\s*=\s*(.+)", s)
        if not m:
            raise ValueError(f"line {n}: cannot parse {s[:60]!r}")
        key, raw = m.group(1), m.group(2)
        while _balance(raw) > 0 and n < len(lines):
            raw += " " + _strip_comment(lines[n].strip())
            n += 1
        target = current if current is not None else out
        if key in target:
            raise ValueError(f"line {n}: duplicate key {key!r}")
        try:
            target[key] = _value(raw)
        except ValueError as e:
            raise ValueError(f"line {n}: {e}") from None
    return out


def loads(text: str) -> dict:
    try:
        import tomllib  # type: ignore
        return tomllib.loads(text)
    except ImportError:
        return parse_toml_subset(text)


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def emit(entries: list[dict], table: str = "source") -> str:
    chunks = []
    for e in entries:
        lines = [f"[[{table}]]"]
        keys = [k for k in FIELD_ORDER if k in e] + sorted(k for k in e if k not in FIELD_ORDER)
        for k in keys:
            v = e[k]
            if v is None or v == "" or v == []:
                continue
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif isinstance(v, list):
                lines.append(f"{k} = [{', '.join(_q(str(x)) for x in v)}]")
            else:
                lines.append(f"{k} = {_q(str(v))}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + "\n"


# ---------------------------------------------------------------- load / check

def load(directory=LIBRARY) -> list[dict]:
    entries = []
    for p in sorted(pathlib.Path(directory).glob("*.toml")):
        for e in loads(p.read_text(encoding="utf-8")).get("source", []):
            e["_file"] = p.name
            entries.append(e)
    return entries


def categories(directory=LIBRARY) -> dict:
    p = pathlib.Path(directory) / "categories.toml"
    if not p.exists():
        return {}
    return {c["slug"]: c for c in loads(p.read_text(encoding="utf-8")).get("category", [])}


def validate(entries: list[dict], known_categories: dict | None = None) -> list[str]:
    errs, seen = [], set()
    for e in entries:
        where = f"{e.get('_file', '?')}:{e.get('id', '?')}"
        for f in REQUIRED:
            if f not in e or e[f] in ("", None):
                errs.append(f"{where}: missing {f}")
        if e.get("id") in seen:
            errs.append(f"{where}: duplicate id")
        seen.add(e.get("id"))
        if "id" in e and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(e["id"])):
            errs.append(f"{where}: id must be kebab-case")
        if e.get("kind") and e["kind"] not in KINDS:
            errs.append(f"{where}: kind {e['kind']!r} not in {sorted(KINDS)}")
        if e.get("cost") and e["cost"] not in COSTS:
            errs.append(f"{where}: cost {e['cost']!r} not in {sorted(COSTS)}")
        if e.get("agent_access") and e["agent_access"] not in ACCESS:
            errs.append(f"{where}: agent_access {e['agent_access']!r} not in {sorted(ACCESS)}")
        if e.get("evidence") and e["evidence"] not in EVIDENCE:
            errs.append(f"{where}: evidence {e['evidence']!r} not in {sorted(EVIDENCE)}")
        sig = e.get("signal")
        if sig is not None and (not isinstance(sig, int) or not 1 <= sig <= 5):
            errs.append(f"{where}: signal must be an integer 1-5")
        if e.get("url") and not str(e["url"]).startswith(("https://", "http://")):
            errs.append(f"{where}: url must be absolute")
        if e.get("verified"):
            try:
                _dt.date.fromisoformat(str(e["verified"]))
            except ValueError:
                errs.append(f"{where}: verified must be YYYY-MM-DD")
        if known_categories and e.get("category") and e["category"] not in known_categories:
            errs.append(f"{where}: unknown category {e['category']!r} (add it to categories.toml)")
        if e.get("kind") in {"mcp", "library", "tool", "skill"} and not e.get("install"):
            errs.append(f"{where}: {e['kind']} entries need an install line")
    return errs


# ---------------------------------------------------------------- query

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return [w for w in _WORD.findall(s.lower()) if len(w) > 1]


def _stem(w: str) -> str:
    for suf in ("ings", "ing", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def search(entries, query="", kind=None, category=None, cost=None, min_signal=1, access=None, n=None):
    q = {_stem(w) for w in _tokens(query)}
    scored = []
    for e in entries:
        if kind and e.get("kind") != kind:
            continue
        if category and e.get("category") != category:
            continue
        if cost and e.get("cost") != cost:
            continue
        if access and e.get("agent_access") != access:
            continue
        if int(e.get("signal", 0)) < min_signal:
            continue
        weight = EVIDENCE_WEIGHT.get(e.get("evidence"), 0.5) * int(e.get("signal", 1))
        if q:
            fields = {
                "name": 4, "category": 3, "tags": 3, "best_for": 2, "take": 1, "agent_notes": 0.5, "id": 3,
            }
            score = 0.0
            for f, w in fields.items():
                v = e.get(f, "")
                v = " ".join(v) if isinstance(v, list) else str(v)
                toks = {_stem(t) for t in _tokens(v)}
                score += w * len(q & toks)
            if score == 0:
                continue
            scored.append((score * (1 + weight / 5), e))
        else:
            scored.append((weight, e))
    scored.sort(key=lambda t: (-t[0], t[1].get("name", "")))
    out = [e for _, e in scored]
    return out[:n] if n else out


def shuffle(entries, n=4, seed=None, kind="site", min_signal=3):
    """Draw n high-signal references from n different categories. Divergence on demand."""
    rng = random.Random(seed)
    pool = [e for e in entries if (not kind or e.get("kind") == kind) and int(e.get("signal", 0)) >= min_signal]
    by_cat: dict = {}
    for e in pool:
        by_cat.setdefault(e.get("category"), []).append(e)
    cats = sorted(by_cat)
    rng.shuffle(cats)
    return [rng.choice(sorted(by_cat[c], key=lambda x: x["id"])) for c in cats[:n]]


def stale(entries, today=None, days=180):
    today = _dt.date.fromisoformat(today) if today else _dt.date.today()
    out = []
    for e in entries:
        try:
            if (today - _dt.date.fromisoformat(str(e.get("verified")))).days > days:
                out.append(e)
        except ValueError:
            out.append(e)
    return out


# ---------------------------------------------------------------- render

KIND_TITLES = [
    ("site", "Reference and inspiration sites"),
    ("font-source", "Type sources"),
    ("feed", "Feeds and newsletters"),
    ("mcp", "MCP servers"),
    ("skill", "Agent skills and rule packs"),
    ("ai-tool", "AI design tools"),
    ("library", "Code libraries"),
    ("tool", "Tools"),
    ("aggregator", "Directories that list new tools"),
]


def _cell(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def render(entries, cats: dict | None = None) -> str:
    cats = cats or {}
    out = [
        "# Source catalogue",
        "",
        "Generated by `python tools/ddr.py sources render` from `library/*.toml`. Do not edit by hand.",
        f"{len(entries)} sources. Signal is 1 to 5: how much the source actually changes design decisions.",
        "Evidence says how it was checked: visited, docs or search (weakest).",
        "",
    ]
    for kind, title in KIND_TITLES:
        group = [e for e in entries if e.get("kind") == kind]
        if not group:
            continue
        out += [f"## {title}", ""]
        by_cat: dict = {}
        for e in group:
            by_cat.setdefault(e.get("category", "other"), []).append(e)
        for cat in sorted(by_cat, key=lambda c: (cats.get(c, {}).get("order", 999), c)):
            label = cats.get(cat, {}).get("title", cat)
            out += [f"### {label}", "", "| Signal | Source | Best for | Cost | Agent access |", "|---|---|---|---|---|"]
            for e in sorted(by_cat[cat], key=lambda x: (-int(x.get("signal", 0)), x["name"].lower())):
                cost = e.get("cost", "") + (f" ({e['price']})" if e.get("price") else "")
                out.append(
                    f"| {'●' * int(e.get('signal', 0))} | [{_cell(e['name'])}]({e['url']}) | {_cell(e.get('best_for'))} "
                    f"| {_cell(cost)} | {_cell(e.get('agent_access', ''))} |"
                )
            out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- CLI

def _print(entries, verbose=False):
    for e in entries:
        print(f"[{e.get('signal')}] {e['name']}  ({e.get('kind')}/{e.get('category')}, {e.get('cost')})  {e['url']}")
        print(f"     {e.get('best_for', '')}")
        if verbose:
            for f in ("take", "avoid", "agent_notes", "install", "price", "licence"):
                if e.get(f):
                    print(f"     {f}: {e[f]}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr sources", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--kind"); s.add_argument("--category"); s.add_argument("--cost"); s.add_argument("--access")
    s.add_argument("--min-signal", type=int, default=1)
    s.add_argument("-n", type=int, default=10)
    s.add_argument("-v", "--verbose", action="store_true")
    s.add_argument("--json", action="store_true")
    sh = sub.add_parser("shuffle"); sh.add_argument("-n", type=int, default=4); sh.add_argument("--seed", type=int)
    sh.add_argument("--kind", default="site")
    sub.add_parser("validate")
    st = sub.add_parser("stale"); st.add_argument("--days", type=int, default=180)
    sub.add_parser("render")
    sub.add_parser("stats")
    sub.add_parser("categories")
    a = sub.add_parser("add")
    for f in FIELD_ORDER:
        a.add_argument(f"--{f.replace('_', '-')}", dest=f)
    a.add_argument("--file", default="community.toml", help="which library/*.toml to append to")
    args = p.parse_args(argv)

    entries = load()
    cats = categories()
    if args.cmd == "search":
        hits = search(entries, args.query, args.kind, args.category, args.cost, args.min_signal, args.access, args.n)
        if args.json:
            print(json.dumps([{k: v for k, v in e.items() if not k.startswith("_")} for e in hits], indent=1))
        else:
            _print(hits, args.verbose)
            if not hits:
                print(f"No catalogue entry matches {args.query!r}. The catalogue holds tools, galleries and libraries, "
                      "not sector examples: search for the kind of source you need (\"product ui\", \"booking\", "
                      "\"editorial type\"), and find category references with web search or a research MCP (`ddr mcp --research`).",
                      file=sys.stderr)
        return 0 if hits else 1
    if args.cmd == "shuffle":
        _print(shuffle(entries, args.n, args.seed, args.kind or None), True)
        return 0
    if args.cmd == "validate":
        errs = validate(entries, cats)
        for m in errs:
            print(m)
        print(f"{len(entries)} sources, {len(errs)} problems")
        return 1 if errs else 0
    if args.cmd == "stale":
        old = stale(entries, days=args.days)
        _print(old)
        print(f"{len(old)} sources not re-verified in {args.days} days")
        return 0
    if args.cmd == "render":
        (LIBRARY / "SOURCES.md").write_text(render(entries, cats), encoding="utf-8")
        print(f"wrote library/SOURCES.md ({len(entries)} sources)")
        return 0
    if args.cmd == "stats":
        from collections import Counter
        for label, key in (("kind", "kind"), ("category", "category"), ("cost", "cost"), ("evidence", "evidence")):
            print(label + ":", dict(Counter(e.get(key) for e in entries).most_common()))
        return 0
    if args.cmd == "categories":
        for slug, c in sorted(cats.items(), key=lambda kv: kv[1].get("order", 999)):
            print(f"{slug:28} {c.get('title', '')}")
        return 0
    if args.cmd == "add":
        e = {f: getattr(args, f) for f in FIELD_ORDER if getattr(args, f)}
        if "signal" in e:
            e["signal"] = int(e["signal"])
        if "tags" in e:
            e["tags"] = [t.strip() for t in e["tags"].split(",") if t.strip()]
        e.setdefault("verified", _dt.date.today().isoformat())
        errs = validate(entries + [e], cats)
        errs = [m for m in errs if f":{e.get('id')}:" in m + ":" or e.get("id", "?") in m]
        if errs:
            print("\n".join(errs))
            return 1
        path = LIBRARY / args.file
        prev = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(prev + ("\n" if prev else "") + emit([e]), encoding="utf-8")
        print(f"added {e['id']} to library/{args.file}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
