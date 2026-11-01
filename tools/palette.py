#!/usr/bin/env python3
"""
palette.py — build perceptually even colour ramps and prove the contrast.

Why this exists: COLOUR.md says "bias the neutrals toward the accent", "check the
accent on both grounds" and "body text 4.5:1". None of those are things you can do
by eye, and a checklist you cannot execute is a wish. This executes them.

Two jobs:

  ramp    Generate a ramp in OKLCH (perceptually uniform) and print sRGB hex.
          Even steps in OKLCH look even. Even steps in HSL do not — that is why
          a hand-built Tailwind-style ramp always has a dead patch in the middle.

  check   Take a palette as name=hex pairs and report WCAG 2.1 contrast for every
          foreground against every ground, flagging what fails and at what size.

Usage
-----
  # a cold-sea ramp: dark slate-green to pale sea-glass, 6 steps
  python palette.py ramp --hue 168 --chroma 0.020:0.045 --light 0.30:0.86 --steps 6

  # a neutral ramp biased toward a magenta accent (the "never pure grey" rule)
  python palette.py ramp --hue 340 --chroma 0.006:0.014 --light 0.18:0.95 --steps 8

  # prove the palette
  python palette.py check --ground "paper=#efe9d6,water=#101410" \
      --fg "ink=#12140f,accent=#c3006b,muted=#5d6152"

Exit code is 1 if any pair marked required fails, so it can gate a build.

No dependencies beyond the standard library.
"""

import argparse
import math
import sys


# ---------- OKLCH -> sRGB ----------

def _srgb_gamma(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055


def oklch_to_hex(L: float, C: float, H: float):
    """L 0..1, C 0..~0.4, H degrees. Returns (hex, clipped?)."""
    a = C * math.cos(math.radians(H))
    b = C * math.sin(math.radians(H))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )
    clipped = any(v < -0.0005 or v > 1.0005 for v in lin)
    rgb = [max(0.0, min(1.0, _srgb_gamma(max(0.0, min(1.0, v))))) for v in lin]
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in rgb), clipped


# ---------- WCAG contrast ----------

def hex_to_rgb(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h: str) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def verdict(ratio: float) -> str:
    if ratio >= 7:
        return "AAA body"
    if ratio >= 4.5:
        return "AA body"
    if ratio >= 3:
        return "AA large / UI only"
    return "FAIL"


# ---------- commands ----------

def parse_range(s: str, name: str):
    if ":" in s:
        a, b = s.split(":", 1)
        return float(a), float(b)
    v = float(s)
    return v, v


def cmd_ramp(a) -> int:
    c0, c1 = parse_range(a.chroma, "chroma")
    l0, l1 = parse_range(a.light, "light")
    h0, h1 = parse_range(a.hue, "hue")
    n = a.steps
    print(f"  {'step':<6}{'hex':<10}{'L':<7}{'C':<8}{'H':<7}  on white   on black")
    hexes = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0
        L = l0 + (l1 - l0) * t
        C = c0 + (c1 - c0) * t
        H = h0 + (h1 - h0) * t
        hx, clipped = oklch_to_hex(L, C, H)
        hexes.append(hx)
        flag = "  <- out of sRGB gamut, clipped" if clipped else ""
        print(
            f"  {i:<6}{hx:<10}{L:<7.3f}{C:<8.4f}{H:<7.1f}  "
            f"{contrast(hx, '#ffffff'):5.2f}     {contrast(hx, '#000000'):5.2f}{flag}"
        )
    print("\n  " + " ".join(hexes))
    if a.css_var:
        print()
        for i, hx in enumerate(hexes):
            print(f"  --{a.css_var}-{i}: {hx};")
    return 0


def blend(fg: str, bg: str, alpha: float) -> str:
    """Composite fg over bg at alpha, the way the browser will."""
    f, b = hex_to_rgb(fg), hex_to_rgb(bg)
    return "#%02x%02x%02x" % tuple(
        round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3)
    )


