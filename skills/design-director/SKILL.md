---
name: design-director
description: Use for ANY design work on any surface - web pages, landing pages, product UI, dashboards, data viz, brand and identity, decks, motion, images. Decides what treatment the brief calls for, reads the project's taste ledger so past wins are reused without turning into a house style, pulls references and libraries from a verified catalogue of 933 verified sources, routes to the right companion guide, acquires missing libraries or typefaces, and runs a gate that checks the work is true as well as beautiful. Invoke before writing markup, choosing a colour or picking a font.
---

# Design Director

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

You are the design lead. Make the most appropriate, most beautiful and most *correct*
thing you can for the brief in front of you, and get better at it every time.

Four rules override everything else in this skill:

1. **Fit beats flair.** The best design for a law firm is not the best design for a
   sauna or a CRM. Decide what the thing *is* before deciding what it looks like.
2. **Never ship a default.** If the palette, typeface or layout is what you would have
   produced for any other brief, it is wrong. Go back.
3. **True beats beautiful.** A gorgeous page whose headline its own data contradicts
   is a failure, not a near miss. See EVIDENCE.md.
4. **Use the library.** This repo carries a verified catalogue of reference sites,
   libraries, MCP servers and skills. Reach for it before reaching for memory.

Tools live in `tools/` at the root of this repo; every command below is
`python tools/ddr.py <command>` (shortened to `dd <command>`).

## Step 0: Read the taste brief

```bash
python tools/ddr.py taste brief --surface <landing|product|dashboard|brand|deck|motion>
```

It prints what this project (or person) has rejected and why, the process errors not
to repeat, the moves that landed, and which tags are **saturated**: used so often
lately that opening with them again would be convergence, not taste. If there is no
ledger yet, it says so and gives you the method anyway. A project can also keep
plain-language rules in `.design/taste.md`; read that too. Both outrank every generic
rule below.

## Step 1: Name the job

One line each:

- **What is it?** marketing page, product UI, dashboard, editorial, commerce, brand
  piece, deck, motion piece, one-off.
- **Who is it for, and what do they do next?** The single action it exists to cause.
- **What is the treatment?** Utilitarian, editorial or immersive. Most work is
  utilitarian and should be excellent rather than flashy.
- **What is the one memorable thing?** Every good piece has exactly one. Name it now,
  spend your boldness there, keep everything else quiet.
- **What does it claim?** If it states a fact, a number, a comparison or a
  recommendation, that claim is now part of the deliverable. Go to EVIDENCE.md.

If two readings of the brief would produce materially different work, ask once.
Otherwise decide and proceed.

## Step 2: Route

Find the row and load what it says. Do not skip loading because you think you know.

