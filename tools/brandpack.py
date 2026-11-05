"""Brand packs: a brand's facts as data, and a lint that checks work against them.

A pack is a folder at $DDR_HOME/brands/<slug>/ (default ~/.design-director):

    brand.toml            slug, name, status, extends, domains, theme, summary, [sources]
    tokens.json           colours, fonts, radius cap, copy rules (see SPEC "Brand pack")
    voice.md              how the brand writes
    graphic-language.md   what the brand does and does not do visually, and its lessons

`extends` names a parent pack merged underneath: dicts overlay key by key (the child
wins), lists union with the child's order first, and a child may allow what its parent
banned but a parent can never take back what the child allows. The `house` pack holds
the rules every brand shares. When a pack is not in your home, the example packs in this
repo's templates/brands/ are read instead (read only; `ddr brand init` copies them).

    ddr brand list
    ddr brand show acme                       # palette, fonts, theme, bans, voice, graphic language, notes
    ddr brand init acme --name "Acme" [--extends house]
    ddr brand validate [acme]
    ddr brand extract --css https://acme.example [site.css ...] [--write acme]
    ddr brand lint src/ --brand acme [--json] # exit 0 pass, 1 findings, 2 could not run

The lint port follows the rules of LangChain's design agent (workspace/tools/brand-lint.mjs
and src/design_agent/brand/schema.py, Apache 2.0), rewritten in standard-library Python
for this repo's pack format. Passing it proves the brand's stated rules are not broken in
the files it read, not that the work is on brand.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import pathlib
import re
import shutil
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources  # noqa: E402  (shares the TOML reader)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "brands"

STATUSES = ("active", "dormant")
THEMES = ("light-only", "light-dark", "dark-only")
CASINGS = ("sentence", "title", "any")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
EXTS = {".css", ".scss", ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro", ".md", ".mdx"}
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", ".turbo", ".vercel", "coverage",
             ".svelte-kit", ".astro", "vendor", ".cache", ".design"}
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
           "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "-apple-system", "blinkmacsystemfont"}
CSS_WIDE = {"inherit", "initial", "unset", "revert", "revert-layer"}
ENTITIES = {"\u2014": ("&mdash;",), "\u2013": ("&ndash;",)}
# Tailwind's named radius scale (v4 values where v3 differs, so a cap is never under-reported).
TW_RADIUS = {"xs": 2, "sm": 4, "": 4, "md": 6, "lg": 8, "xl": 12, "2xl": 16, "3xl": 24, "4xl": 32}
PILL_PX = 999


# ---------------------------------------------------------------- paths

def home() -> pathlib.Path:
    env = os.environ.get("DDR_HOME")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".design-director"


def brands_dir() -> pathlib.Path:
    return home() / "brands"


def find(slug: str):
    """(folder, layer) for a slug: your home copy wins over the repo's template."""
    for base, layer in ((brands_dir(), "home"), (pathlib.Path(TEMPLATES), "template")):
        d = base / slug
        if (d / "brand.toml").exists():
            return d, layer
    return None, None


def slugs() -> list:
    found = {}
    for base, layer in ((pathlib.Path(TEMPLATES), "template"), (brands_dir(), "home")):
        if base.is_dir():
            for p in base.glob("*/brand.toml"):
                found[p.parent.name] = layer
    return sorted(found.items())


def project_brand(project) -> str | None:
    f = pathlib.Path(project) / ".design" / "brand"
    try:
        line = f.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    return line[0].strip() if line and line[0].strip() else None


# ---------------------------------------------------------------- colours

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9A-Za-z_-])")


def norm_hex(h: str) -> str | None:
    """#ABC, #abcd, #aabbcc, #aabbccdd to #aabbcc (alpha is not a different colour)."""
    raw = h.strip().lstrip("#").lower()
    if not re.fullmatch(r"[0-9a-f]{3,8}", raw) or len(raw) not in (3, 4, 6, 8):
        return None
    if len(raw) <= 4:
        raw = "".join(c * 2 for c in raw[:3])
    return "#" + raw[:6]


def _channel(v: str) -> int:
    v = v.strip()
    x = float(v[:-1]) * 2.55 if v.endswith("%") else float(v)
    return max(0, min(255, int(round(x))))


RGB = re.compile(r"rgba?\(\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*(?:[,/]\s*[\d.]+%?\s*)?\)", re.I)
HSL = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?\s*[,\s]\s*([\d.]+)%\s*[,\s]\s*([\d.]+)%\s*(?:[,/]\s*[\d.]+%?\s*)?\)", re.I)


def _rgb_hex(m) -> str:
    return "#" + "".join(f"{_channel(m.group(i)):02x}" for i in (1, 2, 3))


def _hsl_hex(m) -> str:
    h, s, l = float(m.group(1)) % 360 / 360, float(m.group(2)) / 100, float(m.group(3)) / 100
    r, g, b = colorsys.hls_to_rgb(h, min(l, 1), min(s, 1))
    return "#" + "".join(f"{int(round(x * 255)):02x}" for x in (r, g, b))


