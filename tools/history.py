"""How old a design is, from the Wayback Machine.

A reference that looked fresh when you saw it may be a five-year-old template, and a site
you admired may have been redesigned since. This reads the Internet Archive's free CDX API
and prints the first capture of each year, how many distinct versions were archived, and
the archive links to tear down (`ddr teardown <archive link>`) to see how it changed.

    ddr history https://example.com
    ddr history example.com --json

Standard library only; it makes one request to web.archive.org.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

CDX = "https://web.archive.org/cdx/search/cdx"


def fetch(url: str, timeout: float = 25.0) -> list[list[str]]:
    # one capture per month: bounded (at most 12 a year), never truncated at a row limit, and recent
    # years always included
    q = urllib.parse.urlencode({"url": url, "output": "json", "fl": "timestamp,digest,statuscode",
                                "collapse": "timestamp:6", "filter": "statuscode:200"})
    req = urllib.request.Request(f"{CDX}?{q}", headers={"User-Agent": "design-director-history/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace").strip()
    rows = json.loads(body) if body else []
    return rows[1:] if rows and rows[0][:1] == ["timestamp"] else rows


def summarise(url: str, rows: list[list[str]]) -> dict:
    years: dict[str, dict] = {}
    for ts, digest, *_ in rows:
        y = ts[:4]
        if y not in years:
            years[y] = {"first": ts, "months": 0, "digests": set()}
        years[y]["months"] += 1
        years[y]["digests"].add(digest)
    target = url if "://" in url else "https://" + url
    return {
        "url": url,
        "months": len(rows),
        "first": rows[0][0] if rows else None,
        "last": rows[-1][0] if rows else None,
        "years": [{"year": y, "months": v["months"], "changed_months": len(v["digests"]),
                   "archive": f"https://web.archive.org/web/{v['first']}/{target}"} for y, v in sorted(years.items())],
    }


def render(s: dict) -> str:
    if not s["months"]:
        return f"{s['url']}: no archived captures. Either new, blocked from archiving, or the URL is wrong."
    L = [f"{s['url']}: archived in {s['months']} months, {s['first'][:4]} to {s['last'][:4]} (one capture a month)"]
    for y in s["years"]:
        L.append(f"  {y['year']}  {y['months']:>2} months, {y['changed_months']:>2} with different content   {y['archive']}")
    L.append("Tear down two or three of these beside today's site (`ddr teardown <link>`) to see whether its\n"
             "signature move is new or worn. Archived pages often lose fonts and scripts: judge layout and copy.")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr history", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        s = summarise(a.url, fetch(a.url))
    except Exception as e:  # network, archive down, rate limit
        print(f"could not read the archive ({type(e).__name__}: {e}). The instrument failed, not the site.", file=sys.stderr)
        return 2
    print(json.dumps(s, indent=2) if a.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
