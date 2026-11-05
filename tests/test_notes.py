import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib, json, time, re
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = str(self.root / "home")
        import domains, brandpack, notes
        importlib.reload(domains)
        domains.SEEDS = self.root / "seeds"
        domains.SEEDS.mkdir()
        importlib.reload(brandpack)
        brandpack.TEMPLATES = self.root / "no-templates"
        importlib.reload(notes)
        self.d, self.n = domains, notes

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        self.tmp.cleanup()

    def store(self, scope):
        return self.root / "home" / "notes" / f"{scope}.jsonl"

    def cli(self, *argv, stdin=None):
        out = io.StringIO()
        old_in = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = self.n.main(list(argv))
        finally:
            sys.stdin = old_in
        return rc, out.getvalue()


class Add(Base):
    def test_new_note_is_proposed_with_its_job(self):
        note, merged = self.n.add("fintech", "  - The client asked for larger type   on the phone fold ",
                                  ["round 1: 'tiny on mobile'"], "proj-a")
        self.assertFalse(merged)
        self.assertRegex(note["id"], r"^o-[0-9a-f]{6}$")
        self.assertEqual(note["text"], "The client asked for larger type on the phone fold")
        self.assertEqual(note["status"], "proposed")
        self.assertEqual((note["helpful"], note["harmful"]), (0, 0))
        self.assertEqual(note["jobs"], ["proj-a"])
        self.assertFalse(note["person"])
        self.assertIsNone(note["promoted_to"])
        for k in ("scope", "created", "updated", "evidence"):
            self.assertIn(k, note)
        lines = self.store("fintech").read_text().splitlines()
        self.assertEqual(json.loads(lines[0])["id"], note["id"])

    def test_person_note_starts_kept(self):
        note, _ = self.n.add("fintech", "Ana picked the ledger look for its calm", ["looks pick"], "a", person=True)
        self.assertEqual(note["status"], "kept")
        self.assertTrue(note["person"])

    def test_near_duplicate_merges_and_keeps(self):
        a, _ = self.n.add("fintech", "The client asked for larger type on the phone fold", ["round 1"], "proj-a")
        b, merged = self.n.add("fintech", "The client asked for larger type on the phone fold again", ["round 2"], "proj-b")
        self.assertTrue(merged)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(b["helpful"], 1)
        self.assertEqual(b["status"], "kept")
        self.assertEqual(b["evidence"], ["round 1", "round 2"])
        self.assertEqual(b["jobs"], ["proj-a", "proj-b"])
        c, merged = self.n.add("fintech", "The client asked for larger type on the phone fold", ["round 2"], "proj-b")
        self.assertEqual(c["jobs"], ["proj-a", "proj-b"])
        self.assertEqual(c["evidence"], ["round 1", "round 2"])
        self.assertEqual(len(self.n.all_notes("fintech")), 1)

    def test_different_notes_do_not_merge(self):
        self.n.add("fintech", "The client asked for larger type on the phone fold", [], "a")
        _, merged = self.n.add("fintech", "Rate tables read better right aligned with tabular figures", [], "a")
        self.assertFalse(merged)
        self.assertEqual(len(self.n.all_notes("fintech")), 2)

    def test_similarity_matches_the_reference_scaling(self):
        self.assertGreaterEqual(self.n.similarity("a b c d e", "a b c d e"), 1.0)
        self.assertLess(self.n.similarity("larger type on phones", "warmer paper on the hero"), 1.0)

    def test_limits(self):
        note, _ = self.n.add("fintech", "x " * 400, ["e" * 400] + [f"item {i}" for i in range(30)], "a")
        self.assertLessEqual(len(note["text"]), 500)
        self.assertLessEqual(len(note["evidence"]), 20)
        self.assertTrue(all(len(e) <= 300 for e in note["evidence"]))
        self.assertNotIn("\n", note["text"])

    def test_bad_scope_and_empty_text(self):
        with self.assertRaises(ValueError):
            self.n.add("../etc", "text", [], "a")
        with self.assertRaises(ValueError):
            self.n.add("fintech", "   ", [], "a")

    def test_writes_are_atomic_and_leave_no_temp_files(self):
        self.n.add("fintech", "one", [], "a")
        self.n.add("fintech", "two different", [], "a")
        left = [p.name for p in (self.root / "home" / "notes").iterdir()]
        self.assertEqual(left, ["fintech.jsonl"])