def colours_in(line: str):
    """(hex, literal) for every colour literal in a line of code."""
    out = []
    for m in HEX.finditer(line):
        before = line[:m.start()]
        if before.endswith(("&", "/", "url(")) or re.search(r"[\w]$", before) or \
                re.search(r"""href\s*=\s*["']?$""", before, re.I):
            continue
        h = norm_hex(m.group(0))
        if h:
            out.append((h, m.group(0)))
    out += [(_rgb_hex(m), m.group(0)) for m in RGB.finditer(line)]
    out += [(_hsl_hex(m), m.group(0)) for m in HSL.finditer(line)]
    return out


# ---------------------------------------------------------------- load and merge

def _merge(base, child):
    if isinstance(base, dict) and isinstance(child, dict):
        out = dict(base)
        for k, v in child.items():
            out[k] = _merge(base[k], v) if k in base else v
        return out
    if isinstance(base, list) and isinstance(child, list):
        return list(child) + [x for x in base if x not in child]
    return child


def _lower(xs) -> set:
    return {str(x).lower() for x in (xs or [])}


def _resolve(parent: dict, child: dict, merged: dict) -> dict:
    """Settle allowed against banned after a merge: the child's word is final."""
    cc, mc = child.get("colors", {}), merged.get("colors", {})
    child_banned = {norm_hex(h) for h in cc.get("banned", {}) if norm_hex(h)}
    child_allowed = {norm_hex(v) for part in ("allowed", "extended") for v in cc.get(part, {}).values()
                     if isinstance(v, str) and norm_hex(v)}
    if mc.get("banned"):
        mc["banned"] = {h: r for h, r in mc["banned"].items() if norm_hex(h) not in child_allowed or norm_hex(h) in child_banned}
    for part in ("allowed", "extended"):
        if mc.get(part):
            mc[part] = {n: v for n, v in mc[part].items()
                        if not (isinstance(v, str) and norm_hex(v) in child_banned and v not in cc.get(part, {}).values())}
    cf, mf = child.get("fonts", {}), merged.get("fonts", {})
    child_faces = _lower(cf.get("display", []) + cf.get("text", []) + cf.get("mono", [])) if all(
        isinstance(cf.get(r, []), list) for r in ("display", "text", "mono")) else set()
    child_bans = _lower(cf.get("banned", []))
    if isinstance(mf.get("banned"), list):
        mf["banned"] = [f for f in mf["banned"] if f.lower() not in child_faces or f.lower() in child_bans]
    for role in ("display", "text", "mono"):
        if isinstance(mf.get(role), list):
            mf[role] = [f for f in mf[role] if f.lower() not in child_bans or f.lower() in _lower(cf.get(role, []))]
    return merged


def _read(folder: pathlib.Path):
    meta = sources.loads((folder / "brand.toml").read_text(encoding="utf-8"))
    tf = folder / "tokens.json"
    tokens = json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else {}
    if not isinstance(tokens, dict):
        raise ValueError(f"{tf} must hold a JSON object")
    text = lambda n: (folder / n).read_text(encoding="utf-8") if (folder / n).exists() else ""  # noqa: E731
    return meta, tokens, text("voice.md"), text("graphic-language.md")


def load(slug: str, _seen=None) -> dict:
    """The merged pack: {"meta", "tokens", "voice", "graphic", "path", "layer", "chain"}.
    Raises KeyError when the pack (or a parent) is missing, ValueError on a cycle or bad file."""
    seen = list(_seen or [])
    if slug in seen:
        raise ValueError("extends goes round in a circle: " + " > ".join(seen + [slug]))
    folder, layer = find(slug)
    if folder is None:
        raise KeyError(slug)
    meta, tokens, voice, graphic = _read(folder)
    pack = {"meta": dict(meta, slug=meta.get("slug", slug)), "tokens": tokens, "voice": voice, "graphic": graphic,
            "path": folder, "layer": layer, "chain": [slug]}
    parent_slug = meta.get("extends")
    if parent_slug:
        parent = load(parent_slug, seen + [slug])
        merged = _resolve(parent["tokens"], tokens, _merge(parent["tokens"], tokens))
        pmeta = {k: v for k, v in parent["meta"].items() if k not in ("slug", "name", "extends", "summary", "status")}
        pack["meta"] = _merge(pmeta, pack["meta"])
        pack["tokens"] = merged
        for k, label in (("voice", "voice"), ("graphic", "graphic")):
            if parent[k].strip():
                pack[k] = (pack[k].rstrip() + "\n\n" if pack[k].strip() else "") + \
                    f"## Inherited from {parent_slug}\n\n" + parent[k].strip() + "\n"
        pack["chain"] = [slug] + parent["chain"]
    return pack


# ---------------------------------------------------------------- validate

def _f(rule, message, file="", severity="error", line=0) -> dict:
    return {"severity": severity, "rule": rule, "message": message, "file": str(file), "line": line}


