# design-director

A design workflow for coding agents. Install it into Claude Code, Codex, Cursor or
Gemini CLI and your agent stops designing like a model.

Agents design well in areas they have studied and badly everywhere else, and they
cannot tell the difference. design-director makes the difference visible. Every brief
is matched to a **design domain** (a sector like fintech or independent stays, plus a
pattern like onboarding or booking) with a confidence score built from evidence: what
the agent has actually looked at, whether it has named the category's slop, what it
has shipped and how that was judged. When the score is too low for the job, the agent
goes and researches the category itself, writes down what it learnt, and only then
designs. It keeps its own library of exemplars and counter-examples, retires the ones
that date, and gets better in every area it works in.

Around that: four skills, guides distilled from a lot of rejected work, a catalogue of
933 verified design sources, and a small command-line toolkit (`ddr`).

## Install

You need git and Python 3.9+. Node 18+ is needed only for screenshots.

```bash
git clone https://github.com/fergo5002/design-director ~/design-director
cd ~/design-director
python3 tools/ddr.py install                 # Claude Code, Codex and ~/.agents
npm install && npx playwright install chromium   # optional: the screenshot gauntlet
ddr doctor
```

`install` does four things, and `ddr uninstall` undoes exactly those four:

1. Symlinks the skills into `~/.claude/skills`, `~/.codex/skills` and `~/.agents/skills`.
   It never overwrites a skill you already have; use `--prefix` if a name clashes.
   Symlinks mean `git pull` updates everything (where symlinks are unavailable it
   copies, and running `install` again refreshes the copies).
2. Adds a short, fenced routing block to `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`
   telling the agent to load design-director for design work. Skills on their own
   trigger unreliably, and this is the difference between the skill being installed
   and being used. Skip it with `--no-routing`.
3. Puts a `ddr` command in `~/.local/bin`.
4. Creates `~/.design-director/domains`, where the agent's expertise accumulates
   (set `DDR_HOME` to keep it somewhere else, a synced folder for instance).

