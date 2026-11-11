# UI

How a screen looks and ranks itself: hierarchy, spacing, alignment, depth, components, density,
responsiveness and motion in product UI. TYPE.md owns typefaces and COLOUR.md owns palettes; this
file owns everything between them and the numbers to build with. UX.md owns how the screen works.
Where this file and SLOP.md or a brand pack disagree, they win.

## The canon

| Source | Use it for | Read it at |
|---|---|---|
| **Refactoring UI** (Wathan and Schoger) | The building method for people without a designer, which is the agent's position: hierarchy by de-emphasis, spacing scales, type and colour systems, depth. Its numbers are codified in the Tailwind default theme | refactoringui.com (book, paid); tailwindcss.com/docs/theme (free, the numbers) |
| **Apple Human Interface Guidelines** | The numeric rulebook: target sizes, minimum type, button roles and counts, contrast, dark mode, motion. Take the principle, never the platform material | developer.apple.com/design/human-interface-guidelines; an agent reads the JSON the site serves at `/tutorials/data/design/human-interface-guidelines/<page>.json` |
| **Practical Typography** (Butterick) | Text that reads: size, leading, measure, emphasis | practicaltypography.com/summary-of-key-rules.html (free) |

Support: **Material 3 and Android** (window size classes, motion tokens), **NN/g** (visual
hierarchy, proximity, aesthetic-usability, animation duration), **Josh Comeau** (shadows),
**Radix Colors** and **Stripe's accessible colour post** (contrast by construction), **Utopia** and
**Every Layout** (fluid scale and intrinsic layout), **Carbon** (dense enterprise UI). Video
channels are demonstrations for a person, not a source of numbers an agent can cite.

## The order to build in

Refactoring UI's order, which is also the order the eye checks:

1. **Start with the feature, not the layout.** Design the thing the person does (the form, the
   card, the row) before the shell around it. No navigation, sidebar or hero until the core
   piece works.
2. **Greyscale first.** Lay out with greys, size, weight and space only. Colour comes last, and
   only where it has a job. If the hierarchy fails in greyscale, colour will not save it.
3. **Hierarchy, then spacing, then type, then colour, then depth, then finishing.**

## Hierarchy

The order in which the eye meets things, set by contrast against the surroundings.

- Decide the first thing seen and the second. Everything else is allowed to be quiet.
- Use three levers together: size, weight and lightness. Reach for weight and lightness before
  size.
- **De-emphasise rather than shout.** Make secondary things smaller, lighter and lower in contrast,
  instead of making the main thing bigger and louder.
- Labels are secondary. Where the value speaks for itself ("4.8 rating", "€42.50"), drop the label
  or quieten it.
- Ceilings for one view (NN/g): two primary and two secondary colours, three levels of contrast,
  three type sizes in any one component, two large elements.
- One or two prominent buttons per view (Apple). The preferred action differs by style, not size.
- Hover and selected states change colour, fill, shadow or underline. Never size, case or weight:
  they shift the layout.

**Check.** The squint test: blur the screenshot 6 px (`filter: blur(6px)` on the root) and name the
first two things you see. The greyscale test: `filter: grayscale(1)`; the ranking and every status
must survive without hue.

## Spacing and rhythm

- **Start with too much white space,** then take it away. Cramped is the commoner fault.
- One scale on a 4 px base, never arbitrary values: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Anything
  off the scale needs a written reason.
- **Proximity groups.** The gap inside a group is clearly smaller than the gap between groups; aim
  for at least twice. A label sits closer to its own field than to the field above it. A run of
  twelve fields reads as three groups of four when the gaps say so (NN/g).
- More space around something says it matters more.
- Siblings get `gap` on flex or grid, not margins on each element.
- Bigger steps at bigger widths, same tokens.

**Good.** Label 8 px above its field, 24 px between fields, 48 px between sections.
**Bad.** 16 px everywhere, so nothing groups; or 13, 17, 22 and 30 px with no scale.

## Layout and alignment

- The most important thing sits top and leading, in reading order.
- Prefer intrinsic layout (flex-wrap, `grid-template-columns: repeat(auto-fit, minmax(...))`,
  container queries) to stacks of breakpoints. Every Layout's primitives (Stack, Cluster, Sidebar,
  Switcher, Cover, Grid, Frame, Reel) cover most screens.
- Cap prose by characters (`max-width: 65ch`) and let tables and charts break wider on purpose.
- One left edge per column, held. Left-align text by default; centre only short, single lines.
- Indentation means hierarchy and nothing else.
- Mixed sizes in one row align on the baseline, not the vertical centre.
- Numbers right-aligned in columns, on tabular figures.
- Icons centred optically, not geometrically: nudge asymmetric glyphs a pixel or two.
- Two buttons in one row share a height.

**Check.** Collect the left edges of the headings, paragraphs and buttons in a section; more than
two or three distinct values needs a reason.