def _is_str_list(x) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def validate(slug: str) -> list:
    """Every problem with a pack's own files, and with what it extends. [] when valid."""
    folder, _layer = find(slug)
    if folder is None:
        return [_f("brand.missing", f"no brand pack {slug!r} in {brands_dir()}: `ddr brand init {slug}`")]
    out = []
    try:
        meta = sources.loads((folder / "brand.toml").read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return [_f("brand.toml", f"brand.toml does not parse: {e}", folder / "brand.toml")]
    bt = folder / "brand.toml"
    if meta.get("slug") and meta["slug"] != slug:
        out.append(_f("brand.slug", f"slug {meta['slug']!r} does not match the folder {slug!r}", bt))
    if not meta.get("name"):
        out.append(_f("brand.name", "brand.toml needs a name", bt))
    if meta.get("status", "active") not in STATUSES:
        out.append(_f("brand.status", f"status must be one of {STATUSES}", bt))
    if meta.get("theme", "light-dark") not in THEMES:
        out.append(_f("brand.theme", f"theme must be one of {THEMES}", bt))
    if "domains" in meta and not _is_str_list(meta["domains"]):
        out.append(_f("brand.domains", "domains must be a list of domain slugs", bt))
    if "sources" in meta and not isinstance(meta["sources"], dict):
        out.append(_f("brand.sources", "[sources] must be a table", bt))
    if meta.get("extends"):
        try:
            load(slug)
        except KeyError as e:
            out.append(_f("brand.extends", f"extends {meta['extends']!r}, but there is no pack {e.args[0]!r}", bt))
        except ValueError as e:
            out.append(_f("brand.extends", str(e), bt))
    tf = folder / "tokens.json"
    if not tf.exists():
        return out + [_f("tokens.json", "no tokens.json: `ddr brand extract --css <site> --write " + slug + "`", tf)]
    try:
        tokens = json.loads(tf.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return out + [_f("tokens.json", f"tokens.json does not parse: {e}", tf)]
    if not isinstance(tokens, dict):
        return out + [_f("tokens.json", "tokens.json must hold an object", tf)]
    out += _validate_tokens(tokens, tf)
    return out


def _validate_tokens(t: dict, tf) -> list:
    out = []
    c = t.get("colors", {})
    if not isinstance(c, dict):
        return [_f("tokens.colors", "colors must be an object", tf)]
    palette = {}
    for part in ("allowed", "extended"):
        group = c.get(part, {})
        if not isinstance(group, dict):
            out.append(_f("tokens.colors", f"colors.{part} must map a name to a hex colour", tf))
            continue
        for name, v in group.items():
            h = norm_hex(v) if isinstance(v, str) and v.startswith("#") else None
            if h is None:
                out.append(_f("tokens.color-value", f"colors.{part}.{name} = {v!r} is not a hex colour", tf))
            else:
                palette[h] = name
    banned = c.get("banned", {})
    if not isinstance(banned, dict):
        out.append(_f("tokens.colors", "colors.banned must map a hex colour to its replacement", tf))
        banned = {}
    for h in banned:
        n = norm_hex(h)
        if n is None:
            out.append(_f("tokens.color-value", f"banned colour {h!r} is not a hex colour", tf))
        elif n in palette:
            out.append(_f("tokens.allowed-and-banned", f"{h} is both allowed (as {palette[n]}) and banned", tf))
    if "always_ok" in c and not _is_str_list(c["always_ok"]):
        out.append(_f("tokens.colors", "colors.always_ok must be a list", tf))
    fonts = t.get("fonts", {})
    if not isinstance(fonts, dict):
        out.append(_f("tokens.fonts", "fonts must be an object", tf))
        fonts = {}
    for role in ("display", "text", "mono", "banned"):
        if role in fonts and not _is_str_list(fonts[role]):
            out.append(_f("tokens.fonts", f"fonts.{role} must be a list of family names", tf))
    r = t.get("radius", {})
    if r and (not isinstance(r, dict) or not isinstance(r.get("max_px"), int) or isinstance(r.get("max_px"), bool)
              or r["max_px"] < 0):
        out.append(_f("tokens.radius", "radius.max_px must be a whole number of pixels, 0 or more", tf))
    cp = t.get("copy", {})
    if not isinstance(cp, dict):
        return out + [_f("tokens.copy", "copy must be an object", tf)]
    for k in ("banned_phrases", "warn_phrases", "banned_chars"):
        if k in cp and not _is_str_list(cp[k]):
            out.append(_f("tokens.copy", f"copy.{k} must be a list of strings", tf))
    casing = cp.get("casing", {})
    if casing and (not isinstance(casing, dict) or casing.get("headlines", "sentence") not in CASINGS):
        out.append(_f("tokens.casing", f"copy.casing.headlines must be one of {CASINGS}", tf))
    return out


# ---------------------------------------------------------------- lint

IGNORE = re.compile(r"ddr-ignore(?::\s*([a-z][a-z.-]*(?:\s*,\s*[a-z][a-z.-]*)*))?")
TEXT_NODE = re.compile(r">([^<>{}]{3,})<")
CLASS_ATTR = re.compile(r"""class(?:Name)?\s*=\s*[{(]?\s*["'`]([^"'`]+)["'`]""")
STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
FONT_DECL = re.compile(r"(?<![\w-])font-family\s*:\s*([^;{}<>]+)", re.I)
JSX_FONT = re.compile(r"""fontFamily\s*:\s*(["'`])(.*?)\1""")
TW_FONT = re.compile(r"(?<![\w-])font-\[([^\]]+)\]")
RADIUS_DECL = re.compile(r"(?<![\w-])border(?:-(?:top|bottom|start|end)-(?:left|right|start|end))?-radius\s*:\s*([^;{}<>]+)", re.I)
TW_RADIUS_ARB = re.compile(r"(?<![\w-])rounded(?:-(?:[trblse]{1,2}))?-\[(\d*\.?\d+)(px|rem|em|%)\]")
TW_RADIUS_NAMED = re.compile(r"(?<![\w\[-])rounded(?:-(?:[trblse]{1,2}))?(?:-(xs|sm|md|lg|xl|2xl|3xl|4xl|full|none))?(?![\w\[-])")
UPPER_CSS = re.compile(r"text-transform\s*:\s*uppercase|textTransform\s*:\s*[\"'`]uppercase", re.I)
# Only a site-wide dark theme counts: a designed dark section ([data-ground="tunnel"], a scoped
# `color-scheme: dark`) is part of a light site, not a dark mode.
DARK = re.compile(r"@media[^{]*prefers-color-scheme\s*:\s*dark|\[data-theme\s*=\s*[\"']?dark[\"']?\]", re.I)
DARK_CLASS = re.compile(r"\.dark(?![\w-])[^;{}()]*(?:\{|,\s*$)")
SELECTOR_FILES = {".css", ".scss", ".html", ".htm", ".vue", ".svelte", ".astro"}


def _ignored(line: str, rule: str) -> bool:
    m = IGNORE.search(line)
    if not m:
        return False
    if not m.group(1):
        return True
    return any(rule == r or rule.startswith(r + ".") for r in (x.strip() for x in m.group(1).split(",")))


def _split_top(value: str) -> list:
    parts, depth, cur = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _clean_family(f: str) -> str:
    return f.replace("!important", "").strip().strip("\"'").strip()


def families(value: str):
    """(top-level families, every family including var() fallbacks)."""
    top = [_clean_family(p) for p in _split_top(value)]
    every = []
    for p in top:
        m = re.match(r"var\(\s*--[\w-]+\s*,(.*)\)$", p, re.S)
        if m:
            every += families(m.group(1))[1]
        elif not p.lower().startswith("var("):
            every.append(p)
    return [t for t in top if t], [e for e in every if e]


def _radius_px(value: str):
    """Largest radius in a declaration in px, or 'pill', or None when it cannot be read."""
    best, pill = None, False
    for m in re.finditer(r"(\d*\.?\d+)(px|rem|em|%)?", value):
        n, unit = float(m.group(1)), (m.group(2) or "px")
        if unit == "%":
            if n >= 50:
                pill = True
            continue
        px = n * 16 if unit in ("rem", "em") else n
        if px >= PILL_PX:
            pill = True
            continue
        best = px if best is None else max(best, px)
    return best, pill


def _code_and_copy(text: str, suffix: str):
    """For each line: (number, line, code to check, visible text spans)."""
    md = suffix in (".md", ".mdx")
    fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if md:
            if line.lstrip().startswith(("```", "~~~")):
                fence = not fence
                yield n, line, line, []
                continue
            if fence:
                yield n, line, line, []
                continue
            if suffix == ".mdx" and line.lstrip().startswith(("import ", "export ", "<")):
                yield n, line, line, [m.group(1) for m in TEXT_NODE.finditer(line)]
                continue
            inline = " ".join(re.findall(r"`([^`]+)`", line))
            yield n, line, inline, [re.sub(r"`[^`]+`", " ", line)]
            continue
        spans = [] if suffix in (".css", ".scss", ".js", ".ts") else [m.group(1) for m in TEXT_NODE.finditer(line)]
        yield n, line, line, spans


def _phrase_re(phrase: str):
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])", re.I)


