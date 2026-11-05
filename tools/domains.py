"""Design domains: what the agent actually knows about an area of design, and how sure it is.

An agent designs well where it has looked hard and shipped before, and badly everywhere
else. A domain makes that explicit. Each one is a folder:

    domain.toml    slug, title, kind (sector or pattern), keywords, aliases, related domains
    dossier.md     the agent's own understanding: who it is for, what the best do, the
                   conventions to keep and to break, the category's slop, its language
    refs.toml      the reference library: exemplars and counter-examples, each with how it
                   was seen, when, what to take or avoid. Retired refs stay as a graveyard
                   so a bad or dated example is never quietly re-added.
    ledger.jsonl   what shipped in this domain, what landed, what was rejected and why

A **sector** is a kind of business or audience (fintech, wellness, local services). A
**pattern** cuts across sectors (onboarding, checkout, pricing, dashboards). Most briefs
are one sector plus one or two patterns, and `match` returns both.

Confidence (0 to 100) is computed from the evidence, never typed in: how many real
references were looked at and how (a search result counts for a quarter of a visit),
whether counter-examples and the category's slop have been named, whether the research
reached outside the category, how much of the dossier is written, and what has shipped
and been judged. Everything decays with a one-year half-life, so a domain nobody has
looked at since last year is no longer an area of expertise. It measures grounding, not
talent: a high score means the agent has done the homework, never that the work is good.

Domains live in $DDR_HOME/domains (default ~/.design-director/domains). Starter domains
ship in this repo's domains/ folder; the first write to one gives you a layer over it in
your home: your references, retirements, notes and ledger, with the starter read live
underneath so later upstream research keeps arriving.

    ddr domain match "a booking site for a sauna in Galway"
    ddr domain brief wellness onboarding
    ddr domain new local-services --kind sector --title "Local services" --keywords "dentist,solicitor"
    ddr domain ref add wellness --name "..." --url ... --verdict exemplar --angle direct \\
        --evidence screenshot --take "..." --score 4
    ddr domain ref retire wellness <id> --reason "redesigned into a template"
    ddr domain ref edit wellness <id> --url https://... --take "..."   # correct in place
    ddr domain status wellness          # the score, its parts, and what would raise it
    ddr domain plan wellness --stakes high
    ddr domain log wellness shipped "Booking page v2"
    ddr domain relate fintech onboarding --how "KYC-heavy signup"
    ddr domain merge banking fintech
    ddr domain audit --online           # stale, weak, dead, contradictory, overlapping
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources  # noqa: E402  (shares the TOML reader)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEDS = ROOT / "domains"

KINDS = ("sector", "pattern")
VERDICTS = ("exemplar", "counter")
ANGLES = ("direct", "leader", "outside")
EVIDENCE = {"search": 0.25, "visited": 1.0, "screenshot": 1.25, "flow": 1.5}
LEDGER_KINDS = ("win", "miss", "shipped", "error", "note")
SECTIONS = ("Who it is for", "What the best do", "Conventions to keep", "Conventions to break",
            "Category slop", "Language", "Open questions")
SECTION_POINTS = {"Who it is for": 3, "What the best do": 5, "Conventions to keep": 3,
                  "Conventions to break": 3, "Category slop": 5, "Language": 3}
SECTION_PROMPTS = {
    "Who it is for": "Who uses this, what they are anxious about, what they are trying to get done, what they compare it with.",
    "What the best do": "The specific moves the best references share, with values where you have them. Name the references.",
    "Conventions to keep": "What users rely on in this category. Breaking these costs trust, so keep them and do them well.",
    "Conventions to break": "Habits of the category that are lazy or dated, and what replaces them.",
    "Category slop": "What generated or template work looks like in this category specifically: the stock images, the copy, the layouts.",
    "Language": "Type, colour, imagery, voice and motion that belong to this world, and why.",
    "Open questions": "What you still do not know, and what would answer it.",
}
# Sections a person or `ddr notes promote` adds; the brief prints them, confidence ignores them.
BRIEF_EXTRA = ("Lessons", "Proposed guidance")
HALF_LIFE = 365          # days, for references and ledger events
STALE_DAYS = 365
STAKES = {"low": 35, "medium": 55, "high": 70}
BANDS = ((65, "strong"), (35, "working"), (0, "thin"))
BAND_ADVICE = {
    "thin": "research before designing; anything made now is a guess",
    "working": "research the gaps below, then design",
    "strong": "design; refresh only what is stale",
}
STOP = {"and", "the", "for", "of", "a", "an", "in", "on", "to", "with", "flow", "flows", "page", "pages",
        "site", "sites", "website", "design", "app", "apps", "ui", "ux", "new"}


# ---------------------------------------------------------------- paths

def home() -> pathlib.Path:
    env = os.environ.get("DDR_HOME")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".design-director"


def home_domains() -> pathlib.Path:
    return home() / "domains"


def slugify(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").replace("ø", "o").replace("Ø", "O").replace("ß", "ss"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if not s:
        raise ValueError("a domain needs a name")
    return s


def _today(today=None) -> _dt.date:
    return today or _dt.date.today()


def _date(s) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _decay(seen, today) -> float:
    d = _date(seen)
    if d is None:
        return 0.5
    age = max(0, (today - d).days)
    return 0.5 ** (age / HALF_LIFE)


def norm_url(u: str) -> str:
    u = (u or "").strip().lower()
    u = re.sub(r"^[a-z]+://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def _host(u: str) -> str:
    return norm_url(u).split("/")[0]


# ---------------------------------------------------------------- read / write

def _q(s) -> str:
    return json.dumps(str(s), ensure_ascii=False)


def _emit_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_q(x) for x in v) + "]"
    return _q(v)


META_ORDER = ("slug", "title", "kind", "summary", "keywords", "aliases", "created", "updated",
              "forked_from", "forked_on", "merged_into", "merged_on")
REF_ORDER = ("id", "name", "url", "verdict", "angle", "evidence", "score", "seen", "take", "avoid",
             "tags", "shots", "notes", "status", "retired_on", "retired_reason", "readded_because", "added")


def _emit_table(d: dict, order) -> list[str]:
    keys = [k for k in order if k in d] + sorted(k for k in d if k not in order and not k.startswith("_"))
    return [f"{k} = {_emit_value(d[k])}" for k in keys if d[k] not in (None, "", [])]


def _write_meta(path: pathlib.Path, meta: dict, related: list[dict]):
    lines = _emit_table(meta, META_ORDER)
    for r in related:
        lines += ["", "[[related]]"] + _emit_table(r, ("slug", "how"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_refs(path: pathlib.Path, refs: list[dict]):
    chunks = ["\n".join(["[[ref]]"] + _emit_table(r, REF_ORDER)) for r in refs]
    path.write_text(("\n\n".join(chunks) + "\n") if chunks else "# references: add with `ddr domain ref add`\n",
                    encoding="utf-8")


def _read_ledger(path: pathlib.Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _folder(slug: str):
    """(path, layer) for a slug: the home copy wins over the repo's seed."""
    h = home_domains() / slug
    if (h / "domain.toml").exists():
        return h, "home"
    s = pathlib.Path(SEEDS) / slug
    if (s / "domain.toml").exists():
        return s, "seed"
    return None, None