## Type in product UI

TYPE.md picks the faces. These are the numbers for using them in an interface.

- Body 16 to 18 px on the web for product UI (Butterick allows 15 to 25 for reading), leading 1.4 to
  1.5 for UI text and 1.5 to 1.6 for long reading. Running text at 60 to 75 characters (TYPE.md);
  narrow UI columns can go to 45.
- A hand-picked scale, not a strict ratio. Tailwind's, with paired leading: 12/16, 14/20, 16/24,
  18/28, 20/28, 24/32, 30/36, 36/40px. From 48 px up, multi-line headings take 110% to 120% leading
  and -2% to -3% tracking (DASHBOARDS.md; TYPE.md owns single-line display type).
- Leading tightens as size grows; tracking tightens on large type and opens on small type and on
  anything set in capitals (+5% to +12%, Butterick).
- Avoid the lightest weights (Thin, Light) at small sizes; favour faces with five or more weights.
  Two weights do most of the work: regular and one heavier.
- Minimum sizes: iOS 11 pt minimum and 17 pt default; macOS 10 pt minimum and 13 pt default
  (Apple). On the web nothing a person must read sits under 12 px, and form inputs never under
  16 px.
- Emphasis with bold or italic, never both; underline only for links.
- Text survives WCAG 1.4.12 text spacing: line height 1.5×, paragraph spacing 2×, letter spacing
  0.12× and word spacing 0.16× with nothing clipped. So never fix a text box's height.

## Colour in product UI

COLOUR.md builds the palette. These are the rules for spending it.

- Greys carry the layout; colour carries meaning. Recipes that work: one accent on greys; two
  colours on greys; greys plus shades of one hue.
- Eight to ten greys and five to ten shades per hue. Build the ramps in OKLCH (palette.py), never by
  eye in HSL.
- **Contrast by construction.** On Stripe's perceptually even (CIELAB) scale, any two colours at
  least five levels apart pass for small text and four apart for large text and icons; build ramps
  the same way and prove each pair with `palette.py check`. Radix's role map: steps 1
  and 2 backgrounds, 3 to 5 component fills (rest, hover, pressed), 6 to 8 borders, 9 and 10 solid
  fills, 11 low-contrast text, 12 high-contrast text.
- Floors: 4.5:1 for text, 3:1 for large text, controls, focus rings and chart marks. Aim for 7:1 on
  small text you can afford it on.
- Grey text on a coloured ground goes muddy; use a lighter or darker shade of the ground's own hue.
- Same colour, same meaning. The brand accent marks the primary action, selection and links; status
  colours (danger, warning, success) are separate and never decorative. A brand red must not also
  mean error.
- Colour is never the only signal: add a word, an icon or a shape.
- Put colour on the background of the one primary control, not on the text and icons of many.
- Dark mode is designed, not inverted: dimmer grounds, slightly brighter foregrounds, higher
  surfaces lighter rather than shadowed, white images toned down.

## Depth and surfaces

- One light source for the page, from above. Raised things cast a shadow below; inset things
  (inputs, pressed buttons) are the reverse.