class _Rules:
    def __init__(self, pack: dict):
        t, meta = pack["tokens"], pack["meta"]
        c = t.get("colors", {})
        self.allowed = {norm_hex(v): n for n, v in c.get("allowed", {}).items() if norm_hex(v or "")}
        self.extended = {norm_hex(v): n for n, v in c.get("extended", {}).items() if norm_hex(v or "")}
        self.banned = {norm_hex(h): r for h, r in c.get("banned", {}).items() if norm_hex(h)}
        self.ok = {norm_hex(x) or x.lower() for x in c.get("always_ok", [])}
        f = t.get("fonts", {})
        self.faces = _lower(f.get("display", []) + f.get("text", []) + f.get("mono", []))
        # a face in the pack's own stacks is the brand's explicit allowance, whatever a parent banned
        self.banned_fonts = _lower(f.get("banned", [])) - self.faces
        self.max_px = t.get("radius", {}).get("max_px")
        cp = t.get("copy", {})
        self.banned_phrases = [(p, _phrase_re(p)) for p in cp.get("banned_phrases", [])]
        self.warn_phrases = [(p, _phrase_re(p)) for p in cp.get("warn_phrases", [])]
        self.banned_chars = cp.get("banned_chars", [])
        self.sentence = cp.get("casing", {}).get("headlines") == "sentence"
        self.light_only = meta.get("theme") == "light-only"

    def name(self, h):
        return self.allowed.get(h) or self.extended.get(h)