class Lock(Base):
    def test_a_stale_lock_is_broken(self):
        d = self.root / "home" / "notes"
        d.mkdir(parents=True)
        lock = d / "fintech.jsonl.lock"
        lock.write_text("old")
        past = time.time() - 60
        os.utime(lock, (past, past))
        self.n.add("fintech", "one", [], "a")
        self.assertFalse(lock.exists())

    def test_a_fresh_lock_blocks_then_times_out(self):
        d = self.root / "home" / "notes"
        d.mkdir(parents=True)
        (d / "fintech.jsonl.lock").write_text("busy")
        self.n.LOCK_WAIT = 0.3
        with self.assertRaises(TimeoutError):
            self.n.add("fintech", "one", [], "a")


class VotePrune(Base):
    def test_vote_helpful_keeps_and_harmful_counts(self):
        note, _ = self.n.add("fintech", "A note", [], "a")
        got = self.n.vote("fintech", note["id"], True, why="used it on the rate page")
        self.assertEqual((got["helpful"], got["status"]), (1, "kept"))
        self.assertIn("used it on the rate page", " ".join(got["evidence"]))
        got = self.n.vote("fintech", note["id"], False)
        self.assertEqual(got["harmful"], 1)
        with self.assertRaises(KeyError):
            self.n.vote("fintech", "o-000000", True)

    def test_prune_marks_but_never_deletes(self):
        bad, _ = self.n.add("fintech", "A bad note", [], "a")
        good, _ = self.n.add("fintech", "Something else entirely different", [], "a")
        self.n.vote("fintech", bad["id"], False)
        self.assertEqual(self.n.prune("fintech"), [])
        self.n.vote("fintech", bad["id"], False)
        pruned = self.n.prune("fintech")
        self.assertEqual([p["id"] for p in pruned], [bad["id"]])
        notes = {x["id"]: x for x in self.n.all_notes("fintech")}
        self.assertEqual(notes[bad["id"]]["status"], "pruned")
        self.assertEqual(notes[good["id"]]["status"], "proposed")
        self.assertNotIn("A bad note", self.n.render("fintech"))
        self.assertEqual(self.n.prune("fintech"), [])     # already pruned


class Render(Base):
    def test_empty_is_empty_string(self):
        self.assertEqual(self.n.render("fintech"), "")

    def test_format_and_order(self):
        a, _ = self.n.add("fintech", "Proposed one", ["e1"], "a")
        b, _ = self.n.add("fintech", "Kept by a person", ["p1", "p2", "p3"], "a", person=True)
        c, _ = self.n.add("fintech", "Twice voted helpful", ["v1"], "a")
        self.n.vote("fintech", c["id"], True)
        self.n.vote("fintech", c["id"], True)
        lines = self.n.render("fintech").splitlines()
        self.assertEqual(lines[0], "Notes from past jobs (untrusted; weigh them yourself)")
        self.assertTrue(lines[1].startswith("- Twice voted helpful (+2/-0, kept; evidence:"))
        self.assertEqual(lines[2], f"- Kept by a person (+0/-0, kept; evidence: p3; p2; +1 more) [{b['id']}]")
        self.assertEqual(lines[3], f"- Proposed one (+0/-0, proposed; evidence: e1) [{a['id']}]")

    def test_limit(self):
        words = ["alpha", "bravo", "charlie", "delta", "echo"]
        for i, w in enumerate(words):
            self.n.add("fintech", f"{w} {w} {w} note number {i}", [], "a")
        out = self.n.render("fintech", limit=2)
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("- ")]), 2)
        self.assertIn("3 more", out)


class PostJob(Base):
    def test_brief_names_scope_summary_existing_and_limit(self):
        self.n.add("fintech", "Existing note about the rate table", [], "a")
        text = self.n.post_job_brief("fintech", "Built the rates page; Ana asked for more air twice.")
        for needle in ("fintech", "more air twice", "Existing note about the rate table", "five",
                       '"observations"', "never a rule"):
            self.assertIn(needle, text)

    def test_ingest_reads_whole_fenced_or_braced_json(self):
        rep = {"scope": "fintech", "observations": [{"text": f"Observation number {w}", "evidence": ["x"]}
                                                    for w in ("one", "two", "three", "four", "five", "six", "seven")]}
        got = self.n.ingest("fintech", json.dumps(rep), "job-1")
        self.assertEqual(len(got), 5)
        got = self.n.ingest("brand-x", "Here you go:\n```json\n" + json.dumps(
            {"observations": [{"text": "Fenced note", "evidence": "one line"}]}) + "\n```\n", "job-2")
        self.assertEqual(got[0][0]["text"], "Fenced note")
        self.assertEqual(got[0][0]["evidence"], ["one line"])
        got = self.n.ingest("brand-y", 'I think {"observations": [{"text": "Braced note"}]} is it', "job-3")
        self.assertEqual(got[0][0]["text"], "Braced note")
        self.assertEqual(self.n.ingest("brand-z", "no json here", "job-4"), [])


