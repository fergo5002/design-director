import sys, os, unittest, pathlib, tempfile, importlib, io, contextlib, json
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


class Pick(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old = os.environ.get("DDR_HOME")
        self.old_taste = os.environ.pop("DD_TASTE", None)
        os.environ["DDR_HOME"] = str(self.root)
        import domains, notes, looks
        importlib.reload(domains)
        domains.SEEDS = self.root / "no-seeds"
        importlib.reload(notes)
        importlib.reload(looks)
        self.d, self.n, self.l = domains, notes, looks
        self.d.create("fintech", "Fintech", "sector", keywords=["fintech", "loan", "bank"])

    def tearDown(self):
        if self.old is None:
            os.environ.pop("DDR_HOME", None)
        else:
            os.environ["DDR_HOME"] = self.old
        if self.old_taste is not None:
            os.environ["DD_TASTE"] = self.old_taste
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = self.l.main(list(argv))
        return rc, out.getvalue()

    def test_pick_records_a_taste_win_and_a_person_note(self):
        rc, out = self.run_cli("pick", "--look", "b", "--why", "the ledger reads calm and the rate leads",
                               "--others", "a,c", "--domain", "fintech", "--tags", "type:grotesk,layout:ledger",
                               "--values", "Sohne 15/1.5")
        self.assertEqual(rc, 0, out)
        ev = [json.loads(l) for l in (self.root / "taste.jsonl").read_text().splitlines()]
        self.assertEqual(ev[-1]["kind"], "win")
        self.assertEqual(ev[-1]["what"], "picked look b over a, c")
        self.assertEqual(ev[-1]["why"], "the ledger reads calm and the rate leads")
        self.assertEqual(ev[-1]["tags"], ["type:grotesk", "layout:ledger"])
        self.assertEqual(ev[-1]["values"], "Sohne 15/1.5")
        notes = self.n.all_notes("fintech")
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0]["person"])
        self.assertEqual(notes[0]["status"], "kept")
        self.assertIn("the ledger reads calm", notes[0]["text"])
        self.assertTrue(notes[0]["evidence"])

    def test_without_a_domain_only_the_taste_win(self):
        rc, out = self.run_cli("pick", "--look", "b", "--why", "warmer")
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.root / "taste.jsonl").exists())
        self.assertFalse((self.root / "notes").exists())
        ev = json.loads((self.root / "taste.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["what"], "picked look b")

    def test_unknown_domain_and_bad_tags_record_nothing(self):
        self.assertEqual(self.run_cli("pick", "--look", "b", "--why", "x", "--domain", "nope")[0], 2)
        self.assertEqual(self.run_cli("pick", "--look", "b", "--why", "x", "--tags", "nonsense")[0], 2)
        self.assertFalse((self.root / "taste.jsonl").exists())
        self.assertEqual(self.run_cli("pick", "--look", "b")[0], 2)


if __name__ == "__main__":
    unittest.main()