def _lint_file(path: pathlib.Path, text: str, R: _Rules, shown: str) -> list:
    out = []
    suffix = path.suffix.lower()

    def add(rule, sev, msg, n, line):
        if not _ignored(line, rule):
            out.append(_f(rule, msg, shown, sev, n))

    for n, line, code, spans in _code_and_copy(text, suffix):
        # colours
        for h, lit in colours_in(code):
            if h in R.banned:
                add("color.banned", "error", f"{lit} is banned for this brand: {R.banned[h]}", n, line)
            elif h in R.allowed or h in R.ok:
                continue
            elif h in R.extended:
                add("color.extended", "warn", f"{lit} is the extended colour {R.extended[h]}: fine for meaning "
                    "(status, charts), check it is not decoration", n, line)
            else:
                add("color.off-palette", "error", f"{lit} is not in the palette; use a named brand colour "
                    "(`ddr brand show` lists them)", n, line)
        # fonts
        decls, rest = [], code
        for m in STYLE_ATTR.finditer(code):
            body = m.group(1) if m.group(1) is not None else m.group(2)
            decls += [x.group(1) for x in FONT_DECL.finditer(body)]
        rest = STYLE_ATTR.sub(lambda m: " " * len(m.group(0)), rest)
        decls += [m.group(1) for m in FONT_DECL.finditer(rest)]
        decls += [m.group(2) for m in JSX_FONT.finditer(code)]
        for m in TW_FONT.finditer(code):
            v = m.group(1)
            if "var(" in v or re.fullmatch(r"[\d.]+", v) or v.startswith(("family-name:var", "length:", "number:")):
                continue
            decls.append(v.replace("family-name:", "").replace("_", " "))
        for value in decls:
            top, every = families(value)
            if not top:
                continue
            first = top[0]
            for fam in every:
                if fam.lower() in R.banned_fonts:
                    add("font.banned", "error", f"{fam} is banned for this brand; use a face from its stacks", n, line)
            fl = first.lower()
            if fl in R.banned_fonts or fl in GENERIC or fl in CSS_WIDE or fl.startswith("var(") or fl in R.faces:
                continue
            add("font.off-brand", "error", f"{first} leads this font stack but is not one of the brand's faces", n, line)
        # radius
        if R.max_px is not None:
            vals = []
            for m in RADIUS_DECL.finditer(code):
                if "var(" in m.group(1) or "calc(" in m.group(1):
                    continue
                vals.append(("border-radius " + m.group(1).strip(), *_radius_px(m.group(1))))
            for cm in CLASS_ATTR.finditer(code):
                cls = cm.group(1)
                for m in TW_RADIUS_ARB.finditer(cls):
                    vals.append((m.group(0), *_radius_px(m.group(1) + m.group(2))))
                for m in TW_RADIUS_NAMED.finditer(cls):
                    key = m.group(1) or ""
                    if key == "full":
                        vals.append((m.group(0), None, True))
                    elif key != "none":
                        vals.append((m.group(0), float(TW_RADIUS[key]), False))
            for where, px, pill in vals:
                if px is not None and px > R.max_px:
                    add("radius.max", "error", f"{where} is {px:g}px, rounder than the brand's {R.max_px}px cap", n, line)
                if pill:
                    add("radius.pill", "warn", f"{where} draws a pill or circle: fine for a round thing, "
                        f"not for a rectangle (the cap is {R.max_px}px)", n, line)
        # casing
        if R.sentence:
            hit = UPPER_CSS.search(code) or any(
                any(tok.split(":")[-1] == "uppercase" for tok in cm.group(1).split()) for cm in CLASS_ATTR.finditer(code)
            ) or re.search(r"@apply\b[^;]*(?<![\w-])uppercase(?![\w-])", code)
            if hit:
                add("case.uppercase-transform", "error", "uppercase transform: this brand sets headlines in sentence "
                    "case, so write the words in the case they should read", n, line)
        # theme
        if R.light_only:
            if DARK.search(code) or (suffix in SELECTOR_FILES and DARK_CLASS.search(code)):
                add("theme.unrequested-dark", "error", "a dark theme on a light-only brand: remove it unless the "
                    "brief asks for dark", n, line)
        # copy
        visible = " ".join(spans)
        if visible.strip():
            for p, rx in R.banned_phrases:
                if rx.search(visible):
                    add("copy.banned-phrase", "error", f"\"{p}\" is banned copy for this brand; say the specific thing", n, line)
            for p, rx in R.warn_phrases:
                if rx.search(visible):
                    add("copy.warn-phrase", "warn", f"\"{p}\" usually reads as filler; check it earns its place", n, line)
            for ch in R.banned_chars:
                forms = (ch, f"&#{ord(ch)};", f"&#x{ord(ch):x};") + ENTITIES.get(ch, ()) if len(ch) == 1 else (ch,)
                if any(fm in visible.lower() if fm.startswith("&") else fm in visible for fm in forms):
                    add("copy.banned-char", "error", f"banned character U+{ord(ch[0]):04X} in visible text; "
                        "use a full stop, comma or brackets", n, line)
    return out


