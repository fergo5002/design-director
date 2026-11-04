import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib, datetime as dt, json
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

TODAY = dt.date(2026, 11, 4)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.home = root / "home"
        self.seeds = root / "seeds"
        self.seeds.mkdir()
        self.old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = str(self.home)
        import domains
        importlib.reload(domains)
        domains.SEEDS = self.seeds
        self.d = domains

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        self.tmp.cleanup()

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.d.main(list(argv))
        return rc, out.getvalue() + err.getvalue()

    def fintech(self):
        return self.d.create("fintech", "Fintech and lending", "sector",
                             summary="Money products: lending, cards, banking, payments.",
                             keywords=["fintech", "lending", "loan", "bank", "payments", "credit"],
                             aliases=["revenue based financing"])

    def ref(self, slug="fintech", **kw):
        base = dict(name="Mercury", url="https://mercury.com", verdict="exemplar", angle="direct",
                    evidence="screenshot", take="Calm ledger type, money right-aligned", score=5,
                    seen=TODAY.isoformat())
        base.update(kw)
        return self.d.add_ref(slug, **base)

    def write_dossier(self, slug, words=40, sections=None):
        dom = self.d.load(slug)
        text = "# Dossier\n\n"
        for s in sections or self.d.SECTIONS:
            text += f"## {s}\n\n" + " ".join(["word"] * words) + "\n\n"
        (dom["path"] / "dossier.md").write_text(text, encoding="utf-8")


class Create(Base):
    def test_create_writes_the_four_files(self):
        self.fintech()
        p = self.home / "domains" / "fintech"
        for f in ("domain.toml", "refs.toml", "dossier.md", "ledger.jsonl"):
            self.assertTrue((p / f).exists(), f)
        dom = self.d.load("fintech")
        self.assertEqual(dom["meta"]["kind"], "sector")
        self.assertIn("lending", dom["meta"]["keywords"])
        for s in self.d.SECTIONS:
            self.assertIn(f"## {s}", dom["dossier"])

    def test_rejects_unknown_kind_and_duplicate(self):
        with self.assertRaises(ValueError):
            self.d.create("x", "X", "industry")
        self.fintech()
        with self.assertRaises(ValueError):
            self.fintech()

    def test_slug_is_normalised(self):
        self.d.create("Local Services!", "Local services", "sector", keywords=["local"])
        self.assertIsNotNone(self.d.load("local-services"))


class Refs(Base):
    def test_add_and_dedupe_by_normalised_url(self):
        self.fintech()
        self.ref()
        with self.assertRaises(ValueError):
            self.ref(url="http://www.mercury.com/")
        self.assertEqual(len(self.d.load("fintech")["refs"]), 1)

    def test_exemplar_needs_take_and_counter_needs_avoid(self):
        self.fintech()
        with self.assertRaises(ValueError):
            self.ref(take="")
        with self.assertRaises(ValueError):
            self.ref(name="Slop bank", url="https://slop.example", verdict="counter", take="", avoid="")
        self.ref(name="Slop bank", url="https://slop.example", verdict="counter", take="",
                 avoid="Purple gradient hero, three icon cards, stock handshake")

    def test_retired_refs_stay_in_the_graveyard_and_block_readding(self):
        self.fintech()
        r = self.ref()
        self.d.retire_ref("fintech", r["id"], reason="Redesigned in 2026 into a generic template", today=TODAY)
        dom = self.d.load("fintech")
        self.assertEqual(dom["refs"][0]["status"], "retired")
        self.assertIn("generic", dom["refs"][0]["retired_reason"])
        with self.assertRaises(ValueError):
            self.ref()
        # with a reason it can come back
        self.ref(force="Re-checked: the redesign was reverted")

    def test_retire_needs_a_reason(self):
        self.fintech()
        r = self.ref()
        with self.assertRaises(ValueError):
            self.d.retire_ref("fintech", r["id"], reason="")

    def test_seen_refreshes_date_and_evidence(self):
        self.fintech()
        r = self.ref(seen="2024-01-01", evidence="visited")
        self.d.reverify("fintech", r["id"], evidence="flow", today=TODAY)
        got = self.d.load("fintech")["refs"][0]
        self.assertEqual(got["seen"], TODAY.isoformat())
        self.assertEqual(got["evidence"], "flow")

    def test_fields_with_quotes_round_trip(self):
        self.fintech()
        self.ref(take='Says "no fees" and means it; a \\ backslash')
        self.assertEqual(self.d.load("fintech")["refs"][0]["take"], 'Says "no fees" and means it; a \\ backslash')


