"""ddr: one entry point for the design-director toolkit.

    python tools/ddr.py install --agent all        # link the skills into Claude Code, Codex, Cursor, Gemini
    python tools/ddr.py doctor                     # what is installed, what is missing, what competes with it
    python tools/ddr.py uninstall                  # remove exactly what install added (keeps your domains)
    python tools/ddr.py init                       # scaffold .design/ in the current project
    python tools/ddr.py mcp                        # recommended MCP servers with per-agent setup
    python tools/ddr.py mcp --tier core --agent claude --apply
    python tools/ddr.py sources search "editorial type pairings"
    python tools/ddr.py taste brief
    python tools/ddr.py domain match "a booking site for a sauna"   # where you stand, and how sure
    python tools/ddr.py lint src/ [--json]          # exit 0 clean, 1 findings, 2 could not look
    python tools/ddr.py gate run --src src/ --file index.html [--copy copy.txt] [--brand acme]
    python tools/ddr.py gate verify --require-review   # is the receipt current, passing and reviewed
    python tools/ddr.py gate waive --reason "<why>" --src src/
    python tools/ddr.py review record --run latest --json review.json
    python tools/ddr.py review show
    python tools/ddr.py shots https://localhost:3000 --full
    python tools/ddr.py teardown https://example.com --into independent-stays   # capture and measure a reference
    python tools/ddr.py sheet --domain independent-stays --with my-fold.png      # yours beside the best, same size
    python tools/ddr.py sheet --images a.png b.png --labels "Before,After" --cols 2 --out sheet.png
    python tools/ddr.py crop before.png after.png --box 0,0,400,300 --scale 2 --out pair.png
    python tools/ddr.py palette ramp --hue 168 --chroma 0.02:0.05 --light 0.25:0.95 --steps 9
    python tools/ddr.py fonts --css "https://api.fontshare.com/v2/css?f[]=switzer@400,600" --family Switzer --out switzer.css
    python tools/ddr.py history https://example.com    # how old the design is, from the Wayback Machine
    python tools/ddr.py mcp --research                  # the servers that find, look at and measure references
    python tools/ddr.py radar
    python tools/ddr.py brand show acme                 # a brand pack: palette, fonts, bans, voice, graphic language
    python tools/ddr.py brand lint src/ --brand acme    # check work against the pack (exit 0, 1 findings, 2 could not run)
    python tools/ddr.py contract add --kind copy --text "Hero" --source "client 2026-11-04" --exact "..."
    python tools/ddr.py contract check --phase final    # every requirement closed with evidence
    python tools/ddr.py claims check --src src/         # every claim on the page checked or read
    python tools/ddr.py notes add fintech "what happened" --evidence "where it shows"
    python tools/ddr.py notes promote --apply           # strong notes into a dossier's Proposed guidance
    python tools/ddr.py looks pick --look b --why "the person's reason" --others a,c --domain fintech
    python tools/ddr.py eval run --arm old=<skill dir> --arm new=skills/design-director --dry-run   # compare two versions on real briefs

Standard library only (Python 3.9+). `shots`, `sheet`, `crop` and the gate's render step need
Node and `npm install` in this repo.
"""
from __future__ import annotations

import os
import pathlib
import re
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


BLOCK_BEGIN = "<!-- design-director:begin (added by `ddr install`; `ddr uninstall` removes it) -->"
BLOCK_END = "<!-- design-director:end -->"
ROUTING = """## Design work

For any design work (a page, component, flow, dashboard, brand, deck, motion, imagery, or a
review of any of these), load the **design-director** skill before writing markup, choosing a
colour or picking a font, and follow it through to its gate. It starts with
`ddr domain match "<the brief>"`: say the confidence it reports in one line, and when it is
below what the job needs, research the domain first with the design-research skill, without
waiting to be asked. Project-specific design rules and the user's direct instructions outrank
the skill. Generic design defaults anywhere else in this file do not."""
INSTRUCTION_FILES = {"claude": HOME / ".claude" / "CLAUDE.md", "codex": HOME / ".codex" / "AGENTS.md"}
# A competing skill claims interface or web design work; merely mentioning design-director does not count.
DESIGN_SKILL = re.compile(r"\b(ui|ux|user interfaces?|interfaces?|web ?sites?|web pages?|landing pages?|front-?end|"
                          r"design systems?|typography|tailwind|shadcn|css|styling)\b", re.I)