`ddr doctor` then checks all of it, and lists anything that competes: other design
skills, and lines in your own instruction files that set design defaults ("always use
Inter", a fixed palette for everything). Those are the usual reason an agent ignores a
design skill. Keep the specific ones; delete the generic ones.

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

## Expertise by domain

```bash
ddr domain match "a booking site for self-catering cottages near Dublin"
#  Sector   independent-stays   confidence  76/100 strong   (matched: self catering, cottage)
#  Pattern  onboarding ...
ddr domain brief independent-stays     # dossier, best exemplars and their takes, counter-examples, ledger
ddr domain status independent-stays    # the score, every part of it, and what would raise it
```

A domain is a folder: a dossier (who it is for, what the best do, the conventions to
keep and to break, the category's slop, its visual language), a reference library
where every entry records how it was seen and when, and a ledger of what shipped and
how it was judged. Confidence comes from that evidence and decays with a one-year
half-life, so stale expertise stops counting. A search result counts for a quarter of
a visit; a screenshot the agent actually looked at counts for more; a walked flow most.
Until three real references have been looked at the score cannot pass 25, and until
the category's slop is written down it cannot pass 60.

The agent creates domains as briefs need them, relates the ones that inform each other,
merges two that turn out to be one, and retires references that have dated (they stay
in a graveyard so they are never quietly re-added). `ddr domain audit --online` finds
stale, weak, dead, moved and contradictory entries and overlapping domains.

The repo ships starter domains in `domains/`, researched with the same loop. Writing to
one gives you your own layer on top of it: your references, retirements, notes and ledger
live in your home, and the starter's research is read live underneath, so `git pull`
keeps improving it without ever overwriting your judgement. `ddr domain resolve` closes a
rejection once it has produced a rule, and `ddr domain edit` changes a domain's keywords.

## What you get

**Skills** (in `skills/`, read by your agent automatically once installed)

| Skill | What it does |
|---|---|
| `design-director` | The lead. Checks its confidence in the domain, names the job, the one memorable thing and what the page claims, routes to the right guide and specimen, bans the generated defaults, acquires missing libraries and fonts, sets the gate, and writes what it learnt back to the domain. |
| `design-research` | The expertise loop: maps the best work in a category, looks at it properly, tears it down, hunts the category's slop, writes the dossier, retires what has dated, and re-scores until the agent has earned the right to design. |
| `design-review` | Lint, render, measure, look, score, and get an unanchored second opinion before anything is called done. |
| `design-taste` | Logs praise, rejections, what shipped and process errors, so the next piece starts from them. |

**Guides** (in `skills/design-director/`): `SLOP.md` (five tests that separate generated
slop from a real design language), `TYPE.md`, `COLOUR.md`, `CRAFT.md`
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
| `ddr domain match "<brief>"` | Which domains a brief falls in and how much the agent knows about each. |
| `ddr domain brief/status/plan` | The dossier and best references; the score and its gaps; what the stakes need. |
| `ddr domain new/edit/ref/relate/merge/resolve/audit` | Build, curate and share the expertise. |
| `ddr taste brief` | What was rejected, what landed, what is **saturated**, and three directions to make. |
| `ddr taste win/miss/shipped/error` | Log outcomes as they happen; `--domain <slug>` also feeds that domain's experience. |
| `ddr sources search "<need>" -v` | Search the catalogue. `--kind mcp`, `--category product-ui`, `--min-signal 4`. |
| `ddr sources shuffle -n 3` | A random high-signal draw across disciplines, for a direction that is not your default. |
| `ddr lint src/` | Catches default fonts, purple-blue gradients, eyebrows, emoji icons, generated copy, removed focus rings, blocked zoom, default form controls, motion without a reduced-motion path. |
| `ddr shots <url> --full` | Playwright at desktop, phone and 320px, with and without reduced motion: screenshots, sideways scroll with culprits, small tap targets, fonts that fell back, axe violations, word load. |
| `ddr teardown <url> --into <domain>` | Look at a reference like a designer and measure what a designer would guess: folds, full page, scroll frames, faces and sizes by text set, palette by painted area, radii, spacing, motion, stack, calls to action, slop tells. `--walk "Book now>Dates"` clicks through a journey and never submits. |
| `ddr sheet --domain <slug> --with yours.png` | Your work beside the category's best exemplars, same width, one image. |
| `ddr history <url>` | Wayback captures by year, to see how old a look really is and how a reference changed. |
| `ddr palette ramp/check/blend` | Perceptually even OKLCH ramps and measured contrast, including over tints. |
| `ddr fonts` | Download, subset and inline a webfont for sandboxed pages. |
| `ddr mcp` | Recommended MCP servers by tier, with setup for Claude Code, Codex and Cursor. |
| `ddr radar` | What changed in the tools you depend on, dead links, and new design MCPs and skills to look at. |
| `ddr doctor` / `ddr uninstall` | Check the install and what competes with it; remove exactly what install added. |

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

- **Research** (`ddr mcp --research`): Exa for search by description, Brave Search for local businesses and images, Tavily, Firecrawl's branding extraction, Mobbin and Refero for real product screens, and Playwright or Chrome DevTools for looking
- **Core** (free, worth having on every machine): Playwright MCP, Chrome DevTools MCP, Context7, shadcn MCP and registries
- **Recommended** (free or freemium, big gains for most work): Exa MCP, Figma MCP, 21st.dev Magic MCP, Firecrawl MCP, Storybook MCP addon, Excalidraw MCP App
- **Optional** (paid or specialist): Mobbin MCP, Refero MCP and refero-design skill, Framer MCP, Webflow MCP, Penpot MCP, Paper MCP, Canva MCP, Adobe for creativity, fal MCP, Recraft MCP, Untitled UI MCP, Argos MCP, MCP for Blender, Brave Search MCP, Tavily MCP

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
