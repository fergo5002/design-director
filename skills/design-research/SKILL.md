---
name: design-research
description: Use when a design needs references before it needs pixels - a new brand, a redesign, a product flow you have not built before (onboarding, checkout, settings, pricing), a dashboard, a type or colour decision, or whenever the work so far looks generic. Finds real shipped examples through a verified catalogue of galleries, product-UI libraries, foundries and studios, follows them into their actual journeys, and records which decision each reference changed in a project ledger.
---

# Design research

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

Research that does not change a decision is browsing. The output of this skill is a
short **reference ledger** in the project (`.design/references.md`) where every row
names the decision it changed, plus the material to make three genuinely different
directions. RESEARCH.md in the design-director skill has the deeper method for brands.

## 1. Frame the question

Write one line: *what decision am I trying to make?* "How do good B2B tools handle an
empty dashboard on day one" is a research question. "Find nice dashboards" is not.

## 2. Pull candidate sources from the catalogue

```bash
python tools/ddr.py sources search "empty state onboarding saas" -n 12 -v
python tools/ddr.py sources search "" --category product-ui --min-signal 4
python tools/ddr.py sources search "" --category typography-inspo
python tools/ddr.py sources shuffle -n 4          # deliberate cross-discipline draw
```

Use at least three kinds of source for anything substantial:

- **Shipped product evidence** (`product-ui`, `mobile-ui`): real screens and whole
  flows from live apps. This is where patterns are proven, not invented.
- **Craft and taste** (`web-gallery`, `award`, `studio`, `typography-inspo`): what the
  best people are doing now. Prefer year and month awards over daily picks.
- **Outside the category** (`brand-identity`, `imagery-photo`, `3d-motion-inspo`,
  `editorial-critique`, and anything the shuffle throws up): where non-generic ideas
  come from.

Check each source's `agent_access` before you start. `mcp` means a server can search
it for you (`ddr mcp` shows setup), `rss` or `api` means you can read it directly,
`scrape-no` means the site's terms forbid automated collection: browse it as a person
would, or ask the user for screenshots. Never scrape a site that forbids it, and never
copy a paywalled library's screens into a public repo.

## 3. Go past the thumbnail

A gallery thumbnail is a lead, not evidence. For every reference that might matter:

- Visit the live work at desktop **and** phone width. A loading screen is not the design.
- Walk the actual journey: sign up, empty state, first success, error, settings.
- Read the designer's or studio's own write-up if there is one.
- Note what is observed versus what you are inferring about how it was built.

## 4. Record decisions, not links

`.design/references.md`, one row per reference that earned its place:

| Reference (URL) | Seen how (visited, flow walked, source read) | Technique, specifically | Decision it changes here | What to leave behind | Licence / asset status |
|---|---|---|---|---|---|

A list of links with no decisions column filled in is not research. Five rows that
each changed something beat fifty that did not.

## 5. Combine, then make

Pull separate ingredients from unrelated references (a composition from one, a
letterform from another, a material or motion from a third) and hold them together
with one idea that belongs to *this* brief. Then return to design-director Step 3 and
make three directions. If they still look generic, come back here and look for
references that **contradict** your favourite direction.

## Rules

- Borrow techniques and principles, never a recognisable logo, photograph, paid font
  or proprietary illustration.
- Record failed access (paywall, bot wall, dead link). If a catalogue entry is dead or
  wrong, fix it with `ddr sources add` or note it for the weekly radar.
- When you find something better than what the catalogue has, add it
  (`ddr sources add --id ... --evidence visited`), so the next person starts ahead.
- Research depth is measured by changed decisions, not by link count.