# A competing rule sets a design default: a named face or framework, a colour, a look.
DESIGN_RULE = re.compile(r"\b(inter|roboto|poppins|montserrat|open sans|lato|helvetica|arial|space grotesk|dm sans|"
                         r"playfair|geist|shadcn|tailwind|bootstrap|material ui|mui|chakra|daisyui|glassmorphism|"
                         r"gradients?|dark mode|dark theme|rounded-\w+|drop shadows?|font-family|fonts?|typefaces?|"
                         r"palettes?|brand colou?rs?|accent colou?rs?)\b|#[0-9a-f]{6}\b|#[0-9a-f]{3}\b", re.I)


def _domain_home() -> pathlib.Path:
    env = os.environ.get("DDR_HOME")
    return pathlib.Path(env).expanduser() if env else HOME / ".design-director"


def _strip_block(text: str) -> str:
    pat = re.compile(re.escape(BLOCK_BEGIN) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.S)
    return pat.sub("", text)


def _route(agent: str, remove: bool = False) -> str:
    target = INSTRUCTION_FILES.get(agent)
    if target is None:
        return ""
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    base = _strip_block(old)
    if remove:
        if base != old:
            if base.strip():
                target.write_text(base.rstrip() + "\n", encoding="utf-8")
            else:
                target.unlink()   # it held nothing but our block
            return f"[{agent}] removed the routing block from {target}"
        return ""
    block = f"{BLOCK_BEGIN}\n{ROUTING}\n{BLOCK_END}\n"
    if BLOCK_BEGIN in old and BLOCK_END in old:   # refresh in place, wherever the user moved it
        pat = re.compile(re.escape(BLOCK_BEGIN) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.S)
        new = pat.sub(lambda _m: block, old, count=1)
    else:
        new = base.rstrip() + ("\n\n" if base.strip() else "") + block
    if new == old:
        return f"[{agent}] routing block already current in {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    return f"[{agent}] {'refreshed' if BLOCK_BEGIN in old else 'added'} the routing block in {target}"


def _ours(dst: pathlib.Path, src: pathlib.Path) -> bool:
    return (dst.is_symlink() and dst.resolve() == src.resolve()) or _ours_copy(dst)


