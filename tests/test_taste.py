import sys, unittest, pathlib, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import taste

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.d.name, "taste.jsonl")

    def tearDown(self):
        self.d.cleanup()

    def add(self, kind, what, tags=(), date="2026-11-01", **kw):
        return taste.append(self.path, kind=kind, what=what, tags=list(tags), date=date, **kw)

    def test_append_and_read_roundtrip(self):
        self.add("win", "masked rise", ["motion:masked-rise"], values="90ms stagger")
        evs = taste.read(self.path)
        self.assertEqual(evs[0]["kind"], "win")
        self.assertEqual(evs[0]["values"], "90ms stagger")
        self.assertEqual(json.loads(self.path.read_text().splitlines()[0])["what"], "masked rise")

    def test_rejects_bad_tags_and_kinds(self):
        with self.assertRaises(ValueError):
            self.add("win", "x", ["no-axis"])
        with self.assertRaises(ValueError):
            self.add("praise", "x", ["type:serif"])

    def test_miss_requires_a_reason(self):
        with self.assertRaises(ValueError):
            self.add("miss", "ugly hero", ["layout:centred"])

    def test_saturation_flags_repeated_wins_and_ships(self):
        for i in range(4):
            self.add("win", f"w{i}", ["type:serif-display", f"colour:c{i}"])
        self.add("shipped", "s", ["type:serif-display"])
        sat = taste.saturation(taste.read(self.path), today="2026-11-01")
        self.assertIn("type:serif-display", [t for t, _ in sat])
        self.assertNotIn("colour:c1", [t for t, _ in sat])

    def test_old_events_decay_out_of_saturation(self):
        for i in range(4):
            self.add("win", f"w{i}", ["type:serif-display"], date="2024-01-01")
        for i in range(4):
            self.add("win", f"n{i}", [f"type:grotesk-{i}"], date="2026-10-30")
        sat = taste.saturation(taste.read(self.path), today="2026-11-01")
        self.assertNotIn("type:serif-display", [t for t, _ in sat])

    def test_brief_has_avoid_proven_saturated_and_three_directions(self):
        for i in range(3):
            self.add("win", f"serif hero {i}", ["type:serif-display"], values="Instrument Serif 96px")
        self.add("miss", "card soup dashboard", ["layout:card-grid"], why="every tile the same weight")
        text = taste.brief(taste.read(self.path), today="2026-11-01", draw=[])
        for needle in ("Avoid", "card soup dashboard", "Proven", "Saturated", "type:serif-display", "Direction B"):
            self.assertIn(needle, text)

    def test_brief_on_empty_ledger_still_gives_method(self):
        text = taste.brief([], today="2026-11-01", draw=[])
        self.assertIn("Direction A", text)
        self.assertIn("No taste logged yet", text)

    def test_export_strips_project(self):
        self.add("win", "w", ["type:serif"], project="secret-client", values="v")
        md = taste.export(taste.read(self.path))
        self.assertNotIn("secret-client", md)
        self.assertIn("type:serif", md)

class Cli(unittest.TestCase):
    def test_file_option_works_before_and_after_the_subcommand(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as d:
            f = str(pathlib.Path(d, "t.jsonl"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(taste.main(["--file", f, "win", "a", "--tags", "type:x"]), 0)
                self.assertEqual(taste.main(["win", "b", "--tags", "type:y", "--file", f]), 0)
            self.assertEqual(len(taste.read(f)), 2)

if __name__ == "__main__":
    unittest.main()