def _walk(paths):
    for p in map(pathlib.Path, paths):
        if p.is_file():
            yield p
            continue
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in EXTS and not (set(f.relative_to(p).parts[:-1]) & SKIP_DIRS):
                yield f


def _report(tool, findings) -> dict:
    if any(f["rule"] == "tool.could-not-run" for f in findings):
        code = 2
    else:
        code = 1 if any(f["severity"] == "error" for f in findings) else 0
    errors = sum(1 for f in findings if f["severity"] == "error")
    warns = len(findings) - errors
    summary = {0: f"pass: {warns} warnings", 1: f"{errors} errors, {warns} warnings",
               2: "could not run: " + "; ".join(f["message"] for f in findings if f["rule"] == "tool.could-not-run")}[code]
    return {"ok": code == 0, "exit": code, "tool": tool, "findings": findings, "summary": summary}


def lint(paths: list, slug: str) -> dict:
    """Check files against a brand pack. The SPEC JSON shape, tool "brand-lint"."""
    try:
        pack = load(slug)
    except KeyError as e:
        return _report("brand-lint", [_f("tool.could-not-run", f"no brand pack {e.args[0]!r}: `ddr brand list`")])
    except (ValueError, OSError) as e:
        return _report("brand-lint", [_f("tool.could-not-run", f"brand pack {slug!r} does not load: {e}")])
    bad = [f for f in validate(slug) if f["severity"] == "error"]
    if bad:
        return _report("brand-lint", [_f("tool.could-not-run", f"brand pack {slug!r} is invalid: {bad[0]['message']} "
                                         f"(`ddr brand validate {slug}`)", bad[0]["file"])])
    if not paths:
        return _report("brand-lint", [_f("tool.could-not-run", "no paths to lint")])
    findings = []
    for p in paths:
        if not pathlib.Path(p).exists():
            findings.append(_f("tool.could-not-run", f"{p} does not exist", p))
    if findings:
        return _report("brand-lint", findings)
    R = _Rules(pack)
    for f in _walk(paths):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            findings.append(_f("tool.could-not-run", f"could not read {f}: {type(e).__name__}", f))
            continue
        findings += _lint_file(f, text, R, str(f))
    return _report("brand-lint", findings)


# ---------------------------------------------------------------- extract

def _fetch(url: str, timeout: float = 15.0):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "design-director-brand-extract/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        return body, r.headers.get("Content-Type", "")


def _css_from(src: str) -> list:
    """CSS texts from a file path or a URL (a stylesheet, or a page and its linked sheets)."""
    if not re.match(r"https?://", src):
        return [pathlib.Path(src).read_text(encoding="utf-8")]
    from urllib.parse import urljoin
    body, ctype = _fetch(src)
    if "css" in ctype or src.split("?")[0].endswith(".css"):
        return [body]
    out = re.findall(r"<style\b[^>]*>(.*?)</style>", body, re.S | re.I)
    for m in re.finditer(r"<link\b[^>]*>", body, re.I):
        tag = m.group(0)
        if not re.search(r"""rel\s*=\s*["']?stylesheet""", tag, re.I):
            continue
        h = re.search(r"""href\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))""", tag, re.I)
        if h:
            out.append(_fetch(urljoin(src, h.group(1) or h.group(2) or h.group(3)))[0])
    return out