def cmd_blend(a) -> int:
    """Check text against a GROUND THAT HAS A TINT ON IT.

    Tokens passing in isolation proves nothing once a wash, an overlay or a
    semi-transparent scrim sits between the text and its background. This is
    where real pages fail their own contrast budget.
    """
    over = dict(p.split("=", 1) for p in a.over.split(",") if p.strip())
    fgs = dict(p.split("=", 1) for p in a.fg.split(",") if p.strip())
    tints = [t.strip() for t in a.tint.split(",") if t.strip()]
    worst, failures = 99.0, []

    for gname, g in over.items():
        for tint in tints:
            composited = blend(tint, g, a.alpha)
            print(f"\n  {tint} at {a.alpha:.0%} over {gname} {g}  ->  {composited}")
            for fname, f in fgs.items():
                r = contrast(f, composited)
                mark = "   <-- " + ("FAILS" if r < 3 else "large text only") if r < 4.5 else ""
                print(f"    {fname:<14}{f:<10}{r:6.2f}  {verdict(r)}{mark}")
                if r < 4.5:
                    failures.append(f"{fname} on {tint}@{a.alpha:.0%}/{gname} = {r:.2f}")
                worst = min(worst, r)

    print(f"\n  worst composited pair: {worst:.2f}:1")
    if failures:
        print("\n  Under 4.5:1 once composited:")
        for f in failures:
            print(f"    - {f}")
        print("  Lower the alpha, or move the tint off the text.")
    if a.strict and failures:
        return 1
    return 0


def cmd_check(a) -> int:
    grounds = dict(p.split("=", 1) for p in a.ground.split(",") if p.strip())
    fgs = dict(p.split("=", 1) for p in a.fg.split(",") if p.strip())
    worst, failures = 99.0, []

    for gname, g in grounds.items():
        print(f"\n  ground {gname} {g}")
        print(f"  {'foreground':<16}{'hex':<10}{'ratio':<9}verdict")
        for fname, f in fgs.items():
            r = contrast(f, g)
            v = verdict(r)
            mark = "  <-- " + ("FAILS EVERYTHING" if r < 3 else "body text not allowed") if r < 4.5 else ""
            print(f"  {fname:<16}{f:<10}{r:<9.2f}{v}{mark}")
            if r < 4.5:
                failures.append(f"{fname} on {gname} = {r:.2f}")
            worst = min(worst, r)

    print(f"\n  worst pair in the palette: {worst:.2f}:1")
    if failures:
        print("\n  Below 4.5:1, so these may not carry body text:")
        for f in failures:
            print(f"    - {f}")
        print("  That is fine for a fill, a rule or a large numeral. It is not fine for a sentence.")
    if a.strict and failures:
        return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("ramp", help="build a perceptually even OKLCH ramp")
    r.add_argument("--hue", default="200", help="degrees, or start:end to drift the hue")
    r.add_argument("--chroma", default="0.02", help="0..0.4, or start:end")
    r.add_argument("--light", default="0.2:0.9", help="0..1, or start:end")
    r.add_argument("--steps", type=int, default=6)
    r.add_argument("--css-var", help="also emit --name-0 .. --name-n custom properties")
    r.set_defaults(fn=cmd_ramp)

    c = sub.add_parser("check", help="WCAG contrast for every foreground on every ground")
    c.add_argument("--ground", required=True, help="name=#hex,name=#hex")
    c.add_argument("--fg", required=True, help="name=#hex,name=#hex")
    c.add_argument("--strict", action="store_true", help="exit 1 if anything is under 4.5:1")
    c.set_defaults(fn=cmd_check)

    b = sub.add_parser("blend", help="contrast against a ground that has a tint over it")
    b.add_argument("--over", required=True, help="the base ground(s): name=#hex,...")
    b.add_argument("--tint", required=True, help="the overlay colour(s): #hex,#hex,...")
    b.add_argument("--alpha", type=float, required=True, help="overlay opacity 0..1")
    b.add_argument("--fg", required=True, help="text colours: name=#hex,...")
    b.add_argument("--strict", action="store_true")
    b.set_defaults(fn=cmd_blend)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
