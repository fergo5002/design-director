# Typography

The single fastest way to look AI-generated is a default typeface. The single fastest way to look expensive is a good one. Type does more work than colour, layout or motion.

## Banned unless the brief names them

**Inter, Space Grotesk, Poppins, Montserrat, Playfair Display, Roboto, Open Sans, Lato, Nunito, Raleway, Plus Jakarta Sans, Bebas Neue, Oswald, DM Sans as a display face.**

Not because they are bad. Inter is an excellent UI face. They are banned because they are the shortlist every model reaches for, so using one announces that nobody chose. Two exceptions:

- **Inter is correct when the product itself is Inter** (Linear does this deliberately).
- **IBM Plex Mono and JetBrains Mono are fine for data and specs.** Monos have not been ruined the same way.

Also banned as a *pairing*: any Google serif display over any Google geometric sans. That is the 2023 AI house style.

## Fontshare is the answer most of the time

**fontshare.com** (Indian Type Foundry). Free for commercial use, professional quality, and almost entirely absent from AI output. Start here before Google Fonts.

| Face | What it is | Use for |
|---|---|---|
| **Switzer** | Clean neutral grotesque, huge weight range | The Helvetica/Suisse job. Best default body sans. |
| **General Sans** | Geometric with warmth | Product UI, friendly brands |
| **Satoshi** | Modern grotesque, slightly technical | SaaS, dev tools |
| **Cabinet Grotesk** | Characterful display grotesque | Headlines with personality |
| **Clash Display** | Heavy, condensed, confident | Big statement type |
| **Zodiak** | High-contrast display serif | Luxury, editorial display |
| **Sentient** | Humanist reading serif | Long-form body copy |
| **Gambetta** | Elegant old-style serif | Editorial, considered brands |
| **Erode** | Serif with rough, organic edges | Craft, artisan, hand-made brands |
| **Melodrama** | Dramatic contrast display serif | Fashion, beauty, hospitality |
| **Supreme** | Neo-grotesque, slightly quirky | Modern, playful but serious |
| **Panchang** | Display with unusual counters | Distinctive headlines |

## Free faces outside Fontshare worth reaching for

| Face | Source | Why |
|---|---|---|
| **Instrument Serif** | Google | High-contrast display serif. The best free stand-in for Domaine or Signifier. Luxury and editorial. |
| **Bricolage Grotesque** | Google, variable | Optical corrections baked in, feels hand-touched. Studios, zines, craft brands. Not for a bank. |
| **Hanken Grotesk** | Google | The best free "bouba grotesk". Closest free thing to Söhne. Warm where Inter is clinical. |
| **Host Grotesk** | Google | Clean grotesque with subtle character in the letterforms. |
| **Albert Sans** | Google | Genuinely underrated body face. Geometric humanist. |
| **Archivo** | Google, variable **width axis** | The free way to get Scout Motors' Regular / SemiCondensed / Wide range from one family. |
| **Roboto Flex** | Google, variable | Enormous axis range if you need extreme control. Ignore that it is Roboto-named. |
| **Newsreader** | Google, variable | Reading serif built for screens. The free Tiempos. |
| **Fraunces** | Google, variable | `SOFT` and `WONK` axes. Warm, characterful display serif. |
| **Geist / Geist Mono** | Vercel, free | Neutral and clean. Fine for dev tools where Inter is banned. |
| **Commit Mono** | Free | Beautiful, customisable mono. Better than the mono you were going to pick. Resend uses it. |
| **Departure Mono** | Free | Pixel/retro mono. Technical, playful, distinctive. |
| **IBM Plex family** | Free | Sans, Serif, Mono, Condensed. Industrial and credible. Scout Motors uses Plex Mono. |
| **Anton** | Google | Free heavyweight condensed display. Alaris's whole hero. Still works. |
| **Syne** | Google | Genuinely odd display face. Art, culture, events. |

## The premium tier, and what it costs

Every specimen that reads as expensive uses one of these. Worth knowing the names so you can recognise them and price them.

| Foundry | Faces | Seen on |
|---|---|---|
| **Klim** (klim.co.nz) | Söhne, Tiempos, Signifier, Domaine, Founders Grotesk, Untitled Sans, Calibre | Attio (Tiempos), Resend (Domaine) |
| **Dinamo** (abcdinamo.com) | ABC Favorit, ABC Diatype, ABC Monument Grotesk, ABC Whyte | Resend (ABC Favorit) |
| **Swiss Typefaces** | Suisse Int'l, Suisse Works | Aesop |
| **Pangram Pangram** | PP Neue Montreal, PP Editorial New, PP Right Grotesk, PP Mori | Widely, in studio work |
| **Grilli Type** | GT America, GT Walsheim, GT Sectra, GT Alpina | Editorial and brand work |
| **Monotype** | Optima / Zapf Humanist | Aesop |

