# Craft

Genre-agnostic technique. These apply whether you are building Aesop's restraint or Alaris's noise. Copy-paste and adapt.

## Motion

### Smooth the progress, never the scroll

Lerp an animation value toward true scroll progress. Native scroll stays native, so trackpads, find-in-page and accessibility settings keep working. This is why you rarely need Lenis.

```js
let target = 0, smooth = 0, raf = null;
const measure = () => {
  const r = section.getBoundingClientRect();
  target = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight)));
};
const tick = () => {
  raf = null;
  const d = target - smooth;
  smooth += d * 0.18;                       // 0.12 slower, 0.25 snappier
  if (Math.abs(d) < 0.0012) smooth = target; // snap, kills jitter
  render(smooth);
  if (Math.abs(target - smooth) > 0.0012) raf = requestAnimationFrame(tick);
};
addEventListener("scroll", () => { measure(); if (!raf) raf = requestAnimationFrame(tick); }, { passive: true });
```

### JS writes variables, CSS owns the look

Never set `transform` from script. Set one number, derive everything in `calc()`.

```css
.tile{
  transform: translate3d(0, calc(16vh - (var(--p,0) * 16vh)), 0)
             scale(calc(.9 + (var(--p,0) * .1)))
             rotate(var(--r));
}
.backdrop{ transform: translate3d(0, calc((var(--p) - .45) * -5vh), 0) } /* parallax, same var */
```

### The reveal system: one class, automatic choreography

Add `class="reveal"` to a block. Script inspects children and assigns roles with a 90ms stagger. No per-element config in markup.

```css
.rv-mask   { display:block; overflow:hidden;
             padding:.2em .06em .22em; margin:-.2em -.06em -.22em }
.rv-mask-i { display:block; transform:translateY(120%);
             transition:transform .95s var(--ease-rise); transition-delay:var(--rv-d,0ms) }
.is-visible .rv-mask-i { transform:none }

.rv-wipe { clip-path:inset(0 100% 0 0); transition:clip-path .72s var(--ease-rise) }
.is-visible .rv-wipe { clip-path:inset(0 -2% 0 0) }

.rv-fade { opacity:0; transform:translateY(16px);
           transition:opacity .7s var(--ease-rise), transform .8s var(--ease-rise) }
.is-visible .rv-fade { opacity:1; transform:none }
```

Three details nearly everyone gets wrong:
- **Padding plus equal negative margin on the mask.** `overflow:hidden` clips descenders. Pad the clip box out, pull it back, costs no layout.
- **`translateY(120%)`, not 100%.** Extra 20% clears the mask edge.
- **Wipe ends at `-2%`, not 0.** Stops an anti-aliased sliver on the edge.

Observer: `{ rootMargin: "0px 0px -12% 0px" }`, unobserve after firing.

### Stagger from CSS

Write an index onto repeated elements (Attio uses `--idx`, Alaris uses `--rv-d`) and let CSS do the delay. No JS timers.

```css
.item{ transition-delay: calc(var(--idx) * 60ms) }
```

### Easing

```css
--ease:       cubic-bezier(.2,.75,.2,1);    /* general UI */
--ease-rise:  cubic-bezier(.65,0,.35,1);    /* symmetric, text reveals */
--ease-punch: cubic-bezier(.16,1.28,.30,1); /* overshoots past 1, entrances */
```

Durations: micro-interaction 150 to 250ms, reveal 600 to 950ms, page transition 350 to 500ms. **Exit faster than enter.**

Correction, 9 October 2026: `--ease-rise` (symmetric) suits a tracked move from A to B, such as a camera move or a line drawing on. A text reveal is an entrance, so it decelerates: use `--ease`. Take every duration and curve from the project's motion tokens; if it has none, define them once (see the Motion section) and never improvise a curve per component. Stagger a list the reader reads in order; do not stagger a group meant to move as one (Chevalier et al. 2014 found it no help or worse).

### Platform first (October 2026)

Reach for the browser before a library for small UI motion. Safe in Chromium, Safari and Firefox: same-document View Transitions (`document.startViewTransition`, Baseline since 14 October 2025), `@starting-style` for entry animations, `linear()` easing, the Web Animations API, `@property`, anchor positioning. Cross-document View Transitions are missing from Firefox, so use them as a free upgrade on multi-page sites, never for meaning. CSS scroll-driven animations scored 9.1% in stable Firefox on 6 October 2026: decoration only; a scroll explainer's meaning stays on GSAP ScrollTrigger (`scroll-film`). React 19.3 has a stable `<ViewTransition>`. For React product UI the library is Motion 14 (`motion/react`); NumberFlow (MIT, 4.6 KB) for animated figures.

Check UI motion with `motion-library/gauge/web_probe.py` (timing against the token, frame pacing at 1x and 4x CPU on a visible page) rather than by eye in a hidden tab.

### The two-frame boil

Hand-drawn artwork alive for the cost of two images. Alternate two drawings at 1 to 4 fps. Cheaper than Lottie, cheaper than video, and it reads as made by a person.