class Confidence(Base):
    def test_empty_domain_is_thin(self):
        self.fintech()
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertEqual(c["band"], "thin")
        self.assertLess(c["score"], 10)
        self.assertTrue(c["gaps"])

    def test_search_only_refs_are_capped(self):
        self.fintech()
        for i in range(12):
            self.ref(name=f"R{i}", url=f"https://r{i}.example", evidence="search")
        self.write_dossier("fintech")
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertLessEqual(c["score"], 25)
        self.assertIn("looked", c["cap"])

    def test_well_researched_domain_is_strong_and_staleness_decays_it(self):
        self.fintech()
        for i in range(10):
            self.ref(name=f"R{i}", url=f"https://r{i}.example", angle=["direct", "leader", "outside"][i % 3])
        for i in range(4):
            self.ref(name=f"C{i}", url=f"https://c{i}.example", verdict="counter", take="", avoid="generic hero")
        self.write_dossier("fintech")
        for i in range(2):
            self.d.log("fintech", "shipped", f"Site {i}", today=TODAY)
        for i in range(3):
            self.d.log("fintech", "win", f"Win {i}", today=TODAY)
        fresh = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertEqual(fresh["band"], "strong")
        self.assertGreaterEqual(fresh["score"], 90)
        old = self.d.confidence(self.d.load("fintech"), today=TODAY + dt.timedelta(days=730))
        self.assertLess(old["score"], fresh["score"] - 25)

    def test_missing_slop_section_caps_confidence(self):
        self.fintech()
        for i in range(10):
            self.ref(name=f"R{i}", url=f"https://r{i}.example", angle=["direct", "leader", "outside"][i % 3])
        secs = [s for s in self.d.SECTIONS if s != "Category slop"]
        self.write_dossier("fintech", sections=secs)
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertLessEqual(c["score"], 60)
        self.assertIn("slop", c["cap"].lower())

    def test_unresolved_miss_costs_and_a_rule_earns(self):
        self.fintech()
        base = self.d.confidence(self.d.load("fintech"), today=TODAY)["parts"]["lessons"]
        self.d.log("fintech", "miss", "Card grid of KPIs", why="nothing leads", today=TODAY)
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertLess(c["parts"]["unresolved"], 0)
        self.assertTrue(any("rule" in g for g in c["gaps"]))
        self.d.log("fintech", "miss", "Glass cards", why="dated", rule="SLOP.md glass", today=TODAY)
        c2 = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertGreater(c2["parts"]["lessons"], base)

    def test_dossier_template_comments_do_not_count_as_words(self):
        self.fintech()
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertEqual(c["parts"]["dossier"], 0)

    def test_plan_targets_scale_with_stakes(self):
        self.fintech()
        dom = self.d.load("fintech")
        low = self.d.plan(dom, "low", today=TODAY)
        high = self.d.plan(dom, "high", today=TODAY)
        self.assertLess(low["target"], high["target"])
        self.assertTrue(high["tasks"])


class Match(Base):
    def test_matches_sector_and_pattern_separately(self):
        self.fintech()
        self.d.create("onboarding", "Onboarding flows", "pattern",
                      keywords=["onboarding", "signup", "sign up", "kyc", "first run", "setup"])
        self.d.create("wellness", "Wellness and booking", "sector", keywords=["sauna", "spa", "yoga", "booking"])
        res = self.d.match("Design the KYC onboarding for a small business lending app")
        self.assertEqual(res["sectors"][0]["slug"], "fintech")
        self.assertEqual(res["patterns"][0]["slug"], "onboarding")
        self.assertNotIn("wellness", [m["slug"] for m in res["sectors"]])

    def test_alias_phrase_matches(self):
        self.fintech()
        res = self.d.match("A site for a revenue based financing startup")
        self.assertEqual(res["sectors"][0]["slug"], "fintech")

    def test_no_match_says_new_territory(self):
        self.fintech()
        rc, out = self.cli("match", "A website for a nursing home in Kildare")
        self.assertEqual(rc, 0)
        self.assertIn("new territory", out.lower())
        self.assertIn("ddr domain new", out)

    def test_merged_domain_redirects(self):
        self.fintech()
        self.d.create("banking", "Banking", "sector", keywords=["bank", "current account", "neobank"])
        self.ref(slug="banking", name="Monzo", url="https://monzo.com")
        self.d.merge("banking", "fintech", today=TODAY)
        res = self.d.match("a neobank current account")
        self.assertEqual(res["sectors"][0]["slug"], "fintech")
        self.assertIn("monzo.com", " ".join(r["url"] for r in self.d.load("fintech")["refs"]))
        # the merged folder is kept, marked, never deleted
        self.assertEqual(self.d.load("banking", follow=False)["meta"]["merged_into"], "fintech")