**Never pirate these.** If one is genuinely right, name it to the client with the licence cost and offer the free substitute below in the meantime.

## Substitution table

| Want | Free substitute |
|---|---|
| Söhne | Hanken Grotesk, or Switzer |
| Tiempos Text | Newsreader, or Sentient |
| Signifier / Domaine Display | Instrument Serif, or Zodiak |
| ABC Favorit | General Sans, or Supreme |
| Suisse Int'l | Switzer, or Archivo |
| PP Neue Montreal | General Sans, or Satoshi |
| GT America | Archivo, or Switzer |
| Aperçu | Cabinet Grotesk |
| Circular | General Sans |
| Scout Sans (width axis) | Archivo variable, or Roboto Flex |
| **Optima / Zapf Humanist** | **No good free match exists.** Flared humanist sans is a real gap. Either licence URW Classico (cheap, metric-compatible) or change direction to Sentient and accept it is a different feeling. Do not pretend a geometric sans is close. |

## Pairing rules

For a brand name, do not automatically italicise the second word or add a decorative full stop. Follow the supplied identity and explicit feedback. A no-overflow check does not establish that a name has enough space around it (17 September 2026).

1. **Two faces. Three only if you have real data**, and then the third is a mono.
2. **Give each a job and never let them swap.** Display, body, utility. Stripe Press: serif reads, sans navigates. Break this and the page looks confused.
3. **Contrast the skeletons, not just the weights.** Grotesque + high-contrast serif works. Two grotesques do not, they just look like a mistake.
4. **If the display face is loud, the body face disappears.** Clash Display needs Switzer, not Cabinet Grotesk.
5. **Match the era.** Optima and Suisse Int'l both read mid-century modernist, which is why Aesop works. Instrument Serif and Satoshi do not share a century.

## Optical scaling (this is most of the craft)

Verified from Alaris and consistent with every good specimen. **As type gets bigger, tighten leading and tracking. As it gets smaller, open them.**

```css
.mega     { font-size:clamp(54px,11vw,180px); line-height:.83; letter-spacing:-.08em }
.display  { font-size:clamp(44px, 8vw,130px); line-height:.88; letter-spacing:-.07em }
.headline { font-size:clamp(36px, 6vw, 88px); line-height:.94; letter-spacing:-.06em }
.body     { font-size:clamp(16px,1.4vw, 20px); line-height:1.55; letter-spacing:0 }
```

Also non-negotiable:

- Running text at **60 to 75 characters**. Use `max-width: 65ch`.
- `text-wrap: balance` on headings, `text-wrap: pretty` on body.
- `font-variant-numeric: tabular-nums` anywhere digits align in a column or change in place.
- Never centre more than three lines of running text.
- Uppercase always gets positive tracking. Lowercase display always gets negative.

## Implementation

- **Next.js**: `next/font/google` or `next/font/local`. Self-hosts, no layout shift, no Google request at runtime.
- **Variable fonts** whenever available. One file, every weight, smaller than two statics.
- **Subset aggressively.** `latin` only unless there is a reason.
- **Published Artifacts**: the CSP blocks every external host, so a linked webfont
  silently falls back to Arial and the page is failed. This is **solved**, and the
  earlier advice to "compose a system stack instead" was defeatism:

  ```bash
  python tools/inline_fonts.py \
      --css "https://api.fontshare.com/v2/css?f[]=switzer@400,500,700" \
      --family Switzer --charset latin-irish --out switzer.css
  ```

  It parses the foundry's CSS, downloads each real `woff2`, subsets it with
  fonttools, and emits base64 `@font-face` rules to paste into a `<style>` block.
  Measured: Switzer at three weights plus Zodiak at two, subset to Latin and the
  fada vowels, came to **53 KB** of inlined CSS from 92 KB of source. Use
  `--charset latin-irish` for anything with Irish place names, `--text "..."` to
  subset to exactly the characters on the page when you only need numerals.

  Splice it at build time against a `/*@FONTS@*/` marker rather than pasting a
  50 KB base64 blob into the file you are editing.
- Always re-run any text measurement on `document.fonts.ready`. Layout that depends on text width is wrong until the font lands.
