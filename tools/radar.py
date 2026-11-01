"""The radar: keep the library current without anyone remembering to.

    ddr radar               # everything below, as one Markdown report
    ddr radar --feeds       # which watched sources changed since last run (releases, RSS)
    ddr radar --links       # which catalogue URLs are dead
    ddr radar --discover    # new design MCPs, skills and libraries not yet in the catalogue
    ddr radar --stale 180   # entries not re-verified in N days
    ddr radar --write       # save feed state to library/radar-state.json (CI does this weekly)

A GitHub Action runs this every Monday and opens an issue with the report. A human (or
an agent) then verifies each lead and adds it with `ddr sources add`. Nothing is added
to the catalogue automatically: a lead is not a verified source.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources  # noqa: E402

STATE = sources.LIBRARY / "radar-state.json"
UA = "design-director-radar/1.0 (+https://github.com/fergo5002/design-director)"
DESIGN_WORDS = re.compile(
    r"\b(figma|penpot|sketch app|framer|webflow|ui|ux|ui/ux|tailwind|shadcn|icons?|fonts?|typefaces?|typography|"
    r"colou?rs?|palettes?|svg|lottie|rive|spline|screenshots?|visual regression|branding|brand identity|mockups?|"
    r"storybook|a11y|accessibility|css|design systems?|design tokens?|web design|ui design|ux design|landing pages?|"
    r"frontend design|front-end design|design agent|design tool|design-to-code|ui components?)\b",
    re.I,
)


def latest(content_type: str, body: str) -> str:
    """Reduce a feed or API response to the one value whose change is news."""
    ct = (content_type or "").lower()
    text = body.strip()
    if "json" in ct or text[:1] in "[{":
        try:
            data = json.loads(text)
            if isinstance(data, list) and data:
                first = data[0]
                return str(first.get("tag_name") or first.get("name") or first.get("sha") or first)[:200]
            if isinstance(data, dict):
                if "dist-tags" in data:
                    return str(data["dist-tags"].get("latest"))
                for k in ("tag_name", "version", "name"):
                    if k in data:
                        return str(data[k])
        except json.JSONDecodeError:
            pass
    if "xml" in ct or text.startswith("<?xml") or "<rss" in text[:400] or "<feed" in text[:400]:
        try:
            root = ET.fromstring(text)
            for tag in ("channel/item/title", "{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title",
                        "item/title", "entry/title"):
                el = root.find(tag)
                if el is not None and (el.text or "").strip():
                    return el.text.strip()[:200]
        except ET.ParseError:
            pass
    return "sha:" + hashlib.sha256(re.sub(r"\s+", " ", text).encode()).hexdigest()[:16]


def diff(old: dict, new: dict) -> list[tuple]:
    out = []
    for k in sorted(new):
        if new[k].get("latest") != old.get(k, {}).get("latest"):
            out.append((k, old.get(k, {}).get("latest"), new[k]["latest"]))
    return out


def _norm(url: str) -> str:
    return url.lower().rstrip("/").replace("http://", "https://").replace("://www.", "://")


def candidates(items, known_urls) -> list[dict]:
    known = {_norm(u) for u in known_urls}
    out = []
    for it in items:
        if _norm(it.get("url", "")) in known:
            continue
        if DESIGN_WORDS.search(f"{it.get('name', '')} {it.get('description', '')}"):
            out.append(it)
    return out


def _is_github_api(url: str) -> bool:
    from urllib.parse import urlparse
    u = urlparse(url)
    return u.scheme == "https" and u.hostname == "api.github.com"


def _safe(text: str) -> str:
    """Third-party text going into a GitHub issue: defuse @mentions and #refs."""
    return re.sub(r"([@#])(?=\w)", lambda m: m.group(1) + "\u200b", str(text or ""))


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _is_github_api(newurl):
            new.remove_header("Authorization")
        return new


_OPENER = urllib.request.build_opener(_NoAuthRedirect)


