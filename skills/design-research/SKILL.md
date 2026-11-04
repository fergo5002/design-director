---
name: design-research
description: Use when a design needs references before it needs pixels, and always when `ddr domain match` reports a confidence below what the job needs, a brief lands in new territory, or the work so far looks generic. Runs the expertise loop - maps the best work in the category, adjacent categories and other disciplines, looks at it properly in a real browser, tears it down, hunts the category's slop, writes what it learned into the domain's dossier and reference library, retires what is dated, and re-scores until the agent has earned the right to design.
---

# Design research: the expertise loop

> Tools: `ddr <command>` once installed (`python tools/ddr.py install`), otherwise `python <repo>/tools/ddr.py <command>`, where `<repo>` is two folders above this skill's real (symlink-resolved) folder.

You design well where you have looked hard, and badly everywhere else. This skill is
how you become an expert in an area before designing for it, and how that expertise
stays true over time. The output is not a moodboard. It is a **domain**: a dossier of
what you now understand, a library of references you have actually seen, and a
confidence score computed from that evidence.

Research that does not change a decision is browsing. Research you did not record is
lost. Do both properly or do not claim you researched.

## 0. Where you stand

```bash
ddr domain match "<the brief in a sentence>"
```

It returns the sector (the kind of business or audience) and the pattern (the flow
or surface: onboarding, checkout, booking, pricing, dashboard) with a confidence for
each. Then `ddr domain plan <slug> --stakes low|medium|high`:

| Stakes | When | Target |
|---|---|---|
| low | a component or a tweak inside an existing system | 35 |
| medium | a page, a flow, a redesign of one surface | 55 |
| high | a new site, a brand, a launch, anything a business will be judged by | 70 |

If the target is met, read `ddr domain brief <sector> <pattern>` and go back to
design-director. If not, run the loop below until it is, or until you have done what
the time allows and can say plainly how far you got. Do not wait to be asked. Tell the
user one line: "Confidence in independent stays is 12, so I'm researching the
category first (about 20 references)."

### New territory

When no domain matches, create one. Choose the level at which references transfer:
care homes and dental practices are both "healthcare" but their sites share almost
nothing, so they are separate sectors. Two domains whose best references would be
the same list are one domain.

```bash
ddr domain new independent-stays --kind sector --title "Independent stays" \
  --summary "Self-catering cottages, guesthouses and small hotels that sell direct" \
  --keywords "self catering,cottage,guesthouse,b&b,boutique hotel,holiday let" \
  --aliases "short term accommodation,holiday rental"
```

Keywords are the words a client would use, not design words. A **pattern** is
something that recurs across sectors with its own best practice; create one when the
brief centres on it. Relate domains that inform each other
(`ddr domain relate independent-stays booking --how "availability before price"`),
merge two that turn out to be one (`ddr domain merge <from> <into>`, nothing is
deleted), and split one that has grown two audiences by creating the second and
moving the references that belong to it.

## Your instruments

Use the best you have, in this order, and say which you used:

| Job | Best | Fallback |
|---|---|---|
| Find candidates by description | Exa MCP (`ddr mcp --research` shows setup) | your own web search, the catalogue |
| Find the best independents in a place or trade | Brave Search MCP local and place search | web search for "best <trade> in <town>", review sites, award shortlists |
| Real product screens and flows | Mobbin or Refero MCP (paid) | public teardowns, walking the flow yourself |
| Look at a reference and measure it | `ddr teardown <url> --into <slug>` | Playwright or Chrome DevTools MCP, then screenshots |
| Walk a journey safely | `ddr teardown <url> --walk "Book now>Check availability"` | Playwright MCP, never submitting anything |
| See how old a design is | `ddr history <url>`, then tear down an archived version | the site's own news or launch posts |
| Compare side by side | `ddr sheet --domain <slug> --with yours.png` | `ddr sheet a.png b.png c.png` |
| Extract a brand's tokens | Firecrawl MCP `branding` format | `ddr teardown`'s measured type and palette |

`ddr teardown` saves the desktop and phone folds, a full page and a strip of
scroll-stop frames, and measures the live page: the faces and sizes by how much text
they set, the palette by painted area, control colours, radii, shadows, section
padding, paragraph width, motion (transition timings, scroll libraries, video,
canvas, reduced-motion rules), the stack it was built on, the nav, the calls to action
and whether one sits above the fold, and the generated-design tells (stock copy,
eyebrows, gradient text, glass, icon-card triads). The numbers make your takes
specific. They never replace looking: open the images.

## 1. Map the territory

Write down who the best actually are before opening a gallery. The best in a category
are the businesses people in that trade admire, the ones winning on reputation, and
the ones whose sites the category copies. Find them three ways:

- **Direct** (`--angle direct`): the strongest 6 to 12 in this exact category, at the
  top of the market and among the small independents who are clearly doing it well.
  Use web search, trade press, award shortlists in the category, and the catalogue
  (`ddr sources search "<category>" -v`).
- **Leader** (`--angle leader`): the best work in an adjacent category that solves the
  same problem for a more demanding customer (a boutique hotel group for a cottage, a
  private bank for a credit union).