class Graph(Base):
    def test_relate_is_symmetric(self):
        self.fintech()
        self.d.create("onboarding", "Onboarding flows", "pattern", keywords=["onboarding"])
        self.d.relate("fintech", "onboarding", how="KYC-heavy signup")
        a = self.d.load("fintech")["related"]
        b = self.d.load("onboarding")["related"]
        self.assertEqual(a[0]["slug"], "onboarding")
        self.assertEqual(b[0]["slug"], "fintech")
        self.d.relate("fintech", "onboarding", how="KYC-heavy signup")  # idempotent
        self.assertEqual(len(self.d.load("fintech")["related"]), 1)

    def test_merge_keeps_dossier_text_and_ledger(self):
        self.fintech()
        self.d.create("banking", "Banking", "sector", keywords=["bank"])
        self.write_dossier("banking", words=5)
        self.d.log("banking", "win", "Ledger type", today=TODAY)
        self.d.merge("banking", "fintech", today=TODAY)
        dom = self.d.load("fintech")
        self.assertIn("Merged from banking", dom["dossier"])
        self.assertTrue(any(e["what"] == "Ledger type" for e in dom["ledger"]))
        self.assertIn("bank", dom["meta"]["keywords"])

    def test_cannot_merge_across_kinds(self):
        self.fintech()
        self.d.create("onboarding", "Onboarding", "pattern", keywords=["onboarding"])
        with self.assertRaises(ValueError):
            self.d.merge("onboarding", "fintech")


class Seeds(Base):
    def seed(self):
        p = self.seeds / "local-services"
        p.mkdir()
        (p / "domain.toml").write_text('slug = "local-services"\ntitle = "Local services"\nkind = "sector"\n'
                                       'keywords = ["nursing home", "dentist", "solicitor", "plumber"]\n', encoding="utf-8")
        (p / "refs.toml").write_text('[[ref]]\nid = "a"\nname = "A"\nurl = "https://a.example"\nverdict = "exemplar"\n'
                                     'angle = "direct"\nevidence = "visited"\ntake = "t"\nscore = 4\nseen = "2026-11-01"\n'
                                     'status = "active"\n', encoding="utf-8")
        (p / "dossier.md").write_text("# Local\n", encoding="utf-8")

    def test_seed_is_visible_and_forked_on_write(self):
        self.seed()
        self.assertEqual(self.d.load("local-services")["layer"], "seed")
        self.d.add_ref("local-services", name="B", url="https://b.example", verdict="exemplar", angle="leader",
                       evidence="visited", take="t2", score=3, seen=TODAY.isoformat())
        dom = self.d.load("local-services")
        self.assertEqual(dom["layer"], "home")
        self.assertEqual(len(dom["refs"]), 2)
        # the seed in the repo is untouched
        self.assertEqual((self.seeds / "local-services" / "refs.toml").read_text().count("[[ref]]"), 1)

    def test_fork_is_a_layer_so_later_seed_work_flows_through(self):
        self.seed()
        self.d.path_for_write("local-services")
        r = self.d.load("local-services")["refs"][0]
        self.d.retire_ref("local-services", r["id"], reason="Dated", today=TODAY)
        with open(self.seeds / "local-services" / "refs.toml", "a") as f:
            f.write('\n[[ref]]\nid = "c"\nname = "C"\nurl = "https://c.example"\nverdict = "exemplar"\n'
                    'angle = "outside"\nevidence = "visited"\ntake = "t3"\nscore = 4\nseen = "2026-11-02"\nstatus = "active"\n')
        (self.seeds / "local-services" / "dossier.md").write_text("# Local\n\n## Category slop\n\nUpstream wrote this later.\n")
        dom = self.d.load("local-services")
        statuses = {x["url"]: x["status"] for x in dom["refs"]}
        self.assertEqual(statuses["https://a.example"], "retired", "your retirement overrides the seed")
        self.assertEqual(statuses["https://c.example"], "active", "new seed work appears without a sync")
        self.assertIn("Upstream wrote this later.", dom["dossier"])
        home_refs = (self.home / "domains" / "local-services" / "refs.toml").read_text()
        self.assertNotIn("c.example", home_refs, "seed refs are read, not copied")

    def test_own_notes_sit_beside_the_seed_text(self):
        self.seed()
        (self.seeds / "local-services" / "dossier.md").write_text("# Local\n\n## Language\n\nSeed language.\n")
        p = self.d.path_for_write("local-services")
        (p / "dossier.md").write_text("# Local\n\n## Language\n\nMy own language notes.\n")
        secs = self.d.dossier_sections(self.d.load("local-services")["dossier"])
        self.assertIn("Seed language.", secs["Language"])
        self.assertIn("My own language notes.", secs["Language"])