def load(slug: str, follow: bool = True) -> dict | None:
    slug = slugify(slug)
    seen = set()
    while True:
        path, layer = _folder(slug)
        if path is None:
            return None
        data = sources.loads((path / "domain.toml").read_text(encoding="utf-8"))
        related = data.pop("related", [])
        meta = data
        if follow and meta.get("merged_into") and meta["merged_into"] not in seen:
            seen.add(slug)
            slug = meta["merged_into"]
            continue
        refs_file = path / "refs.toml"
        refs = sources.loads(refs_file.read_text(encoding="utf-8")).get("ref", []) if refs_file.exists() else []
        for r in refs:
            r.setdefault("status", "active")
        dossier = (path / "dossier.md").read_text(encoding="utf-8") if (path / "dossier.md").exists() else ""
        dom = {"slug": meta.get("slug", slug), "meta": meta, "related": related, "refs": refs,
               "ledger": _read_ledger(path / "ledger.jsonl"), "dossier": dossier, "own_dossier": dossier,
               "path": path, "layer": layer}
        if layer == "home" and meta.get("forked_from") == "seed":
            _overlay_seed(dom)
        return dom


def _seed_folder(slug: str):
    s = pathlib.Path(SEEDS) / slug
    return s if (s / "domain.toml").exists() else None


def _overlay_seed(dom: dict):
    """A fork is a layer over the repo's starter, not a frozen copy: the starter's references,
    dossier and relations are read live underneath your own, so upstream research keeps flowing
    in. Your references override the starter's by address (a retirement in your layer hides
    theirs) and your dossier notes sit under each of their sections."""
    seed = _seed_folder(dom["slug"])
    if seed is None or seed.resolve() == dom["path"].resolve():
        return
    data = sources.loads((seed / "domain.toml").read_text(encoding="utf-8"))
    for r in data.pop("related", []):
        if not any(x.get("slug") == r.get("slug") for x in dom["related"]):
            dom["related"].append(dict(r, _layer="seed"))
    for k in ("keywords", "aliases"):
        mine = dom["meta"].get(k, [])
        dropped = set(dom["meta"].get(f"dropped_{k}", []))
        dom["meta"][k] = mine + [x for x in data.get(k, []) if x not in mine and x not in dropped]
    have = {norm_url(r["url"]) for r in dom["refs"]}
    if (seed / "refs.toml").exists():
        for r in sources.loads((seed / "refs.toml").read_text(encoding="utf-8")).get("ref", []):
            if norm_url(r["url"]) not in have:
                r = dict(r, _layer="seed")
                r.setdefault("status", "active")
                dom["refs"].append(r)
    seed_text = (seed / "dossier.md").read_text(encoding="utf-8") if (seed / "dossier.md").exists() else ""
    dom["dossier"] = _combine_dossiers(seed_text, dom["own_dossier"])
    dom["seed_path"] = seed


def _combine_dossiers(seed_text: str, own_text: str) -> str:
    a, b = dossier_sections(seed_text), dossier_sections(own_text)
    title = (re.search(r"^# .+$", seed_text, re.M) or re.search(r"^# .+$", own_text, re.M))
    out = [title.group(0) if title else "# Dossier", ""]
    done = set()
    for name in list(SECTIONS) + [k for k in list(a) + list(b) if k not in SECTIONS]:
        if name in done:
            continue
        done.add(name)
        parts = [x for x in (a.get(name, ""), b.get(name, "")) if x]
        if parts:
            out += [f"## {name}", "", "\n\n".join(parts), ""]
    return "\n".join(out)


def slugs() -> list[str]:
    found = set()
    for base in (home_domains(), pathlib.Path(SEEDS)):
        if base.exists():
            found |= {p.parent.name for p in base.glob("*/domain.toml")}
    return sorted(found)


def all_domains(include_merged: bool = False) -> list[dict]:
    out = []
    for s in slugs():
        d = load(s, follow=False)
        if d and (include_merged or not d["meta"].get("merged_into")):
            out.append(d)
    return out


def dossier_template(title: str) -> str:
    body = f"# {title}\n\n"
    for s in SECTIONS:
        body += f"## {s}\n\n<!-- {SECTION_PROMPTS[s]} -->\n\n"
    return body


def create(slug, title, kind, summary="", keywords=(), aliases=(), today=None) -> dict:
    slug = slugify(slug)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}: a sector is a kind of business or audience, "
                         "a pattern cuts across sectors (onboarding, checkout, pricing)")
    if _folder(slug)[0] is not None:
        raise ValueError(f"domain {slug!r} already exists; use it, relate to it or merge into it")
    path = home_domains() / slug
    path.mkdir(parents=True, exist_ok=True)
    day = _today(today).isoformat()
    meta = {"slug": slug, "title": title or slug, "kind": kind, "summary": summary,
            "keywords": [k.strip().lower() for k in keywords if k and k.strip()],
            "aliases": [a.strip().lower() for a in aliases if a and a.strip()],
            "created": day, "updated": day}
    _write_meta(path / "domain.toml", meta, [])
    _write_refs(path / "refs.toml", [])
    (path / "dossier.md").write_text(dossier_template(meta["title"]), encoding="utf-8")
    (path / "ledger.jsonl").touch()
    return load(slug)


def path_for_write(slug: str, today=None) -> pathlib.Path:
    """The writable folder for a domain, making an empty layer over a repo starter on first write."""
    slug = slugify(slug)
    path, layer = _folder(slug)
    if path is None:
        raise ValueError(f"no domain {slug!r}; create it with `ddr domain new {slug} --kind sector|pattern`")
    if layer == "home":
        return path
    dst = home_domains() / slug
    dst.mkdir(parents=True, exist_ok=True)
    data = sources.loads((path / "domain.toml").read_text(encoding="utf-8"))
    data.pop("related", None)
    data["forked_from"] = "seed"
    data["forked_on"] = _today(today).isoformat()
    data["keywords"], data["aliases"] = [], []   # read live from the starter
    _write_meta(dst / "domain.toml", data, [])
    _write_refs(dst / "refs.toml", [])
    body = f"# {data.get('title', slug)}\n\n<!-- Your own notes. The starter's dossier is read live from the repo and sits above\n" \
           "     these under each heading, so upstream research keeps arriving with git pull. -->\n\n"
    for sec in SECTIONS:
        body += f"## {sec}\n\n"
    (dst / "dossier.md").write_text(body, encoding="utf-8")
    (dst / "ledger.jsonl").touch()
    return dst


