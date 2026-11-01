"""Slop lint: catch the tells that make a front end look generated, before a human has to.

    ddr lint src/                       # every rule except opt-in ones
    ddr lint src/ --enable em-dash      # opt-in rules
    ddr lint src/ --disable eyebrow     # a brief that genuinely wants one
    ddr lint src/ --json

Silence one line with a comment containing `dd-lint-ignore <rule>` (or bare
`dd-lint-ignore` for every rule on that line). A project can set defaults in
.design/lint.toml:  enable = ["em-dash"]  disable = ["eyebrow"]

This is a negative test only. Passing it proves the obvious tells are absent, not
that the design is good. CHECKLIST.md is the positive test.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, asdict

EXTS = {".css", ".scss", ".sass", ".less", ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue",
        ".svelte", ".astro", ".mdx", ".liquid", ".njk", ".hbs", ".erb"}
MD_EXTS = {".md"}   # opt in with --md: plain Markdown is usually notes, not shipped copy
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", ".turbo", ".vercel", "coverage",
             ".svelte-kit", ".astro", "vendor", ".cache", "storybook-static", "docs", "plans", "specs"}
OPT_IN = {"em-dash"}

DEFAULT_FONTS = ["Inter", "Space Grotesk", "Poppins", "Montserrat", "Playfair Display", "Roboto",
                 "Open Sans", "Lato", "Nunito", "Raleway", "Plus Jakarta Sans", "Bebas Neue", "Oswald",
                 "DM Sans"]
AI_WORDS = ["seamless", "seamlessly", "elevate your", "unlock", "unleash", "empower", "streamline",
            "revolutionize", "revolutionise", "cutting-edge", "next-level", "game-changer", "game changer",
            "supercharge", "delve", "tapestry", "effortlessly", "in today's fast-paced", "it's not just",
            "harness the power", "take it to the next level", "look no further", "world-class",
            "best-in-class", "transformative", "redefine", "reimagine"]

PURPLES = r"(?:purple|violet|indigo|fuchsia)"
BLUES = r"(?:blue|sky|cyan)"
PURPLE_HEX = re.compile(r"#(?:7c3aed|8b5cf6|a855f7|9333ea|6d28d9|6366f1|4f46e5|a78bfa|c084fc|d946ef)", re.I)
BLUE_HEX = re.compile(r"#(?:2563eb|3b82f6|60a5fa|0ea5e9|06b6d4|1d4ed8|38bdf8)", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    level: str          # error | warn | info
    message: str

    def __str__(self):
        return f"{self.file}:{self.line}  {self.level:5}  {self.rule:22} {self.message}"


def _font_re():
    names = "|".join(re.escape(f) for f in DEFAULT_FONTS)
    import_names = names.replace(" ", "_")
    url_names = names.replace(" ", "\\+")
    return re.compile(
        rf"(?:font-family\s*:[^;{{}}]*?['\"]?\b({names})\b(?![\w-])"
        rf"|import\s*\{{[^}}]*\b({import_names})\b[^}}]*\}}\s*from\s*['\"]next/font"
        rf"|fonts\.googleapis\.com/css2?\?family=({url_names})\b"
        rf"|font-(?:sans|display|heading)\s*:\s*\[?['\"]({names})\b)",
        re.I,
    )


FONT_RE = _font_re()
TW_PB = re.compile(rf"\bfrom-{PURPLES}-\d+\b[^\"'`]*\b(?:via|to)-{BLUES}-\d+|\bfrom-{BLUES}-\d+\b[^\"'`]*\b(?:via|to)-{PURPLES}-\d+")
GRAD_TEXT = re.compile(r"bg-clip-text[^\"'`]*text-transparent|text-transparent[^\"'`]*bg-clip-text|background-clip\s*:\s*text")
CLASS_ATTR = re.compile(r"class(?:Name)?\s*=\s*[{(]?\s*[\"'`]([^\"'`]+)[\"'`]")
OUTLINE_NONE = re.compile(r"outline\s*:\s*(?:none|0)\b|\boutline-none\b")
FOCUS_OK = re.compile(r"focus-visible|:focus\b|focus:ring|focus:outline|focus-within")
ZOOM = re.compile(r"(?:maximum-scale\s*=\s*1(?:\.0)?\b|user-scalable\s*=\s*(?:no|0))", re.I)
TRANSITION_ALL = re.compile(r"transition\s*:\s*all\b|\btransition-all\b")
CONTROL = re.compile(r"<input[^>]*type\s*=\s*[\"'](?:range|checkbox|radio)[\"'][^>]*>", re.I)
CONTROL_STYLED = re.compile(r"appearance-none|appearance\s*:\s*none|accent-color|accent-\w+-\d+|\bpeer\b|sr-only")
CONTROL_CSS = re.compile(r"appearance\s*:\s*none|accent-color|-webkit-slider-thumb|::-moz-range|input\[type=[\"']?(?:range|checkbox|radio)")
MOTION = re.compile(r"@keyframes|\banimate-[a-z]|from ['\"](?:framer-motion|motion/react|motion|gsap)['\"]|\bgsap\.")
REDUCED = re.compile(r"prefers-reduced-motion|useReducedMotion|motion-reduce|motion-safe|reducedMotion")
TEXT_NODE = re.compile(r">([^<>{}]{3,})<")
IGNORE = re.compile(r"dd-lint-ignore(?:\s+([a-z-]+(?:\s*,\s*[a-z-]+)*))?")


def _ignored(line: str, rule: str) -> bool:
    m = IGNORE.search(line)
    if not m:
        return False
    return not m.group(1) or rule in [r.strip() for r in m.group(1).split(",")]


def _copy_spans(line: str, suffix: str) -> list[str]:
    if suffix in {".md", ".mdx"}:
        return [line] if not line.lstrip().startswith(("```", "import ", "export ")) else []
    return [m.group(1) for m in TEXT_NODE.finditer(line)]


def lint_text(text: str, name: str = "file", enable=(), disable=()) -> list[Finding]:
    enable, disable = set(enable), set(disable)
    suffix = pathlib.Path(name).suffix.lower()
    out: list[Finding] = []
    file_focus_ok = bool(FOCUS_OK.search(text))
    file_control_ok = bool(CONTROL_STYLED.search(text))

    def add(n, rule, level, msg, line):
        if rule in disable or (rule in OPT_IN and rule not in enable) or _ignored(line, rule):
            return
        out.append(Finding(name, n, rule, level, msg))

    for n, line in enumerate(text.splitlines(), 1):
        m = FONT_RE.search(line)
        if m:
            face = next(g for g in m.groups() if g).replace("_", " ").replace("+", " ")
            add(n, "default-font", "warn", f"{face} is the default a model reaches for. Choose a face for this brief (TYPE.md).", line)
        if TW_PB.search(line) or (re.search(r"gradient\(", line) and (
                (PURPLE_HEX.search(line) and BLUE_HEX.search(line))
                or (re.search(PURPLES, line, re.I) and re.search(BLUES, line, re.I)))):
            add(n, "purple-blue-gradient", "error", "Purple-to-blue gradient: the most recognisable generated look.", line)
        if GRAD_TEXT.search(line):
            add(n, "gradient-text", "warn", "Gradient-filled text. Earn it or drop it.", line)
        for cm in CLASS_ATTR.finditer(line):
            cls = cm.group(1).split()
            if "uppercase" in cls and any(c.startswith("tracking-") for c in cls) and any(
                    c in ("text-xs", "text-sm", "text-[10px]", "text-[11px]", "text-[12px]") for c in cls):
                add(n, "eyebrow", "warn", "Small tracked uppercase label above a heading (an eyebrow). Usually filler.", line)
        if suffix not in {".css", ".scss", ".sass", ".less", ".ts", ".js"}:
            for span in _copy_spans(line, suffix):
                if EMOJI.search(span):
                    add(n, "emoji-icon", "warn", "Emoji used as an icon. Use a drawn icon set.", line)
                    break
            low = " ".join(_copy_spans(line, suffix)).lower()
            for w in AI_WORDS:
                if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", low):
                    add(n, "ai-copy", "warn", f"\"{w}\" reads as generated copy. Say the specific thing.", line)
                    break
            if "—" in " ".join(_copy_spans(line, suffix)):
                add(n, "em-dash", "info", "Em dash in copy.", line)
        if OUTLINE_NONE.search(line) and not file_focus_ok:
            add(n, "focus-removed", "error", "Focus outline removed with no focus-visible replacement in this file.", line)
        if ZOOM.search(line):
            add(n, "zoom-blocked", "error", "Viewport blocks pinch zoom. Remove maximum-scale / user-scalable.", line)
        if TRANSITION_ALL.search(line):
            add(n, "transition-all", "info", "transition: all animates layout properties too. Name the properties.", line)
        for cm in CONTROL.finditer(line):
            if not (CONTROL_STYLED.search(cm.group(0)) or file_control_ok):
                add(n, "default-control", "warn", "Form control left in its browser default state.", line)
    return out


def _walk(paths, md=False):
    exts = EXTS | (MD_EXTS if md else set())
    for p in map(pathlib.Path, paths):
        if p.is_file():
            yield p
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts and not (set(f.relative_to(p).parts) & SKIP_DIRS):
                yield f


def _project_config():
    cfg = pathlib.Path.cwd() / ".design" / "lint.toml"
    if not cfg.exists():
        return set(), set()
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import sources
    data = sources.loads(cfg.read_text(encoding="utf-8"))
    return set(data.get("enable", [])), set(data.get("disable", []))


def lint_paths(paths, enable=(), disable=(), md=False) -> list[Finding]:
    found, motion_at, reduced, controls_styled = [], None, False, False
    for f in _walk(paths, md):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += lint_text(text, str(f), enable, disable)
        if motion_at is None and MOTION.search(text):
            motion_at = str(f)
        reduced = reduced or bool(REDUCED.search(text))
        if f.suffix.lower() in {".css", ".scss", ".sass", ".less"} or "<style" in text:
            controls_styled = controls_styled or bool(CONTROL_CSS.search(text))
    if controls_styled:
        found = [x for x in found if x.rule != "default-control"]
    if motion_at and not reduced and "no-reduced-motion" not in set(disable):
        found.append(Finding(motion_at, 1, "no-reduced-motion", "error",
                             "Animation found but no prefers-reduced-motion handling anywhere in these paths."))
    return found


def main(argv=None):
    p = argparse.ArgumentParser(prog="ddr lint", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="*", default=["."])
    p.add_argument("--enable", default="", help="comma list of opt-in rules, e.g. em-dash")
    p.add_argument("--disable", default="", help="comma list of rules to skip")
    p.add_argument("--json", action="store_true")
    p.add_argument("--md", action="store_true", help="also lint plain .md files as copy")
    p.add_argument("--errors-only", action="store_true")
    a = p.parse_args(argv)
    cfg_en, cfg_dis = _project_config()
    en = cfg_en | {x for x in a.enable.split(",") if x}
    dis = cfg_dis | {x for x in a.disable.split(",") if x}
    found = lint_paths(a.paths, en, dis, a.md)
    if a.errors_only:
        found = [f for f in found if f.level == "error"]
    if a.json:
        print(json.dumps([asdict(f) for f in found], indent=1))
    else:
        for f in found:
            print(f)
        from collections import Counter
        c = Counter(f.level for f in found)
        print(f"\n{c['error']} errors, {c['warn']} warnings, {c['info']} notes. "
              "A clean lint means the obvious tells are absent, not that the design is good.")
    return 1 if any(f.level == "error" for f in found) else 0


if __name__ == "__main__":
    sys.exit(main())
