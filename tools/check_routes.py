#!/usr/bin/env python3
"""Prove that everything the skills point at actually exists.

A routing table is prose, and prose is never executed. An earlier version of this
skill routed every chart to a skill that was not installed, and nobody noticed for
weeks. This checker reads every skills/**/*.md and fails if it names:

  - a companion file (COLOUR.md, skills/x/Y.md) that is not in the repo
  - a tool (tools/x.py, tools/x.mjs) that is not in the repo
  - a catalogue entry, written `src:<id>`, that is not in library/*.toml
  - a ddr subcommand that tools/ddr.py does not handle

    python tools/check_routes.py          # report
    python tools/check_routes.py --quiet  # exit code only
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

FILE_REF = re.compile(r"\b([A-Z][A-Z0-9_-]+\.md)\b")
TOOL_REF = re.compile(r"\btools/([\w.-]+\.(?:py|mjs|js))\b")
SRC_REF = re.compile(r"\bsrc:([a-z0-9][a-z0-9-]*)\b")
DD_REF = re.compile(r"`(?:python3?\s+\S*tools/ddr\.py|ddr)\s+([a-z]+)")
DD_COMMANDS = {"install", "init", "doctor", "mcp", "sources", "taste", "lint", "radar", "palette", "fonts", "routes", "shots", "help"}
# Files that exist outside a skill folder but are fine to name.
REPO_FILES = {"README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "SOURCES.md", "LICENSE.md", "CHANGELOG.md",
              "SKILL.md", "DESIGN.md", "GEMINI.md"}


def check() -> list[str]:
    import sources
    ids = {e["id"] for e in sources.load()}
    all_md = {p.name for p in ROOT.rglob("*.md") if "node_modules" not in p.parts}
    problems = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        rel = md.relative_to(ROOT)
        for m in FILE_REF.finditer(text):
            name = m.group(1)
            if name not in all_md and name not in REPO_FILES:
                problems.append(f"{rel}: names {name}, which is not in the repo")
        for m in TOOL_REF.finditer(text):
            if not (ROOT / "tools" / m.group(1)).exists():
                problems.append(f"{rel}: names tools/{m.group(1)}, which does not exist")
        for m in SRC_REF.finditer(text):
            if m.group(1) not in ids:
                problems.append(f"{rel}: names src:{m.group(1)}, which is not in the catalogue")
        for m in DD_REF.finditer(text):
            if m.group(1) not in DD_COMMANDS:
                problems.append(f"{rel}: names `ddr {m.group(1)}`, which ddr.py does not handle")
    servers = ROOT / "mcp" / "servers.toml"
    if servers.exists():
        for s in sources.loads(servers.read_text(encoding="utf-8")).get("server", []):
            if s.get("catalogue") not in ids:
                problems.append(f"mcp/servers.toml: {s.get('id')} points at catalogue id {s.get('catalogue')!r}, which does not exist")
            for f in ("tier", "why", "claude", "docs"):
                if not s.get(f):
                    problems.append(f"mcp/servers.toml: {s.get('id')} has no {f}")
    return problems


def main():
    problems = check()
    if "--quiet" not in sys.argv:
        for p in problems:
            print(p)
        print(f"{len(problems)} broken references")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