def _save(dom: dict, today=None):
    meta = dict(dom["meta"], updated=_today(today).isoformat())
    dom["meta"]["updated"] = meta["updated"]
    if dom.get("seed_path"):   # keywords and aliases from the starter stay in the starter
        seed = sources.loads((dom["seed_path"] / "domain.toml").read_text(encoding="utf-8"))
        for k in ("keywords", "aliases"):
            meta[k] = [x for x in meta.get(k, []) if x not in seed.get(k, [])]
    _write_meta(dom["path"] / "domain.toml", meta, [r for r in dom["related"] if not r.get("_layer")])
    _write_refs(dom["path"] / "refs.toml", [r for r in dom["refs"] if not r.get("_layer")])


def _writable(slug: str, today=None) -> dict:
    target = load(slug)
    if target is None:
        raise ValueError(f"no domain {slug!r}; create it with `ddr domain new {slugify(slug)} --kind sector|pattern`")
    path_for_write(target["slug"], today)
    return load(target["slug"])


# ---------------------------------------------------------------- references

def _ref_id(name: str, existing: set) -> str:
    base = slugify(name)[:40].rstrip("-")
    rid, n = base, 2
    while rid in existing:
        rid, n = f"{base}-{n}", n + 1
    return rid


def add_ref(slug, name, url, verdict, angle, evidence, take="", avoid="", score=3, seen=None,
            tags=(), shots="", notes="", force="", today=None) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    if angle not in ANGLES:
        raise ValueError(f"angle must be one of {ANGLES}: direct (this category), leader (best in an "
                         "adjacent category), outside (another discipline entirely)")
    if evidence not in EVIDENCE:
        raise ValueError(f"evidence must be one of {tuple(EVIDENCE)}: say how you actually saw it")
    if not (name and url):
        raise ValueError("a reference needs a name and a url")
    score = int(score)
    if not 1 <= score <= 5:
        raise ValueError("score is 1 to 5")
    if verdict == "exemplar" and not (take or "").strip():
        raise ValueError("an exemplar needs --take: the specific move worth taking, with values if you have them")
    if verdict == "counter" and not (avoid or "").strip():
        raise ValueError("a counter-example needs --avoid: exactly what makes it bad")
    dom = _writable(slug, today)
    key = norm_url(url)
    for r in dom["refs"]:
        if norm_url(r["url"]) == key:
            if r.get("status") == "retired":
                if not force:
                    raise ValueError(f"{url} was retired on {r.get('retired_on')}: {r.get('retired_reason')}. "
                                     "Pass --force \"<why it deserves to come back>\" if it has changed.")
                dom["refs"].remove(r)
                break
            raise ValueError(f"{url} is already in {dom['slug']} as {r['id']}; use `ddr domain ref seen` to refresh it")
    ref = {"id": _ref_id(name, {r["id"] for r in dom["refs"]}), "name": name, "url": url, "verdict": verdict,
           "angle": angle, "evidence": evidence, "score": score, "seen": seen or _today(today).isoformat(),
           "take": take, "avoid": avoid, "tags": [t for t in tags if t], "shots": shots, "notes": notes,
           "status": "active", "readded_because": force or "", "added": _today(today).isoformat()}
    dom["refs"].append(ref)
    _save(dom, today)
    return ref


def _find_ref(dom: dict, key: str) -> dict:
    """Find a reference to change. A starter's reference is taken into your layer first."""
    for r in dom["refs"]:
        if r["id"] == key or norm_url(r["url"]) == norm_url(key):
            r.pop("_layer", None)
            return r
    raise ValueError(f"no reference {key!r} in {dom['slug']}")


def retire_ref(slug, key, reason, today=None) -> dict:
    if not (reason or "").strip():
        raise ValueError("say why it is retired (dated, redesigned, generic, dead), so it is not re-added")
    dom = _writable(slug, today)
    r = _find_ref(dom, key)
    r["status"] = "retired"
    r["retired_on"] = _today(today).isoformat()
    r["retired_reason"] = reason.strip()
    _save(dom, today)
    return r


def reverify(slug, key, evidence=None, score=None, today=None) -> dict:
    dom = _writable(slug, today)
    r = _find_ref(dom, key)
    if evidence:
        if evidence not in EVIDENCE:
            raise ValueError(f"evidence must be one of {tuple(EVIDENCE)}")
        r["evidence"] = evidence
    if score is not None:
        if not 1 <= int(score) <= 5:
            raise ValueError("score is 1 to 5")
        r["score"] = int(score)
    r["seen"] = _today(today).isoformat()
    _save(dom, today)
    return r


EDITABLE = ("name", "url", "verdict", "angle", "evidence", "score", "seen", "take", "avoid", "tags", "shots", "notes")


def edit_ref(slug, key, today=None, **changes) -> dict:
    """Correct a reference in place (a moved address, a better take) instead of retiring and re-adding it."""
    dom = _writable(slug, today)
    was_seed = any(x.get("_layer") == "seed" and (x["id"] == key or norm_url(x["url"]) == norm_url(key)) for x in dom["refs"])
    r = _find_ref(dom, key)
    old_url = r["url"]
    changes = {k: v for k, v in changes.items() if k in EDITABLE and v not in (None, "")}
    if "verdict" in changes and changes["verdict"] not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    if "angle" in changes and changes["angle"] not in ANGLES:
        raise ValueError(f"angle must be one of {ANGLES}")
    if "evidence" in changes and changes["evidence"] not in EVIDENCE:
        raise ValueError(f"evidence must be one of {tuple(EVIDENCE)}")
    if "score" in changes:
        changes["score"] = int(changes["score"])
        if not 1 <= changes["score"] <= 5:
            raise ValueError("score is 1 to 5")
    if "url" in changes:
        key2 = norm_url(changes["url"])
        clash = [x for x in dom["refs"] if x is not r and norm_url(x["url"]) == key2]
        if clash:
            raise ValueError(f"{changes['url']} is already in {dom['slug']} as {clash[0]['id']}")
    merged = dict(r, **changes)
    if merged["verdict"] == "exemplar" and not (merged.get("take") or "").strip():
        raise ValueError("an exemplar needs a take")
    if merged["verdict"] == "counter" and not (merged.get("avoid") or "").strip():
        raise ValueError("a counter-example needs an avoid")
    r.update(changes)
    if was_seed and "url" in changes and norm_url(old_url) != norm_url(changes["url"]):
        # without this the starter's copy under the old address comes back on the next load
        dom["refs"].append({"id": r["id"] + "-old", "name": r["name"], "url": old_url, "verdict": r["verdict"],
                            "angle": r.get("angle", "direct"), "evidence": r.get("evidence", "visited"),
                            "score": r.get("score", 3), "take": r.get("take", ""), "avoid": r.get("avoid", ""),
                            "status": "retired", "retired_on": _today(today).isoformat(),
                            "retired_reason": f"moved to {changes['url']}"})
    _save(dom, today)
    return r


def active(dom) -> list[dict]:
    return [r for r in dom["refs"] if r.get("status", "active") == "active"]


# ---------------------------------------------------------------- ledger, graph

