# The gate

Run before claiming done. Ordered by what costs most when it is wrong, not by what
is easiest to check. Every line is here because something got past a previous
version of this skill.

## 1. Is it true

- [ ] Every number, count, comparison, superlative and date range in the copy has
      been checked **by a script** against the source. Not re-read. Checked.
- [ ] No series was averaged without asserting zero nulls first.
- [ ] The stated provenance is the window that actually has data.
- [ ] Data is injected at build time, not transcribed into markup.
- [ ] Units are named correctly (wind speed is not gust; mean is not median).
- [ ] The graphic carries the argument. A reader can see the claim without the caption.
- [ ] A capacity or progress bar fills in the direction its meaning grows (booked fills, empty stays dark). A headline phrased the other way ("3 places left") never reverses the visual meaning. Keep temporary holds distinct from confirmed ones.

If the data does not support the headline, **change the headline**, not the caveat.
EVIDENCE.md.

## 2. Is it AI-free

Negative test, the ban list: no Inter / Space Grotesk / Poppins / Montserrat /
Playfair / Roboto / Open Sans / Lato / Plus Jakarta / DM Sans as display. No
purple-to-blue gradient. No `#F4F1EA` with terracotta. No emoji as icons. Nothing
centred by default. No `rounded-lg` on everything. No accent bar on a rounded card.

Positive test, which matters more:

- [ ] **Name three decisions here that a model would not have made by default.**
      If you cannot name three, go back. They must be decisions, not adjectives:
      a specific typeface and why, a specific hex and where it came from, a
      structural choice with a reason.
- [ ] Every colour traces to the subject's own world, not to a colour wheel.
      (Admiralty magenta because magenta is what charts use for navigation. Not
      "a pink accent".)
- [ ] **No form control is in its browser default state.** A stock range slider or
      checkbox on an otherwise designed page is the single element that announces
      nobody looked. If a control is redundant with another, delete it rather than
      styling it.
- [ ] The page has exactly one loud thing.
- [ ] In an established brand, each decorative layer has a purpose. A palette
      match alone does not justify extra mock-ups, rotated collages or props.
      When demonstrating existing work, inspect a simple presentation of the
      real work before inventing a composition around it.

- [ ] When a redesign retains an object the user likes, compare the actual original asset and its interactions with the new version. A recognisable substitute is not evidence of fidelity. Read intermediate motion frames as well as opening and closing poses.

## 3. Does it hold up

- [ ] Comparable offer cards use consistent content order. Check price, savings
      and action alignment with unequal copy lengths, and calculate comparisons
      using the same eligibility rules as purchase or redemption.

**Measure, or look once?** The bundled `artifact-design` skill says write it, look once
and publish, with no repeated screenshots and no DOM probes. This file says measure.
The rule: **measure whenever the thing goes to anyone but you, and whenever you are
about to make a claim about contrast, motion or accessibility.** One look is enough for
a throwaway you will bin yourself. When it is genuinely unclear which one it is, measure,
because the probe costs a minute and a wrong claim costs a lot more. This governs
sections 3 and 4.

- [ ] Contrast **measured**: `tools/palette.py check --strict`, once per theme.
      Running both themes together produces cross-theme noise; run them separately.
- [ ] Anything under a wash, scrim or overlay measured **composited**:
      `tools/palette.py blend --alpha <a>`. Tokens passing in isolation prove
      nothing. A 50% wash once took a caption from 7:1 to 2.17:1.
- [ ] Photographic choice cards: judge each photograph alone at laptop size before any
      text or scrim goes over it. Is the subject obvious, and is the source at least the
      rendered width times the device pixel ratio? A scrim that rescues contrast can still
      make the picture mud. When it does, put the words below the photograph. (Oak Smoke,
      2026-10-02.)
- [ ] Text over a colour scale uses pure `#000`/`#fff`, verified across the whole
      ramp, not spot-checked.
- [ ] `:focus-visible` present, tested with a real Tab press. Calling `.focus()`
      in the console does **not** trigger `:focus-visible` and will report `none`.
- [ ] Targets 44x44 at a genuinely narrow width. Twelve items across a phone is
      about 30px each: put the row and whatever it aligns to in a shared horizontal
      scroller rather than breaking the alignment.