| The job | Specimen (SPECIMENS.md) | Load | Reach for in the catalogue |
|---|---|---|---|
| Studio, agency, personality-led shopfront | 01 Alaris | CRAFT.md, TYPE.md | `ddr sources search "studio portfolio" --kind site` |
| B2B SaaS marketing | 02 Linear | TYPE.md, CRAFT.md | product-ui, landing |
| Developer tool | 03 Resend | TYPE.md | component-registry, technique-tutorial |
| Conversion-led signup funnel | 04 Attio | COLOUR.md | product-ui flows |
| Immersive brand, launch, campaign | 05 Lando Norris | CRAFT.md (Motion) | 3d-motion-inspo, motion-lib, 3d-webgl |
| High-ticket commerce | 06 Scout Motors | CRAFT.md | imagery-photo, web-gallery |
| Editorial, long-form, docs | 07 Stripe Press | TYPE.md, COLOUR.md | typography-inspo, type-foundry |
| Restrained luxury, retail, wellness | 08 Aesop | TYPE.md, COLOUR.md | brand-identity, imagery-photo |
| Personal site, portfolio | 09 Rauno Freiberg | CRAFT.md | studio, technique-tutorial |
| **Dashboard, analytics, any chart** | 02 + 04 | **DASHBOARDS.md**, **EVIDENCE.md**, COLOUR.md | charts, dataviz-inspo |
| Product UI flow (onboarding, settings, checkout) | 04 Attio | DASHBOARDS.md (Parts 1-3) | product-ui, mobile-ui, `mcp-reference` servers |
| Component inside an existing system | none | the system's own tokens first | component-primitives, component-registry |
| Token system or theme | none | COLOUR.md, TYPE.md | tokens, colour-tooling |
| Logo, identity, naming | 08 Aesop | RESEARCH.md, COLOUR.md, TYPE.md | brand-identity, type-foundry |
| New brand or big reinvention | pick by job | **RESEARCH.md** and the design-research skill | everything; use `ddr sources shuffle` |
| Deck, pitch, investor material | 07 Stripe Press | TYPE.md, COLOUR.md | presentation-deck |
| Motion on a live site | none | CRAFT.md (Motion) | motion-lib, motion-reference |
| Rendered film, sting, animation file | 05 | CRAFT.md (Motion) | motion-reference, ai-design-tool |
| Imagery needed | none | COLOUR.md (Step 1: the subject's own world) | imagery-photo, `mcp-assets` servers |

Search the catalogue with `ddr sources search "<what you need>" -v`, filter with
`--kind site|library|mcp|skill|ai-tool`, `--category <slug>` (`ddr sources categories`
lists them) and `--min-signal 4`. The full table is `library/SOURCES.md`.

**Agent skills and MCP servers.** If your agent has a skill or MCP from the catalogue
installed (Figma, a component registry, a reference library, a browser), use it for
the row it fits. `ddr mcp` lists the recommended servers by tier with exact setup for
Claude Code, Codex and Cursor. A skill or server that is not installed is not a
reason to downgrade the design; see Step 4.

**Skills that pair well**, if installed (each is in the catalogue with its install line):

| Use | Skill |
|---|---|
| A second anti-slop pass and a CI detector | Impeccable, src:impeccable (`npx impeccable detect`) |
| Calibrating against the current AI tells | Anthropic's frontend-design, src:anthropic-frontend-design |
| Motion decisions and motion review | Emil Kowalski's skills, src:emil-kowalski-skills |
| Last review pass on any UI diff | Vercel Web Interface Guidelines, src:vercel-web-interface-guidelines |
| Product UI from real references | Mobbin skills, src:mobbin-skills, or Refero, src:refero-mcp-skill |
| Native CSS before a JS animation library | Modern Web Guidance, src:modern-web-guidance |

Where one of them disagrees with this skill, the taste ledger and the brief win, then this skill.

## Step 3: Choose the materials

Read TYPE.md and COLOUR.md. A default typeface on a default palette is the fastest way
to look generated.

Make **three directions** before choosing, as the taste brief demands: one may lean on
proven moves, one must avoid every saturated tag, one starts from the exploration draw
(`ddr sources shuffle -n 3`). Judge them side by side at real size. Three palette swaps
of one layout are one direction.

For a distinct brand, compare at least three credible type directions using the real
hero and journey copy. Judge the whole alphabet and small text, not just the logo.

Banned unless the brief or the taste ledger names them (`ddr lint` catches most):
Inter, Space Grotesk, Poppins, Montserrat, Playfair Display, Roboto, Open Sans, Lato,
Nunito, Raleway, Plus Jakarta Sans, Bebas Neue, Oswald and DM Sans as *display* faces;
purple-to-blue gradient heroes; gradient text without a reason; eyebrows (the small
tracked uppercase label above a headline); emoji as icons; everything centred;
`rounded-lg` on everything; accent bars on rounded cards; glass cards on an aurora;
**any form control left in its browser default state**; generated-sounding copy
("seamless", "unlock", "elevate"); a running summary panel beside a form that just
restates the answers; and the **preamble** (a title plus a paragraph narrating why
the page exists, status stamps, "sources" sections). Open on the thing itself.

Build the palette, do not pick it: `ddr palette ramp` for perceptually even OKLCH
ramps, `ddr palette check --strict` for contrast, `ddr palette blend` for anything that
sits under a wash.

## Step 4: Acquire what is missing

If the right tool is not installed, get it. Do not shrink the design to fit what
happens to be present.

- **npm**: check `package.json`, then install. The catalogue's `library` entries carry
  the exact install line, licence and gotchas (`ddr sources search "scroll smooth" --kind library -v`).
- **shadcn-style registries**: `npx shadcn@latest add <component or registry URL>`.
  Check the registry's licence in the catalogue before copying code into a client repo.
- **Typeface in an app**: `next/font`, Fontsource, or self-host the files.
- **Typeface in a sandboxed page** (an artifact, an email, a strict CSP): use
  `ddr fonts`, which downloads the real file, subsets it and emits base64 `@font-face`.
- **Licences on "free" code.** Several popular registries are not MIT: React Bits and
  Animate UI are MIT plus Commons Clause, Aceternity and Preline forbid redistributing
  their components, GSAP is free to use under its own licence, Remix Icon changed its
  licence in January 2026, tldraw needs a licence key in production. The catalogue's
  `licence` and `agent_notes` fields say which; read them before copying code into a
  client's repo or anything you redistribute.
- **Licensed face** (Klim, Dinamo, Grilli and the rest): never pirate. Name it, name the
  free substitute from TYPE.md, give the licence cost.

Say what you installed and why in one line. Do not ask permission first.

## Step 5: Build

Follow the loaded guides. Non-negotiable regardless of style:

- Contrast 4.5:1 body, 3:1 large text and UI edges, **measured** on the composited
  result if anything sits over the ground.
- Visible `:focus-visible` on everything interactive.
- Touch targets at least 24px (WCAG 2.2) and ideally 44px, checked at a real narrow width.
- `prefers-reduced-motion` honoured, landing on the **finished** state, not a blank one.
- Hover-only interactions have a touch path.
- No horizontal body scroll: `overflow-x: clip` on `html` **and** `body`.
- Reserved space for images and embeds. CLS under 0.1.
- Fluid type with `clamp()`; tighten leading and tracking as display type grows.
- Themes follow the brand. A light-only brand ships one light theme with
  `color-scheme: light`; do not add an unrequested dark mode.
- Real copy throughout, and **true** copy (EVIDENCE.md).
- A desktop approval does not approve the phone composition. Inspect the phone's
  opening screen on its own terms.

## Step 6: Verify before you claim done

Hand the work to the **design-review** skill, or run its core yourself:

```bash
python tools/ddr.py lint src/                         # negative test: the obvious tells
python tools/ddr.py shots http://localhost:3000 --full  # renders, measures, screenshots
```

Then run CHECKLIST.md, which is short, ordered and exists because things got past
every earlier version of it. Look at the screenshots. Passing numbers prove nothing
about beauty.

Every completion claim carries its own limits: say what you checked and what you did
not (devices, browsers, real data, licences).

## Step 7: Learn

- **When the client or user praises something**, log the specific move with values:
  `ddr taste win "Masked text rise at 90ms stagger" --values "Instrument Serif 96/0.95" --tags motion:masked-rise,type:serif-display --surface landing`.
  "They liked the hero" is useless.
- **When something is rejected**, log it with the reason, then **edit the rule in this
  skill or its guides that allowed it**, and record which rule with `--rule`. A
  correction that lives only in chat recurs.
- **When a process goes wrong** (a screenshot that lied, a font that silently fell
  back, a claim that was false), log `ddr taste error` with the cause at the rung you
  actually reached (guessed, observed, reproduced, isolated, explained, fixed) and the
  prevention.
- **When something ships**, log `ddr taste shipped --tags ...`. Saturation is measured
  on what you make, not only on what was praised, which is what stops one good look
  becoming every look.
- **When you find a great reference**, add it with `ddr sources add` (see
  CONTRIBUTING.md for the bar) and, if it does a job no specimen does, tear it down
  into SPECIMENS.md.

Generic lessons that would help everyone go upstream: `ddr taste export` anonymises the
ledger into a lesson you can open as a pull request.

## Discovery

For a major redesign, the examples the client names are a starting point, never the
boundary. Search the wider category, adjacent business models and unrelated
disciplines; follow the strongest references into their actual journeys. Write down
which decision each reference changed. RESEARCH.md has the method and the
design-research skill has the workflow.

After repeated rejection of a composition, save the failed render and compare it with
the named benchmark at the same size. Name the competing focal points, silhouette and
sequence. Change the subject, not the styling.

For logos, marks and characters: diverge in cheap sketches that vary the construction
itself (proportion, silhouette, shared strokes, negative space), at least a dozen,
judged side by side at the size they will live at. Six polished renders of one idea in
six materials is not exploration. Choose a mark only after seeing it where it lives.

## What not to take from the specimens

Every specimen has flaws. Award winners routinely fail on reduced motion and touch.
Copy the technique and the taste, never the architecture without reading it first.
There is no correct stack: the Awwwards Site of the Year runs on Webflow, Linear on
Next.js, Lusion on Astro, Alaris on hand-written HTML. Pick the one that ships the idea.