- **Outside** (`--angle outside`): at least two references from another discipline
  entirely, chosen for the subject's world (printed guidebooks, architecture
  monographs, menus, film titles, signage). `ddr sources shuffle -n 4` gives a draw.

Galleries (Awwwards, recent.design, Land-book) are leads, never evidence. Prefer year
and month awards over daily picks.

## 2. Look properly

A reference only counts as much as you actually saw:

| `--evidence` | What it means | Weight |
|---|---|---|
| `search` | You read about it or saw a thumbnail | a quarter |
| `visited` | You loaded the live site and read it | one |
| `screenshot` | You rendered it and looked at the pixels at desktop and phone | more |
| `flow` | You walked the real journey (book, sign up, check out) | most |

Tear down each serious candidate and open the images:

```bash
ddr teardown https://a.example https://b.example --into <slug>
```

Look at the folds and the scroll frames, not only the numbers. For the two or three
best, run `ddr history <url>` too: a "fresh" reference whose look dates from 2019 is a
template now, and an archived version shows which moves are new. Walk the journey that matches the
brief as far as it goes without paying or submitting anything. A loading screen or a
cookie wall is not the design; note it and look past it.

If a site's terms forbid automated access (`agent_access = "scrape-no"` in the
catalogue), browse it as a person would and record `visited`. Never copy paywalled
screens or anyone's photography into a public repo; screenshots stay in your domain
home, which is never published.

## 3. Tear down and record

For every reference that earned its place, record it straight away, using the
measured values from its `teardown.md`:

```bash
ddr domain ref add <slug> --name "Name" --url https://... --verdict exemplar \
  --angle direct --evidence screenshot --score 4 --shots shots/<host> \
  --take "Availability calendar is the hero, prices shown per night beside each date, set in a condensed serif at 15px" \
  --avoid "Autoplay drone video delays the first useful screen by 4s" \
  --tags layout:calendar-hero,type:serif-condensed
```

`--take` is the specific move, with values when you have them (sizes, colours,
timings, the actual words). "Clean and modern" is not a take. Score honestly: 5
changes how you would design this, 3 is solid and typical, anything you would score
2 is not an exemplar.

## 4. Hunt the slop

Find 3 to 5 **counter-examples** (`--verdict counter --avoid "..."`): the template
sites, the generated-looking ones, the dated ones in this category. They are as
valuable as the exemplars, because they show what this category's slop specifically
looks like, which SLOP.md in design-director can only describe in general. Write the
pattern into the dossier's *Category slop* section. Confidence is capped at 60 until
that section exists.

## 5. Write the dossier

Open `$(ddr domain path <slug>)/dossier.md` and write each section from what you saw,
naming the references. Be concrete and opinionated:

- **Who it is for**: who uses it, what they are anxious about, what they compare it with.
- **What the best do**: the moves the best share, with values.
- **Conventions to keep**: what users rely on. Do these exceptionally well.
- **Conventions to break**: what is lazy or dated here, and what replaces it.
- **Category slop**: what generated and template work looks like in this category.
- **Language**: type, colour, imagery, voice and motion that belong to this world, and why.
- **Open questions**: what you still do not know and what would answer it.

## 6. Curate

```bash
ddr domain audit <slug> --online
```

It flags references that are stale (not seen in a year), weak (search only),
contradictory (an exemplar you scored 2), dead, moved, or all from one angle or one
source. Act on every finding: look again (`ddr domain ref seen`), re-score, or retire
with a reason (`ddr domain ref retire <slug> <id> --reason "redesigned into a
template in 2026"`). Retired references stay in the graveyard so they are never
quietly re-added. A library is only as good as what you are willing to throw out.

## 7. Compare, then re-score

Make a contact sheet of the domain's best (`ddr sheet --domain <slug> --n 6`) and look
at it as a set. If they all look alike, the library has converged on one idea and the
next search should look for the reference that contradicts them.

## 8. Re-score and decide

```bash
ddr domain status <slug>
```

It shows the score, every part of it, any cap and what would raise it. Repeat the
loop on the biggest gaps until the stakes target is met. Then tell the user where you
landed in one line ("Independent stays is now 58: 14 sites looked at, 4 counter-examples,
the slop written down") and go back to design-director Step 1.

## Depth

Scale the effort to the stakes and say what you did:

- **low**: 4 to 6 references, one counter-example, the slop line written. Minutes.
- **medium**: 8 to 12 references across all three angles, 3 counter-examples, every
  dossier section. Under an hour.
- **high**: 15 to 25 references, flows walked on the best 3, 4 or more
  counter-examples, two outside references, an audit pass. As long as it takes.

The project still keeps its own short ledger in `.design/references.md`: the 5 to 10
references that changed a decision on *this* job, one row each, with the decision it
changed. The domain is what you know; the project ledger is what you used.

## Rules

- Borrow techniques and principles, never a recognisable logo, photograph, paid font
  or proprietary illustration.
- Record failed access (paywall, bot wall, dead link) instead of guessing what was behind it.
- Never record a reference as seen that you did not see. The score exists to stop you
  claiming expertise you have not earned; inflating it defeats the only thing it is for.
- When a catalogue entry is dead or wrong, fix it with `ddr sources add`, and add great
  new sources there too, so the next person starts ahead.