- [ ] `overflow-x:clip` on `html` **and** `body`.
- [ ] `prefers-reduced-motion` lands on the finished state. If someone says nothing moves on their phone, check whether Reduce Motion is on before blaming the site.
- [ ] Themes match the site: light only unless the brief or the site has a dark theme, and a browser set to dark still renders light. Where two themes exist, `data-theme` beats the media query in both directions.
- [ ] One `h1`, no skipped heading levels, every control has an accessible name.

## 3b. Is it readable, and is it varied

- [ ] When shortening an existing proposal, preserve its explanatory app screens,
      worked examples and file hierarchies. Audit each original section before
      replacing it. Reduced word count does not justify replacing a useful
      visual demonstration with prose panels. Carry one example through the
      input, review and output so the reader can see how the parts connect.

- [ ] When the brief asks to make service value visible, show the actual product mechanic or deliverable. A feature list with dividers, numbers or icons does not meet that brief. Review pricing inclusions and switching separately at desktop and phone widths.


- [ ] The main offer is demonstrated visually before secondary implementation details.
      A checkout hold or similar supporting mechanic does not displace the core
      product benefit. Remove captions and closing slogans that only repeat the
      graphic or section above. Do not require three sections, or a unique component
      sequence per page, if satisfying that rule adds filler to a shorter page.

Added 14 September 2026. A page can pass every other section here and still be a wall.
A real sauna-brand site did: correct contrast, correct focus, correct motion, true copy, and
1,036 words over sixteen phone screens with five prose-only sections in a row. Its owner
could not read it. None of the gates below existed to catch that, because they all
measure a pixel and none of them measures the *load*.

Measure the rendered page, not the source. At phone width:

- [ ] **Footer.** Measure it separately from main. Repeated navigation should not
      dominate a phone screen. Consider native disclosure groups whilst retaining
      contact and legal access, and test their keyboard and touch paths.
- [ ] **Browser title.** Read the final document title, not only its metadata
      source. Use a short page label and a single brand suffix. Check long dynamic
      names and the homepage, where a template can repeat the brand.

- [ ] **Words.** `main.innerText` word count. A marketing homepage over about 400 words
      of prose is not finished. Count graphic text separately: words inside a console
      screen or a slider card are part of the picture, not part of the reading.
- [ ] **Screens.** `scrollHeight / innerHeight`. If it is long, check what is taking the
      height. Long because of graphics is fine. Long because of paragraphs is the defect.
- [ ] **Sections with nothing to look at.** More than one in a row is the thing that
      reads as bloat. One on its own can be the interrupt that makes the others work.
- [ ] **Adjacent shapes differ.** If two sections in a row share a layout, one of them is
      wrong. Same for two pages opening the same way.
- [ ] **The variety is enforced, not described.** A rule in a comment lasts until the next
      person. Read the shapes out of the JSX in a test and fail on a repeat.

## 4. Did you actually look, and was the instrument sound

**Run the probe first, before any browser finding is worth anything:**

```js
// into javascript_tool / browser_evaluate
// paste the contents of tools/instrument-check.js from this repo
```

It returns `CLEAR`, `USABLE WITH CAVEATS` or `INSTRUMENT DEGRADED`, and it cannot
hang. **A hidden tab is the default state for MCP browser work**, and in a hidden
tab `requestAnimationFrame` never fires, so every frame-based probe hangs and every
screenshot times out. That looks exactly like a frozen page and is not one.

- [ ] Probe run, verdict read. Anything below `CLEAR` means fix the instrument
      before drawing any conclusion about the design.
- [ ] Rendered and viewed at desktop **and** narrow. Not reasoned about.
- [ ] For a phone-led booking page, check the opening screen at both 390x844 and
      320x568. A full-screen hero must reach the viewport bottom, with its main
      action entirely visible. Check header hierarchy separately from overflow.
      Tap the arrow itself as well as its label and inspect the destination:
      session controls must be visible and a repeated booking bar must not cover them.
- [ ] For a published Artifact: previewed **wrapped as the host wraps it** (doctype,
      charset, viewport). A bare fragment on a local server renders in quirks mode
      under `windows-1252`, and is a different document from the one that ships.
