# Specimen library

Nine reference-grade sites, each doing a **different job**. All stacks, typefaces and palettes below were verified by reading source on 2026-08-20, not taken from blog posts.

Read the one that matches the job. Do not read all nine.

---

## 01 — Alaris · Studio shopfront, personality-led
**alaris.studio** · Melbourne web studio

| | |
|---|---|
| Stack | Hand-written vanilla. No framework, no animation library. Cloudflare static. |
| Type | Anton (display) + Helvetica/Arial |
| Palette | `#ff3f0a` on `#0a0a0a`, cream `#f4f0e8`, paper `#fffaf0` |
| Scale | 12 CSS variables, 16 keyframes, 394 `clamp()` calls |

**The job:** convince a stranger in ten seconds that these people have taste and are fun to work with. It is a shopfront, not a funnel.

**Steal:**
- **The two-frame boil.** 20 of its 22 image sequences are *two frames* at 1 to 4 fps. Hand-drawn artwork that feels alive for the cost of two small WebPs.
- **Hand-drawn borders as inline SVG in a custom property**, two paths per card (one heavy stroke, one lighter offset pass at 58% opacity), and **the video masked by that same path**. Looks drawn, not pasted.
- **Smooth the progress, not the scroll.** `p += (target - p) * 0.18` in rAF. Native scroll stays native.
- The `.reveal` system, optical type scale, the grain overlay.

**Do not steal:** the architecture. 1,006 of 3,773 rules use `!important`, `.site-header` is restyled twelve times, dead reverted code is left in place.

**Reach for it when:** a small studio, creative or trade needs personality and craft signal more than conversion mechanics.

---

## 02 — Linear · B2B SaaS product marketing
**linear.app**

| | |
|---|---|
| Stack | Next.js |
| Type | InterVariable + a mono. (One of the few places Inter is *correct*, because the product itself is Inter.) |
| Palette | `#08090a` near-black ground, `#e4e5e9` light, accents `#4354b8` indigo, `#e5591d` orange, `#f79ce0` pink |

**The job:** make a project tracker feel like a category-defining product. Sells taste as a proxy for quality.

**Steal:**
- **Section-scoped accent.** `--accent: var(--color-green)` redefined per section, so each block owns a hue while components stay generic.
- **`--grid-areas-default` / `--grid-areas-mobile` / `--grid-areas-desktop`** swapping `grid-template-areas` through a variable instead of rewriting layout per breakpoint.
- Semantic state tokens (`--diff-new-color: #27A644`, `--diff-old-color: #F34E52`) kept separate from brand accents.
- `--glow-opacity: 0.02` and `0.03`. That is the level a real glow sits at. Yours is almost certainly ten times too strong.

**Reach for it when:** a software product needs to look inevitable. Best template for structure, section rhythm and how to show a UI product.

---

## 03 — Resend · Developer tool with taste
**resend.com**

| | |
|---|---|
| Stack | Next.js |
| Type | **ABC Favorit** (Dinamo) + **Domaine** (Klim) + **Commit Mono** + Inter Variable |
| Palette | Greys on black, warm grey `#c7c2bc` |

**The job:** make an email API feel considered. Proves developer tools do not have to look like developer tools.

**Steal:**
- **The type stack is the whole trick.** A grotesque with personality, a high-contrast serif for display, and a beautiful free mono. Three voices, no Inter in sight for display.
- **Animated conic-gradient borders**: `--border-color: conic-gradient(from var(--angle) at 50% 50%, ...)` with `--angle` registered via `@property` and animated. That is the rotating glow border.
- Commit Mono is free and better than the mono you were going to use.

**Reach for it when:** anything technical that must not look generic. The closest reference for a developer-facing product.

---

## 04 — Attio · Conversion-led signup funnel
**attio.com**

| | |
|---|---|
| Stack | Next.js |
| Type | Inter + **Inter Display** + **Tiempos Text** (Klim) including italic |
| Palette | Near-monochrome cool greys `#e6e7ea` `#eeeff1` `#cdced2` `#242629` `#101112`, single accent `#266df0` |

**The job:** move a buyer from landing to signup. The most disciplined page in the library.

**Steal:**
- **One accent, and only one.** Everything else is a cool grey ramp. This is why the CTA is impossible to miss.
- **Primitive to semantic token mapping**: `--color-primary-background: var(--color-black-50)`, `--color-weak-stroke: var(--color-black-300)`. Components reference meaning, never raw values.
- **Container query units**: `--cell-h: clamp(3.5rem, 7.8cqw, 5rem)`. Sizes off the container, not the viewport. Better than `vw` inside components.
- **`--idx: 0..20`** written onto repeated elements to drive stagger from CSS.
- Tiempos Text italic as the editorial counterpoint to a UI sans. Cheap sophistication.

**Reach for it when:** the page has one job and that job is signup. Use this for the sauna funnel, not Alaris.

---

## 05 — Lando Norris · Immersive brand / campaign
**landonorris.com** by **OFF+BRAND** · Awwwards Site of the Year

| | |
|---|---|
| Stack | **Webflow** + **Rive** + heavy WebGL/canvas |
| Type | **Brier** (display) |
| Palette | **`#d2ff00` acid lime** on `#101400` near-black |

**The job:** a personality at global scale. Entertainment first, information second.

**Steal:**
- **The palette choice.** An F1 driver site that refuses the obvious McLaren papaya and goes acid lime on black instead. The obvious brand colour is usually the wrong one.
- **Rive over Lottie** for interactive character animation. State machines, tiny files, responds to input.
- **The stack lesson.** The best site on the internet this year is on **Webflow**. Stop equating hand-coding with quality.