class Audit(Base):
    def test_flags_stale_weak_and_contradictory_refs(self):
        self.fintech()
        self.ref(name="Old", url="https://old.example", seen="2024-06-01")
        self.ref(name="Weak", url="https://weak.example", evidence="search")
        self.ref(name="Meh", url="https://meh.example", score=2)
        found = self.d.audit(self.d.load("fintech"), today=TODAY)
        kinds = {f["kind"] for f in found}
        self.assertTrue({"stale", "weak", "contradiction"} <= kinds)

    def test_flags_overlapping_domains(self):
        self.fintech()
        self.d.create("lending", "Lending", "sector", keywords=["lending", "loan", "credit", "fintech"])
        found = self.d.audit_all(today=TODAY)
        self.assertTrue(any(f["kind"] == "overlap" for f in found))


class Cli(Base):
    def test_end_to_end(self):
        rc, out = self.cli("new", "fintech", "--title", "Fintech", "--kind", "sector", "--keywords", "fintech,lending")
        self.assertEqual(rc, 0, out)
        rc, out = self.cli("ref", "add", "fintech", "--name", "Mercury", "--url", "https://mercury.com",
                           "--verdict", "exemplar", "--angle", "direct", "--evidence", "screenshot",
                           "--take", "Calm ledger", "--score", "5")
        self.assertEqual(rc, 0, out)
        rc, out = self.cli("status", "fintech")
        self.assertEqual(rc, 0)
        self.assertIn("confidence", out.lower())
        rc, out = self.cli("brief", "fintech")
        self.assertIn("Mercury", out)
        rc, out = self.cli("list")
        self.assertIn("fintech", out)
        rc, out = self.cli("log", "fintech", "miss", "Purple hero")
        self.assertEqual(rc, 2)  # a miss needs --why
        rc, out = self.cli("log", "fintech", "miss", "Purple hero", "--why", "generated look")
        self.assertEqual(rc, 0)
        rc, out = self.cli("plan", "fintech", "--stakes", "high")
        self.assertIn("target", out.lower())
        rc, out = self.cli("path", "fintech")
        self.assertIn(str(self.home), out)
        rc, out = self.cli("ref", "list", "fintech")
        self.assertIn("mercury.com", out)