def extract(srcs: list) -> dict:
    """A draft tokens.json from CSS files or URLs, for a person or agent to review."""
    css = "\n".join(t for s in srcs for t in _css_from(s))
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    allowed, counts = {}, Counter()
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+)", css):
        cols = colours_in(m.group(2))
        if len(cols) == 1 and m.group(2).strip() == cols[0][1]:
            name = re.sub(r"^--(?:color-|colour-|brand-)?", "", m.group(1))
            allowed.setdefault(name, cols[0][0])
    for line in css.splitlines():
        stripped = re.sub(r"--[\w-]+\s*:\s*[^;{}]+", "", line)
        for h, _ in colours_in(stripped):
            if h not in allowed.values():
                counts[h] += 1
    fam_count, by_sel = Counter(), {}
    radii = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip().lower()
        for d in FONT_DECL.finditer(m.group(2)):
            top, _ = families(d.group(1))
            if top and not top[0].lower().startswith("var("):
                fam_count[top[0]] += 1
                by_sel.setdefault(sel, top)
        for d in RADIUS_DECL.finditer(m.group(2)):
            px, pill = _radius_px(d.group(1))
            if px is not None and not pill:
                radii.append(px)

    def is_mono(stack):
        return "mono" in stack[0].lower() or "monospace" in [s.lower() for s in stack]

    stacks = list(by_sel.items())
    mono = next((s[0] for _, s in stacks if is_mono(s)), None)
    text = next((s[0] for sel, s in stacks if re.search(r"(^|[\s,])(body|html|:root)\b", sel) and not is_mono(s)), None)
    display = next((s[0] for sel, s in stacks if re.search(r"(^|[\s,])h[1-3]\b", sel) and not is_mono(s)), None)
    ranked = [f for f, _ in fam_count.most_common() if f.lower() not in GENERIC]
    text = text or next((f for f in ranked if "mono" not in f.lower()), None)
    tokens = {
        "colors": {"allowed": allowed, "extended": {}, "banned": {},
                   "always_ok": ["#000000", "#ffffff", "transparent", "currentcolor", "inherit"]},
        "fonts": {"display": [display or text] if (display or text) else [], "text": [text] if text else [],
                  "mono": [mono] if mono else [], "banned": []},
        "radius": {"max_px": int(max(radii)) if radii else 8},
        "copy": {"banned_phrases": [], "warn_phrases": [], "banned_chars": []},
        "_ranked_colors": [{"hex": h, "count": n} for h, n in counts.most_common(24)],
        "_families_seen": [{"family": f, "count": n} for f, n in fam_count.most_common(12)],
        "_note": "Draft from extracted CSS. Name the colours, move ranked ones into allowed or extended, "
                 "then delete the keys that start with an underscore.",
    }
    return tokens


# ---------------------------------------------------------------- show, init

def show(slug: str) -> str:
    p = load(slug)
    t, m = p["tokens"], p["meta"]
    c, f = t.get("colors", {}), t.get("fonts", {})
    L = [f"# {m.get('name', slug)} ({slug}, {m.get('status', 'active')}, {p['layer']})"]
    if m.get("summary"):
        L.append(m["summary"])
    if len(p["chain"]) > 1:
        L.append("extends: " + " > ".join(p["chain"][1:]))
    L.append(f"theme: {m.get('theme', 'not set')}")
    if m.get("domains"):
        L.append("domains: " + ", ".join(m["domains"]))
    L += ["", "## Palette"]
    L += [f"- {n}: {v}" for n, v in c.get("allowed", {}).items()] or ["- none set"]
    if c.get("extended"):
        L += ["", "Extended (for meaning, not decoration):"] + [f"- {n}: {v}" for n, v in c["extended"].items()]
    if c.get("always_ok"):
        L.append("Always fine: " + ", ".join(c["always_ok"]))
    L += ["", "## Fonts"]
    for role in ("display", "text", "mono"):
        if f.get(role):
            L.append(f"- {role}: " + ", ".join(f[role]))
    rad = t.get("radius", {}).get("max_px")
    L += ["", f"Radius cap: {rad}px" if rad is not None else "Radius cap: none set"]
    cp = t.get("copy", {})
    L += ["", "## Banned"]
    if c.get("banned"):
        L.append("- colours: " + "; ".join(f"{h} ({r})" for h, r in c["banned"].items()))
    if f.get("banned"):
        L.append("- fonts: " + ", ".join(f["banned"]))
    if cp.get("banned_phrases"):
        L.append("- phrases: " + ", ".join(cp["banned_phrases"]))
    if cp.get("warn_phrases"):
        L.append("- phrases to question: " + ", ".join(cp["warn_phrases"]))
    if cp.get("banned_chars"):
        L.append("- characters: " + ", ".join(f"U+{ord(x[0]):04X}" for x in cp["banned_chars"] if x))
    if cp.get("casing", {}).get("headlines"):
        L.append(f"- headline casing: {cp['casing']['headlines']}")
    if p["voice"].strip():
        L += ["", "## voice.md", "", p["voice"].strip()]
    if p["graphic"].strip():
        L += ["", "## graphic-language.md", "", p["graphic"].strip()]
    try:
        import notes
        rendered = notes.render(slug)
    except Exception as e:  # notes must never block a brand read
        rendered = f"(notes unavailable: {type(e).__name__})"
    if rendered:
        L += ["", rendered]
    return "\n".join(L)


