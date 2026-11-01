#!/usr/bin/env python3
"""
inline_fonts.py — turn a webfont into an inlined, subset @font-face block.

Why this exists: published Artifacts run under a CSP that blocks every external
host, fonts included. Fontshare, Google Fonts and every other CDN are unreachable.
A page that links one silently falls back to Arial, which is a failed page.

This downloads the real files, subsets them to only the glyphs you need, and
emits base64 @font-face rules you can paste straight into a <style> block.

Usage
-----
  # From a Fontshare CSS URL (it parses every @font-face in the response)
  python inline_fonts.py \
      --css "https://api.fontshare.com/v2/css?f[]=switzer@400,500,700" \
      --family Switzer --charset latin-irish --out switzer.css

  # From a direct font file URL
  python inline_fonts.py --url https://.../font.woff2 \
      --family Zodiak --weight 100 --charset numerals --out zodiak.css

  # Subset to exactly the characters used on the page (smallest possible)
  python inline_fonts.py --css "..." --family Zodiak --text "An Fharraige 0123456789°" ...

Charsets
--------
  latin        ASCII printable + common typographic punctuation
  latin-irish  latin + the fada vowels (ÁÉÍÓÚáéíóú) — use for any Irish copy
  numerals     digits, degree, arrows, maths signs, minimal punctuation
  <literal>    anything else is treated as a literal character list

Requires: fonttools, brotli  (pip install fonttools brotli)
"""

import argparse
import base64
import io
import re
import sys
import urllib.request

LATIN = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
    " «»‐–—‘’“”•…"
    "°×÷−©®™·′″"
)
CHARSETS = {
    "latin": LATIN,
    "latin-irish": LATIN + "ÁÉÍÓÚáéíóú",
    "numerals": "0123456789.,:-+/°–—→↑↓←− ",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
FACE_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)


def fetch(url: str) -> bytes:
    if url.startswith("//"):
        url = "https:" + url
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_css(css: str):
    """Yield (woff2_url, weight, style) for every @font-face in a CSS response."""
    for block in FACE_RE.findall(css):
        m = re.search(r"url\(['\"]?([^'\"\)]+\.woff2)['\"]?\)", block)
        if not m:
            continue
        w = re.search(r"font-weight:\s*(\d+)", block)
        s = re.search(r"font-style:\s*(\w+)", block)
        yield m.group(1), int(w.group(1)) if w else 400, s.group(1) if s else "normal"


def subset(raw: bytes, chars: str) -> bytes:
    from fontTools.subset import Subsetter, Options
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(raw))
    opts = Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    opts.layout_features = ["kern", "liga", "calt", "tnum", "onum", "frac", "ccmp", "locl"]
    opts.notdef_outline = True
    opts.recalc_bounds = True
    sub = Subsetter(options=opts)
    sub.populate(unicodes=[ord(c) for c in set(chars)])
    sub.subset(font)
    out = io.BytesIO()
    font.flavor = "woff2"
    font.save(out)
    return out.getvalue()


def face_rule(family: str, weight: int, style: str, data: bytes, display: str) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return (
        "@font-face{"
        f"font-family:'{family}';"
        f"font-style:{style};"
        f"font-weight:{weight};"
        f"font-display:{display};"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2')"
        "}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--css", help="a webfont CSS URL (Fontshare, Google Fonts, ...)")
    src.add_argument("--url", help="a direct .woff2/.ttf/.otf URL")
    p.add_argument("--family", required=True, help="font-family name to emit")
    p.add_argument("--weight", type=int, default=400, help="weight, only with --url")
    p.add_argument("--style", default="normal", help="style, only with --url")
    p.add_argument("--charset", default="latin", help="latin | latin-irish | numerals | literal chars")
    p.add_argument("--text", help="subset to exactly these characters (overrides --charset)")
    p.add_argument("--display", default="swap", choices=["swap", "block", "fallback", "optional"])
    p.add_argument("--out", help="write CSS here (default: stdout)")
    a = p.parse_args()

    chars = a.text if a.text else CHARSETS.get(a.charset, a.charset)
    if a.text:
        chars += " "  # nbsp is nearly always needed and nearly always forgotten

    if a.css:
        faces = list(parse_css(fetch(a.css).decode("utf-8", "replace")))
        if not faces:
            print("no @font-face with a .woff2 url found in that CSS", file=sys.stderr)
            return 1
    else:
        faces = [(a.url, a.weight, a.style)]

    rules, total_raw, total_sub = [], 0, 0
    for url, weight, style in faces:
        raw = fetch(url)
        cut = subset(raw, chars)
        total_raw += len(raw)
        total_sub += len(cut)
        rules.append(face_rule(a.family, weight, style, cut, a.display))
        print(
            f"  {a.family} {weight} {style}: {len(raw)/1024:6.1f} KB -> "
            f"{len(cut)/1024:5.1f} KB subset -> {len(cut)*4//3/1024:5.1f} KB base64",
            file=sys.stderr,
        )

    css = "\n".join(rules) + "\n"
    inflated = len(css.encode()) / 1024
    print(
        f"  TOTAL {len(faces)} face(s): {total_raw/1024:.1f} KB -> {inflated:.1f} KB of inlined CSS",
        file=sys.stderr,
    )
    if inflated > 200:
        print(
            "  WARNING: over 200 KB inlined. Tighten --text or drop a weight.",
            file=sys.stderr,
        )

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(css)
        print(f"  wrote {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(css)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