- A fixed set of about five elevation levels with jobs: resting card, raised card, dropdown and
  popover, sticky bar, modal. Tailwind v4's levels are a sound start: `sm` `0 1px 3px 0 rgb(0 0 0 / .1),
  0 1px 2px -1px rgb(0 0 0 / .1)`; `md` `0 4px 6px -1px rgb(0 0 0 / .1), 0 2px 4px -2px rgb(0 0 0 /
  .1)`; `lg` `0 10px 15px -3px rgb(0 0 0 / .1), 0 4px 6px -4px rgb(0 0 0 / .1)`; `xl` `0 20px 25px
  -5px rgb(0 0 0 / .1), 0 8px 10px -6px rgb(0 0 0 / .1)`.
- Layer two to five soft shadows at low opacity rather than one hard one, keep the vertical offset
  about twice the horizontal on every shadow, and tint shadows towards the ground's hue rather than
  pure black (Comeau). Never animate a layered shadow.
- Fewer borders. Separate with space first, then a slightly different background, then a shadow.
  One card uses one of border, shadow or fill, never all three.
- Radius is a decision kept everywhere: sharp, slightly rounded or very rounded. A nested corner's
  radius is the outer radius minus the gap between them.

**Check.** Count distinct `box-shadow` and `border-radius` values; more than about five of either
is a missing system. If the shadow is the first thing you notice when squinting, it is too strong.

## Components

- **Buttons.** Primary (filled with the accent) for the single most likely action; secondary
  (outline or tinted); tertiary (text). The destructive action is never the primary style unless
  it is the main thing the page is for. Hit area 44 by 44 on touch, 24 by 24 at the very least.
  Every button has rest, hover, focus-visible, pressed, disabled and busy states. Full-width primary
  on a phone.
- **Inputs.** Drawn inset or outlined, the border at 3:1 against its surroundings, label above,
  error shown with text and an icon as well as colour. Never a browser-default control left as it
  came.
- **Cards.** One job each. Group by space and a shared ground; use containers sparingly, every box
  adds weight.
- **Tables.** Header quieter than the rows; numbers right-aligned on tabular figures; row hover
  as a faint fill; zebra stripes only when rows are wide and many.
- **Dialogs.** The largest shadow level, a dimmed backdrop, one primary action, and the dialog
  behaviour in UX.md.
- **Navigation and tabs.** The current item is marked by more than colour (a weight-neutral
  underline, a fill, an indicator). Labels never reweight or resize when selected.
- **Badges.** Text plus colour: a light tint of the hue with dark text of the same hue, small and
  quiet.
- **Icons.** One family, one stroke weight, one size set, matched to the weight of the text beside
  them. An icon plus a word for anything not universal. Never emoji as icons.
- **Images.** Fixed aspect ratio so nothing shifts, `object-fit: cover`, real alt text, and a
  designed fallback (a tint or an initial) instead of a grey box. Text over a photograph sits on a
  scrim, measured on the lightest part of the image.

## Tokens and consistency

Define the tokens before building: spacing steps, type sizes with leading, colour roles, radii,
shadow levels, durations and easings. Name colours by role (`--text-muted`, `--surface-raised`), not
by value. When two components do the same job, they look the same. Rough ceilings for one product
page: about 8 type sizes, 3 weights, 2 families, 4 radii, 5 shadows; past them, write down why.

## Density

- Choose density from the task. Browsing and first use: comfortable. Repeated expert work
  (tables, queues, dashboards): compact.
- Compact shrinks the gaps and row heights, never the type below its floor and never the targets
  below 24 px (44 on touch). Row heights around 32 to 40 px compact and 48 px comfortable.
- Compact still groups: smaller steps, same inside-versus-between rule.
- Offer a density switch in expert tools. DASHBOARDS.md has the rest.

## Responsive

- Design for the space, not the device. Window size classes (Android): compact under 600 px,
  medium 600 to 839, expanded 840 to 1199, large 1200 to 1599, extra large 1600 and up. Tailwind's
  breakpoints sit close: 640, 768, 1024, 1280, 1536.
- Fluid type and space between two ends with `clamp()` (Utopia), so few breakpoints are needed.
- After columns stack, check the groupings again: stacking separates things that sat together.
- A phone on its side is medium wide and compact tall: two-pane layouts need height too.
- Reflow at 320 px wide with no sideways scroll (WCAG 1.4.10), measured against
  `document.documentElement.clientWidth`.

## Motion in product UI

CRAFT.md covers motion technique and the longer reveals of marketing pages. Product UI is quicker.

- Motion explains a change or confirms an action. No motion on things people do many times a
  minute, and none for its own sake (Apple).
- Durations: press and toggle feedback 100 to 150 ms; micro-interactions, menus and popovers 150 to
  250 ms; a dialog or panel 200 to 300 ms; a full page transition 350 to 500 ms (DASHBOARDS.md).
  Exits shorter than entrances. Most UI motion sits between 100 and 500 ms (NN/g); Material's
  tokens run 50 to 600 ms for UI.
- Easing: enter on a decelerating curve (`cubic-bezier(0, 0, 0, 1)` or `(0.05, 0.7, 0.1, 1)` for
  emphasis), exit on an accelerating one (`cubic-bezier(0.3, 0, 1, 1)`), things that start and end
  on screen on `cubic-bezier(0.2, 0, 0, 1)` (Material 3). Never linear for movement, never bounce in
  product UI.
- Animate `transform` and `opacity`, not size or position properties.
- Reduced motion swaps movement for a fade or nothing, and lands on the finished state.

**Check.** Read every computed `transition-duration` and `animation-duration`; anything over
500 ms in product UI needs a reason.

## Finishing

- Spend polish where people look: the first screen, the primary action, and the empty, loading and
  error states. A designed empty state (one sentence, the first action as a button) beats any
  ornament.
- Real words in every mock. "Feature one" and lorem ipsum hide the real layout problems.
- Test the extremes: one item, two hundred items, a very long name, zoomed to 200%, 320 px wide.
- Polish by effect (glass, glow, gradient text, grain on everything, an icon in a tinted circle on
  every card, an accent bar on a rounded card) reads as generated. SLOP.md has the list.

## Beauty is not evidence

People rate attractive interfaces as easier to use and forgive small faults (the
aesthetic-usability effect, NN/g; Kurosu and Kashimura, 1995). It never covers a broken flow, and it
makes a polished mock look tested when it is not. Look good for the person; never take your own
polish as proof the task works. Do the task end to end, by keyboard, at 390 px, before calling it
done.