class Feedback(Base):
    """Fixes for friction the first research agents hit."""

    def test_slug_keeps_accented_letters_as_plain_ones(self):
        self.assertEqual(self.d.slugify("Snøhetta Norges Bank"), "snohetta-norges-bank")
        self.assertEqual(self.d.slugify("Café Été"), "cafe-ete")

    def test_ref_edit_changes_fields_and_keeps_validation(self):
        self.fintech()
        r = self.ref()
        self.d.edit_ref("fintech", r["id"], url="https://mercury.com/business", take="Better take", score=4)
        got = self.d.load("fintech")["refs"][0]
        self.assertEqual((got["url"], got["take"], got["score"]), ("https://mercury.com/business", "Better take", 4))
        self.ref(name="Other", url="https://other.example")
        with self.assertRaises(ValueError):
            self.d.edit_ref("fintech", r["id"], url="https://www.other.example/")
        with self.assertRaises(ValueError):
            self.d.edit_ref("fintech", r["id"], verdict="great")
        rc, out = self.cli("ref", "edit", "fintech", r["id"], "--notes", "Seen at 1440 and 390")
        self.assertEqual(rc, 0, out)

    def test_brief_separates_take_from_leave(self):
        self.fintech()
        self.ref(take="Calm ledger type", avoid="Cookie wall")
        self.assertIn("Calm ledger type. Leave: Cookie wall", self.d.brief(self.d.load("fintech")))

    def test_walked_flows_raise_the_ceiling_above_the_high_target(self):
        self.fintech()
        for i in range(10):
            self.ref(name=f"R{i}", url=f"https://r{i}.example", angle=["direct", "leader", "outside"][i % 3],
                     evidence="flow" if i < 3 else "screenshot")
        for i in range(4):
            self.ref(name=f"C{i}", url=f"https://c{i}.example", verdict="counter", take="", avoid="generic")
        self.write_dossier("fintech")
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertGreater(c["parts"]["depth"], 0)
        self.assertGreater(c["score"], 70)

    def test_online_audit_tells_blocked_from_dead_and_sees_path_moves(self):
        self.fintech()
        self.ref(name="Walled", url="https://walled.example", evidence="visited")
        self.ref(name="Gone", url="https://gone.example/page")
        self.ref(name="Moved", url="https://moved.example/us/en")
        answers = {"https://walled.example": (403, "https://walled.example"),
                   "https://gone.example/page": (404, "https://gone.example/page"),
                   "https://moved.example/us/en": (200, "https://moved.example/eu/en/")}
        orig = self.d._check_url
        self.d._check_url = lambda u, timeout=8.0: answers[u]
        try:
            found = {f["ref"]: f["kind"] for f in self.d.audit(self.d.load("fintech"), today=TODAY, online=True)}
        finally:
            self.d._check_url = orig
        self.assertEqual(found["walled"], "blocked")
        self.assertEqual(found["gone"], "dead")
        self.assertEqual(found["moved"], "moved")


class Record(Base):
    """Fixes for friction seeding a person's own record."""

    def test_resolve_closes_an_open_miss(self):
        self.fintech()
        self.d.log("fintech", "miss", "Card grid of KPIs", why="nothing leads", today=TODAY)
        self.assertLess(self.d.confidence(self.d.load("fintech"), today=TODAY)["parts"]["unresolved"], 0)
        self.d.resolve("fintech", "card grid", rule="DASHBOARDS.md Part 2", today=TODAY)
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertEqual(c["parts"]["unresolved"], 0)
        self.assertGreater(c["parts"]["lessons"], 0)
        with self.assertRaises(ValueError):
            self.d.resolve("fintech", "nothing like this", rule="x")

    def test_relogging_a_miss_with_a_rule_resolves_it_instead_of_duplicating(self):
        self.fintech()
        self.d.log("fintech", "miss", "Glass cards", why="dated", today=TODAY)
        self.d.log("fintech", "miss", "Glass cards", why="dated", rule="SLOP.md", today=TODAY)
        misses = [e for e in self.d.load("fintech")["ledger"] if e["kind"] == "miss"]
        self.assertEqual(len(misses), 1)
        self.assertEqual(misses[0]["rule"], "SLOP.md")

    def test_log_takes_the_original_date_so_old_events_decay(self):
        self.fintech()
        ev = self.d.log("fintech", "win", "Old win", date="2025-01-01", today=TODAY)
        self.assertEqual(ev["date"], "2025-01-01")
        with self.assertRaises(ValueError):
            self.d.log("fintech", "win", "x", date="yesterday")

    def test_edit_domain_meta(self):
        self.fintech()
        self.d.edit_domain("fintech", title="Fintech", add_keywords=["neobank"], add_aliases=["challenger bank"])
        m = self.d.load("fintech")["meta"]
        self.assertEqual(m["title"], "Fintech")
        self.assertIn("neobank", m["keywords"])
        self.assertIn("lending", m["keywords"])
        self.assertEqual(self.d.match("a challenger bank site")["sectors"][0]["slug"], "fintech")

    def test_relate_again_updates_the_note(self):
        self.fintech()
        self.d.create("onboarding", "Onboarding", "pattern", keywords=["onboarding"])
        self.d.relate("fintech", "onboarding", how="old")
        self.d.relate("fintech", "onboarding", how="KYC-heavy signup")
        self.assertEqual(self.d.load("onboarding")["related"][0]["how"], "KYC-heavy signup")

    def test_a_long_judged_record_lifts_the_no_references_cap(self):
        self.fintech()
        self.write_dossier("fintech")
        for i in range(4):
            self.d.log("fintech", "win", f"Win {i}", today=TODAY)
        for i in range(4):
            self.d.log("fintech", "miss", f"Miss {i}", why="w", rule="r", today=TODAY)
        self.d.log("fintech", "shipped", "Site", today=TODAY)
        c = self.d.confidence(self.d.load("fintech"), today=TODAY)
        self.assertNotIn("capped at 25", c["cap"])
        self.assertGreater(c["score"], 25)