def _rewrite_ledger(dom: dict):
    with (dom["path"] / "ledger.jsonl").open("w", encoding="utf-8") as f:
        for ev in dom["ledger"]:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def resolve(slug, what, rule, today=None) -> dict:
    """Close an open rejection by naming the rule it produced."""
    if not (rule or "").strip():
        raise ValueError("name the rule the rejection produced")
    dom = _writable(slug, today)
    open_ = [e for e in dom["ledger"] if e.get("kind") == "miss" and not e.get("rule")]
    exact = [e for e in open_ if e["what"].lower() == what.strip().lower()]
    hits = exact or [e for e in open_ if what.strip().lower() in e["what"].lower()]
    if not hits:
        raise ValueError(f"no open rejection matches {what!r}; `ddr domain brief {dom['slug']}` lists the ledger")
    if len(hits) > 1:
        raise ValueError("several open rejections match: " + "; ".join(e["what"] for e in hits[:5]))
    hits[0]["rule"] = rule.strip()
    hits[0]["resolved"] = _today(today).isoformat()
    _rewrite_ledger(dom)
    return hits[0]


def log(slug, kind, what, why="", rule="", prevention="", tags=(), project="", today=None, date=None) -> dict:
    if kind not in LEDGER_KINDS:
        raise ValueError(f"kind must be one of {LEDGER_KINDS}")
    if not (what or "").strip():
        raise ValueError("say what it was, specifically")
    if kind in ("miss", "error") and not (why or "").strip():
        raise ValueError(f"a {kind} needs --why, or the same mistake comes back")
    if date is not None and _date(date) is None:
        raise ValueError("date must be YYYY-MM-DD")
    dom = _writable(slug, today)
    if kind == "miss" and rule:
        same = [e for e in dom["ledger"] if e.get("kind") == "miss" and not e.get("rule")
                and e["what"].lower() == what.strip().lower()]
        if same:
            return resolve(dom["slug"], what, rule, today)
    ev = {"date": _date(date).isoformat() if date else _today(today).isoformat(), "kind": kind, "what": what.strip()}
    for k, v in (("why", why), ("rule", rule), ("prevention", prevention), ("project", project)):
        if v:
            ev[k] = v
    if tags:
        ev["tags"] = [t for t in tags if t]
    with (dom["path"] / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def relate(a, b, how="", today=None):
    da, db = _writable(a, today), _writable(b, today)
    if da["slug"] == db["slug"]:
        raise ValueError("a domain cannot relate to itself")
    for x, y in ((da, db), (db, da)):
        cur = next((r for r in x["related"] if r.get("slug") == y["slug"]), None)
        if cur is None:
            x["related"].append({"slug": y["slug"], "how": how})
        elif how and cur.get("how") != how:
            cur["how"] = how
            cur.pop("_layer", None)
        else:
            continue
        _save(x, today)


def edit_domain(slug, title=None, summary=None, keywords=None, add_keywords=(), aliases=None, add_aliases=(),
                today=None) -> dict:
    dom = _writable(slug, today)
    m = dom["meta"]
    if title:
        m["title"] = title
    if summary is not None and summary != "":
        m["summary"] = summary
    seed_meta = sources.loads((dom["seed_path"] / "domain.toml").read_text(encoding="utf-8")) if dom.get("seed_path") else {}
    for k, replace, extra in (("keywords", keywords, add_keywords), ("aliases", aliases, add_aliases)):
        cur = [x.strip().lower() for x in replace if x.strip()] if replace is not None else list(m.get(k, []))
        cur += [x.strip().lower() for x in extra if x.strip() and x.strip().lower() not in cur]
        m[k] = cur
        if replace is not None and seed_meta:   # a replace on a fork can drop the starter's words too
            m[f"dropped_{k}"] = [x for x in seed_meta.get(k, []) if x not in cur]
        elif seed_meta:
            m[f"dropped_{k}"] = [x for x in m.get(f"dropped_{k}", []) if x not in cur]
    _save(dom, today)
    return load(dom["slug"])


def merge(src, dst, today=None) -> dict:
    s, d = _writable(src, today), _writable(dst, today)
    if s["slug"] == d["slug"]:
        raise ValueError("cannot merge a domain into itself")
    if s["meta"].get("kind") != d["meta"].get("kind"):
        raise ValueError("a sector and a pattern are different axes; relate them instead of merging")
    have = {norm_url(r["url"]) for r in d["refs"]}
    ids = {r["id"] for r in d["refs"]}
    for r in s["refs"]:
        if norm_url(r["url"]) not in have:
            r = dict(r)
            r.pop("_layer", None)   # a starter's reference becomes the destination's own
            if r["id"] in ids:
                r["id"] = _ref_id(r["name"], ids)
            ids.add(r["id"])
            d["refs"].append(r)
    for k in ("keywords", "aliases"):
        d["meta"][k] = sorted(set(d["meta"].get(k, [])) | set(s["meta"].get(k, [])) | ({s["slug"]} if k == "aliases" else set()))
    for r in s["related"]:
        if r["slug"] not in (d["slug"],) and not any(x["slug"] == r["slug"] for x in d["related"]):
            d["related"].append({k: v for k, v in r.items() if k != "_layer"})
    d["related"] = [r for r in d["related"] if r["slug"] != s["slug"]]
    body = re.sub(r"^# .*\n", "", s["own_dossier"] if s.get("seed_path") else s["dossier"], count=1).strip()
    body = re.sub(r"^## ", "### ", body, flags=re.M)
    day = _today(today).isoformat()
    if body:
        (d["path"] / "dossier.md").write_text(
            d["own_dossier"].rstrip() + f"\n\n## Merged from {s['slug']} ({day})\n\n"
            "<!-- Fold these notes into the sections above, then delete this block. -->\n\n" + body + "\n",
            encoding="utf-8")
    with (d["path"] / "ledger.jsonl").open("a", encoding="utf-8") as f:
        for ev in s["ledger"]:
            f.write(json.dumps(dict(ev, merged_from=s["slug"]), ensure_ascii=False) + "\n")
    _save(d, today)
    s["meta"]["merged_into"] = d["slug"]
    s["meta"]["merged_on"] = day
    _save(s, today)
    return load(d["slug"])


def sync(slug, today=None) -> list[dict]:
    """Starters are read live under your layer, so there is nothing to copy for a layered fork.
    For a fork made by an older version (a full copy), copy across references the starter has
    gained since, except ones you retired."""
    dom0 = load(slug)
    if dom0 is not None and dom0.get("seed_path"):
        return []
    seed = pathlib.Path(SEEDS) / slugify(slug)
    if not (seed / "refs.toml").exists():
        return []
    dom = _writable(slug, today)
    have = {norm_url(r["url"]) for r in dom["refs"]}
    ids = {r["id"] for r in dom["refs"]}
    added = []
    for r in sources.loads((seed / "refs.toml").read_text(encoding="utf-8")).get("ref", []):
        if norm_url(r["url"]) in have:
            continue
        r = dict(r)
        if r["id"] in ids:
            r["id"] = _ref_id(r["name"], ids)
        ids.add(r["id"])
        dom["refs"].append(r)
        added.append(r)
    if added:
        _save(dom, today)
    return added


# ---------------------------------------------------------------- confidence

def dossier_sections(text: str) -> dict:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, current = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1)
            out.setdefault(current, "")
            continue
        if current:
            out[current] += line + "\n"
    return {k: v.strip() for k, v in out.items()}


