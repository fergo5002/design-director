---
name: design-review
description: Use before calling any front end, page, deck or visual done, and whenever someone asks "is this good", "does this look AI-generated", "review the design" or "why does this feel off". Runs the gate in code (contract, claims, slop and brand lint, renders at the real viewports, copy fidelity, reading load), then scores fresh screenshots against nine anchored areas, writes ranked notes, records the review with a verdict computed by rule, and for anything important gets an unanchored second opinion. Logs what it finds to the taste ledger.
---

# Design review

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

A review that could not have failed is a ritual. The order below is fixed so the cheapest
check that could catch a disaster runs first, and nothing is called good on the strength of
a check that cannot see beauty. The rubric is a reading aid for judgement, not a scorecard
to optimise: a piece that hits every anchor and still reads like generic marketing scores
low on idea.

## 1. Three gates before any score

1. **Accuracy.** Every number, date, name, comparison and superlative traces to a source in
   the claims ledger (`.design/brief/claims.json`), checked by a script or a direct read,
   never from memory. EVIDENCE.md in design-director has the method. An invented feature
   or figure fails the piece outright, however well it is made.
2. **Deterministic gates.** Run them, all of them, in code:

   ```bash
   python tools/ddr.py gate run --src <src dirs> --file <page.html>   # or --url <url>
   python tools/ddr.py gate run --src <src> --url <url> --copy copy.txt --brand <slug>
   ```

   Seven steps in a fixed order: contract, claims, lint, brand, render, fidelity, load.
   Exit 1 is a finding to fix. **Exit 2 means a step did not run, which is never a pass.**
   For a non-web artefact (a PDF, a print file) say why: `--no-render --why "<reason>"`.
   The receipt hashes every input, so `ddr gate verify` knows when the work changed after
   it was checked.
3. **The ask.** When someone asked for a specific change, that change is the bar. Check it
   first, against the contract (`.design/brief/contract.json`), before judging anything else.

**Prove the instrument before accusing the object.** If a browser tool hangs or returns
something strange, paste `tools/instrument-check.js` into the page first. A hidden tab never
fires `requestAnimationFrame`, so every frame-based probe hangs and looks exactly like a
frozen page.

## 2. Regenerate the evidence

Never score from the maker's own sheet or from memory. Score from the shots of this gate
run (`.design/gate/<run_id>/shots/`). Open at least the phone fold and a desktop or mac
fold; `ddr review record` refuses a review that does not list both. Then make your own views:

```bash
python tools/ddr.py sheet --images <yours.png> <exemplar.png> --labels "Yours,Best" --cols 2 --out sheet.png
python tools/ddr.py crop <before.png> <after.png> --box L,T,W,H --scale 2 --out pair.png
```

Put the work beside the two best exemplars in the domain (`ddr domain brief <slug>` lists
them) at the same size. Zoom into type and fine geometry with a crop. For an edit, crop the
same region before and after. If the work is plainly weaker than the category's best, say
so, whatever the scores say.

## 3. Score the nine areas

Score each 1 to 5; 4 and 2 sit between the anchors. Cite the shot, the crop, the size or
the number behind every score.

| Area | 5 | 3 | 1 |
|---|---|---|---|
| **Idea** | One sentence a stranger could repeat; a real thing shown or bold type carrying it; survives the kill test | A real message, but the visual idea is generic or arrives as decoration | No message; shapes, glows or a stock field standing in for a concept |
| **Hierarchy** | One focal element read first on the phone fold, at most two demands, the rest stepped down hard | Readable, but two elements compete or the support is too loud | Flat: everything at one weight, or labels where the headline should be |
| **Copy** | Fewest words; each fact once; supplied copy exact (fidelity step clean); voice and casing from the brand | An unrequested sub-line, caption or eyebrow; a word too many | Invented copy, banned hype, or supplied copy changed |
| **Craft** | Type sized for the view it ships at, optical spacing, every state designed (hover, focus, empty, error, loading), motion lands on a finished state | Correct but stock: default spacing, tight padding, one awkward wrap | Clipped or garbled text, broken alignment, a missing focus state |
| **Brand** | Tokens only, one accent with meaning, the real logo at its size and clear space (brand step clean) | A slip: a second accent, a radius past the cap, the logo too small | An invented colour, a redrawn logo, off-brand faces |
| **Fit** | The right treatment for this subject and audience; each viewport recomposed, legible at the smallest | One size scaled rather than recomposed, or small text lost on a phone | Wrong treatment for the audience, or text under platform chrome |
| **Truth** | Every claim in the claims ledger verified (claims step clean); nothing on the page the ledger does not hold | A claim verified by memory rather than a read, or vaguer than its source | A false or unsourced headline claim |
| **Distinctiveness** | Three named decisions a model would not make by default, and all five tests in SLOP.md pass | One or two such decisions; one SLOP.md test fails | None you can name, or two SLOP.md tests fail |
| **Load** | Words and screens fit the job (load step: words in main, screens per viewport, no run of text-only sections, smallest text 14px or more) | Long for its job, or two text-only sections in a row | A wall: hundreds of words of prose, text under 12px on a phone |