def init(slug: str, name: str = "", extends: str = "house") -> pathlib.Path:
    if not SLUG.fullmatch(slug):
        raise ValueError("a brand slug is lower case letters, digits and hyphens")
    dst = brands_dir() / slug
    if dst.exists():
        raise ValueError(f"{dst} exists; edit it, or pick another slug")
    tpl = pathlib.Path(TEMPLATES) / ("house" if slug == "house" else "example")
    if not (tpl / "brand.toml").exists():
        raise ValueError(f"no template at {tpl}")
    shutil.copytree(tpl, dst)
    text = (dst / "brand.toml").read_text(encoding="utf-8")
    text = re.sub(r'(?m)^slug\s*=.*$', f"slug = {json.dumps(slug)}", text)
    if name:
        text = re.sub(r'(?m)^name\s*=.*$', f"name = {json.dumps(name)}", text)
    if slug != "house":
        if re.search(r"(?m)^extends\s*=", text):
            text = re.sub(r'(?m)^extends\s*=.*$', f"extends = {json.dumps(extends)}" if extends else "", text)
        elif extends:
            text = f"extends = {json.dumps(extends)}\n" + text
    (dst / "brand.toml").write_text(text, encoding="utf-8")
    return dst


# ---------------------------------------------------------------- CLI

def _print_findings(res):
    for f in res["findings"]:
        where = f"{f['file']}:{f['line']}" if f.get("line") else (f["file"] or "-")
        print(f"{where}  {f['severity']:5}  {f['rule']:26} {f['message']}")
    print(res["summary"])


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr brand", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("show").add_argument("slug")
    i = sub.add_parser("init"); i.add_argument("slug"); i.add_argument("--name", default="")
    i.add_argument("--extends", default="house")
    v = sub.add_parser("validate"); v.add_argument("slug", nargs="?"); v.add_argument("--json", action="store_true")
    e = sub.add_parser("extract"); e.add_argument("--css", nargs="+", required=True, help="CSS files or URLs")
    e.add_argument("--write", metavar="SLUG", help="write the draft into this pack's tokens.json")
    li = sub.add_parser("lint"); li.add_argument("paths", nargs="*", default=["."])
    li.add_argument("--brand"); li.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    if a.cmd == "list":
        rows = slugs()
        if not rows:
            print(f"no brand packs yet ({brands_dir()}). `ddr brand init <slug>` starts one.")
        for slug, layer in rows:
            try:
                m = load(slug)["meta"]
                print(f"  {slug:20} {m.get('status', 'active'):8} {m.get('theme', ''):11} {layer:8} {m.get('name', '')}")
            except (KeyError, ValueError, OSError) as ex:
                print(f"  {slug:20} broken: {ex}")
        return 0
    if a.cmd == "show":
        try:
            print(show(a.slug)); return 0
        except KeyError:
            print(f"no brand pack {a.slug!r}: `ddr brand list`", file=sys.stderr); return 2
        except (ValueError, OSError) as ex:
            print(f"brand pack {a.slug!r} does not load: {ex}", file=sys.stderr); return 2
    if a.cmd == "init":
        try:
            dst = init(a.slug, a.name, a.extends)
        except ValueError as ex:
            print(f"not done: {ex}", file=sys.stderr); return 2
        print(f"created {dst}\nnext: `ddr brand extract --css <site or stylesheet> --write {a.slug}`, "
              "then write voice.md and graphic-language.md")
        return 0
    if a.cmd == "validate":
        targets = [a.slug] if a.slug else [s for s, layer in slugs() if layer == "home"]
        worst = 0
        for s in targets:
            found = validate(s)
            if found and found[0]["rule"] == "brand.missing":
                print(found[0]["message"], file=sys.stderr); worst = 2; continue
            print(f"{s}: {'valid' if not found else str(len(found)) + ' problems'}")
            for f in found:
                print(f"  {f['rule']:24} {f['message']}")
            if found and worst < 2:
                worst = 1
        return worst
    if a.cmd == "extract":
        try:
            tokens = extract(a.css)
        except (OSError, ValueError) as ex:
            print(f"could not run: {ex}", file=sys.stderr); return 2
        text = json.dumps(tokens, indent=2, ensure_ascii=False) + "\n"
        if a.write:
            folder, layer = find(a.write)
            if folder is None or layer != "home":
                print(f"no pack {a.write!r} in {brands_dir()}: `ddr brand init {a.write}` first", file=sys.stderr); return 2
            tf = folder / "tokens.json"
            if tf.exists():
                shutil.copy(tf, folder / "tokens.json.bak")
            tf.write_text(text, encoding="utf-8")
            print(f"wrote {tf} (the old one is tokens.json.bak). Review it: it is a draft.")
        else:
            print(text, end="")
        return 0
    if a.cmd == "lint":
        slug = a.brand or project_brand(pathlib.Path.cwd())
        if not slug:
            res = _report("brand-lint", [_f("tool.could-not-run", "no brand: pass --brand <slug> or write the slug into .design/brand")])
        else:
            res = lint(a.paths, slug)
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            _print_findings(res)
        return res["exit"]
    return 2


if __name__ == "__main__":
    sys.exit(main())