def _words(s: str) -> int:
    return len(re.findall(r"\w+", s))


def confidence(dom: dict, today=None) -> dict:
    today = _today(today)
    refs = active(dom)
    hands_on = [r for r in refs if r.get("evidence") != "search"]
    w = lambda r: EVIDENCE.get(r.get("evidence"), 0.25) * _decay(r.get("seen"), today)  # noqa: E731
    ex = sum(w(r) for r in refs if r.get("verdict") == "exemplar")
    co = sum(w(r) for r in refs if r.get("verdict") == "counter")
    angle_w = {a: sum(w(r) for r in hands_on if r.get("angle") == a) for a in ANGLES}
    secs = dossier_sections(dom.get("dossier", ""))
    dossier_pts, empty = 0.0, []
    for s, pts in SECTION_POINTS.items():
        n = _words(secs.get(s, ""))
        dossier_pts += pts if n >= 30 else pts / 2 if n >= 10 else 0
        if n < 30:
            empty.append(s)
    led = dom.get("ledger", [])
    lw = lambda e: _decay(e.get("date"), today)  # noqa: E731
    shipped = sum(lw(e) for e in led if e.get("kind") == "shipped")
    wins = sum(lw(e) for e in led if e.get("kind") == "win")
    lessons = sum(lw(e) for e in led if (e.get("kind") == "miss" and e.get("rule")) or
                  (e.get("kind") == "error" and e.get("prevention")))
    open_misses = [e for e in led if e.get("kind") == "miss" and not e.get("rule")]
    parts = {
        "exemplars": round(28 * min(ex, 10) / 10, 1),
        "counters": round(8 * min(co, 4) / 4, 1),
        "breadth": 4 * sum(1 for a in ANGLES if angle_w[a] >= 0.5),
        "dossier": round(dossier_pts, 1),
        "depth": round(2 * min(sum(_decay(r.get("seen"), today) for r in hands_on if r.get("evidence") == "flow"), 4), 1),
        "shipped": round(6 * min(shipped, 2), 1),
        "wins": round(3 * min(wins, 3), 1),
        "lessons": round(3 * min(lessons, 3), 1),
        "unresolved": -3 * min(len(open_misses), 3),
    }
    raw = max(0.0, sum(parts.values()))
    cap, ceiling = "", 100
    judged = sum(1 for e in led if e.get("kind") in ("win", "shipped") or (e.get("kind") == "miss" and e.get("why")))
    if len(hands_on) < 3 and judged < 6:
        ceiling, cap = 25, f"capped at 25: only {len(hands_on)} references actually looked at and {judged} pieces of judged work; a search result is not a look"
    elif _words(secs.get("Category slop", "")) < 30:
        ceiling, cap = 60, "capped at 60: the category's slop is not written down, and you cannot avoid what you have not named"
    score = int(round(min(raw, ceiling)))
    band = next(name for floor, name in BANDS if score >= floor)

    gaps = []
    n_ex = sum(1 for r in refs if r.get("verdict") == "exemplar")
    if ex < 10:
        gaps.append(f"look properly at more exemplars ({n_ex} active, fresh weight {ex:.1f} of 10; a screenshot or a walked flow counts more than a visit)")
    if co < 4:
        gaps.append(f"find counter-examples: the generated, dated or weak work in this category ({sum(1 for r in refs if r.get('verdict') == 'counter')} so far, aim for 4)")
    for a in ANGLES:
        if angle_w[a] < 0.5:
            gaps.append({"direct": "study the direct competitors in this category",
                         "leader": "study the best work in an adjacent category",
                         "outside": "bring in a reference from another discipline entirely (print, architecture, film, products)"}[a])
    for s in empty:
        gaps.append(f"write the dossier's '{s}' section from what you saw")
    stale = [r for r in refs if _decay(r.get("seen"), today) < 0.5]
    if stale:
        gaps.append(f"re-verify or retire {len(stale)} references not seen in over a year")
    weak = [r for r in refs if r.get("evidence") == "search"]
    if weak:
        gaps.append(f"visit {len(weak)} references known only from search results")
    for e in open_misses[:3]:
        gaps.append(f"turn the rejection '{e['what']}' into a rule (`ddr domain log ... miss --rule`) so it cannot recur")
    flows = sum(1 for r in hands_on if r.get("evidence") == "flow")
    if flows < 4:
        gaps.append(f"walk the real journey on the best references (book, sign up, apply) as far as it goes without submitting ({flows} walked so far, `ddr teardown <url> --walk`)")
    if shipped == 0:
        gaps.append("nothing has shipped in this domain yet; experience comes from shipping and being judged")
    return {"score": score, "band": band, "parts": parts, "cap": cap, "gaps": gaps,
            "advice": BAND_ADVICE[band]}


def plan(dom: dict, stakes: str = "medium", today=None) -> dict:
    if stakes not in STAKES:
        raise ValueError(f"stakes must be one of {tuple(STAKES)}")
    c = confidence(dom, today)
    target = STAKES[stakes]
    return {"stakes": stakes, "target": target, "score": c["score"], "met": c["score"] >= target,
            "tasks": [] if c["score"] >= target else c["gaps"], "cap": c["cap"]}


# ---------------------------------------------------------------- match

_WORD = re.compile(r"[a-z0-9]+")


def _canon(w: str) -> str:
    """One form for a word and its plural on both sides of a match: cottage and cottages,
    guesthouse and guesthouses, agency and agencies, book and booking."""
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "i"
    elif w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if w.endswith("ing") and len(w) - 3 >= 3:
        w = w[:-3]
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    if w.endswith("y") and len(w) > 3:
        w = w[:-1] + "i"
    return w


def _stems(s: str) -> list[str]:
    return [_canon(w) for w in _WORD.findall((s or "").lower())]


def _phrase_in(phrase: str, brief_stems: list[str]) -> bool:
    p = [x for x in _stems(phrase) if x]
    if not p:
        return False
    n = len(p)
    return any(brief_stems[i:i + n] == p for i in range(len(brief_stems) - n + 1))


def match(brief: str, today=None) -> dict:
    b = _stems(brief)
    out = {"sectors": [], "patterns": []}
    for dom in all_domains():
        m = dom["meta"]
        score, hits = 0, []
        for a in m.get("aliases", []):
            if _phrase_in(a, b):
                score += 3
                hits.append(a)
        for k in m.get("keywords", []):
            if _phrase_in(k, b):
                score += 2
                hits.append(k)
        for t in set(_stems(m.get("title", ""))) - {_canon(x) for x in STOP}:
            if t in b and t not in {x for h in hits for x in _stems(h)}:
                score += 1
                hits.append(t)
        if score >= 2:
            c = confidence(dom, today)
            row = {"slug": dom["slug"], "title": m.get("title"), "kind": m.get("kind"), "match": score,
                   "hits": hits, "score": c["score"], "band": c["band"], "related": dom["related"]}
            out["sectors" if m.get("kind") == "sector" else "patterns"].append(row)
    for k in out:
        out[k].sort(key=lambda r: (-r["match"], -r["score"]))
        out[k] = out[k][:3]
    return out


