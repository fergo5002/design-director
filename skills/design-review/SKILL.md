---
name: design-review
description: Use before calling any front end, page, deck or visual done, and whenever someone asks "is this good", "does this look AI-generated", "review the design" or "why does this feel off". Runs the slop lint, renders the work at desktop and phone with and without reduced motion, measures overflow, tap targets, fonts, word load and accessibility, then judges the screenshots against a rubric and, for anything important, gets an unanchored second opinion. Logs what it finds to the taste ledger.
---

# Design review

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

A review that could not have failed is a ritual. This one is ordered so the cheapest
check that could catch a disaster runs first, and so nothing is called good on the
strength of a check that cannot see beauty.

## 1. Is it true

Before anything visual: every number, date, comparison and superlative on the page is
checked against its source **by a script or a direct read**, not by memory. EVIDENCE.md
in design-director has the method. A false headline fails the review outright.

## 2. Negative test: the obvious tells

```bash
python tools/ddr.py lint <src dirs>
```

Errors (purple-blue gradient, removed focus ring, blocked zoom, animation with no
reduced-motion path) must be fixed. Warnings need a reason to stay. A clean lint
means the obvious tells are absent, nothing more.

## 3. Render it

```bash
python tools/ddr.py shots <url> [more urls] --full
```

First time only: `npm install && npx playwright install chromium` in this repo.
The report lists horizontal overflow (with the culprit elements), tap targets under
24px, fonts that silently fell back, missing alt text, console errors, h1 count and
serious axe violations, at desktop, phone and 320px, with and without reduced motion.

**Prove the instrument before accusing the object.** If a browser tool hangs or
returns something strange, paste `tools/instrument-check.js` into the page first. A
hidden tab never fires `requestAnimationFrame`, so every frame-based probe hangs and
looks exactly like a frozen page.

## 4. Look at the screenshots

Open every fold screenshot. Then score each line 1 to 5 and write one sentence of
evidence for each score:

| Line | The question |
|---|---|
| Fit | Is this the right treatment for this subject and this audience? |
| Focus | Is there exactly one memorable thing, and does everything else stay quiet? |
| Hierarchy | Can you tell in two seconds what this is and what to do next, on the phone fold? |
| Type | Is the face chosen for this brief, with leading and tracking tuned by size? |
| Colour | Does every colour trace to the subject's world, and is contrast measured? |
| Craft | Spacing rhythm, alignment, states (hover, focus, empty, error, loading), motion that lands on a finished state. |
| Distinctiveness | Name three decisions here a model would not have made by default. Fewer than three scores 2 at most. |
| Truth | Copy and data verified (section 1). |
| Load | Words and screens per page. More than one text-only section in a row reads as a wall. |

Anything under 3 is a defect to fix, not a note. Run CHECKLIST.md from
design-director for the full gate.

## 5. Unanchored second opinion

For anything that ships to real people, get a review that has not seen your
reasoning. Give a fresh agent (or a person) **the screenshots and the brief, not your
conclusion**, and ask it to score the same rubric and name the three weakest things.
Compare. Where it disagrees with you, look again before defending your version.

## 6. Report with limits, and log

Report: what passed, what failed with evidence, what you fixed, and what you did
**not** check (real devices, Safari, slow networks, real data, licences). Then log:

```bash
python tools/ddr.py taste error "<what went wrong in the process>" --why "<cause>" --rung observed --prevention "<rule>"
python tools/ddr.py taste miss "<rejected design move>" --why "<reason>" --tags <axis:value> --rule "<rule you edited>"
python tools/ddr.py taste shipped --what "<thing>" --tags <axis:value,...>
```