Fewer than three named decisions caps distinctiveness at 2. Write the three decisions into
its evidence.

## 4. Notes and strengths

At most 12 notes, ranked by impact. Each has:

- **where**: the shot and region (`phone fold, hero`), or the file and line
- **what** is wrong, **why** it matters to the person looking, and the concrete **fix**
- **severity**: MUST-FIX or NICE-TO-HAVE

Then name the **strengths to protect**, so the next pass does not break what works.

## 5. The verdict follows a rule

- **rework** if idea scores 2 or less, or any area scores 1
- **ship** if every area scores 4 or more and no note is MUST-FIX
- **fix-then-ship** otherwise

The rule lives in code. A review whose verdict does not match it is refused.

## 6. Record it

Write the review as JSON and record it against the gate run:

```bash
python tools/ddr.py review record --run latest --json review.json
python tools/ddr.py review show
```

```json
{"reviewer": "self", "scores": {"idea": [4, "evidence"], "hierarchy": [4, "..."], "copy": [5, "..."],
  "craft": [4, "..."], "brand": [5, "..."], "fit": [4, "..."], "truth": [5, "..."],
  "distinctiveness": [4, "three decisions: ..."], "load": [4, "..."]},
 "notes": [{"where": "phone fold, hero", "what": "...", "why": "...", "fix": "...", "severity": "nice-to-have"}],
 "strengths": ["..."], "viewed": [".design/gate/<run_id>/shots/<file>.png"],
 "compared_with": ["<exemplar shot at the same size>"], "verdict": "ship"}
```

`reviewer` is `self` or `independent`. `ddr gate verify --require-review` passes only when
the receipt is current and the recorded verdict is ship. Changing any input after the review
makes the receipt stale: run the gate and review again. When the gate genuinely cannot apply,
`ddr gate waive --reason "<why>"` records that openly and logs it as an error in the taste
ledger. It is never silent.

## 7. Failure patterns

| Pattern | What it looks like | Fix |
|---|---|---|
| Wallpaper | A headline over a field of nodes, dots or glows | Find the real thing to show, or let bold type carry it |
| Over-full frame | Three or more things to read separately on one screen | Split it, or cut the weakest |
| Flat hierarchy | Headline, labels and support at similar sizes | One element big and at full contrast; the rest step down hard |
| Extra words | A sub-line, caption, URL or eyebrow nobody asked for | Delete it; put the explanation in the reply |
| Scaled, not recomposed | The phone layout is the desktop one shrunk | Recompose each size; spend the extra height on content |
| Template sameness | Every section one layout recoloured | Vary the spatial idea; keep the system |
| Lost on a phone | Proof text at 11px on a 390px screen | Fewer words, larger type |
| Unofficial logo | A typeset stand-in or recoloured mark | The real file from the brand pack, at its minimum size or larger |
| Generic software look | Mono on prose, tracked uppercase labels, everything centred, floating columns, glows | Same content: mono only for literal values, labels in the text face, one alignment, real containers, no effects |
| Faked weight | A light face stroked or outlined to look heavier | A real weight of the face, or more size |
| Silent fallback | The chosen face never painted, so it ships in the system font | Fix the font load until the render step's font check is clean |
| Self-review | "It's fine" from the maker | An independent look with fresh evidence (section 8) |

## 8. Unanchored second opinion

For anything that ships to real people, get a review that has not seen your reasoning.
Give a fresh agent (or a person) **the screenshots and the brief, not your conclusion**,
and ask it to score the same nine areas and name the three weakest things. Record it with
`"reviewer": "independent"`. Compare. Where it disagrees with you, look again before
defending your version.

## 9. Report with limits, and log

Report: the gate verdict and receipt, the review verdict, what failed with evidence, what
you fixed, and what you did **not** check (real devices, Safari, slow networks, real data,
licences). Then log:

```bash
python tools/ddr.py taste error "<what went wrong in the process>" --why "<cause>" --rung observed --prevention "<rule>"
python tools/ddr.py taste miss "<rejected design move>" --why "<reason>" --tags <axis:value> --rule "<rule you edited>"
python tools/ddr.py taste shipped --what "<thing>" --tags <axis:value,...> --domain <slug>
```

If the review showed that a reference in the domain led you somewhere bad, retire it with
the reason (`ddr domain ref retire <slug> <id> --reason "..."`).