```css
.boil > :nth-child(1){ animation: bA .667s steps(1,end) infinite }
.boil > :nth-child(2){ animation: bB .667s steps(1,end) infinite }
@keyframes bA{ 0%,49.9%{opacity:1} 50%,100%{opacity:0} }
@keyframes bB{ 0%,49.9%{opacity:0} 50%,100%{opacity:1} }
```

### Reduced motion

```css
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{ animation:none!important; transition:none!important; scroll-behavior:auto!important }
}
```

Then make sure every section lands on its **finished** state, not a broken one. Sticky sections become static, pinned scroll becomes a grid, `opacity:0` becomes 1. This is the step people skip.

## Layout

### `overflow:clip`, never `overflow-x:hidden`

`overflow-x:hidden` on `html`/`body` creates a scroll container and **silently breaks `position:sticky`** for every descendant. This is the single most common cause of "my sticky section stopped working".

```css
html,body{ overflow-x:hidden }
@supports (overflow:clip){ html,body{ overflow-x:clip } }
```

**Both elements.** Setting it on `html` alone leaves `body` as the scroll container
and the page still slides sideways under pressure. This gets shortened to just
`html` constantly, including by whoever wrote this file, and then the bug comes back.

### Container query units inside components

`--cell-h: clamp(3.5rem, 7.8cqw, 5rem)`. Sizes off the container, not the viewport, so a component works anywhere. Attio does this throughout. Better than `vw` for anything that is not full-bleed.

### Grid areas through a variable

Swap the whole layout per breakpoint without rewriting it (Linear):

```css
.block{ grid-template-areas: var(--grid-areas-mobile) }
@media (min-width:900px){ .block{ grid-template-areas: var(--grid-areas-desktop) } }
```

### Auto-fitting display type

How headlines sit exactly edge to edge at any width. Measure, do not guess.

```js
el.style.fontSize = "100px";
el.style.fontSize = Math.max(20, Math.min(100 * avail / el.scrollWidth, 260)) + "px";
```

Re-run on resize, load, `pageshow` and `document.fonts.ready`.

### Spacing

Lay out sibling groups with flex or grid and `gap`. Never per-element margins that collapse or double. Wide content (tables, code, diagrams) gets `overflow-x:auto` on its own container so the body never scrolls sideways.

## Texture and surface

### Grain

About 400 bytes, no network request, and it does more for perceived quality than anything else per byte.

```css
.grain{
  position:fixed; inset:0; z-index:999; pointer-events:none;
  opacity:.055; mix-blend-mode:screen;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.65'/%3E%3C/svg%3E");
}
@media (max-width:860px),(pointer:coarse){ .grain{ display:none } } /* dear on phone GPUs */
```

### Hand-drawn edges without an image

Two wobbly SVG paths in a custom property: one heavy stroke, one lighter offset pass at ~58% opacity. That is what a real marker line looks like. Give each instance a different path and a sub-degree tilt so nothing repeats. Then **mask the content with the same path filled white**, sized ~100.6% so the mask edge hides under the stroke.

### `box-decoration-break: clone`

Any highlighted or padded inline text that might wrap needs this, or the middle lines lose their padding.

```css
.highlight{ background:var(--accent); padding:0 .055em .035em;
            -webkit-box-decoration-break:clone; box-decoration-break:clone }
```

### `@property` so custom properties can animate

An unregistered custom property is a string and jumps between keyframes. Register it and it interpolates.

```css
@property --glow{ syntax:"<length>"; inherits:false; initial-value:0px }
@property --angle{ syntax:"<angle>"; inherits:false; initial-value:0deg }
```

`--angle` plus a `conic-gradient` border is the rotating glow border Resend uses.

## Performance

- **`content-visibility:auto`** with `contain-intrinsic-size: auto 820px` on below-the-fold sections. Skips rendering work until needed.
- **Defer video `preload`** until an observer fires ~420px ahead. Drop to `metadata` on `saveData` or 2g. Pause everything on `pagehide`.
- **Prefetch on hover and focus**, gated off for save-data.
- **Never ship a full-screen fixed blend-mode layer to mobile.** Compositing cost.
- **`background-attachment:fixed` is janky or broken on mobile.** Force `scroll` under `(pointer:coarse)`.
- Reserve space for every image and embed. CLS under 0.1.
- Re-measure anything text-width-dependent on `document.fonts.ready`.
- **Profile any live generative scene before it ships** (a WebGL hero once shipped untested and was called "really laggy"). Headed, GPU-backed Chromium at 1.5x and 2x; split frames by state (holding, changing, pointer, scroll); fresh browser per run, variants interleaved, three rounds, because one browser's runs drift. When the page's own thread is idle, trace every thread: a saturated `CrGpuMain` in `DoRasterCHROMIUM` means the drawing, not the script.
- **Many moving lines go on one canvas, not as live SVG paths.** About 100 SVG paths of 240 points rewritten per frame held 28 frames a second; the same lines on a canvas at exactly one device pixel (`lineWidth = 1 / dpr`, a whole-pixel backing store, the element sized to it) held 55, because Chrome draws strokes that thin on its fast hairline path. A 1 CSS px line on a 2x screen is two device pixels and loses it. Darken the ink by density to keep the weight; cache what does not move in a layer; one precomputed mask for holes and edges.