**Do not assume:** that heavy WebGL is required. Igloo Inc (Site of the Year 2024) held ~1s LCP with a full WebGL scene, so it is possible, but it is expert work.

**Reach for it when:** a launch, a campaign or a personal brand where being memorable beats being efficient.

---

## 06 — Scout Motors · High-ticket commerce
**scoutmotors.com** · Awwwards E-commerce of the Year nominee

| | |
|---|---|
| Stack | **Astro** + Lenis + Swiper |
| Type | Bespoke **Scout Sans** in Regular, Medium, **SemiCondensed** and **Wide** + IBM Plex Mono |
| Palette | Cinematic, imagery-led |

**The job:** sell a vehicle nobody can buy yet. Builds heritage through a full-screen scroll narrative before the pre-order ask appears.

**Steal:**
- **Earn the ask.** The CTA arrives only after the story. Correct for considered, high-value purchases and wrong for a $9 SaaS.
- **A width-axis type family.** Regular, SemiCondensed and Wide from one family gives enormous range with total consistency. If you cannot commission one, use a variable font with a width axis.
- IBM Plex Mono for specs and data. Free, industrial, credible.

**Reach for it when:** the price is high, the decision is slow, and the product needs desire built before the button appears. This is the sauna-installation reference, not Alaris.

---

## 07 — Stripe Press · Editorial, long-form, reading
**press.stripe.com**

| | |
|---|---|
| Stack | Custom |
| Type | Serif-led, editorial gravitas |
| Palette | **Per-book colour worlds** |

**The job:** make reading online feel like owning an object.

**Steal — this is the best colour system in the library:**

Every book carries its own `--backgroundColor` and `--backgroundGradient`. Real values from source:

```
#143199  deep ultramarine      #4D1A28  oxblood
#201E8E  indigo                #93935F  olive
#2328A0  cobalt                #C1B676  sand
#0d121f  midnight              #96DCED  sky
#442C25  bitter chocolate      #FFB55E  amber
#1D1A15  bistre                #0AEB9A  mint
#6E665B  warm taupe            #ffd943  signature yellow

linear-gradient(#ff815a, #ffaf5b, #ffdf5b)
linear-gradient(#e7d4e5, #cad9e5, #eeebcc, ...)
```

- **Give each item its own colour world** instead of one brand palette flattened across everything. Works for case studies, packages, collections, chapters.
- Those are not tints of one hue. They are saturated, confident, and mostly *not* on any AI's shortlist.
- Serif for the reading, sans for navigation. Never mix the roles.

**Reach for it when:** anything that must be read rather than scanned. Docs, case studies, a long about page, an essay.

---

## 08 — Aesop · Restrained luxury, retail, wellness
**aesop.com**

| | |
|---|---|
| Stack | Commerce platform |
| Type | **Suisse Int'l** (Swiss Typefaces) + **Zapf Humanist** (Optima) |
| Palette | `#f6f5e8` warm cream, `#fffef2` paper, `#000000`, `#333333`. Near-monochrome. |

**The job:** sell soap at a premium through restraint alone. Almost no colour, almost no motion, total discipline.

**Steal:**
- **Zapf Humanist / Optima.** A humanist sans with flared stems that reads as both classical and modern. Essentially never used on the web and no AI will ever suggest it.
- **`#f6f5e8` and `#fffef2`.** Warm off-whites with a green-yellow bias, not the flagged `#F4F1EA` AI cream. The difference is small and completely legible to the eye.
- **Restraint as the differentiator.** Two typefaces, four colours, generous space, no animation. When everyone else is moving, stillness reads as expensive.

**Reach for it when:** wellness, beauty, hospitality, spa, sauna retail, or any premium physical product.

---

## 09 — Rauno Freiberg · Personal site, craft signal
**rauno.me**

| | |
|---|---|
| Stack | Next.js |
| Type | System / variable via CSS custom properties |
| Palette | Near-monochrome with `#ff484c` and `#0000ff` |

**The job:** prove craft to other designers and engineers with almost nothing on the page.

**Steal:**
- **Pure `#0000ff`.** Nobody uses unmodified web blue any more, which is exactly why it reads as deliberate.
- Interaction detail over visual volume. A personal site is judged on how things *feel* under the cursor, not on how much is on screen.
- Small, fast, no hero image, no scroll narrative. Confidence looks like this.

**Reach for it when:** a personal site, a CV, an about page, or anything where the audience is peers rather than customers.

---

## Cross-cutting findings

**There is no correct stack.** Site of the Year is Webflow. Linear, Attio, Resend and Rauno are Next.js. Lusion and Scout Motors are Astro. Alaris is hand-written vanilla. Choose by what ships the idea.

**The premium tell is the typeface, not the effect.** Every specimen that reads as expensive is using a licensed face from Klim, Dinamo or Swiss Typefaces, or a bespoke one. See TYPE.md for the free faces that get closest.

**One accent, or a set of deliberate worlds.** Attio uses exactly one hue. Stripe Press gives every item its own. Both work. What never works is three brand colours sprayed evenly across everything.

**Further reading, not yet torn down:** Lusion (lusion.co, Astro + WebGL, Site of the Year 2023), Igloo Inc (igloo.inc, Site of the Year 2024, ~1s LCP with full WebGL), by-kin.com, Messenger (Developer Site of the Year).
