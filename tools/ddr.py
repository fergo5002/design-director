"""ddr: one entry point for the design-director toolkit.

    python tools/ddr.py install --agent all        # link the skills into Claude Code, Codex, Cursor, Gemini
    python tools/ddr.py doctor                     # what is installed, what is missing, what is stale
    python tools/ddr.py init                       # scaffold .design/ in the current project
    python tools/ddr.py mcp                        # recommended MCP servers with per-agent setup
    python tools/ddr.py mcp --tier core --agent claude --apply
    python tools/ddr.py sources search "editorial type pairings"
    python tools/ddr.py taste brief
    python tools/ddr.py lint src/
    python tools/ddr.py shots https://localhost:3000 --full
    python tools/ddr.py palette ramp --hue 168 --chroma 0.02:0.05 --light 0.25:0.95 --steps 9
    python tools/ddr.py fonts --css "https://api.fontshare.com/v2/css?f[]=switzer@400,600" --family Switzer --out switzer.css
    python tools/ddr.py radar

Standard library only (Python 3.9+). `shots` needs Node and `npm install` in this repo.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

SKILLS = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
HOME = pathlib.Path.home()
def agent_dirs() -> dict:
    return {
        "claude": HOME / ".claude" / "skills",
        "codex": HOME / ".codex" / "skills",
        "agents": HOME / ".agents" / "skills",   # the cross-agent convention some tools read
    }


MARKER = ".ddr-source"   # written into copied skills so a later install can refresh them


def _copy(src: pathlib.Path, dst: pathlib.Path):
    shutil.copytree(src, dst)
    (dst / MARKER).write_text(str(ROOT), encoding="utf-8")


def _ours_copy(dst: pathlib.Path) -> bool:
    m = dst / MARKER
    return not dst.is_symlink() and m.is_file() and m.read_text(encoding="utf-8").strip() == str(ROOT)


def _link(src: pathlib.Path, dst: pathlib.Path, copy: bool) -> str:
    if dst.is_symlink() and dst.resolve() == src.resolve():
        return f"ok      {dst} (already linked)"
    if _ours_copy(dst):
        shutil.rmtree(dst)
        _copy(src, dst)
        return f"updated {dst} (copy refreshed from this repo)"
    if dst.exists() or dst.is_symlink():
        return f"SKIPPED {dst} exists and is not this repo's. Rename yours or use --prefix."
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        _copy(src, dst)
        return f"copied  {dst}"
    try:
        dst.symlink_to(src, target_is_directory=True)
        return f"linked  {dst} -> {src}"
    except OSError:  # Windows without developer mode
        _copy(src, dst)
        return f"copied  {dst} (symlinks unavailable; run install again after git pull to refresh)"


def _shim() -> str:
    """Put a `ddr` command on PATH so agents can call the tools from any project."""
    py = sys.executable or "python3"
    if os.name == "nt":
        target = HOME / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "ddr.cmd"
        marker = "rem ddr-shim: design-director"
        body = f'@echo off\r\n{marker}\r\n"{py}" "{TOOLS / "ddr.py"}" %*\r\n'
    else:
        target = HOME / ".local" / "bin" / "ddr"
        marker = "# ddr-shim: design-director"
        body = f'#!/bin/sh\n{marker}\nexec "{py}" "{TOOLS / "ddr.py"}" "$@"\n'
    if target.is_symlink():
        return f"[shim]  SKIPPED {target} is a symlink; remove it and run install again"
    if target.exists() and marker not in target.read_text(errors="ignore").splitlines()[:3]:
        return f"[shim]  SKIPPED {target} exists and is not ours"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o755)
    on_path = str(target.parent) in os.environ.get("PATH", "").split(os.pathsep)
    return f"[shim]  {target}" + ("" if on_path else f"  (add {target.parent} to your PATH)")


def install(argv):
    import argparse
    p = argparse.ArgumentParser(prog="ddr install")
    p.add_argument("--agent", default="all",
                   help="claude, codex, agents, cursor, gemini, or all (cursor and gemini only with --project)")
    p.add_argument("--project", help="install into a project instead of your home folder")
    p.add_argument("--copy", action="store_true", help="copy instead of symlink (symlinks update with git pull)")
    p.add_argument("--prefix", default="", help="install skills as <prefix><name> to avoid clashing with your own")
    a = p.parse_args(argv)
    proj = pathlib.Path(a.project).resolve() if a.project else None
    if a.agent == "all":
        agents = ["claude", "codex", "agents"] + (["cursor", "gemini"] if proj else [])
    else:
        agents = a.agent.split(",")
    for agent in agents:
        if agent in ("cursor", "gemini") and (proj is None or proj == ROOT.resolve()):
            print(f"[{agent}] skipped: Cursor and Gemini read per-project files. "
                  f"Run `ddr install --agent {agent} --project <your project>` in each project.")
            continue
        if agent in ("claude", "codex", "agents"):
            base = (proj / f".{agent}" / "skills") if proj else agent_dirs()[agent]
            for s in SKILLS:
                print(f"[{agent}] " + _link(ROOT / "skills" / s, base / f"{a.prefix}{s}", a.copy))
        elif agent == "cursor":
            target = proj / ".cursor" / "rules" / "design-director.mdc"
            target.parent.mkdir(parents=True, exist_ok=True)
            body = "\n".join(f"- {s}: {ROOT / 'skills' / s / 'SKILL.md'}" for s in SKILLS)
            target.write_text(
                "---\ndescription: Design work of any kind (UI, landing pages, dashboards, brand, decks, motion). "
                "Load before writing markup, picking a colour or a font.\nalwaysApply: false\n---\n\n"
                f"Read and follow the design-director skill files:\n\n{body}\n\n"
                f"Tools: run `python {TOOLS / 'ddr.py'} --help`.\n", encoding="utf-8")
            print(f"[cursor] wrote {target}")
        elif agent == "gemini":
            target = proj / "GEMINI.md"
            line = f"@{ROOT / 'AGENTS.md'}"
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            if line not in existing:
                target.write_text(existing + ("\n" if existing else "") + line + "\n", encoding="utf-8")
            print(f"[gemini] {target} imports {ROOT / 'AGENTS.md'}")
        else:
            print(f"unknown agent {agent}")
    print(_shim())
    print("\nClaude Code users can instead install it as a plugin:\n"
          "  /plugin marketplace add fergo5002/design-director\n  /plugin install design-director@design-director")
    print(f"\nNext: python {TOOLS / 'ddr.py'} doctor")
    return 0


def init(argv):
    """Scaffold .design/ in the current project: house taste, reference ledger, lint config."""
    target = pathlib.Path.cwd() / ".design"
    target.mkdir(exist_ok=True)
    for name in ("taste.md", "references.md", "lint.toml"):
        dst = target / name
        if dst.exists():
            print(f"kept    {dst}")
        else:
            shutil.copy(ROOT / "templates" / name, dst)
            print(f"created {dst}")
    gi = target / ".gitignore"
    if not gi.exists():
        gi.write_text("shots/\n", encoding="utf-8")
    print("Commit .design/: it is this project's design memory. Screenshots are ignored.")
    return 0


def _which(cmd):
    return shutil.which(cmd) is not None


def doctor(argv):
    import sources
    ok = True
    print(f"design-director at {ROOT}")
    try:
        rev = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h %cs"], capture_output=True, text=True).stdout.strip()
        print(f"  version      {rev or 'not a git checkout'}")
    except FileNotFoundError:
        pass
    print(f"  python       {sys.version.split()[0]}")
    print(f"  node         {'yes' if _which('node') else 'MISSING (needed for shots)'}")
    pw = (ROOT / "node_modules" / "playwright").exists()
    print(f"  playwright   {'yes' if pw else 'missing: npm install && npx playwright install chromium'}")
    for agent, base in agent_dirs().items():
        state = []
        for s in SKILLS:
            d = base / s
            state.append(f"{s}:{'linked' if d.is_symlink() and d.resolve() == (ROOT / 'skills' / s).resolve() else ('OTHER' if d.exists() else '-')}")
        print(f"  {agent:12} {' '.join(state)}")
    entries = sources.load()
    errs = sources.validate(entries, sources.categories())
    ok &= not errs
    print(f"  catalogue    {len(entries)} sources, {len(errs)} problems, {len(sources.stale(entries, days=180))} not re-verified in 180 days")
    import taste
    for label, path in (("taste (here)", taste.default_path()), ("taste (global)", taste.default_path(True))):
        n = len(taste.read(path))
        print(f"  {label:12} {n} events at {path}" if n else f"  {label:12} none yet ({path})")
    claude = shutil.which("claude")
    if claude:
        try:
            out = subprocess.run([claude, "mcp", "list"], capture_output=True, text=True, timeout=60).stdout
            names = [l.split(":")[0] for l in out.splitlines() if ":" in l and not l.startswith(" ")]
            print(f"  claude mcp   {', '.join(names[:12]) or 'none'}")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"  claude mcp   could not list ({type(e).__name__})")
    return 0 if ok else 1


SAFE_PREFIXES = (["claude", "mcp", "add"], ["claude", "plugin"], ["npx", "shadcn@latest", "mcp", "init"],
                 ["npx", "@21st-dev/cli@latest", "init"])
UNSAFE = set(";|&`$<>\n")


def _safe_commands(cmd: str):
    """Split a catalogue setup line into argv lists, or None if it is anything but a plain,
    known setup command. Commands joined with && become separate runs; no shell is used."""
    import shlex
    out = []
    for part in cmd.split(" && "):
        if any(c in UNSAFE for c in part):
            return None
        argv = shlex.split(part)
        if not any(argv[:len(pre)] == pre for pre in SAFE_PREFIXES):
            return None
        out.append(argv)
    return out


def mcp(argv):
    import argparse
    import sources
    p = argparse.ArgumentParser(prog="ddr mcp")
    p.add_argument("--tier", choices=["core", "recommended", "optional", "all"], default="all")
    p.add_argument("--agent", choices=["claude", "codex", "cursor"], default="claude")
    p.add_argument("--apply", action="store_true", help="claude only: run the setup commands for one --tier")
    a = p.parse_args(argv)
    if a.apply and (a.agent != "claude" or a.tier == "all"):
        print("--apply needs --agent claude and an explicit --tier (core, recommended or optional)", file=sys.stderr)
        return 2
    data = sources.loads((ROOT / "mcp" / "servers.toml").read_text(encoding="utf-8"))
    order = ["core", "recommended", "optional"]
    rc, skipped = 0, []
    for s in sorted(data.get("server", []), key=lambda s: (order.index(s["tier"]), s["id"])):
        if a.tier != "all" and s["tier"] != a.tier:
            continue
        print(f"\n[{s['tier']}] {s['name']}: {s['why']}")
        if s.get("needs"):
            print(f"  needs: {s['needs']}")
        cmd = s.get(a.agent)
        print("  " + (cmd or f"(no {a.agent} setup documented; see {s.get('docs', '')})").replace("\n", "\n  "))
        if a.apply:
            runs = _safe_commands(cmd) if cmd else None
            if not runs:
                skipped.append(s["id"])
                continue
            for run in runs:
                exe = shutil.which(run[0])
                if not exe:
                    skipped.append(f"{s['id']} ({run[0]} not found)")
                    break
                rc |= subprocess.run([exe, *run[1:]]).returncode
    if skipped:
        print(f"\nNot applied, set these up by hand: {', '.join(skipped)}")
    if a.agent == "codex":
        print("\nCodex: paste the blocks above into ~/.codex/config.toml")
    if a.agent == "cursor":
        print("\nCursor: merge the blocks above into .cursor/mcp.json under \"mcpServers\"")
    return rc


def _run_py(module, argv):
    mod = __import__(module)
    return mod.main(argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "install":
        return install(rest)
    if cmd == "init":
        return init(rest)
    if cmd == "doctor":
        return doctor(rest)
    if cmd == "mcp":
        return mcp(rest)
    if cmd == "sources":
        return _run_py("sources", rest)
    if cmd == "taste":
        return _run_py("taste", rest)
    if cmd == "lint":
        return _run_py("slop_lint", rest)
    if cmd == "radar":
        return _run_py("radar", rest)
    if cmd in ("palette", "fonts", "routes"):
        script = {"palette": "palette.py", "fonts": "inline_fonts.py", "routes": "check_routes.py"}[cmd]
        return subprocess.call([sys.executable, str(TOOLS / script), *rest])
    if cmd == "shots":
        if not _which("node"):
            print("shots needs Node.js 18+"); return 2
        return subprocess.call(["node", str(TOOLS / "shots.mjs"), *rest], cwd=os.getcwd())
    print(f"unknown command {cmd!r}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
