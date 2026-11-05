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
personal ledger at `$DDR_HOME/taste.jsonl` (default `~/.design-director`), or `$DD_TASTE`.
Commit the project ledger: it is the project's design memory.

Add `--domain <slug>` to any event and it also lands in that design domain's ledger,
where shipped work, wins and rules learnt from misses raise the domain's confidence
and unresolved misses lower it (`ddr domain status <slug>`).

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

## Notes: what a job showed, for the next job

The taste ledger records verdicts. Notes record observations: what happened in a job,
with where it shows, kept per domain, per brand or for `house`, so the next job in the
same place can weigh them. `ddr domain brief <slug>` and `ddr brand show <slug>` end with
the notes for that scope.

**When to add one.** At the end of a job, write at most five, and only things that could
change what the next job does. Each one says what happened and where it shows, never a
rule:

```bash
python tools/ddr.py notes add fintech "The client asked for more air around the rate table twice" \
  --evidence "round 1: 'it is cramped'" --evidence "round 2: phone fold shot, 390px" --job ~/Dev/rates
```

"Always use 24px gaps" is a rule, so it does not belong here; "asked for more air twice,
on the phone fold" is an observation. When an earlier note says the same thing, repeat its
words: a near-duplicate merges into it and counts as a second sighting. A helper can do
this from a summary: `ddr notes brief <scope> --summary "..."` prints the post-job prompt,
and `ddr notes ingest <scope> --job <label>` reads the JSON it writes back.

**Vote on the notes a job used.** If a note shaped a decision and it held up, vote it
helpful; if following it made the work worse, vote it harmful, with the reason:

```bash
python tools/ddr.py notes vote fintech o-1a2b3c --helpful --why "kept the table airy; the client approved it"
python tools/ddr.py notes vote fintech o-4d5e6f --harmful --why "the client wanted it dense this time"
python tools/ddr.py notes prune fintech     # harmful leading by two is marked pruned, never deleted
```

**Weighed, not obeyed.** Notes are untrusted: they come from past jobs, they can be
wrong, and they are lexical, so two notes that differ in one deciding word can merge.
The person's explicit ask, a supplied reference and the brand pack all outrank them. A note
starts `proposed`; it is `kept` once seen again, voted helpful, or when it is the person's
own words (`ddr looks pick` records the reason given for a pick as one).

**Promotion.** A kept note scoring at least 3 (helpful minus harmful) that two or more
jobs saw, or that came from the person, is a candidate. `ddr notes promote` lists the
candidates; `--apply` appends each under `## Proposed guidance` in the domain's
`dossier.md` (or the brand's `graphic-language.md`) with its id and counts, and marks it
promoted. Proposed guidance is printed in the brief but never scores confidence: a person
folds it into the dossier proper, or deletes it.

## Sharing lessons upstream

`ddr taste export` writes an anonymised summary (projects removed). Lessons that would
help anyone, not just one client's taste, are welcome as pull requests to
`lessons/` in this repo. See CONTRIBUTING.md.
