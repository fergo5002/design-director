---
name: design-taste
description: Use whenever someone reacts to a design - praise ("love this", "that's it"), rejection ("this is shit", "too AI", "no"), or a correction to a design rule - and whenever a design ships or a design process goes wrong (a screenshot that lied, a font that fell back, a false claim on a page). Records the specific move, reason and tags to the taste ledger so wins get reused without becoming a house style, and rejections change the rule that allowed them.
---

# Design taste

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

Taste is the record of what actually landed and what did not, kept specifically
enough to act on and balanced so it never collapses into one look.

## Log the moment it happens

```bash
# praise: the specific move with values, never "they liked the hero"
python tools/ddr.py taste win "Masked text rise, 90ms stagger, over warm paper" \
  --values "Instrument Serif 96/0.95 -0.02em, #f6f5e8, 600ms ease-out" \
  --tags motion:masked-rise,type:serif-display,colour:warm-paper --surface landing

# rejection: the reason is required; then edit the rule that allowed it
python tools/ddr.py taste miss "Identical KPI cards across the top" \
  --why "nothing leads; reads as generated" --tags layout:card-grid,density:uniform \
  --surface dashboard --rule "DASHBOARDS.md Part 2: one primary metric leads"

# what shipped (this is what keeps the saturation measure honest)
python tools/ddr.py taste shipped --what "Pricing page v2" --tags type:grotesk,colour:mono,layout:asymmetric

# a process error, with the cause at the rung you actually reached
python tools/ddr.py taste error "Screenshot timed out, page blamed" --why "hidden tab, rAF never fires" \
  --rung isolated --prevention "run tools/instrument-check.js before any browser diagnosis"
```

Ledger location: `.design/taste.jsonl` in the project by default, `--global` for a
personal ledger at `~/.design-director/taste.jsonl`, or `$DD_TASTE`. Commit the project
ledger: it is the project's design memory.

## Tags

`axis:value`, lower case. Axes: type, colour, layout, motion, imagery, density, mood,
material, interaction, copy, surface, brand, data, sound. Reuse values you have used
before (`ddr taste saturation` lists the live ones) so counts mean something. Two to
five tags per event.

## Why wins do not take over

Every win and every shipped piece adds weight to its tags, and that weight halves
every 120 days. Any tag holding more than 30% of recent weight is **saturated**.
`ddr taste brief` then asks for three directions: one may use proven moves, one must
avoid every saturated tag, and one starts from a random cross-discipline draw from the
catalogue. Praise makes a move available, not mandatory.

## When a rejection arrives

1. Log the miss with the reason in the person's own words where possible.
2. Find the rule in design-director (or its guides) that allowed it, and change it.
   If no rule covered it, add one where it will be read at the right moment.
3. Re-log with `--rule` naming the edit. A miss with no rule is a warning that it
   will come back.
4. If the same miss appears twice, a note is not enough: add a check (a lint rule, a
   test, a line in CHECKLIST.md).

## Sharing lessons upstream

`ddr taste export` writes an anonymised summary (projects removed). Lessons that would
help anyone, not just one client's taste, are welcome as pull requests to
`lessons/` in this repo. See CONTRIBUTING.md.