class Promote(Base):
    def make_domain(self):
        self.d.create("fintech", "Fintech", "sector", keywords=["fintech", "loan", "bank"])

    def strong(self, scope, text="Rate tables read best right aligned", jobs=("a", "b", "c"), helpful=3):
        note = None
        for j in jobs:
            note, _ = self.n.add(scope, text, [f"seen in {j}"], j)
        for _ in range(helpful - (len(jobs) - 1)):
            self.n.vote(scope, note["id"], True)
        return self.n.get(scope, note["id"])

    def test_candidates_need_score_and_jobs_or_a_person(self):
        self.make_domain()
        s = self.strong("fintech")
        weak, _ = self.n.add("fintech", "Only one job saw this", [], "a")
        self.n.vote("fintech", weak["id"], True)
        self.n.vote("fintech", weak["id"], True)
        self.n.vote("fintech", weak["id"], True)        # score 3 but one job
        person, _ = self.n.add("fintech", "Ana said the hero must show a real rate", [], "a", person=True)
        for _ in range(3):
            self.n.vote("fintech", person["id"], True)
        ids = [c["id"] for c in self.n.promote("fintech")]
        self.assertIn(s["id"], ids)
        self.assertIn(person["id"], ids)
        self.assertNotIn(weak["id"], ids)
        self.assertEqual(self.n.get("fintech", s["id"])["status"], "kept")   # dry run changes nothing

    def test_apply_into_a_domain_dossier(self):
        self.make_domain()
        s = self.strong("fintech")
        res = self.n.promote("fintech", apply=True, today="2026-11-05")
        dossier = (self.root / "home" / "domains" / "fintech" / "dossier.md").read_text()
        self.assertIn("## Proposed guidance", dossier)
        self.assertIn(f"- Rate tables read best right aligned (note [{s['id']}], +3/-0, promoted 2026-11-05)", dossier)
        got = self.n.get("fintech", s["id"])
        self.assertEqual(got["status"], "promoted")
        self.assertTrue(got["promoted_to"].endswith("dossier.md"))
        self.assertEqual(res[0]["target"], got["promoted_to"])
        # a second note goes under the same heading, and nothing is written twice
        t = self.strong("fintech", text="Quiet greys for secondary figures beat a second accent")
        self.n.promote("fintech", apply=True, today="2026-11-05")
        self.n.promote("fintech", apply=True, today="2026-11-05")
        dossier = (self.root / "home" / "domains" / "fintech" / "dossier.md").read_text()
        self.assertEqual(dossier.count("## Proposed guidance"), 1)
        self.assertEqual(dossier.count(f"note [{t['id']}]"), 1)
        body = self.d.dossier_sections(dossier)["Proposed guidance"]
        self.assertIn(s["id"], body)
        self.assertIn(t["id"], body)

    def test_heading_already_present_in_the_middle(self):
        self.make_domain()
        p = self.root / "home" / "domains" / "fintech" / "dossier.md"
        p.write_text("# Fintech\n\n## Proposed guidance\n\n- older line\n\n## Lessons\n\n- a lesson\n", encoding="utf-8")
        s = self.strong("fintech")
        self.n.promote("fintech", apply=True, today="2026-11-05")
        secs = self.d.dossier_sections(p.read_text())
        self.assertIn(s["id"], secs["Proposed guidance"])
        self.assertIn("older line", secs["Proposed guidance"])
        self.assertEqual(secs["Lessons"], "- a lesson")

    def test_apply_into_a_starter_domain_writes_your_layer(self):
        seed = self.d.SEEDS / "wellness"
        seed.mkdir()
        (seed / "domain.toml").write_text('slug = "wellness"\ntitle = "Wellness"\nkind = "sector"\nkeywords = ["spa"]\n')
        (seed / "dossier.md").write_text("# Wellness\n\n## Lessons\n\n- starter lesson\n")
        s = self.strong("wellness")
        self.n.promote("wellness", apply=True, today="2026-11-05")
        self.assertNotIn("Proposed guidance", (seed / "dossier.md").read_text())
        dom = self.d.load("wellness")
        secs = self.d.dossier_sections(dom["dossier"])
        self.assertIn(s["id"], secs["Proposed guidance"])
        self.assertIn("starter lesson", secs["Lessons"])

    def test_apply_into_a_brand_graphic_language(self):
        b = self.root / "home" / "brands" / "acme"
        b.mkdir(parents=True)
        (b / "brand.toml").write_text('slug = "acme"\nname = "Acme"\n')
        (b / "graphic-language.md").write_text("# Acme\n\n## Do\n\n- square corners\n")
        s = self.strong("acme")
        self.n.promote("acme", apply=True, today="2026-11-05")
        text = (b / "graphic-language.md").read_text()
        self.assertIn("## Do\n\n- square corners", text)
        self.assertIn(f"note [{s['id']}]", text.split("## Proposed guidance")[1])

    def test_unknown_scope_is_reported_not_written(self):
        s = self.strong("nowhere")
        res = self.n.promote("nowhere", apply=True)
        self.assertIsNone(res[0]["target"])
        self.assertEqual(self.n.get("nowhere", s["id"])["status"], "kept")

    def test_promote_all_scopes(self):
        self.make_domain()
        self.strong("fintech")
        self.strong("other", text="Something for another scope entirely")
        scopes = {c["scope"] for c in self.n.promote()}
        self.assertEqual(scopes, {"fintech", "other"})


