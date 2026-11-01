# Dashboards

The rules for any dense product surface: consoles, admin panels, analytics, operator
tools. Load this alongside COLOUR.md and EVIDENCE.md whenever the job is a dashboard.

Sources: three teardown videos studied 2026-09-07 (foundations `EcbgbKtOELY`, the
anti-vibe-code redesign `PDcQJOPby1k`, dashboard construction `B7k5rOgmOGY`),
cross-checked against the Linear and Attio specimens. Transcripts are the primary
source, not a summary of them.

---

## Part 1: The AI tells, by name

These are the specific things that make a dashboard read as generated. Every one of
them was found in one real booking console in a single afternoon.

| The tell | Why it happens | What to do instead |
|---|---|---|
| **A row of 4 KPI boxes** with a big number and a small label | It is the first layout any model produces for "dashboard" | Give the tiles a **sparkline or a fill bar inside them**. Or drop to a two-column layout with small doughnuts. A number with nothing beside it is a spreadsheet cell. |
| **The same KPI row on three pages** | Each page was generated in isolation | A figure appears **once**, on the page that owns it. If Reports owns revenue, Overview links to it, it does not restate it. |
| **Gradient circle with initials** for the account | Universal model default | An account **card**: name, role, and the thing they need (venue, plan, shift). Or a real avatar. |
| **Emoji as icons** | Cheap colour | Lucide or Phosphor at the **line height of the adjacent text**. |
| **Decorative cards that do nothing** | Filling a grid | Delete. If a card has no action and no changing number, it is a paragraph. |
| **Bright AI colours** (violet-to-blue, six evenly-sprayed hues) | No palette was built | One accent. Colour arrives through **data**, not through buttons and icons. |
| **Everything `rounded-lg` with a shadow** | Defaults | Three radii tied to what a thing *is*: control, surface, panel. |
| **Vast dead space** in a sidebar or under a short page | No density decision was made | A dashboard uses most of the screen. See Part 3. |
| **A form control in its browser default state** | Nobody looked | Style every checkbox, radio, range and select, or use a radiogroup. |
| **Text stating a fact nobody computed** | Prose written before the query | EVIDENCE.md. Compute it, inject it at build time. |

**The compound tell:** good tokens with generic composition. A validated palette and
a proper type scale do not save a layout that any model would have produced. The owner's verdict:
*"the landing page, the UI and UX are better now but still look really
bad… it looks AI-generated, not sleek or clean."* The tokens were fine. The
composition was the problem.

---

## Part 2: The sidebar

The spine of the product. Everything persistent and globally relevant lives here.

- **Account management goes at the top**, not the bottom. A picture or a card makes
  it identifiable, and a chevron signals it is clickable.
- **Icon plus a short title** on every link. Not icon-only, not text-only. This is
  what makes a collapse toggle possible later, and what gives a notification count
  or a "new" chip somewhere to sit.
- **Group links by what is relevant.** Grouping is the whole job of a sidebar: it is
  how you reduce the cognitive load of thirty routes down to five decisions.
- **Settings and help go to the bottom.** They are reached rarely and looked for
  deliberately.
- **Nest into disclosure once a group passes about six links.** A flat list of
  twenty is a menu, not navigation.
- **An active state is mandatory**, and a left rectangle indicator reads faster than
  a fill alone because it survives at a glance and in peripheral vision.
- Sidebar links are **ghost buttons**: no background until hover.
- The empty space at the bottom is an opportunity, not a gap. Dub and Linear both
  put live notifications, usage, or a status line there. **A hole in the sidebar on
  every screen is the most-seen flaw in the product.**
- Never state the product or tenant name twice. If a logo and a switcher both say
  "Firecracker Saunas", one of them goes.

---

## Part 3: Density, grid and type

A dashboard is not a landing page shrunk down. They are different instruments.

| | Landing page | Dashboard |
|---|---|---|
| Font sizes | up to 6, huge range, display type to 130px | narrow range, **rarely above 24px** |
| Steps between sizes | large | small, 1 to 2px apart at the bottom of the scale |
| Grid | a guideline, break it freely | **followed strictly**, because all the space is used |
| Space | generous, it is the point | earned, every block justifies its area |
| Motion | can carry the page | tame and user-focused; the charts are where you get creative |

- The main region reflects **what is most important to this user**. A project tool
  puts status there. A financial tool puts positions there. A sauna puts **how full
  the room is tonight** there, because that is the entire business.
- Two columns by two rows is a complete and respectable dashboard grid. Reach for
  more only when the content demands it.
- The top strip is for **page actions and simple navigation**. Two actions is
  usually right, three is the ceiling, and one of them is primary.
- 4px base unit, because it always halves cleanly.
- **Group by proximity before you reach for a border.** Related things sit closer.
  That is a hierarchy signal and it costs nothing.

### The type mechanics that do the work

- One family is enough. A second is a mono for figures, and that is the only
  third voice a dashboard earns.
- Large type: tracking **-2% to -3%**, line height **110% to 120%**. This single
  adjustment is the difference between amateur and professional display type.
- Small type gets **positive tracking**. Uppercase always does.
- `font-variant-numeric: tabular-nums` on every column of figures and every number
  that changes in place. Or prove the face's digits are already uniform.

---

## Part 4: The four components, and nothing else

Master these and every page in the product is already designed.

### 1. Lists and tables
Separation has exactly three tools: **space, a line, or colour**. Pick one per
context, do not stack all three.

A table becomes an instrument only when it can be **searched, filtered and sorted**.
Displaying the data is half the job.

