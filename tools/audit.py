"""ddr audit: measured faults on a rendered page, at every scroll stop, at the sizes Fergus uses.

    ddr audit --url https://example.com
    ddr audit --file out/index.html --viewports mac-1512x820,phone-390x844 --json
    ddr audit --url http://localhost:8000/dashboard --storage-state .design/state/brand.json --strict

Each finding names a CSS selector, the text involved and its rect in page pixels, so it can be fixed without a
screenshot:

  clip.text      glyphs cut by an ancestor with overflow hidden or clip (the ink, so descenders count)
  clip.box       a box with overflow hidden too small for its own words (whole lines hidden)
  offscreen      words, controls or pictures running off the viewport's side
  page.sideways  the page itself scrolls sideways
  overlap        one text block on top of another
  tap.small      touch only: a target under 44 by 44 CSS px
  tap.close      touch only: two targets under 8 px apart
  contrast       text against the pixels really behind it, under WCAG AA (4.5:1, 3:1 for large text)
  line.length    a paragraph over 85 characters a line (or under 45, on screens 600 px and wider)
  text.small     touch only: text under 16 px

and, for the first screen, a count of headings, filled actions and words, and the largest text, so "one headline,
one action" can be checked. Exit 0 when it looked (it reports, it does not judge), 1 with --strict and any finding,
2 when it could not look. A clean audit means these faults were not measured; it says nothing about whether the
page is good, and it cannot see motion (`ddr motion`) or what the words say.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "audit.mjs"
DEFAULT_VIEWPORTS = "mac-1512x820,mac-1440x780,phone-390x844"
TIMEOUT = 600
# The order findings are worth reading in: cut words first, then what makes a phone hard to use, then reading.
ORDER = ("clip.text", "offscreen", "page.sideways", "overlap", "clip.box", "contrast", "tap.small", "tap.close",
         "text.small", "line.length")


def node_ready() -> str | None:
    if not shutil.which("node") or not (ROOT / "node_modules" / "playwright").exists():
        return "needs Node.js 18+ and `npm install && npx playwright install chromium` in the design-director repo"
    return None


def run(target_flag: str, target: str, viewports: str, max_items: int = 5, max_stops: int = 12,
        storage_state: str | None = None, json_out: pathlib.Path | None = None) -> dict:
    """Run tools/audit.mjs and return its report (exit 2 inside it when it could not look)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = json_out or pathlib.Path(tmp) / "audit.json"
        argv = ["node", str(RUNNER), target_flag, target, "--viewports", viewports, "--json-out", str(out),
                "--max-items", str(max_items), "--max-stops", str(max_stops)]
        if storage_state:
            argv += ["--storage-state", storage_state]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return _cannot(f"the audit took longer than {TIMEOUT}s")
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _cannot(f"the audit wrote no report (exit {p.returncode}). {(p.stderr or '')[-400:].strip()}")


def _cannot(why: str) -> dict:
    return {"ok": False, "exit": 2, "tool": "audit", "viewports": [], "total": 0, "summary": why,
            "findings": [{"severity": "error", "rule": "tool.could-not-run", "message": why}]}


def _rect(r) -> str:
    return f"{r[0]},{r[1]} {r[2]}x{r[3]}" if isinstance(r, list) and len(r) == 4 else ""


def line(check: str, it: dict) -> str:
    text = f' "{it["text"]}"' if it.get("text") else ""
    return f"{check:13} {it.get('selector', '')}{text}: {it.get('detail', '')}  @ {_rect(it.get('rect'))} (stop {it.get('stop', 0)})"


def worst(rep: dict, n: int = 3) -> list[str]:
    """The n items most worth fixing first, across viewports: by ORDER, then each check's own score."""
    rows = []
    for v in rep.get("viewports", []):
        for check, c in (v.get("checks") or {}).items():
            for it in c.get("items", []):
                rank = ORDER.index(check) if check in ORDER else len(ORDER)
                rows.append((rank, -(it.get("score") or 0), f"{v['viewport']}: {line(check, it)}"))
    return [r[2] for r in sorted(rows)[:n]]


def counts(rep: dict) -> dict:
    out = {}
    for v in rep.get("viewports", []):
        for check, c in (v.get("checks") or {}).items():
            out[check] = out.get(check, 0) + c.get("count", 0)
    return {k: out[k] for k in sorted(out, key=lambda k: ORDER.index(k) if k in ORDER else 99) if out[k]}


def print_text(rep: dict) -> None:
    print(f"ddr audit {rep.get('target', '')}")
    for v in rep.get("viewports", []):
        if v.get("error"):
            print(f"\n{v['viewport']}: could not look ({v['error']})")
            continue
        capped = f", capped from {v.get('stopsWanted')}" if v.get("stopsCapped") else ""
        n = sum(c["count"] for c in v["checks"].values())
        print(f"\n{v['viewport']}: {v['stops']} scroll stops{capped}, {n} found"
              + (f", HTTP {v['status']}" if v.get("status") and v["status"] >= 400 else "")
              + (f", landed on {v['finalUrl']}" if v.get("finalUrl") and v["finalUrl"] != rep.get("target") else ""))
        f = v.get("fold") or {}
        if f:
            big = f.get("largest") or {}
            print(f"  first screen  {f.get('headings')} headings {f.get('headingText')}, {f.get('primaryActions')} filled actions "
                  f"{f.get('actionText')}, {f.get('words')} words, largest {big.get('px')}px {big.get('selector', '')} \"{big.get('text', '')}\"")
        for check in sorted(v["checks"], key=lambda k: ORDER.index(k) if k in ORDER else 99):
            c = v["checks"][check]
            for it in c["items"]:
                print("  " + line(check, it))
            if c["cut"]:
                print(f"  {check:13} ... {c['cut']} more not shown (--max-items)")
        if v.get("contrastUnmeasured"):
            print(f"  contrast      {v['contrastUnmeasured']} text runs not measured (gradient or transparent text)")
    print(f"\n{rep.get('summary', '')}")
    print("Measured, not judged: a clean audit cannot see motion (ddr motion), whether the words say what it is, or taste.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ddr audit", description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url")
    src.add_argument("--file")
    ap.add_argument("--viewports", default=DEFAULT_VIEWPORTS)
    ap.add_argument("--max-items", type=int, default=5, help="items kept per check per viewport (the rest are counted)")
    ap.add_argument("--max-stops", type=int, default=12, help="scroll stops per viewport, spread evenly when capped")
    ap.add_argument("--storage-state", help="a Playwright storage state (cookies) for a page behind a sign-in")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything is found")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0) and 2
    if a.url and not a.url.startswith(("http://", "https://")):
        print(f"audit: --url needs a scheme, for example http://{a.url}", file=sys.stderr)
        return 2
    if a.file and not pathlib.Path(a.file).is_file():
        print(f"audit: no such file {a.file}", file=sys.stderr)
        return 2
    why = node_ready()
    if why:
        print(f"audit {why}", file=sys.stderr)
        return 2
    flag, target = ("--url", a.url) if a.url else ("--file", str(pathlib.Path(a.file).resolve()))
    rep = run(flag, target, a.viewports, a.max_items, a.max_stops, a.storage_state)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print_text(rep)
    if rep.get("exit") == 2:
        if not a.json:
            print(f"audit could not look: {rep.get('summary')}", file=sys.stderr)
        return 2
    return 1 if a.strict and rep.get("total") else 0


if __name__ == "__main__":
    sys.exit(main())