def _description(skill_md: pathlib.Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return ""
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def conflicts() -> dict:
    """Other skills and instruction lines that also claim design work, which is the usual
    reason an agent ignores design-director: something else told it what to do first."""
    ours = {(ROOT / "skills" / s).resolve() for s in SKILLS}
    skills = []
    for agent, base in agent_dirs().items():
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not (d / "SKILL.md").exists():
                continue
            if d.resolve() in ours or _ours_copy(d):
                continue
            desc = _description(d / "SKILL.md")
            claim = re.sub(r"design-director", "", desc, flags=re.I)
            if DESIGN_SKILL.search(d.name.replace("-", " ")) or DESIGN_SKILL.search(claim):
                skills.append({"agent": agent, "name": d.name, "path": str(d), "description": desc[:120]})
    rules = []
    for agent, f in INSTRUCTION_FILES.items():
        if not f.exists():
            continue
        text = _strip_block(f.read_text(encoding="utf-8", errors="ignore"))
        for n, line in enumerate(text.splitlines(), 1):
            if DESIGN_RULE.search(line) and len(line.strip()) > 3:
                rules.append({"agent": agent, "file": str(f), "line_no": n, "line": line.strip()[:140]})
    return {"skills": skills, "rules": rules}


def install(argv):
    import argparse
    p = argparse.ArgumentParser(prog="ddr install")
    p.add_argument("--agent", default="all",
                   help="claude, codex, agents, cursor, gemini, or all (cursor and gemini only with --project)")
    p.add_argument("--project", help="install into a project instead of your home folder")
    p.add_argument("--copy", action="store_true", help="copy instead of symlink (symlinks update with git pull)")
    p.add_argument("--prefix", default="", help="install skills as <prefix><name> to avoid clashing with your own")
    p.add_argument("--no-routing", action="store_true",
                   help="do not add the short routing block to ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md")
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
            lead = base / f"{a.prefix}design-director"
            if proj is None and not a.no_routing and agent in INSTRUCTION_FILES:
                if _ours(lead, ROOT / "skills" / "design-director"):
                    print(_route(agent))
                else:
                    print(f"[{agent}] routing block not added: {lead} is not this repo's skill")
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
    dh = _domain_home() / "domains"
    dh.mkdir(parents=True, exist_ok=True)
    print(f"[domains] your design expertise accumulates in {dh} (set DDR_HOME to move it)")
    found = conflicts()
    if found["skills"] or found["rules"]:
        print(f"\nHeads up: {len(found['skills'])} other design skills and {len(found['rules'])} design lines in your "
              "instructions may compete with design-director. `ddr doctor` lists them.")
    print("\nClaude Code users can instead install it as a plugin:\n"
          "  /plugin marketplace add fergo5002/design-director\n  /plugin install design-director@design-director")
    print(f"\nNext: python {TOOLS / 'ddr.py'} doctor")
    return 0


def uninstall(argv):
    """Remove exactly what install made: our skill links or copies, the routing blocks and the shim.
    Your domains, taste ledger and anything else in DDR_HOME are kept."""
    import argparse
    p = argparse.ArgumentParser(prog="ddr uninstall")
    p.add_argument("--prefix", default="")
    a = p.parse_args(argv)
    for agent, base in agent_dirs().items():
        for s in SKILLS:
            d = base / f"{a.prefix}{s}"
            if d.is_symlink() and d.resolve() == (ROOT / "skills" / s).resolve():
                d.unlink(); print(f"[{agent}] unlinked {d}")
            elif _ours_copy(d):
                shutil.rmtree(d); print(f"[{agent}] removed copy {d}")
        msg = _route(agent, remove=True)
        if msg:
            print(msg)
    shim = HOME / ("AppData/Local/Microsoft/WindowsApps/ddr.cmd" if os.name == "nt" else ".local/bin/ddr")
    if shim.exists() and not shim.is_symlink() and "ddr-shim: design-director" in shim.read_text(errors="ignore"):
        shim.unlink(); print(f"[shim]  removed {shim}")
    print(f"kept your domains and taste in {_domain_home()}")
    return 0


def init(argv):
    """Scaffold .design/ in the current project: house taste, reference ledger, lint config, the brief."""
    target = pathlib.Path.cwd() / ".design"
    target.mkdir(exist_ok=True)
    (target / "brief").mkdir(exist_ok=True)
    for name, dst in [(n, target / n) for n in ("taste.md", "references.md", "lint.toml")] + \
            [("brief.md", target / "brief" / "BRIEF.md")]:
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
        if "design-director:OTHER" in state:
            print(f"  {'':12} a different design-director is installed there, so this repo's version is not the one "
                  f"your agent loads. Keep it, or install alongside with --prefix.")
    for agent, f in INSTRUCTION_FILES.items():
        has = f.exists() and BLOCK_BEGIN in f.read_text(encoding="utf-8", errors="ignore")
        print(f"  routing      {agent}: {'present in ' + str(f) if has else 'MISSING (run ddr install), so the agent may never reach for the skill'}")
    try:
        import domains
        doms = domains.all_domains()
        print(f"  domains      {len(doms)} at {domains.home_domains()} (plus the repo's starters)")
        for d in doms:
            c = domains.confidence(d)
            print(f"               {d['slug']:22} {c['score']:>3}/100 {c['band']}")
    except Exception as e:  # never let a bad domain file break doctor
        print(f"  domains      could not read ({e})")
    found = conflicts()
    for c in found["skills"]:
        print(f"  competing    [{c['agent']}] skill {c['name']}: {c['description']}")
    for r in found["rules"][:12]:
        print(f"  your rule    {r['file']}:{r['line_no']}: {r['line']}")
    if found["rules"]:
        print("               Specific rules for a project should win. Generic defaults (\"use Inter\", \"use shadcn defaults\",\n"
              "               a fixed palette for everything) make every design look the same: edit or delete them.")
    if found["skills"]:
        print("               Other design skills are fine to keep; the routing block tells your agent design-director leads.")
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
    p.add_argument("--research", action="store_true", help="only the servers that find, look at and measure references")
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
        if a.research and not s.get("research"):
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


def _pop(argv, name, default=None, valued=True):
    """Remove --name [value] from argv and return the value."""
    if name not in argv:
        return default
    i = argv.index(name)
    if not valued:
        del argv[i]
        return True
    val = argv[i + 1] if i + 1 < len(argv) else default
    del argv[i:i + 2]
    return val


def _url_slug(u: str) -> str:
    from urllib.parse import urlparse
    x = urlparse(u if "://" in u else "https://" + u)
    tail = re.sub(r"\W+", "-", x.path).rstrip("-")
    return re.sub(r"^www\.", "", (x.hostname or "").lower()) + tail


def teardown(argv):
    """ddr teardown <url...> [--into <domain>] [--frames 6] [--walk "A>B"]: capture and measure references."""
    argv = list(argv)
    if not _which("node"):
        print("teardown needs Node.js 18+ and `npm install` in the design-director repo"); return 2
    into = _pop(argv, "--into")
    if into:
        import domains
        dom = domains.load(into)
        if dom is None:
            print(f"no domain {into!r}: `ddr domain new {into} --kind sector|pattern` first"); return 2
        argv += ["--out", str(domains.path_for_write(dom["slug"]) / "shots")]
    rc = subprocess.call(["node", str(TOOLS / "teardown.mjs"), *argv], cwd=os.getcwd())
    if into:
        urls = [a if "://" in a else "https://" + a for i, a in enumerate(argv)
                if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--out", "--frames", "--walk", "--viewports", "--full-max"))]
        print("\nRecord each one once you have opened the images and judged it:")
        for u in urls:
            print(f'  ddr domain ref add {into} --name "..." --url {u} --verdict exemplar|counter --angle direct|leader|outside \\\n'
                  f'      --evidence screenshot --shots shots/{_url_slug(u)} --score N --take "<the move, with the measured values>"')
    return rc


def _exemplar_shots(dom, n):
    import domains
    refs = sorted((r for r in domains.active(dom) if r.get("verdict") == "exemplar"),
                  key=lambda r: -int(r.get("score", 3)))
    found = []
    for r in refs:
        cands = []
        if r.get("shots"):
            sp0 = pathlib.Path(r["shots"])
            for base in ([dom["path"]] + ([dom["seed_path"]] if dom.get("seed_path") else [])):
                sp = sp0 if sp0.is_absolute() else base / sp0
                cands += [sp / "desktop__fold.png", sp] if sp.is_dir() or not sp.suffix else [sp]
        for base in ([dom["path"]] + ([dom["seed_path"]] if dom.get("seed_path") else [])):
            cands.append(base / "shots" / _url_slug(r["url"]) / "desktop__fold.png")
        hit = next((c for c in cands if c.is_file()), None)
        if hit:
            found.append((r["name"], hit))
        if len(found) >= n:
            break
    return found


def sheet(argv):
    """ddr sheet <png...> [--labels] or ddr sheet --domain <slug> [--with yours.png] [--n 3]."""
    argv = list(argv)
    if not _which("node"):
        print("sheet needs Node.js 18+ and `npm install` in the design-director repo"); return 2
    slug = _pop(argv, "--domain")
    if slug:
        import domains
        dom = domains.load(slug)
        if dom is None:
            print(f"no domain {slug!r}"); return 2
        mine = _pop(argv, "--with")
        n = int(_pop(argv, "--n", "3"))
        shots = _exemplar_shots(dom, n)
        if not shots:
            print(f"no exemplar in {slug} has screenshots yet: `ddr teardown <url> --into {slug}` first"); return 2
        files = ([mine] if mine else []) + [str(f) for _, f in shots]
        labels = (["Yours"] if mine else []) + [name for name, _ in shots]
        if "--out" not in argv:
            argv += ["--out", str(pathlib.Path.cwd() / f"sheet-{dom['slug']}.png")]
        argv = files + ["--labels", ",".join(l.replace(",", " ") for l in labels)] + argv
    return subprocess.call(["node", str(TOOLS / "sheet.mjs"), *argv], cwd=os.getcwd())


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
    if cmd == "uninstall":
        return uninstall(rest)
    if cmd == "doctor":
        return doctor(rest)
    if cmd == "mcp":
        return mcp(rest)
    if cmd == "sources":
        return _run_py("sources", rest)
    if cmd == "taste":
        return _run_py("taste", rest)
    if cmd in ("domain", "domains"):
        return _run_py("domains", rest)
    if cmd == "lint":
        return _run_py("slop_lint", rest)
    if cmd == "radar":
        return _run_py("radar", rest)
    if cmd == "history":
        return _run_py("history", rest)
    if cmd == "brand":
        return _run_py("brandpack", rest)
    if cmd in ("contract", "claims", "notes", "looks"):
        return _run_py(cmd, rest)
    if cmd == "eval":
        return _run_py("evals", rest)
    if cmd in ("palette", "fonts", "routes"):
        script = {"palette": "palette.py", "fonts": "inline_fonts.py", "routes": "check_routes.py"}[cmd]
        return subprocess.call([sys.executable, str(TOOLS / script), *rest])
    if cmd == "gate":
        return _run_py("gate", rest)
    if cmd == "review":
        return _run_py("review", rest)
    if cmd == "crop":
        if not _which("node"):
            print("crop needs Node.js 18+ and `npm install` in the design-director repo"); return 2
        return subprocess.call(["node", str(TOOLS / "crop.mjs"), *rest], cwd=os.getcwd())
    if cmd == "teardown":
        return teardown(rest)
    if cmd == "sheet":
        return sheet(rest)
    if cmd == "shots":
        if not _which("node"):
            print("shots needs Node.js 18+"); return 2
        return subprocess.call(["node", str(TOOLS / "shots.mjs"), *rest], cwd=os.getcwd())
    print(f"unknown command {cmd!r}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
