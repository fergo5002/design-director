# design-director

A design workflow for coding agents. Install it into Claude Code, Codex, Cursor or
Gemini CLI and your agent stops designing like a model: it names the job before it
picks a colour, pulls real references from a verified catalogue, makes three genuinely
different directions, checks its own work in a real browser, and remembers what you
liked and hated without turning one good look into every look.

It is four skills, a set of guides distilled from a lot of rejected work, a catalogue
of 933 verified design sources, and a small command-line toolkit (`ddr`).

## Install

You need git and Python 3.9+. Node 18+ is needed only for screenshots.

```bash
git clone https://github.com/fergo5002/design-director ~/design-director
cd ~/design-director
python3 tools/ddr.py install                 # Claude Code, Codex and ~/.agents
npm install && npx playwright install chromium   # optional: the screenshot gauntlet
ddr doctor
```

`install` symlinks the skills into `~/.claude/skills`, `~/.codex/skills` and
`~/.agents/skills`, and puts a `ddr` command in `~/.local/bin`. It never overwrites a
skill or command you already have; use `--prefix` if a name clashes. Symlinks mean
`git pull` updates everything (where symlinks are unavailable it copies, and running
`install` again refreshes the copies).

Cursor and Gemini CLI read per-project files, so run this in each project you use them in:

```bash
ddr install --agent cursor,gemini --project ~/code/my-app
```

**Claude Code plugin**, if you prefer:

```
/plugin marketplace add fergo5002/design-director
/plugin install design-director@design-director
```

(The plugin gives you the skills. Clone the repo too if you want the `ddr` tools.)

Then, in any project:

```bash
ddr init        # creates .design/ with your house taste, a reference ledger and lint config
```

## What you get

**Skills** (in `skills/`, read by your agent automatically once installed)

| Skill | What it does |
|---|---|
| `design-director` | The lead. Names the job, the one memorable thing and what the page claims, routes to the right guide and specimen, bans the generated defaults, acquires missing libraries and fonts, sets the gate. |
| `design-research` | Turns "find inspiration" into a reference ledger where every row names the decision it changed. |
| `design-review` | Lint, render, measure, look, score, and get an unanchored second opinion before anything is called done. |
| `design-taste` | Logs praise, rejections, what shipped and process errors, so the next piece starts from them. |

**Guides** (in `skills/design-director/`): `TYPE.md`, `COLOUR.md`, `CRAFT.md`
(spacing, motion, interaction), `DASHBOARDS.md`, `EVIDENCE.md` (making sure the page
tells the truth), `SPECIMENS.md` (nine torn-down reference sites and the technique
each one is the best example of), `RESEARCH.md`, and `CHECKLIST.md`, the gate.

**The catalogue** (`library/`, browsable as [`library/SOURCES.md`](library/SOURCES.md)):
reference galleries, product-UI libraries like Mobbin and Refero, award sites, type
foundries, free fonts, colour, imagery, studios, critique, newsletters, component
registries, motion, 3D and chart libraries, testing tools, MCP servers, agent skills
and AI design tools. Every entry records cost, how an agent can get at it (MCP, API,
RSS, or "browse only, no scraping"), a 1 to 5 signal score, what to take, what to
avoid, and how it was verified.

**The toolkit** (`ddr`, standard-library Python):

| Command | What it does |
|---|---|
| `ddr taste brief` | What was rejected, what landed, what is **saturated**, and three directions to make. |
| `ddr taste win/miss/shipped/error` | Log outcomes as they happen. |
| `ddr sources search "<need>" -v` | Search the catalogue. `--kind mcp`, `--category product-ui`, `--min-signal 4`. |
| `ddr sources shuffle -n 3` | A random high-signal draw across disciplines, for a direction that is not your default. |
| `ddr lint src/` | Catches default fonts, purple-blue gradients, eyebrows, emoji icons, generated copy, removed focus rings, blocked zoom, default form controls, motion without a reduced-motion path. |
| `ddr shots <url> --full` | Playwright at desktop, phone and 320px, with and without reduced motion: screenshots, sideways scroll with culprits, small tap targets, fonts that fell back, axe violations, word load. |
| `ddr palette ramp/check/blend` | Perceptually even OKLCH ramps and measured contrast, including over tints. |
| `ddr fonts` | Download, subset and inline a webfont for sandboxed pages. |
| `ddr mcp` | Recommended MCP servers by tier, with setup for Claude Code, Codex and Cursor. |
| `ddr radar` | What changed in the tools you depend on, dead links, and new design MCPs and skills to look at. |

## Taste without a house style

Most "learn my taste" setups converge: whatever got praised once gets made forever.
The ledger counts what you praise **and what you ship**, lets old weight decay (half
every 120 days), and flags any tag holding more than 30% of recent work as saturated.
The brief then asks for three directions: one may reuse proven moves, one must avoid
every saturated tag, and one starts from a random draw from the catalogue. Praise makes
a move available. It never makes it mandatory.

Rejections need a reason, and the skill asks for the rule that allowed the mistake to
be edited. Process errors are logged with how far the diagnosis actually got
(guessed, observed, reproduced, isolated, explained, fixed), so a guess is never
written up as a cause.

## Connectors and MCP servers

`ddr mcp` prints the recommended set. In short:

- **Core** (free, worth having on every machine): Playwright MCP, Chrome DevTools MCP, Context7, shadcn MCP and registries
- **Recommended** (free or freemium, big gains for most work): Figma MCP, 21st.dev Magic MCP, Firecrawl MCP, Storybook MCP addon, Excalidraw MCP App
- **Optional** (paid or specialist): Mobbin MCP, Refero MCP and refero-design skill, Framer MCP, Webflow MCP, Penpot MCP, Paper MCP, Canva MCP, Adobe for creativity, fal MCP, Recraft MCP, Untitled UI MCP, Argos MCP, MCP for Blender

Each one is in the catalogue with cost, auth, maintenance state and security notes.
`ddr mcp --tier core --agent claude --apply` adds the core set to Claude Code; for
Codex and Cursor it prints the config blocks to paste.

## Staying current

A GitHub Action runs `ddr radar` every Monday and opens an issue: releases and feed
changes in the libraries and sites the catalogue watches, dead links, entries not
re-verified in six months, and new design-related MCP servers and skills from GitHub
and the official MCP registry. Leads are never added automatically; someone verifies
each one and adds it with `ddr sources add`. Run `ddr radar` locally any time.

## Contributing

Sources, lessons, rules and tools are all welcome. The bar is in
[CONTRIBUTING.md](CONTRIBUTING.md): you visited it, the signal is honest, the take is
specific. Every change goes through a reviewed pull request.

## Licence

MIT for everything in this repo. Sources in the catalogue are links, each under its
own terms; the catalogue records licences for code, fonts and assets, and marks sites
whose terms forbid scraping.
