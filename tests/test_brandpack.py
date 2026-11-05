import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib, json
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

EM, EN = "\u2014", "\u2013"

HOUSE_TOKENS = {
    "colors": {"banned": {"#7c3aed": "use ink"}, "always_ok": ["#000000", "#ffffff", "transparent", "currentcolor", "inherit"]},
    "fonts": {"banned": ["Inter", "Poppins"]},
    "copy": {"banned_phrases": ["seamless"], "warn_phrases": ["unlock"], "banned_chars": [EM, EN]},
}
BRAND_TOKENS = {
    "colors": {"allowed": {"ink": "#0b1b2b", "paper": "#f6f5f1", "lime": "#ccff00"},
               "extended": {"positive": "#1f7a4d"},
               "banned": {"#ff0000": "use ink"}},
    "fonts": {"display": ["Sohne Breit"], "text": ["Sohne"], "mono": ["Sohne Mono"]},
    "radius": {"max_px": 8},
    "copy": {"banned_phrases": ["world-class"], "casing": {"headlines": "sentence"}},
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = str(self.root / "home")
        import domains, brandpack
        importlib.reload(domains)
        domains.SEEDS = self.root / "no-seeds"
        importlib.reload(brandpack)
        brandpack.TEMPLATES = self.root / "no-templates"
        self.b = brandpack
        self.src = self.root / "src"
        self.src.mkdir()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        self.tmp.cleanup()

    def pack(self, slug, tokens, extends=None, theme="light-only", voice="", graphic="", extra=""):
        d = self.root / "home" / "brands" / slug
        d.mkdir(parents=True, exist_ok=True)
        lines = [f'slug = "{slug}"', f'name = "{slug.title()}"', 'status = "active"', f'theme = "{theme}"']
        if extends:
            lines.append(f'extends = "{extends}"')
        (d / "brand.toml").write_text("\n".join(lines) + "\n" + extra, encoding="utf-8")
        (d / "tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
        if voice:
            (d / "voice.md").write_text(voice, encoding="utf-8")
        if graphic:
            (d / "graphic-language.md").write_text(graphic, encoding="utf-8")
        return d

    def standard(self, **kw):
        self.pack("house", HOUSE_TOKENS, voice="# House voice\nPlain words.\n", graphic="# House graphic\nNo eyebrows.\n")
        return self.pack("acme", BRAND_TOKENS, extends="house", voice="# Acme voice\nDry.\n",
                         graphic="# Acme graphic\nLedger rules.\n", **kw)

    def write(self, name, text):
        p = self.src / name
        p.write_text(text, encoding="utf-8")
        return p

    def rules(self, text, name="a.css", slug="acme"):
        self.write(name, text)
        res = self.b.lint([str(self.src / name)], slug)
        return [(f["rule"], f["severity"]) for f in res["findings"]], res


class Load(Base):
    def test_missing_pack_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.b.load("nope")

    def test_extends_merge_dicts_overlay_lists_union_child_first(self):
        self.standard()
        p = self.b.load("acme")
        t = p["tokens"]
        self.assertEqual(t["colors"]["allowed"]["ink"], "#0b1b2b")
        self.assertEqual(t["colors"]["banned"]["#7c3aed"], "use ink")    # from house
        self.assertEqual(t["colors"]["banned"]["#ff0000"], "use ink")    # from acme
        self.assertEqual(t["fonts"]["banned"], ["Inter", "Poppins"])
        self.assertEqual(t["copy"]["banned_phrases"], ["world-class", "seamless"])   # child order first
        self.assertEqual(p["meta"]["slug"], "acme")
        self.assertIn("Acme voice", p["voice"])
        self.assertIn("House voice", p["voice"])
        self.assertLess(p["voice"].index("Acme voice"), p["voice"].index("House voice"))
        self.assertIn("Ledger rules", p["graphic"])
        self.assertEqual(p["path"], self.root / "home" / "brands" / "acme")

    def test_child_can_allow_what_the_parent_bans_but_not_the_reverse(self):
        self.pack("house", {"colors": {"allowed": {"red": "#ff0000"}, "banned": {"#7c3aed": "use ink"}},
                            "fonts": {"banned": ["Inter"], "text": ["Arial"]}})
        self.pack("kid", {"colors": {"allowed": {"violet": "#7C3AED"}, "banned": {"#ff0000": "no red here"}},
                          "fonts": {"text": ["Inter"], "banned": ["Arial"]}}, extends="house")
        t = self.b.load("kid")["tokens"]
        self.assertNotIn("#7c3aed", {k.lower() for k in t["colors"]["banned"]})   # child allowed it
        self.assertIn("violet", t["colors"]["allowed"])
        self.assertIn("#ff0000", t["colors"]["banned"])                            # child banned it
        self.assertNotIn("red", t["colors"]["allowed"])
        self.assertNotIn("Inter", t["fonts"]["banned"])
        self.assertIn("Inter", t["fonts"]["text"])
        self.assertIn("Arial", t["fonts"]["banned"])
        self.assertNotIn("Arial", t["fonts"]["text"])

    def test_extends_cycle_is_an_error(self):
        self.pack("a", {}, extends="b")
        self.pack("b", {}, extends="a")
        with self.assertRaises(ValueError):
            self.b.load("a")

    def test_brand_toml_with_a_sources_table_parses_without_tomllib(self):
        import sources
        text = ('slug = "draft"\nname = "Draft"\nextends = "house"\ndomains = ["fintech", "onboarding"]\n\n'
                '[sources]\nrepo = "~/Dev/draft"\ntokens_from = ["a.css"]\n')
        mine = sources.parse_toml_subset(text)
        self.assertEqual(mine["sources"]["repo"], "~/Dev/draft")
        self.assertEqual(mine["domains"], ["fintech", "onboarding"])
        try:
            import tomllib
        except ImportError:
            return
        self.assertEqual(mine, tomllib.loads(text))

    def test_project_brand(self):
        proj = self.root / "proj"
        self.assertIsNone(self.b.project_brand(proj))
        (proj / ".design").mkdir(parents=True)
        (proj / ".design" / "brand").write_text("acme\n", encoding="utf-8")
        self.assertEqual(self.b.project_brand(proj), "acme")


class Validate(Base):
    def test_good_pack_is_valid(self):
        self.standard()
        self.assertEqual(self.b.validate("acme"), [])

    def test_problems_are_listed(self):
        self.pack("bad", {"colors": {"allowed": {"ink": "nothex", "a": "#123456"}, "banned": {"#123456": "x"}},
                          "radius": {"max_px": "eight"}, "fonts": {"text": "Sohne"},
                          "copy": {"casing": {"headlines": "shouty"}}}, theme="neon")
        rules = {f["rule"] for f in self.b.validate("bad")}
        for r in ("brand.theme", "tokens.color-value", "tokens.allowed-and-banned", "tokens.radius",
                  "tokens.fonts", "tokens.casing"):
            self.assertIn(r, rules)

    def test_missing_pack_and_missing_parent(self):
        self.assertEqual(self.b.validate("nope")[0]["rule"], "brand.missing")
        self.pack("orphan", {}, extends="ghost")
        self.assertIn("brand.extends", {f["rule"] for f in self.b.validate("orphan")})

    def test_bad_json(self):
        d = self.pack("broken", {})
        (d / "tokens.json").write_text("{not json", encoding="utf-8")
        self.assertIn("tokens.json", {f["rule"] for f in self.b.validate("broken")})


class Colours(Base):
    def setUp(self):
        super().setUp()
        self.standard()

    def test_allowed_colour_passes_and_off_palette_fails(self):
        got, res = self.rules(".a { color: #0b1b2b; background: #123456; }\n")
        self.assertEqual(got, [("color.off-palette", "error")])
        self.assertEqual(res["exit"], 1)
        self.assertFalse(res["ok"])
        self.assertEqual(res["tool"], "brand-lint")
        self.assertEqual(res["findings"][0]["line"], 1)

    def test_three_digit_hex_and_case_normalise(self):
        got, _ = self.rules(".a { color: #CF0; border-color: #FFF; }\n")
        self.assertEqual(got, [])

    def test_alpha_is_ignored(self):
        got, _ = self.rules(".a { color: #0b1b2b80; background: #cf08; }\n")
        self.assertEqual(got, [])

    def test_rgb_and_hsl_are_normalised(self):
        got, _ = self.rules(".a { color: rgb(11, 27, 43); background: rgba(204 255 0 / 0.5); }\n"
                            ".b { color: hsl(0, 0%, 100%); }\n.c { color: rgb(1,2,3); }\n")
        self.assertEqual(got, [("color.off-palette", "error")])

    def test_banned_gives_the_replacement(self):
        got, res = self.rules(".a { color: #7C3AED; }\n")
        self.assertEqual(got, [("color.banned", "error")])
        self.assertIn("use ink", res["findings"][0]["message"])

    def test_extended_is_a_warning_and_passes(self):
        got, res = self.rules(".a { color: #1f7a4d; }\n")
        self.assertEqual(got, [("color.extended", "warn")])
        self.assertEqual(res["exit"], 0)
        self.assertTrue(res["ok"])

    def test_token_definition_is_still_checked(self):
        got, _ = self.rules(":root { --ink: #0b1b2c; }\n")
        self.assertEqual(got, [("color.off-palette", "error")])

    def test_tailwind_arbitrary_colour(self):
        got, _ = self.rules('<div class="bg-[#123456] text-[#0b1b2b]">Hi there</div>\n', name="a.html")
        self.assertEqual(got, [("color.off-palette", "error")])

    def test_fragments_and_entities_are_not_colours(self):
        got, _ = self.rules('<a href="#add">Go &#123; to</a> <a href="/x/#bad">b</a>\n', name="a.html")
        self.assertEqual(got, [])

    def test_ddr_ignore(self):
        got, _ = self.rules(".a { color: #123456; } /* ddr-ignore: color.off-palette */\n"
                            ".b { color: #123456; } /* ddr-ignore: font.banned */\n"
                            ".c { color: #123456; } /* ddr-ignore: color */\n")
        self.assertEqual(got, [("color.off-palette", "error")])


class Fonts(Base):
    def setUp(self):
        super().setUp()
        self.standard()

    def test_stack_faces_generics_and_vars_pass(self):
        got, _ = self.rules('.a { font-family: "Sohne Breit", serif; }\n.b { font-family: sans-serif; }\n'
                            ".c { font-family: var(--font-text); }\n.d { font-family: inherit; }\n")
        self.assertEqual(got, [])

    def test_off_brand_first_family(self):
        got, _ = self.rules(".a { font-family: Georgia, 'Sohne', serif; }\n")
        self.assertEqual(got, [("font.off-brand", "error")])

    def test_banned_anywhere_in_the_list(self):
        got, _ = self.rules(".a { font-family: Sohne, Inter, sans-serif; }\n"
                            ".b { font-family: var(--x, Poppins), serif; }\n")
        self.assertEqual(got, [("font.banned", "error"), ("font.banned", "error")])

    def test_a_face_in_the_brands_own_stack_is_never_banned(self):
        # house bans Inter; a brand that sets Inter in its text stack has allowed it explicitly
        self.pack("house", {"fonts": {"banned": ["Inter", "Poppins"]}})
        self.pack("plain", {"fonts": {"text": ["Inter"], "display": ["Sohne"]}}, extends="house")
        got, _ = self.rules(".a { font-family: Inter, sans-serif; }\n.b { font-family: Sohne, Poppins; }\n", slug="plain")
        self.assertEqual(got, [("font.banned", "error")])
        self.assertNotIn("Inter", self.b.load("plain")["tokens"]["fonts"]["banned"])

    def test_banned_first_is_reported_once(self):
        got, _ = self.rules(".a { font-family: Inter, sans-serif; }\n")
        self.assertEqual(got, [("font.banned", "error")])

    def test_inline_style_and_jsx(self):
        got, _ = self.rules('<p style="font-family: Georgia, serif; color: #0b1b2b">Hello there</p>\n', name="a.html")
        self.assertEqual(got, [("font.off-brand", "error")])
        got, _ = self.rules('const s = { fontFamily: "Inter, sans-serif" };\n', name="a.tsx")
        self.assertEqual(got, [("font.banned", "error")])

    def test_tailwind_arbitrary_font(self):
        got, _ = self.rules('<h1 class="font-[Georgia,serif] font-[600]">Hello there</h1>\n'
                            '<h2 class="font-[\'Sohne_Breit\',serif]">Fine heading</h2>\n'
                            '<h3 class="font-[family-name:var(--f)]">Fine too</h3>\n', name="a.html")
        self.assertEqual(got, [("font.off-brand", "error")])


class Radius(Base):
    def setUp(self):
        super().setUp()
        self.standard()

    def test_radius_cap(self):
        got, _ = self.rules(".a { border-radius: 8px; }\n.b { border-radius: 12px; }\n.c { border-radius: 1rem; }\n"
                            ".d { border-top-left-radius: 4px 20px; }\n")
        self.assertEqual(got, [("radius.max", "error")] * 3)

    def test_pills_are_warnings(self):
        got, res = self.rules(".a { border-radius: 9999px; }\n.b { border-radius: 50%; }\n")
        self.assertEqual(got, [("radius.pill", "warn")] * 2)
        self.assertEqual(res["exit"], 0)

    def test_tailwind_radius(self):
        got, _ = self.rules('<div class="rounded-[6px] rounded-[16px] rounded-full rounded-3xl">Hello there</div>\n',
                            name="a.html")
        self.assertEqual(sorted(got), sorted([("radius.max", "error"), ("radius.pill", "warn"), ("radius.max", "error")]))


class Copy(Base):
    def setUp(self):
        super().setUp()
        self.standard()

    def test_banned_and_warn_phrases_in_text_nodes(self):
        got, _ = self.rules("<p>A seamless way to unlock it</p>\n<p>Seamlessly fine</p>\n", name="a.html")
        self.assertEqual(got, [("copy.banned-phrase", "error"), ("copy.warn-phrase", "warn")])

    def test_phrase_in_markup_attribute_is_not_copy(self):
        got, _ = self.rules('<div class="seamless">Plain words here</div>\n', name="a.html")
        self.assertEqual(got, [])

    def test_banned_chars_and_entities(self):
        got, _ = self.rules(f"<p>Fast {EM} and calm</p>\n<p>One&mdash;two</p>\n<p>3{EN}4 days</p>\n", name="a.html")
        self.assertEqual(got, [("copy.banned-char", "error")] * 3)

    def test_markdown_prose_but_not_code_fences(self):
        got, _ = self.rules(f"# Title\n\nA seamless thing {EM} yes\n\n```\nseamless {EM}\n```\n", name="a.md")
        self.assertEqual(sorted(got), [("copy.banned-char", "error"), ("copy.banned-phrase", "error")])

    def test_markdown_issue_numbers_are_not_colours(self):
        got, _ = self.rules("Fixed in #123 and #456.\n", name="a.md")
        self.assertEqual(got, [])


class CaseAndTheme(Base):
    def test_uppercase_transform_when_sentence_case(self):
        self.standard()
        got, _ = self.rules(".a { text-transform: uppercase; }\n")
        self.assertEqual(got, [("case.uppercase-transform", "error")])
        got, _ = self.rules('<h2 class="md:uppercase text-sm">Hi there</h2>\n', name="a.html")
        self.assertEqual(got, [("case.uppercase-transform", "error")])

    def test_uppercase_allowed_when_casing_is_any(self):
        self.pack("loud", {"copy": {"casing": {"headlines": "any"}}})
        got, _ = self.rules(".a { text-transform: uppercase; }\n", slug="loud")
        self.assertEqual(got, [])

    def test_unrequested_dark(self):
        self.standard()
        got, _ = self.rules("@media (prefers-color-scheme: dark) { }\n[data-theme=\"dark\"] .a { }\n")
        self.assertEqual(got, [("theme.unrequested-dark", "error")] * 2)

    def test_dark_class_selector_counts_but_designed_dark_grounds_do_not(self):
        self.standard()
        got, _ = self.rules(".dark .card { color: #0b1b2b; }\nhtml.dark,\n")
        self.assertEqual(got, [("theme.unrequested-dark", "error")] * 2)
        got, _ = self.rules('[data-ground="tunnel"] { background: #0b1b2b; color-scheme: dark; }\n'
                            ".darker { }\n.dark-mode-toggle { }\n")
        self.assertEqual(got, [])
        got, _ = self.rules("const dark = theme.dark ? 1 : 0;\nwindow.matchMedia('(prefers-color-scheme: dark)');\n",
                            name="a.js")
        self.assertEqual(got, [])

    def test_dark_allowed_when_theme_is_light_dark(self):
        self.pack("both", {}, theme="light-dark")
        got, _ = self.rules("@media (prefers-color-scheme: dark) { }\n", slug="both")
        self.assertEqual(got, [])


class CouldNotRun(Base):
    def test_missing_pack_is_exit_2(self):
        self.write("a.css", ".a{}\n")
        res = self.b.lint([str(self.src / "a.css")], "nope")
        self.assertEqual(res["exit"], 2)
        self.assertEqual(res["findings"][0]["rule"], "tool.could-not-run")

    def test_missing_path_is_exit_2(self):
        self.standard()
        res = self.b.lint([str(self.root / "missing")], "acme")
        self.assertEqual(res["exit"], 2)
        self.assertFalse(res["ok"])

    def test_directory_walk_picks_design_files_and_skips_node_modules(self):
        self.standard()
        (self.src / "node_modules").mkdir()
        (self.src / "node_modules" / "x.css").write_text(".a{color:#123456}\n", encoding="utf-8")
        self.write("b.txt", "#123456\n")
        self.write("c.scss", ".a{color:#123456}\n")
        res = self.b.lint([str(self.src)], "acme")
        self.assertEqual([f["file"].endswith("c.scss") for f in res["findings"]], [True])

    def test_cli_json_and_exit_codes(self):
        self.standard()
        self.write("a.css", ".a { color: #123456; }\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.b.main(["lint", str(self.src / "a.css"), "--brand", "acme", "--json"])
        self.assertEqual(rc, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data["exit"], 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.b.main(["lint", str(self.src / "a.css"), "--brand", "nope"]), 2)
            self.assertEqual(self.b.main(["lint", str(self.root / "gone"), "--brand", "acme"]), 2)


class Cli(Base):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = self.b.main(list(argv))
        return rc, out.getvalue()

    def test_show_prints_palette_fonts_and_the_prose_in_full(self):
        self.standard()
        rc, out = self.run_cli("show", "acme")
        self.assertEqual(rc, 0)
        for needle in ("ink", "#0b1b2b", "Sohne Breit", "light-only", "8", "Inter", "Acme voice", "Dry.",
                       "Acme graphic", "Ledger rules.", "House graphic"):
            self.assertIn(needle, out)
        self.assertEqual(self.run_cli("show", "nope")[0], 2)

    def test_show_ends_with_the_brands_notes(self):
        self.standard()
        import notes
        importlib.reload(notes)
        notes.add("acme", "The client asked twice for more air around the ledger", ["round 1"], "job-a")
        rc, out = self.run_cli("show", "acme")
        self.assertIn("Notes from past jobs", out)
        self.assertIn("more air around the ledger", out)

    def test_init_copies_the_templates_and_list_finds_it(self):
        self.b.TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates" / "brands"
        rc, out = self.run_cli("init", "house")
        self.assertEqual(rc, 0, out)
        rc, out = self.run_cli("init", "zeta", "--name", "Zeta Ltd")
        self.assertEqual(rc, 0, out)
        p = self.b.load("zeta")
        self.assertEqual(p["meta"]["slug"], "zeta")
        self.assertEqual(p["meta"]["name"], "Zeta Ltd")
        self.assertEqual(p["meta"]["extends"], "house")
        self.assertEqual(self.b.validate("zeta"), [])
        self.assertEqual(self.run_cli("init", "zeta")[0], 2)    # never overwrites
        rc, out = self.run_cli("list")
        self.assertIn("zeta", out)
        self.assertIn("house", out)

    def test_validate_cli(self):
        self.standard()
        self.assertEqual(self.run_cli("validate", "acme")[0], 0)
        self.assertEqual(self.run_cli("validate")[0], 0)
        self.pack("bad", {"radius": {"max_px": -1}})
        self.assertEqual(self.run_cli("validate", "bad")[0], 1)
        self.assertEqual(self.run_cli("validate", "nope")[0], 2)

    def test_lint_uses_the_project_brand(self):
        self.standard()
        proj = self.root / "proj"
        (proj / ".design").mkdir(parents=True)
        (proj / ".design" / "brand").write_text("acme\n", encoding="utf-8")
        (proj / "a.css").write_text(".a{color:#123456}\n", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(proj)
        try:
            rc, _ = self.run_cli("lint", "a.css")
        finally:
            os.chdir(cwd)
        self.assertEqual(rc, 1)


class Extract(Base):
    CSS = (":root { --ink: #0B1B2B; --paper: #f6f5f1; --gap: 8px; }\n"
           "body { font-family: 'Sohne', sans-serif; color: #0b1b2b; }\n"
           "h1, h2 { font-family: \"Sohne Breit\", serif; }\n"
           "code { font-family: 'Sohne Mono', monospace; }\n"
           ".x { color: #ccff00; } .y { color: #ccff00; } .z { border-radius: 6px; } .p { border-radius: 9999px; }\n")

    def test_extract_from_files(self):
        f = self.write("site.css", self.CSS)
        t = self.b.extract([str(f)])
        self.assertEqual(t["colors"]["allowed"]["ink"], "#0b1b2b")
        self.assertEqual(t["colors"]["allowed"]["paper"], "#f6f5f1")
        self.assertEqual(t["_ranked_colors"][0]["hex"], "#ccff00")
        self.assertEqual(t["fonts"]["text"], ["Sohne"])
        self.assertEqual(t["fonts"]["display"], ["Sohne Breit"])
        self.assertEqual(t["fonts"]["mono"], ["Sohne Mono"])
        self.assertEqual(t["radius"]["max_px"], 6)

    def test_extract_from_a_url_follows_linked_stylesheets(self):
        import http.server, threading, functools
        site = self.root / "site"
        site.mkdir()
        (site / "index.html").write_text('<html><head><link rel="stylesheet" href="/s.css">'
                                         '<style>.q{color:#abcdef}</style></head></html>', encoding="utf-8")
        (site / "s.css").write_text(self.CSS, encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
        handler.log_message = lambda *a, **k: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            t = self.b.extract([f"http://127.0.0.1:{srv.server_address[1]}/index.html"])
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(t["colors"]["allowed"]["ink"], "#0b1b2b")
        self.assertIn("#abcdef", [c["hex"] for c in t["_ranked_colors"]])

    def test_extract_writes_only_with_write(self):
        f = self.write("site.css", self.CSS)
        self.pack("acme", {})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.b.main(["extract", "--css", str(f)]), 0)
        self.assertEqual(json.loads((self.root / "home/brands/acme/tokens.json").read_text()), {})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.b.main(["extract", "--css", str(f), "--write", "acme"]), 0)
        got = json.loads((self.root / "home/brands/acme/tokens.json").read_text())
        self.assertEqual(got["colors"]["allowed"]["ink"], "#0b1b2b")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.b.main(["extract", "--css", str(self.root / "gone.css")]), 2)


class Templates(unittest.TestCase):
    def test_shipped_templates_are_valid_and_neutral(self):
        tmp = tempfile.TemporaryDirectory()
        old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = tmp.name
        try:
            import brandpack
            importlib.reload(brandpack)
            for slug in ("house", "example"):
                self.assertEqual(brandpack.validate(slug), [], slug)
            t = brandpack.load("example")["tokens"]
            self.assertIn(EM, t["copy"]["banned_chars"])
            self.assertIn(EN, t["copy"]["banned_chars"])
            self.assertTrue(t["fonts"]["banned"])
            for f in (brandpack.TEMPLATES).rglob("*"):
                if f.is_file():
                    text = f.read_text(encoding="utf-8")
                    self.assertNotIn(EM, text, f)
                    self.assertNotIn(EN, text, f)
        finally:
            if old is None:
                os.environ.pop("DDR_HOME", None)
            else:
                os.environ["DDR_HOME"] = old
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