- [ ] `<script>` is pure ASCII so a missing charset cannot break the page.
- [ ] Any finding from `getComputedStyle` confirmed against actual pixels before
      acting on it. It has reported stale colours for JS-created elements while the
      rendering was correct, and "fixing" that wastes a cycle.
- [ ] **A tool failing is evidence about the tool.** A timeout, a null or a strange
      reading says something about the measurement path until that path is shown
      healthy. Take a control reading on something known good.
- [ ] **Two wrong diagnoses means stop guessing.** Do not reach for a third story.
      Baseline, then bisect one variable at a time, writing down what each step
      rules out. See CLAIMS.md.

## 5. What you are allowed to say about it

The gate above is worthless if the report overstates it. Full method:
CLAIMS.md.

- [ ] **Every check named here either passed, failed, or was not run.** Say which.
      "Verified X and Y, did not verify Z" is the complete form. A completion claim
      without its limits is not a completion claim.
- [ ] **No check reported as passing that could not have failed.** If you cannot
      say what result would have made you report a failure, you ran a ritual.
- [ ] **You checked the thing that ships, not the thing you built.** Composited
      pixel, not token. Host-wrapped page, not bare fragment. True copy, not merely
      real copy. Each of those pairs has already produced a false "verified" here.
- [ ] Nothing is stated at a rung above the one it earned: *guessed*, *observed*,
      *reproduced*, *isolated*, *explained*, *fixed*. "Guess, untested" is a
      complete and useful sentence, and it is the honest name for a first idea.

## 6. Did you write it down

- [ ] Secondary promotions have a measured phone-height budget and a reviewed phone screenshot. Remove repeated account links and copy that merely repeats the purchase action. Desktop approval does not establish that a stacked mobile promotion is appropriately sized.
- [ ] When shrinking approved artwork, retain the named visual motif at a smaller scale before replacing it with a logo or a different decoration. Check the original version when a user refers to a stamp, card or other specific detail.

- [ ] Anything praised is logged with `python tools/taste.py win` with values.
- [ ] Anything corrected is logged with `python tools/taste.py miss` **and** the rule that allowed it has been
      edited.
- [ ] `python tools/check_routes.py` exits 0 if SKILL.md was touched.


### Continuous demos and guided experiences

When the brief asks for an automatically playing demo, verify an uninterrupted run from the submitted entry to the ending. The acceptance path must not press Play or manually advance a chapter unless the user explicitly requested that behaviour. Count visible choices, inspect the actual transitions and review the smallest phone. A set of individually passing screens does not establish a coherent journey. Keep Reduce Motion and explicit pause as deliberate exceptions with complete still states.

### Personal professional websites

Count visible hero elements and repeated credentials. Keep the person, a short professional description, one meaningful image and necessary navigation. Decorative chapter numbers, Roman indices, scroll prompts and duplicate credential strips are not evidence of craft. Remove them unless a specific navigation need justifies their presence. Review enquiry entrances as real paths, with an honest destination and no fake submission state.

Career credentials are facts, not a performance chart. Do not connect them with a decorative growth curve. Inspect date and label bounds at wide desktop, 390px and 320px, and give the complete section a height budget. When adapting an approved monogram, preserve its construction and check a separate small-size favicon rendering.

### Connecting an existing merchant website

Compare the served original before replacing it. Keep its named visual features and media whilst connecting real data. An experience selector must expose the distinctions needed to choose, including price, duration, location and group size; do not hide a small, meaningful set of purchase choices in a native dropdown. Inspect gift, account and checkout typography separately from the marketing page. Follow booking links on a phone and require the booking controls to be visible at the destination. Verify the exact requested Vercel/customer address after the latest alias assignment, including queued older production builds, before handing it over.

### Scroll animation continuity

For a request about more frames or jitter, measure actual rendered frames separately from scroll distance and interpolation. Compare the current and revised sequence under identical wheel, continuous scroll and reversal inputs. Sample frame timing without screenshot capture in the measurement loop, and include the real drawing-buffer scale plus a slower-CPU check. Do not claim that a longer timeline raises frame rate, or that desktop emulation proves physical-phone smoothness.