Selecting rows must reveal a **contextual bulk-action bar**. That one micro-
interaction is what turns a list into a tool.

Rows need somewhere for the eye to rest. A row of `17:00 · Social Sauna · <void> ·
0/9` is a spreadsheet. Put a description, a fill bar, or a face in the void.

### 2. Cards
Generous internal margins. Choose **either** an outline **or** a background tint,
never both. Outlines suit dark grounds, background tints suit light ones.

### 3. User input
Every input needs focus, error with a message, and often a warning state. Every
button needs **four states minimum**: default, hover, active, disabled. Plus loading
where it can be slow.

### 4. Tabs
The way to add pages without growing the sidebar. Related views of one context stay
in that context.

---

## Part 5: Choosing the overlay

Getting this wrong is a design failure that reads as confusion.

| Use | When | Rules |
|---|---|---|
| **Popover** | Simple context, non-blocking, click-away is harmless. Display settings, a filter, a quick switcher. | No confirm needed. Escape and outside-click both dismiss. |
| **Modal** | Complex context directly related to what is on screen, and the user should stay on the page. Creating the thing the list contains. | Blocking. Needs an explicit confirm or cancel. **Follow it with a toast**, because the user could not see the page change. |
| **Sheet / drawer** | Detail of a row, where the list context must stay visible. | Stacks over the page. Escape closes. The row it came from stays marked. |
| **New page** | Permanent or very large context. | **Back link or breadcrumb is required.** |
| **Toast** | Anything the user should know without losing the screen. | The notification system of the product. Cover success, warning **and error**, because error states are the ones that get skipped. |

A settings surface with three tabs, one card of label-value pairs and 400px of
white space below it is not a designed page. Settings is where a product's care is
most visible, because it is where the user goes when something is wrong.

---

## Part 6: Charts

Everyone forgets the same things.

- **Grid lines and axis numbers.** Both. This is the single most common omission.
- A **summary figure and a range selector on the card itself**, not in a control
  strip somewhere else on the page.
- **Hover is not optional.** Line and area get a crosshair plus a readout. Bars get
  a per-mark tooltip. A percent bubble beside the value earns its place.
- **Dim the siblings on hover.** Hovering one bar should recede the others. It is
  cheap and it makes the chart feel alive.
- Identity beside the mark: a favicon, an avatar, a venue name. Not a colour and a
  legend when a label would do.
- Never invent a chart form. If a reader cannot name the shape, it is wrong.
- Sequential means one hue, light to dark, and it means **magnitude**. Never reuse
  a magnitude ramp for categories or status.
- Run `dataviz`'s `validate_palette.js`. Do not reason about Delta E.

Sparklines inside stat tiles are the cheapest upgrade available to a KPI row and
they remove the tell in Part 1 outright.

---

## Part 7: Feel

This is what people mean by "feels good", and it is judged before anything is read.

- **Every action gets a response.** No exceptions. Press states, hover states,
  focus rings, spinners, success messages, error text.
- **Optimistic UI.** The row disappears the instant it is deleted and reconciles
  behind the scenes. Gmail is the reference. Waiting for a round trip before
  changing the screen is the difference between a fast product and a slow one, and
  it is entirely a front-end decision.
- **Micro-interactions confirm.** A copy button with hover and press states still
  has not told anyone it copied. A chip that rises out of it has.
- Durations: micro 150 to 250ms, reveal 600 to 950ms, page transition 350 to 500ms.
  **Exit faster than enter.**
- Motion on a dashboard is restrained by default. Spend the budget on the charts,
  the overlays and the state changes, not on the page.
- `prefers-reduced-motion` lands on the **finished** state.

---

## Part 8: Colour, on a dashboard specifically

- **Colour is for purpose, never decoration.** If a hue is not carrying meaning, it
  is noise.
- Colour should arrive through **data**: a fill ramp, a chart series, a status chip,
  a heat cell. Not through tinted buttons and coloured icons.
- One accent, on the primary action and links. Status is a separate system and does
  not count against it.
- A magnitude ramp is one hue, light to dark, strictly decreasing in OKLab
  lightness, and it means exactly one thing across the entire product.
- Dark mode: depth comes from **lighter surfaces**, never from bigger shadows.
  Lower border contrast. Dim chip saturation and brightness, then raise the text
  inside them for hierarchy.
- Light mode shadows: most are far too strong. Drop the opacity, raise the blur,
  layer three soft ones rather than one hard one. **If the shadow is the first thing
  you notice, it is wrong.** Cards need very little; popovers need more, because
  they sit above other content.
- Text over any colour scale uses pure `#000` and `#fff`, per COLOUR.md.

---

## Part 9: Icons

Most icons in most products are too big.

Take the **line height of the text beside it** and make the icon that size. 20px
text at 1.45 gives a 29px box, so the icon is not 24px by default just because the
library ships at 24.

Then tighten the gap. An icon and its label are one object.

---

## The gate

Before calling a dashboard done, answer these. Any "no" is unfinished work.

1. Does any figure appear on more than one page?
2. Does every KPI tile carry a mark as well as a number?
3. Is there a hole in the sidebar on any screen?
4. Can every table be searched, filtered and sorted, and does selection reveal
   actions?
5. Does every row have something in its middle?
6. Do the charts have grid lines, axis numbers, a summary, a range control and a
   hover readout?
7. Is there a designed empty state for every list?
8. Does every destructive or slow action respond instantly and confirm with a toast?
9. Is every overlay the right kind of overlay per Part 5?
10. Is the settings surface as designed as the overview?
11. Does colour appear anywhere it is not carrying meaning?
12. Measured contrast, per theme, on the composited result?
