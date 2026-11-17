"""ddr motion: is the page smooth, idle and while scrolling, measured rather than judged from stills.

    ddr motion --url https://example.com --scroll
    ddr motion --file out/index.html --scroll --viewport phone-390x844 --json
    ddr motion --url http://localhost:8000/dashboard --storage-state .design/state/brand.json --strict

Headless Chromium idles on the page for a few seconds, then (with --scroll) scrolls it top to bottom 14 px a frame,
and reports frame time percentiles and dropped frames for each phase and each section, long tasks over 50 ms,
layout shifts with the elements that moved, and the elements animating layout properties (width, top, margin and
the like, which make the browser lay the page out again every frame). The pass rule is frame-probe.js's: each
section's p95 within 1.5 refresh intervals, no frame over 100 ms, no long animation frame over 100 ms.

Exit 0 when it measured, 1 with --strict when the verdict is NOT SMOOTH, 2 when it could not measure (including a
page whose animation frames never ran). Headless frames are paced by a timer, not a display, so a stall on the main
thread shows and a compositor-only judder does not: for that, paste tools/motion-probe.js into his real Chrome.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "motion.mjs"


def run(target_flag: str, target: str, viewport: str = "mac-1512x820", scroll: bool = True, idle_ms: int = 3000,
        max_scroll_ms: int = 12000, storage_state: str | None = None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "motion.json"
        argv = ["node", str(RUNNER), target_flag, target, "--viewport", viewport, "--idle", str(idle_ms),
                "--max-scroll", str(max_scroll_ms), "--json-out", str(out)]
        if scroll:
            argv.append("--scroll")
        if storage_state:
            argv += ["--storage-state", storage_state]
        budget = (idle_ms + max_scroll_ms * 2) / 1000 + 120
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=budget)
        except subprocess.TimeoutExpired:
            return _cannot(f"motion took longer than {int(budget)}s")
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _cannot(f"motion wrote no report (exit {p.returncode}). {(p.stderr or '')[-400:].strip()}")


def _cannot(why: str) -> dict:
    return {"ok": False, "exit": 2, "tool": "motion", "summary": why,
            "findings": [{"severity": "error", "rule": "tool.could-not-run", "message": why}]}


def _phase(name: str, p: dict) -> str:
    if not p or not p.get("frames"):
        return f"  {name:7} not measured"
    return (f"  {name:7} {p['frames']:4} frames  p50 {p['p50']}  p95 {p['p95']}  p99 {p['p99']}  worst {p['worst']} ms"
            f"  dropped {p['dropped']}{'' if p.get('ok', True) else '  <- fails'}")


def problems(r: dict) -> list[str]:
    """The lines worth acting on, worst first: failing sections, stalls, layout animation, shifts."""
    out = []
    for name, row in sorted((r.get("sections") or {}).items(), key=lambda kv: -(kv[1].get("worst") or 0)):
        if not row.get("ok", True):
            out.append(f"section {name}: p95 {row['p95']} ms, worst {row['worst']} ms over {row['frames']} frames")
    for t in (r.get("longTasks") or {}).get("items", [])[:3]:
        out.append(f"long task {t['ms']} ms at {t['at'] / 1000:.1f}s into the run")
    for a in (r.get("layoutAnimations") or [])[:3]:
        how = f"script, {a['writes']} writes" if a.get("kind") == "script" else f"{a['kind']} {a.get('name') or ''}".strip()
        out.append(f"layout animation {a['selector']}: {', '.join(a['props'])} ({how}); animate transform or opacity instead")
    ls = r.get("layoutShift") or {}
    if ls.get("total"):
        src = ", ".join(f"{s['selector']} ({s['value']})" for s in ls.get("sources", [])[:3]) or "no node named"
        out.append(f"layout shift {ls['total']} over {ls['count']} shifts: {src}")
    return out


def print_text(rep: dict) -> None:
    r = rep.get("result") or {}
    head = "headless Chromium" if r.get("headless") else "Chromium"
    print(f"ddr motion {rep.get('target', '')} at {rep.get('viewport')} ({head})")
    if not r:
        print(rep.get("summary"))
        return
    print(f"verdict {r['verdict']}  refresh {r['refreshMs']} ms")
    if r.get("why"):
        print(f"  {r['why']}")
    print(_phase("idle", r["phases"].get("idle")))
    print(_phase("scroll", r["phases"].get("scroll")))
    for line in problems(r):
        print(f"  {line}")
    lt = r.get("longTasks") or {}
    print(f"  long tasks over 50 ms during the run: {lt.get('count', 0)} ({lt.get('over100', 0)} over 100 ms)")
    print("Headless frames are paced by a timer: a main-thread stall shows here, a compositor judder does not. "
          "Smooth on a real screen is checked in his browser (motion-probe.js, foreground).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ddr motion", description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url")
    src.add_argument("--file")
    ap.add_argument("--viewport", default="mac-1512x820")
    ap.add_argument("--scroll", action="store_true", help="scroll top to bottom after the idle phase")
    ap.add_argument("--idle", type=int, default=3000, help="milliseconds to watch the page idle (default 3000)")
    ap.add_argument("--max-scroll", type=int, default=12000, help="a long page scrolls in about this many ms")
    ap.add_argument("--storage-state", help="a Playwright storage state (cookies) for a page behind a sign-in")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 when the verdict is NOT SMOOTH")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0) and 2
    if a.url and not a.url.startswith(("http://", "https://")):
        print(f"motion: --url needs a scheme, for example http://{a.url}", file=sys.stderr)
        return 2
    if a.file and not pathlib.Path(a.file).is_file():
        print(f"motion: no such file {a.file}", file=sys.stderr)
        return 2
    import audit
    why = audit.node_ready()
    if why:
        print(f"motion {why}", file=sys.stderr)
        return 2
    flag, target = ("--url", a.url) if a.url else ("--file", str(pathlib.Path(a.file).resolve()))
    rep = run(flag, target, a.viewport, a.scroll, a.idle, a.max_scroll, a.storage_state)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print_text(rep)
    if rep.get("exit") == 2:
        if not a.json:
            print(f"motion could not measure: {rep.get('summary')}", file=sys.stderr)
        return 2
    return 1 if a.strict and (rep.get("result") or {}).get("verdict") == "NOT SMOOTH" else 0


if __name__ == "__main__":
    sys.exit(main())