def _get(url: str, timeout=20, method="GET"):
    headers = {"User-Agent": UA, "Accept": "application/json, application/xml, text/html;q=0.8, */*;q=0.5"}
    if _is_github_api(url) and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers, method=method)
    with _OPENER.open(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(2_000_000).decode("utf-8", "replace")


def check_feeds(entries) -> dict:
    watched = [e for e in entries if e.get("freshness")]

    def one(e):
        try:
            _, ct, body = _get(e["freshness"])
            return e["id"], {"latest": latest(ct, body), "url": e["freshness"], "checked": _dt.date.today().isoformat()}
        except Exception as ex:  # a dead feed is a finding, not a crash
            return e["id"], {"latest": None, "error": str(ex)[:120], "url": e["freshness"]}

    with cf.ThreadPoolExecutor(8) as pool:
        return dict(pool.map(one, watched))


def check_links(entries) -> list[tuple]:
    def one(e):
        for method in ("HEAD", "GET"):
            try:
                status, _, _ = _get(e["url"], timeout=15, method=method)
                return None if status < 400 else (e["id"], e["url"], status)
            except urllib.error.HTTPError as ex:
                if method == "GET":
                    # 401/403/429 are usually bot walls, not dead sites
                    return None if ex.code in (401, 403, 429) else (e["id"], e["url"], ex.code)
            except Exception as ex:
                if method == "GET":
                    return (e["id"], e["url"], str(ex)[:80])
        return None

    with cf.ThreadPoolExecutor(12) as pool:
        return [r for r in pool.map(one, entries) if r]


def discover(entries, days=21) -> list[dict]:
    known = [e["url"] for e in entries] + [e.get("install", "") for e in entries]
    since = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
    items = []
    queries = [
        f"https://api.github.com/search/repositories?q=mcp+design+in:name,description,topics+pushed:>{since}&sort=stars&per_page=30",
        f"https://api.github.com/search/repositories?q=topic:mcp-server+figma+OR+ui+OR+design+created:>{since}&sort=stars&per_page=30",
        f"https://api.github.com/search/repositories?q=claude+skill+design+in:name,description+pushed:>{since}&sort=stars&per_page=20",
        f"https://api.github.com/search/repositories?q=shadcn+registry+in:name,description+created:>{since}&sort=stars&per_page=20",
    ]
    for q in queries:
        try:
            _, _, body = _get(q)
            for r in json.loads(body).get("items", []):
                if r.get("stargazers_count", 0) >= 25 and not r.get("archived"):
                    items.append({"name": r["full_name"], "url": r["html_url"], "description": r.get("description") or "",
                                  "stars": r["stargazers_count"], "source": "github"})
        except Exception as ex:
            items.append({"name": "github search failed", "url": q, "description": str(ex)[:100], "source": "error"})
    try:
        _, _, body = _get("https://registry.modelcontextprotocol.io/v0/servers?limit=100&search=design")
        for s in json.loads(body).get("servers", []):
            srv = s.get("server", s)
            url = (srv.get("repository") or {}).get("url") or srv.get("websiteUrl") or ""
            items.append({"name": srv.get("name", "?"), "url": url, "description": srv.get("description", ""),
                          "source": "mcp-registry"})
    except Exception as ex:
        items.append({"name": "mcp registry failed", "url": "", "description": str(ex)[:100], "source": "error"})
    seen, uniq = set(), []
    for it in candidates(items, known) + [i for i in items if i["source"] == "error"]:
        if it["url"] not in seen:
            seen.add(it["url"]); uniq.append(it)
    return uniq


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr radar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--feeds", action="store_true"); p.add_argument("--links", action="store_true")
    p.add_argument("--discover", action="store_true"); p.add_argument("--stale", type=int)
    p.add_argument("--write", action="store_true"); p.add_argument("--out")
    a = p.parse_args(argv)
    every = not (a.feeds or a.links or a.discover or a.stale)
    entries = sources.load()
    L = [f"# Design radar, {_dt.date.today().isoformat()}", "",
         f"{len(entries)} sources in the catalogue. Every lead below needs a human or agent to verify it before it goes in.", ""]
    if every or a.feeds:
        old = json.loads(STATE.read_text()) if STATE.exists() else {}
        new = check_feeds(entries)
        merged = {**old, **{k: v for k, v in new.items() if v.get("latest")}}
        changes = diff(old, {k: v for k, v in new.items() if v.get("latest")})
        L += ["## Changed since last run", ""]
        moved = [(k, o, n) for k, o, n in changes if o]
        first = [k for k, o, n in changes if not o]
        L += [f"- **{k}**: {o} -> {n}" for k, o, n in moved] or ["- Nothing moved."]
        if first:
            L.append(f"- Baseline recorded for {len(first)} newly watched feeds; changes show from the next run.")
        broken = [(k, v["error"]) for k, v in new.items() if v.get("error")]
        if broken:
            L += ["", "Feeds that failed to load:", ""] + [f"- {k}: {err}" for k, err in broken]
        L.append("")
        if a.write:
            STATE.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n")
    if every or a.links:
        dead = check_links(entries)
        L += ["## Dead or failing links", ""] + ([f"- {i}: {u} ({s})" for i, u, s in dead] or ["- None."]) + [""]
    if every or a.discover:
        found = discover(entries)
        L += ["## New leads to verify", ""]
        L += [f"- [{_safe(c['name'])}]({c['url']}) ({c['source']}{', ' + str(c['stars']) + ' stars' if c.get('stars') else ''}): {_safe(c['description'][:160])}"
              for c in found[:40]] or ["- None this week."]
        L.append("")
    days = a.stale or (180 if every else None)
    if days:
        old_entries = sources.stale(entries, days=days)
        L += [f"## Not re-verified in {days} days", ""]
        L += [f"- {e['id']} (last {e.get('verified')})" for e in old_entries[:60]] or ["- None."]
        L.append("")
    text = "\n".join(L)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
