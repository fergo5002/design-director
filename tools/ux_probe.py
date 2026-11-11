"""ddr ux: run tools/ux-probe.js on a built page at a phone and a desktop size.

    python tools/ddr.py ux --file out/index.html                    # 390x844 and 1440x900
    python tools/ddr.py ux --file out/index.html --viewports 390x844,820x1180,1440x900 --json
    python tools/ddr.py ux --url http://localhost:3000/checkout     # the page as served, with its assets

It counts what a script can count (UX.md, "Cheap checks"): unlabelled fields, wrong input types,
missing autofill, vague buttons, clickable divs, small targets, sideways scroll, numbers that do not
line up, pre-ticked consent. Exit 0 when nothing fails, 1 when something fails, 2 when the probe
could not run. Warnings never change the exit code but are always printed: read them.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "ux-probe.js"
RENDER = ROOT / "tools" / "eval_render.mjs"


def run(target: str, viewport: str) -> dict:
    flag = "--url" if target.startswith(("http://", "https://")) else "--file"
    p = subprocess.run(["node", str(RENDER), "probe", flag, target, "--viewport", viewport,
                        "--expr", PROBE.read_text()], capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    try:
        data = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise RuntimeError((p.stderr or p.stdout).strip()[-400:] or "no output from the probe")
    if not data.get("ok") or not isinstance(data.get("value"), dict):
        raise RuntimeError(data.get("error") or f"probe returned {data!r}"[:400])
    return data["value"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ddr ux", description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="the built HTML page (root-relative assets will not load from a file)")
    src.add_argument("--url", help="the page as served, e.g. http://localhost:3000/")
    ap.add_argument("--viewports", default="390x844,1440x900")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.url:
        if not a.url.startswith(("http://", "https://")):
            print(f"ux: --url needs a scheme, for example http://{a.url}", file=sys.stderr); return 2
        target = a.url
    else:
        page = pathlib.Path(a.file).resolve()
        if not page.exists():
            print(f"ux: no such file {a.file}", file=sys.stderr); return 2
        target = str(page)
    viewports = [v.strip() for v in a.viewports.split(",") if v.strip()]
    if not viewports:
        print("ux: no viewports given, so nothing was checked", file=sys.stderr); return 2
    if not shutil.which("node") or not (ROOT / "node_modules" / "playwright").exists():
        print("ux needs Node.js 18+ and `npm install && npx playwright install chromium` in the design-director repo",
              file=sys.stderr); return 2
    results = {}
    try:
        for vp in viewports:
            results[vp] = run(target, vp)
    except (RuntimeError, subprocess.SubprocessError) as e:
        print(f"ux: the probe could not run: {e}", file=sys.stderr); return 2
    fails = sum(r["fails"] for r in results.values())
    if a.json:
        print(json.dumps({"target": target, "fails": fails, "results": results}, indent=1))
    else:
        for vp, r in results.items():
            print(f"{vp}: {r['fails']} fail, {r['warns']} warn")
            for f in sorted(r["findings"], key=lambda f: (f["severity"] != "fail", f["rule"])):
                print(f"  {f['severity']:4} {f['rule']:34} {f['where']}")
        print("A clean probe means the countable rules passed. It cannot see whether the words, the flow or the hierarchy are right.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