## Touch is a different design, not a degraded one

```css
@media (hover:none),(pointer:coarse){
  /* pinned scroll section becomes a plain grid */
  .pinned{ height:auto; overflow:visible }
  .pinned .shell{ position:relative; height:auto }
  /* hover-only media never downloads */
  .tile video{ display:none }
  .tile .poster{ opacity:1 }
}
```

- Every hover interaction needs a touch path. Auto-play at ~42% visibility instead of on hover.
- 44x44 minimum targets, 8px apart.
- Test `(hover:none)` and `(pointer:coarse)` separately. A touchscreen laptop is both.

## Controls

**A form control left in its browser default state is an AI tell**, and on a page
where everything else has been designed it is the one element that announces nobody
looked. A stock `<input type=range>` with `accent-color` set is still a stock range.

Before styling one, ask whether it should exist. A range scrubber sitting above a
row of twelve month buttons is two controls for one job; deleting it removed the
ugliest element on the page and lost nothing, because the buttons already carried
click, touch and screen-reader support.

When a set of choices *is* the control, use a **radiogroup with roving tabindex**
rather than a slider. One tab stop for the whole group, arrows to move within it,
which is what a screen reader user expects and what a keyboard user will try.

```js
function mark(nodes, sel){                     // one tab stop, the rest -1
  [...nodes].forEach((n, i) => {
    const b = n.tagName === "BUTTON" ? n : n.querySelector("button");
    b.setAttribute("aria-checked", i === sel ? "true" : "false");
    b.tabIndex = i === sel ? 0 : -1;
  });
}
container.addEventListener("keydown", e => {
  const n = {ArrowRight:+1, ArrowDown:+1, ArrowLeft:-1, ArrowUp:-1}[e.key];
  if (n == null) return;
  e.preventDefault();
  const next = (get() + n + count) % count;
  set(next);
  container.querySelectorAll("button")[next].focus();
});
```

Container gets `role="radiogroup"` and a label; each button `role="radio"` and
`aria-checked`. Use `aria-checked`, not `aria-pressed`, and match your CSS selectors
to it.

## Charts that get scrubbed

Separate a **static layer** from a **cursor layer**. Rebuild the static layer only
when the size, the dataset or a display option changes; on scrub, move three
attributes. Rebuilding the whole SVG on every `pointermove` works but is wasteful,
and it makes every other performance problem harder to see.

Guard the `ResizeObserver` on the dimension you actually care about, or a mutation
that nudges layout re-enters it:

```js
new ResizeObserver(() => {
  const w = chart.clientWidth;
  if (w && w !== lastW) { lastW = w; scheduleLayout(); }
}).observe(chart);
```

Set the `viewBox` from the **measured pixel size** so one SVG unit is one CSS pixel.
Then hairlines stay at 1px and axis text stays at its true size at every width,
which a fixed `viewBox` cannot do. Put long labels in HTML beside the SVG rather
than inside it, or they scale with the drawing.

## Auditing in a browser without fooling yourself

**Run `tools/instrument-check.js` first.** Paste it into
`javascript_tool` or `browser_evaluate` before diagnosing any rendering, layout,
freeze or timeout problem. It checks the measurement path rather than the page,
returns `CLEAR` / `USABLE WITH CAVEATS` / `INSTRUMENT DEGRADED`, and cannot hang
because it races rAF against `setTimeout`. Everything below is what it tests, and
the reason each test is in it.

Three ways this wastes an hour, all encountered in one session:

- **A backgrounded tab does not fire `requestAnimationFrame`.** Any probe that
  `await`s a rAF will hang, and screenshots of a hidden tab time out. This looks
  exactly like a frozen renderer. Measured 2026-08-21: **hidden is the default
  state** for MCP browser work, so this is the normal condition rather than the
  unlucky one. Check `document.visibilityState` **before** diagnosing anything,
  and foreground the tab you are auditing.
- **`getComputedStyle` can report a stale colour** for elements created in script
  while the rendering is correct. Confirm any computed-style finding against actual
  pixels before you "fix" it.
- **Serving a bare Artifact fragment over a local server is a different document.**
  No doctype means quirks mode; no `<meta charset>` means mojibake. Wrap your local
  preview exactly the way the host wraps it, and keep the `<script>` pure ASCII
  (`°`, not `°`) so the charset cannot matter.

Bisect properly when something does break: strip one variable at a time, in a fresh
tab, and establish a known-good baseline first. A minimal page that loads instantly
tells you whether the harness or the page is at fault, and that is the only question
worth answering first.

## Accessibility floor

- `:focus-visible` on everything interactive, with `outline-offset`. Never remove without replacing.
- Contrast 4.5:1 body, 3:1 large and UI edges. Check the accent on both grounds.
- A skip link, and `.sr-only` for icon-only controls.
- Semantic headings in order. One `h1`.
- `prefers-reduced-motion` landing on the finished state.
- Real `alt` text, or `alt=""` when decorative. Never a filename.