# ---------------------------------------------------------------- audit

def _check_url(url: str, timeout: float = 8.0):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url if "://" in url else "https://" + url, method="GET",
                                 headers={"User-Agent": "design-director-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:  # DNS, TLS, timeout
        return type(e).__name__, url


def audit(dom: dict, today=None, online: bool = False) -> list[dict]:
    today = _today(today)
    found = []
    add = lambda kind, detail, fix, ref=None: found.append(  # noqa: E731
        {"domain": dom["slug"], "kind": kind, "ref": ref, "detail": detail, "fix": fix})
    refs = active(dom)
    for r in refs:
        d = _date(r.get("seen"))
        if d and (today - d).days > STALE_DAYS:
            add("stale", f"{r['name']} last seen {r['seen']}", f"look again: `ddr domain ref seen {dom['slug']} {r['id']}`, or retire it", r["id"])
        if r.get("evidence") == "search":
            add("weak", f"{r['name']} is known only from a search result", "visit it and screenshot it, or retire it", r["id"])
        if r.get("verdict") == "exemplar" and int(r.get("score", 3)) <= 2:
            add("contradiction", f"{r['name']} is an exemplar scored {r.get('score')}", "an exemplar you rate 2 is not an exemplar: re-score, make it a counter, or retire it", r["id"])
        if r.get("verdict") == "counter" and int(r.get("score", 3)) >= 4:
            add("contradiction", f"{r['name']} is a counter-example scored {r.get('score')}", "re-score or make it an exemplar", r["id"])
        if r.get("verdict") == "exemplar" and not r.get("take"):
            add("vague", f"{r['name']} has no take", "write the specific move worth taking", r["id"])
    hands_on = [r for r in refs if r.get("evidence") != "search"]
    if len(hands_on) >= 4 and len({r.get("angle") for r in hands_on}) == 1:
        add("monoculture", f"every reference is '{hands_on[0].get('angle')}'", "look outside the category before the work converges on its neighbours")
    hosts = {}
    for r in refs:
        hosts.setdefault(_host(r["url"]), []).append(r["id"])
    for h, ids in hosts.items():
        if len(ids) > 2:
            add("monoculture", f"{len(ids)} references from {h}", "one source is one opinion; keep the best and find others")
    for e in [e for e in dom["ledger"] if e.get("kind") == "miss" and not e.get("rule")]:
        add("unresolved", f"rejection '{e['what']}' has no rule", "edit the rule that allowed it and log the miss again with --rule")
    if online:
        for r in refs:
            status, final = _check_url(r["url"])
            seen_d = _date(r.get("seen"))
            fresh_look = r.get("evidence") in ("screenshot", "flow") and seen_d and (today - seen_d).days <= 30
            if (status in (401, 403, 429, 503) or status == 202) and fresh_look:
                continue   # a bot wall to plain requests, but you rendered it this month
            if status in (401, 403, 429, 503) or status == 202:
                add("blocked", f"{r['name']} answered {status} to a plain request", "a bot wall, not proof it is dead: check it in the renderer (`ddr teardown`)", r["id"])
            elif not isinstance(status, int) or status >= 400:
                add("dead", f"{r['name']} returned {status}", "retire it, or find where it moved", r["id"])
            elif norm_url(final) != norm_url(r["url"]):
                where = _host(final) if _host(final) != _host(r["url"]) else norm_url(final)
                add("moved", f"{r['name']} now redirects to {where}", "look at it again (a moved page has often been redesigned), then `ddr domain ref edit` the url", r["id"])
    return found


def audit_all(today=None, online=False) -> list[dict]:
    doms = all_domains()
    found = []
    for d in doms:
        found += audit(d, today, online)
        if len(d["meta"].get("keywords", [])) < 3:
            found.append({"domain": d["slug"], "kind": "unfindable", "ref": None,
                          "detail": "fewer than three keywords, so briefs will not match it",
                          "fix": "add the words a person would use to describe this work"})
    for i, a in enumerate(doms):
        ka = {" ".join(_stems(k)) for k in a["meta"].get("keywords", [])}
        for b in doms[i + 1:]:
            if a["meta"].get("kind") != b["meta"].get("kind"):
                continue
            kb = {" ".join(_stems(k)) for k in b["meta"].get("keywords", [])}
            if ka and kb and len(ka & kb) / len(ka | kb) >= 0.5:
                found.append({"domain": a["slug"], "kind": "overlap", "ref": None,
                              "detail": f"{a['slug']} and {b['slug']} share most of their keywords",
                              "fix": f"merge them (`ddr domain merge {b['slug']} {a['slug']}`) or sharpen what separates them"})
    return found


# ---------------------------------------------------------------- brief

def brief(dom: dict, today=None, n_refs: int = 8) -> str:
    today = _today(today)
    c = confidence(dom, today)
    m = dom["meta"]
    L = [f"# {m.get('title')} ({m.get('kind')}, {dom['slug']})",
         f"Confidence {c['score']}/100, {c['band']}: {c['advice']}." + (f" {c['cap'][0].upper() + c['cap'][1:]}." if c['cap'] else "")]
    if m.get("summary"):
        L.append(m["summary"])
    secs = dossier_sections(dom["dossier"])
    for s in ("Who it is for", "What the best do", "Conventions to keep", "Conventions to break", "Category slop", "Language"):
        if secs.get(s):
            L += ["", f"## {s}", secs[s]]
    refs = active(dom)
    ex = sorted((r for r in refs if r.get("verdict") == "exemplar"),
                key=lambda r: -(int(r.get("score", 3)) * EVIDENCE.get(r.get("evidence"), 0.25) * _decay(r.get("seen"), today)))
    if ex:
        L += ["", "## Exemplars"]
        stop = lambda t: (t or "").rstrip() + ("" if (t or "").rstrip().endswith((".", "!", "?")) else ".")  # noqa: E731
        L += [f"- {r['name']} ({r['url']}, {r.get('angle')}, {r.get('evidence')} {r.get('seen')}, {r.get('score')}/5): {stop(r.get('take'))}"
              + (f" Leave: {r['avoid']}" if r.get("avoid") else "") for r in ex[:n_refs]]
    co = [r for r in refs if r.get("verdict") == "counter"]
    if co:
        L += ["", "## Counter-examples (do not make these)"]
        L += [f"- {r['name']} ({r['url']}): {r.get('avoid')}" for r in co[:n_refs]]
    led = dom["ledger"][-10:]
    if led:
        L += ["", "## Ledger (most recent last)"]
        for e in led:
            extra = "; ".join(f"{k}: {e[k]}" for k in ("why", "rule", "prevention") if e.get(k))
            L.append(f"- {e['date']} {e['kind']}: {e['what']}" + (f" ({extra})" if extra else ""))
    retired = [r for r in dom["refs"] if r.get("status") == "retired"]
    if retired:
        L += ["", f"Retired: {len(retired)} references (dated, weak or redesigned). `ddr domain ref list {dom['slug']} --all` shows why."]
    if dom["related"]:
        L += ["", "## Related domains"]
        for r in dom["related"]:
            rd = load(r["slug"])
            rc = confidence(rd, today) if rd else None
            L.append(f"- {r['slug']}" + (f" ({rc['score']}/100)" if rc else "") + (f": {r['how']}" if r.get("how") else ""))
    if c["gaps"]:
        L += ["", "## What would raise confidence"] + [f"- {g}" for g in c["gaps"][:8]]
    for s in BRIEF_EXTRA:   # lessons relocated here and promoted notes, in full; neither scores
        if secs.get(s):
            L += ["", f"## {s}", secs[s]]
    try:
        import notes
        rendered = notes.render(dom["slug"])
    except Exception as e:  # notes must never block a brief
        rendered = f"(notes unavailable: {type(e).__name__})"
    if rendered:
        L += ["", rendered]
    return "\n".join(L)


# ---------------------------------------------------------------- CLI

def _csv(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _print_status(dom, today=None):
    c = confidence(dom, today)
    m = dom["meta"]
    print(f"{dom['slug']}  {m.get('title')}  ({m.get('kind')}, {dom['layer']})")
    print(f"confidence {c['score']}/100  {c['band']}: {c['advice']}")
    if c["cap"]:
        print(f"  {c['cap']}")
    print("  " + "  ".join(f"{k} {v:g}" for k, v in c["parts"].items()))
    refs = active(dom)
    print(f"  {sum(1 for r in refs if r['verdict'] == 'exemplar')} exemplars, "
          f"{sum(1 for r in refs if r['verdict'] == 'counter')} counter-examples, "
          f"{sum(1 for r in dom['refs'] if r.get('status') == 'retired')} retired, {len(dom['ledger'])} ledger events")
    for g in c["gaps"]:
        print(f"  - {g}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr domain", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("home")
    m = sub.add_parser("match"); m.add_argument("brief", nargs="+"); m.add_argument("--json", action="store_true")
    n = sub.add_parser("new"); n.add_argument("slug"); n.add_argument("--title", default="")
    n.add_argument("--kind", required=True, choices=KINDS); n.add_argument("--summary", default="")
    n.add_argument("--keywords", default=""); n.add_argument("--aliases", default="")
    for name in ("status", "path", "sync"):
        sub.add_parser(name).add_argument("slug")
    b = sub.add_parser("brief"); b.add_argument("slugs", nargs="+")
    pl = sub.add_parser("plan"); pl.add_argument("slug"); pl.add_argument("--stakes", default="medium", choices=tuple(STAKES))
    au = sub.add_parser("audit"); au.add_argument("slug", nargs="?"); au.add_argument("--online", action="store_true")
    rl = sub.add_parser("relate"); rl.add_argument("a"); rl.add_argument("b"); rl.add_argument("--how", default="")
    mg = sub.add_parser("merge"); mg.add_argument("src"); mg.add_argument("dst")
    lg = sub.add_parser("log"); lg.add_argument("slug"); lg.add_argument("kind", choices=LEDGER_KINDS)
    lg.add_argument("what"); lg.add_argument("--why", default=""); lg.add_argument("--rule", default="")
    lg.add_argument("--prevention", default=""); lg.add_argument("--tags", default=""); lg.add_argument("--project", default="")
    lg.add_argument("--date", help="when it happened (YYYY-MM-DD), so old events decay properly")
    rz = sub.add_parser("resolve", help="close an open rejection by naming the rule it produced")
    rz.add_argument("slug"); rz.add_argument("what"); rz.add_argument("--rule", required=True)
    ed = sub.add_parser("edit", help="change a domain's title, summary, keywords or aliases")
    ed.add_argument("slug"); ed.add_argument("--title"); ed.add_argument("--summary")
    ed.add_argument("--keywords", help="replace the keywords"); ed.add_argument("--add-keywords", default="")
    ed.add_argument("--aliases", help="replace the aliases"); ed.add_argument("--add-aliases", default="")
    r = sub.add_parser("ref"); rs = r.add_subparsers(dest="rcmd", required=True)
    ra = rs.add_parser("add"); ra.add_argument("slug")
    ra.add_argument("--name", required=True); ra.add_argument("--url", required=True)
    ra.add_argument("--verdict", required=True, choices=VERDICTS); ra.add_argument("--angle", required=True, choices=ANGLES)
    ra.add_argument("--evidence", required=True, choices=tuple(EVIDENCE)); ra.add_argument("--take", default="")
    ra.add_argument("--avoid", default=""); ra.add_argument("--score", type=int, default=3)
    ra.add_argument("--seen"); ra.add_argument("--tags", default=""); ra.add_argument("--shots", default="")
    ra.add_argument("--notes", default=""); ra.add_argument("--force", default="", metavar="REASON",
                    help="re-add a retired reference, saying why it deserves to come back")
    for act in ra._actions:
        act.help = act.help or {"--name": "what it is, as a person would name it", "--url": "the page you actually looked at",
                                "--verdict": "exemplar (take something) or counter (avoid something)",
                                "--angle": "direct (this category), leader (best in an adjacent one), outside (another discipline)",
                                "--evidence": "how you saw it: search < visited < screenshot < flow",
                                "--take": "the specific move worth taking, with values", "--avoid": "exactly what to leave behind",
                                "--score": "1 to 5; an exemplar you would score 2 is not an exemplar",
                                "--seen": "date seen, default today", "--tags": "axis:value tags, comma separated",
                                "--shots": "folder of its screenshots, relative to the domain", "--notes": "anything else worth knowing"
                                }.get(act.option_strings[0] if act.option_strings else "", None)
    re_ = rs.add_parser("edit", help="correct a reference in place"); re_.add_argument("slug"); re_.add_argument("key")
    for f in ("name", "url", "verdict", "angle", "evidence", "take", "avoid", "seen", "tags", "shots", "notes"):
        re_.add_argument(f"--{f}")
    re_.add_argument("--score", type=int)
    rr = rs.add_parser("retire"); rr.add_argument("slug"); rr.add_argument("key"); rr.add_argument("--reason", required=True)
    rv = rs.add_parser("seen"); rv.add_argument("slug"); rv.add_argument("key")
    rv.add_argument("--evidence", choices=tuple(EVIDENCE)); rv.add_argument("--score", type=int)
    rli = rs.add_parser("list"); rli.add_argument("slug"); rli.add_argument("--all", action="store_true")
    a = p.parse_args(argv)

    def need(slug):
        d = load(slug)
        if d is None:
            raise ValueError(f"no domain {slug!r}. `ddr domain list` shows what exists; "
                             f"`ddr domain new {slugify(slug)} --kind sector|pattern` makes it")
        return d

    try:
        if a.cmd == "home":
            print(home_domains()); return 0
        if a.cmd == "list":
            doms = all_domains(include_merged=True)
            if not doms:
                print(f"no domains yet (home {home_domains()}). Create one when a brief lands outside them:\n"
                      "  ddr domain new <slug> --kind sector|pattern --title ... --keywords ...")
                return 0
            for d in doms:
                if d["meta"].get("merged_into"):
                    print(f"  {d['slug']:24} merged into {d['meta']['merged_into']} on {d['meta'].get('merged_on')}")
                    continue
                c = confidence(d)
                print(f"  {d['slug']:24} {d['meta'].get('kind', ''):8} {c['score']:>3}/100 {c['band']:8} "
                      f"{len(active(d)):>3} refs  {d['layer']:5} {d['meta'].get('title', '')}")
            return 0
        if a.cmd == "match":
            text = " ".join(a.brief)
            res = match(text)
            if a.json:
                print(json.dumps(res, indent=2)); return 0
            for k, label in (("sectors", "Sector"), ("patterns", "Pattern")):
                for row in res[k]:
                    print(f"{label:8} {row['slug']:22} confidence {row['score']:>3}/100 {row['band']:8} (matched: {', '.join(row['hits'])})")
                    for rel in row["related"]:
                        print(f"           related: {rel['slug']}" + (f" ({rel['how']})" if rel.get("how") else ""))
            if not res["sectors"] and res["patterns"]:
                print("No sector matched. Fine if the job is the pattern alone; if the brief is for a particular kind of "
                      "business, create that sector too (`ddr domain new <slug> --kind sector`).")
            elif not res["sectors"]:
                print("New territory: no sector domain covers this brief. You have no grounded expertise here yet.\n"
                      "Create one, then research it before designing:\n"
                      "  ddr domain new <slug> --kind sector --title \"...\" --keywords \"words,a,client,would,use\"\n"
                      "Choose the level a reference would transfer at: 'care homes' rather than 'healthcare' if their sites differ.")
            if not res["patterns"]:
                print("No pattern domain matched. If the brief centres on a flow or a surface used across sectors "
                      "(onboarding, checkout, pricing, booking, dashboards), create or reuse a pattern domain for it.")
            return 0
        if a.cmd == "new":
            dom = create(a.slug, a.title, a.kind, a.summary, _csv(a.keywords), _csv(a.aliases))
            print(f"created {dom['slug']} at {dom['path']}")
            for f in audit_all():
                if f["kind"] == "overlap" and dom["slug"] in f["detail"]:
                    print(f"  note: {f['detail']}; {f['fix']}")
            print(f"next: research it (design-research skill), then `ddr domain status {dom['slug']}`")
            return 0
        if a.cmd == "status":
            _print_status(need(a.slug)); return 0
        if a.cmd == "path":
            print(path_for_write(need(a.slug)["slug"])); return 0
        if a.cmd == "sync":
            d0 = need(a.slug)
            if d0.get("seed_path"):
                print("nothing to sync: the starter is read live under your layer"); return 0
            added = sync(d0["slug"])
            print(f"pulled {len(added)} new references from the repo seed" + "".join(f"\n  + {x['name']} {x['url']}" for x in added))
            return 0
        if a.cmd == "brief":
            print("\n\n".join(brief(need(s)) for s in a.slugs)); return 0
        if a.cmd == "plan":
            res = plan(need(a.slug), a.stakes)
            print(f"stakes {res['stakes']}: target {res['target']}, confidence {res['score']}"
                  + ("  (met: design now)" if res["met"] else "  (not met: research first)"))
            if res["cap"]:
                print(f"  {res['cap']}")
            for t in res["tasks"]:
                print(f"  - {t}")
            return 0
        if a.cmd == "audit":
            found = audit(need(a.slug), online=a.online) if a.slug else audit_all(online=a.online)
            for f in found:
                print(f"{f['domain']:20} {f['kind']:13} {f['detail']}\n{'':34} -> {f['fix']}")
            print(f"{len(found)} findings")
            return 0
        if a.cmd == "resolve":
            ev = resolve(a.slug, a.what, a.rule); print(f"resolved '{ev['what']}' with {ev['rule']}"); return 0
        if a.cmd == "edit":
            d = edit_domain(a.slug, a.title, a.summary, _csv(a.keywords) if a.keywords is not None else None,
                            _csv(a.add_keywords), _csv(a.aliases) if a.aliases is not None else None, _csv(a.add_aliases))
            print(f"edited {d['slug']}: {', '.join(d['meta'].get('keywords', []))}"); return 0
        if a.cmd == "relate":
            relate(a.a, a.b, a.how); print(f"related {a.a} <-> {a.b}"); return 0
        if a.cmd == "merge":
            d = merge(a.src, a.dst)
            print(f"merged {a.src} into {d['slug']}; fold the merged notes in {d['path'] / 'dossier.md'} into its sections")
            return 0
        if a.cmd == "log":
            ev = log(a.slug, a.kind, a.what, a.why, a.rule, a.prevention, _csv(a.tags), a.project, date=a.date)
            print(f"logged {ev['kind']} to {a.slug}")
            if a.kind == "miss" and not a.rule:
                print("now edit the rule that allowed it, then log it again with --rule")
            return 0
        if a.cmd == "ref":
            if a.rcmd == "add":
                ref = add_ref(a.slug, a.name, a.url, a.verdict, a.angle, a.evidence, a.take, a.avoid, a.score,
                              a.seen, _csv(a.tags), a.shots, a.notes, a.force)
                print(f"added {ref['id']} to {a.slug}")
                return 0
            if a.rcmd == "retire":
                ref = retire_ref(a.slug, a.key, a.reason); print(f"retired {ref['id']}: {ref['retired_reason']}"); return 0
            if a.rcmd == "edit":
                ch = {k: getattr(a, k) for k in EDITABLE}
                if ch.get("tags"):
                    ch["tags"] = _csv(ch["tags"])
                ref = edit_ref(a.slug, a.key, **ch); print(f"edited {ref['id']}"); return 0
            if a.rcmd == "seen":
                ref = reverify(a.slug, a.key, a.evidence, a.score); print(f"{ref['id']} seen {ref['seen']} ({ref['evidence']})"); return 0
            if a.rcmd == "list":
                dom = need(a.slug)
                for x in dom["refs"]:
                    if x.get("status") == "retired" and not a.all:
                        continue
                    tail = f"  RETIRED {x.get('retired_on')}: {x.get('retired_reason')}" if x.get("status") == "retired" else ""
                    print(f"  {x['id']:28} {x['verdict']:8} {x.get('angle', ''):8} {x.get('score')}/5 "
                          f"{x.get('evidence', ''):10} {x.get('seen', '')}  {x['url']}{tail}")
                return 0
    except ValueError as e:
        print(f"not done: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