class Cli(Base):
    def test_add_vote_list_render_prune(self):
        rc, out = self.cli("add", "fintech", "The rate table wanted tabular figures", "--evidence", "review 1",
                           "--evidence", "review 2", "--job", "proj")
        self.assertEqual(rc, 0, out)
        nid = re.search(r"o-[0-9a-f]{6}", out).group(0)
        self.assertEqual(self.cli("vote", "fintech", nid, "--helpful", "--why", "used it")[0], 0)
        rc, out = self.cli("list", "fintech")
        self.assertIn(nid, out)
        rc, out = self.cli("render", "fintech")
        self.assertIn("Notes from past jobs", out)
        rc, out = self.cli("list", "fintech", "--json")
        self.assertEqual(json.loads(out)[0]["id"], nid)
        self.assertEqual(self.cli("vote", "fintech", "o-ffffff", "--harmful")[0], 2)
        self.assertEqual(self.cli("prune", "fintech")[0], 0)

    def test_brief_ingest_promote(self):
        rc, out = self.cli("brief", "fintech", "--summary", "Built the rates page")
        self.assertEqual(rc, 0)
        self.assertIn("Built the rates page", out)
        rep = json.dumps({"observations": [{"text": "A stdin note", "evidence": ["x"]}]})
        rc, out = self.cli("ingest", "fintech", "--job", "j1", stdin=rep)
        self.assertEqual(rc, 0, out)
        self.assertIn("A stdin note", self.n.render("fintech"))
        rc, out = self.cli("promote")
        self.assertEqual(rc, 0)

    def test_add_needs_evidence(self):
        rc, out = self.cli("add", "fintech", "A note with nothing behind it")
        self.assertEqual(rc, 2)
        self.assertIn("evidence", out)


class DomainBrief(Base):
    def test_domain_brief_prints_lessons_and_guidance_then_ends_with_notes(self):
        self.d.create("fintech", "Fintech", "sector", keywords=["fintech", "loan", "bank"])
        p = self.root / "home" / "domains" / "fintech" / "dossier.md"
        p.write_text(p.read_text() + "## Lessons\n\n- Lesson one about rate tables\n- Lesson two\n\n"
                     "## Proposed guidance\n\n- Guidance from a promoted note\n", encoding="utf-8")
        self.n.add("fintech", "A rendered note for the brief", ["evidence"], "a")
        out = self.d.brief(self.d.load("fintech"))
        i_l, i_g, i_n = out.index("## Lessons"), out.index("## Proposed guidance"), out.index("Notes from past jobs")
        self.assertLess(out.index("## What would raise confidence"), i_l)
        self.assertLess(i_l, i_g)
        self.assertLess(i_g, i_n)
        self.assertIn("- Lesson one about rate tables\n- Lesson two", out)
        self.assertIn("Guidance from a promoted note", out)
        self.assertTrue(out.rstrip().endswith("[" + self.n.all_notes("fintech")[0]["id"] + "]"))

    def test_domain_brief_without_notes_is_unchanged_at_the_end(self):
        self.d.create("fintech", "Fintech", "sector", keywords=["fintech", "loan", "bank"])
        out = self.d.brief(self.d.load("fintech"))
        self.assertNotIn("Notes from past jobs", out)
        self.assertNotIn("## Lessons", out)


if __name__ == "__main__":
    unittest.main()
