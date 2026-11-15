---
name: design-review
description: Use before calling any front end, page, deck or visual done, and whenever someone asks "is this good", "does this look AI-generated", "review the design" or "why does this feel off". Runs the gate in code (contract, claims, slop and brand lint, renders at the real viewports, copy fidelity, reading load), then hands fresh screenshots to one critic who has not seen the build: a cold read of the first screen before it sees the ask, each thing asked for checked in the asker's own words, defects worst first, no scores. The verdict is computed by rule, and must-fixes close on evidence rather than a second review. Logs what it finds to the taste ledger.
---

# Design review

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

A review that could not have failed is a ritual. The order below is fixed so the cheapest
check that could catch a disaster runs first, and nothing is called good on the strength of
a check that cannot see beauty.

Why one critic and no scores: across 150 scored reviews of real work, 80% of the scores were
exactly the pass mark and not one review said rework, while the asker sent shipped pages back
for not saying what the product was. The reviewers' written notes did find the real faults.
So the critic writes notes and a cold read, and code computes the verdict.

## 1. Three gates before the critic

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

Never judge from the maker's own sheet or from memory. Judge from the shots of this gate
run (`.design/gate/<run_id>/shots/`). Open at least the phone fold and a desktop or mac
fold; `ddr review record` refuses a review that does not list both. Then make your own views:

```bash
python tools/ddr.py sheet --images <yours.png> <exemplar.png> --labels "Yours,Best" --cols 2 --out sheet.png
python tools/ddr.py crop <before.png> <after.png> --box L,T,W,H --scale 2 --out pair.png
```

Put the work beside the two best exemplars in the domain (`ddr domain brief <slug>` lists
them) at the same size. Zoom into type and fine geometry with a crop. For an edit, crop the
same region before and after. If the work is plainly weaker than the category's best, say
so, whatever the checks say.

## 3. One critic, cold read first

The critic is a fresh agent (or a person) that has not seen how the work was built. Give it
the shots and, at first, nothing else. The builder never critiques its own work when a fresh
agent can be started; if none can, say so in the report and do the passes below honestly,
cold read first.

**Part 1, cold read.** Open only the first screen on a laptop and on a phone. Five seconds,
as a stranger. Write, before anything else is opened:

```json
{"what_it_is": "", "who_for": "", "next_action": "", "first_noticed": "", "confusing": []}
```

This is the check that scores could not do: whether the page says what it is to someone who
has not been told. It is copied unchanged into the record; it is not improved once the
critic knows the ask.

**Part 2, the ask.** Now show the critic what was asked, in the asker's own words, never a
summary. Does the cold read match what the thing is meant to be? Then each separate thing
asked for is marked `yes`, `no` or `cannot-tell`, with the shot and region that shows it.
Split the ask into things a person would check, not fragments of a sentence ("if we need
one" is not an ask). An ask only the deploy can meet ("post it to /v10") is `after-ship`:
it is checked on the live URL, not held against the build.

**Part 3, defects.** Every shot, worst first, at most ten. Each one: **where** (shot and
region), **what** is wrong, the concrete **fix**, and **must-fix** (the asker would notice and
object) or **nice-to-have**. Walk the failure patterns in section 7 and the lint warnings the
gate printed; a warning the critic finds real on screen is a must-fix.

## 4. The verdict follows a rule

- **rework** if the cold read does not match what the thing is for
- **fix-then-ship** while any ask is `no` or any must-fix is open
- **ship** otherwise (`cannot-tell` and `after-ship` are not a `no`; say what would tell)

Rework is kept for the one fault a fix list cannot repair. Measured on real work: in 18
critic passes the cold read always matched, and all 14 reworks came from an ask marked `no`
(a deploy instruction judged before the deploy, a sentence fragment, a fixable clip, a taste
call). The owner approved four of the five pages they held up as they stood; the fifth
failed on its taste asks, which is why those go to the owner rather than round the critic.

The rule lives in code. Leave `verdict` out and it is computed; a stated verdict that breaks
the rule is refused, and `ddr gate verify` recomputes it from the stored read.

## 5. Record it, and close must-fixes on evidence

```bash
python tools/ddr.py review record --run latest --json critic.json
python tools/ddr.py review show
```

```json
{"reviewer": "independent", "critic": "<who or which model>",
 "viewed": [".design/gate/<run_id>/shots/<file>.png"],
 "cold_read": {"what_it_is": "", "who_for": "", "next_action": "", "first_noticed": "", "confusing": []},
 "cold_read_matches": true,
 "ask": [{"item": "<the asker's words>", "met": "yes", "evidence": "phone fold, hero"}],
 "defects": [{"where": "phone fold, footer", "what": "...", "fix": "...", "severity": "must-fix"}]}
```

`viewed` must hold a phone fold and a desktop or mac fold from that run. `reviewer` is
`independent` or, when no fresh critic could be started, `self`.

After fix-then-ship, fix the must-fixes and unmet asks, run the gate again, and close each
one on evidence instead of a second review (`a1` is ask 1):

```bash
python tools/ddr.py review resolve --from <run the critic read> \
  --evidence "1=phone fold of the new run: headline on two lines" --evidence "a2=hero now says 24 hours"
```

A read carries once, onto a later run that passed the gate, and never past a run that has its
own review. It refuses an open item with no evidence, and it never carries a rework: a miss on what the
thing is for needs a fresh critic. A second critic pass is for a rework or a new ask, not
for checking fixes.

`ddr gate verify --require-review` passes only when the receipt is current and the read for
that run says ship. Changing any input after the gate makes the receipt stale. When the gate
genuinely cannot apply, `ddr gate waive --reason "<why>"` records that openly and logs it as
an error in the taste ledger. It is never silent.

A record with `scores` (the older nine-area review) is still accepted, with its own rule.

## 6. Strengths to protect

After the record, name what works and must survive the fixes, so the next pass does not
break it. Put them in the report, not in the critic's record.

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
| Self-review | "It's fine" from the maker | A fresh critic with fresh evidence (section 3) |

## 8. When to look again

A fresh critic again only for a rework, a new ask, or a change large enough that the earlier
read no longer describes the work. A taste ask the critic marked `no` ("give it soul") goes
to the asker with the shots, not round another critic. Where it disagrees with the first, look again before
defending either. More passes on the same ask are polish, not review: after two, show the
asker where it stands and what the critic read.

## 9. Report with limits, and log

Report: the gate verdict and receipt, the critic's cold read and verdict, what failed with evidence, what
you fixed, and what you did **not** check (real devices, Safari, slow networks, real data,
licences). Then log:

```bash
python tools/ddr.py taste error "<what went wrong in the process>" --why "<cause>" --rung observed --prevention "<rule>"
python tools/ddr.py taste miss "<rejected design move>" --why "<reason>" --tags <axis:value> --rule "<rule you edited>"
python tools/ddr.py taste shipped --what "<thing>" --tags <axis:value,...> --domain <slug>
```

If the review showed that a reference in the domain led you somewhere bad, retire it with
the reason (`ddr domain ref retire <slug> <id> --reason "..."`).