class Polish(Base):
    def test_recently_rendered_ref_is_not_reported_as_blocked(self):
        self.fintech()
        self.ref(name="Walled", url="https://walled.example", evidence="screenshot", seen=TODAY.isoformat())
        self.ref(name="Old wall", url="https://oldwall.example", evidence="screenshot", seen="2026-01-01")
        orig = self.d._check_url
        self.d._check_url = lambda u, timeout=8.0: (403, u)
        try:
            found = {f["ref"]: f["kind"] for f in self.d.audit(self.d.load("fintech"), today=TODAY, online=True)}
        finally:
            self.d._check_url = orig
        self.assertNotIn("walled", found)
        self.assertEqual(found["old-wall"], "blocked")

    def test_long_names_do_not_make_ids_ending_in_a_hyphen(self):
        self.fintech()
        r = self.ref(name="GOV.UK Design System: Create accounts and Confirm an email address patterns", url="https://g.example")
        self.assertFalse(r["id"].endswith("-"), r["id"])

    def test_pattern_only_brief_is_not_told_off(self):
        self.d.create("onboarding", "Onboarding", "pattern", keywords=["onboarding", "signup"])
        rc, out = self.cli("match", "improve the signup flow")
        self.assertIn("onboarding", out)
        self.assertNotIn("New territory", out)


class ReviewFindings(Base):
    def seed(self, slug="wellness", refs=('[[ref]]\nid = "loyly"\nname = "Loyly"\nurl = "https://loyly.fi"\nverdict = "exemplar"\n'
                                           'angle = "direct"\nevidence = "screenshot"\ntake = "t"\nscore = 4\nseen = "2026-11-01"\n'
                                           'shots = "shots/loyly.fi"\n'),
             dossier="# W\n\n## Extra notes\n\nSeed extra.\n"):
        p = self.seeds / slug
        p.mkdir()
        (p / "domain.toml").write_text(f'slug = "{slug}"\ntitle = "W"\nkind = "sector"\nkeywords = ["sauna", "spa", "wellness"]\n')
        (p / "refs.toml").write_text(refs)
        (p / "dossier.md").write_text(dossier)
        return p

    def test_editing_a_starter_refs_url_does_not_resurrect_the_old_one(self):
        self.seed()
        self.d.edit_ref("wellness", "loyly", url="https://loyly.fi/en")
        act = self.d.active(self.d.load("wellness"))
        self.assertEqual([r["url"] for r in act], ["https://loyly.fi/en"])
        self.assertEqual(len({r["id"] for r in self.d.load("wellness")["refs"]}), len(self.d.load("wellness")["refs"]))

    def test_merging_a_forked_starter_keeps_its_references(self):
        self.seed()
        self.d.log("wellness", "note", "forked")
        self.d.create("spas", "Spas", "sector", keywords=["spa"])
        self.d.merge("wellness", "spas")
        self.assertIn("https://loyly.fi", [r["url"] for r in self.d.load("spas")["refs"]])

    def test_custom_section_in_both_layers_appears_once(self):
        self.seed()
        p = self.d.path_for_write("wellness")
        (p / "dossier.md").write_text("# W\n\n## Extra notes\n\nMine.\n")
        text = self.d.load("wellness")["dossier"]
        self.assertEqual(text.count("## Extra notes"), 1)
        self.assertIn("Seed extra.", text); self.assertIn("Mine.", text)

    def test_replacing_keywords_on_a_fork_can_drop_the_starters(self):
        self.seed()
        self.d.edit_domain("wellness", keywords=["steam"])
        self.assertEqual(self.d.load("wellness")["meta"]["keywords"], ["steam"])

    def test_seen_score_is_checked(self):
        self.seed()
        with self.assertRaises(ValueError):
            self.d.reverify("wellness", "loyly", score=9)

if __name__ == "__main__":
    unittest.main()
