import sys, unittest, pathlib, tempfile, io, contextlib, json
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import contract


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = contract.main(["--project", str(self.p)] + list(argv))
        return rc, out.getvalue()

    def file(self):
        return self.p / ".design" / "brief" / "contract.json"

    def data(self):
        return json.loads(self.file().read_text())

    def rules(self, res):
        return sorted({f["rule"] for f in res["findings"]})


class Init(Base):
    def test_init_new(self):
        rc, out = self.cli("init", "--brief", "Rates page")
        self.assertEqual(rc, 0, out)
        d = self.data()
        self.assertEqual((d["version"], d["job"], d["brief"], d["requirements"]), (1, "new", "Rates page", []))
        self.assertRegex(d["created"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(self.cli("init")[0], 2)          # never overwrites

    def test_edit_list_adds_the_scope_requirement(self):
        self.cli("init", "--job", "edit-list", "--brief", "Masthead fixes")
        r = self.data()["requirements"]
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["id"], r[0]["kind"], r[0]["status"]), ("R1", "scope", "open"))
        self.assertIn("Only the listed changes", r[0]["text"])
        self.assertTrue(r[0]["source"])

    def test_bad_job(self):
        self.assertNotEqual(self.cli("init", "--job", "rebrand")[0], 0)


class AddSet(Base):
    def test_ids_are_allocated_in_order(self):
        self.cli("init", "--job", "edit-list")
        self.cli("add", "--kind", "change", "--text", "Make SC the same size as PFOR", "--source", "Fergus 2026-11-04")
        self.cli("add", "--kind", "copy", "--text", "Masthead line", "--source", "Fergus", "--exact", "Decisions in 24 hours")
        self.assertEqual([r["id"] for r in self.data()["requirements"]], ["R1", "R2", "R3"])
        self.assertEqual(self.data()["requirements"][2]["exact"], "Decisions in 24 hours")

    def test_add_validates(self):
        self.cli("init")
        self.assertEqual(self.cli("add", "--kind", "copy", "--text", "x", "--source", "s")[0], 2)   # copy needs exact
        self.assertEqual(self.cli("add", "--kind", "vibe", "--text", "x", "--source", "s")[0], 2)
        self.assertEqual(self.cli("add", "--kind", "change", "--text", "", "--source", "s")[0], 2)

    def test_set_status_evidence_and_supersede(self):
        self.cli("init")
        self.cli("add", "--kind", "change", "--text", "A", "--source", "s")
        self.cli("add", "--kind", "change", "--text", "B", "--source", "s")
        self.assertEqual(self.cli("set", "R1", "--status", "superseded", "--superseded-by", "R2",
                                  "--evidence", "Fergus replaced it with R2 on 2026-11-05")[0], 0)
        self.assertEqual(self.data()["requirements"][0]["superseded_by"], "R2")
        self.assertEqual(self.cli("set", "R9", "--status", "satisfied")[0], 2)
        self.assertEqual(self.cli("set", "R2", "--status", "done")[0], 2)
        self.assertEqual(self.cli("set", "R2", "--status", "waived", "--by", "Fergus",
                                  "--evidence", "said the old size is fine")[0], 0)
        self.assertIn("waived by Fergus", self.data()["requirements"][1]["evidence"])

    def test_list_and_copy(self):
        self.cli("init")
        self.cli("add", "--kind", "copy", "--text", "Hero", "--source", "s", "--exact", "Decisions in 24 hours")
        self.cli("add", "--kind", "copy", "--text", "Old", "--source", "s", "--exact", "Old line")
        self.cli("set", "R2", "--status", "superseded", "--superseded-by", "R1", "--evidence", "replaced by R1 in round 2")
        rc, out = self.cli("list")
        self.assertIn("R1", out)
        rc, out = self.cli("copy")
        self.assertEqual(out.strip().splitlines(), ["Decisions in 24 hours"])
        self.assertEqual(contract.exact_copy(self.p), ["Decisions in 24 hours"])


class Check(Base):
    def write(self, reqs, job="new", **extra):
        self.file().parent.mkdir(parents=True, exist_ok=True)
        d = {"version": 1, "job": job, "brief": "b", "created": "2026-11-05", "requirements": reqs}
        d.update(extra)
        self.file().write_text(json.dumps(d))

    def req(self, id_="R1", **kw):
        r = {"id": id_, "kind": "change", "text": "Make it so", "source": "Fergus 2026-11-04",
             "status": "open", "evidence": "", "superseded_by": None, "exact": None}
        r.update(kw)
        return r

    def test_missing_file_could_not_run(self):
        res = contract.check(self.p, "plan")
        self.assertEqual(res["exit"], 2)
        self.assertEqual(res["findings"][0]["rule"], "tool.could-not-run")
        self.assertIsNone(contract.load(self.p))

    def test_unreadable_json_could_not_run(self):
        self.file().parent.mkdir(parents=True)
        self.file().write_text("{nope")
        self.assertEqual(contract.check(self.p, "plan")["exit"], 2)

    def test_bad_phase(self):
        self.write([self.req()])
        self.assertEqual(contract.check(self.p, "draft")["exit"], 2)

    def test_plan_passes_with_open_sourced_requirements(self):
        self.write([self.req()])
        res = contract.check(self.p, "plan")
        self.assertEqual(res["exit"], 0, res)
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "contract")

    def test_plan_needs_requirements_and_sources(self):
        self.write([])
        self.assertIn("contract.empty", self.rules(contract.check(self.p, "plan")))
        self.write([self.req(source="")])
        self.assertIn("contract.no-source", self.rules(contract.check(self.p, "plan")))

    def test_schema_errors(self):
        self.write([self.req(kind="vibe"), self.req("R1"), self.req("X3", status="maybe"),
                    self.req("R4", kind="copy", exact=None), self.req("R5", text="")], job="rebrand", version=2)
        rules = self.rules(contract.check(self.p, "plan"))
        for r in ("contract.version", "contract.job", "contract.kind", "contract.duplicate-id", "contract.id",
                  "contract.status", "contract.copy-exact", "contract.no-text"):
            self.assertIn(r, rules)

    def test_edit_list_needs_its_scope(self):
        self.write([self.req()], job="edit-list")
        self.assertIn("contract.scope-missing", self.rules(contract.check(self.p, "plan")))

    def test_final_fails_on_open(self):
        self.write([self.req()])
        res = contract.check(self.p, "final")
        self.assertEqual(res["exit"], 1)
        self.assertIn("contract.open", self.rules(res))

    def test_final_needs_real_evidence(self):
        self.write([self.req(status="satisfied", evidence="done")])
        self.assertIn("contract.thin-evidence", self.rules(contract.check(self.p, "final")))
        self.write([self.req(status="satisfied", evidence="desktop fold shot shows SC at 48px, PFOR at 48px")])
        self.assertEqual(contract.check(self.p, "final")["exit"], 0)

    def test_final_supersession_must_point_at_a_real_id(self):
        ev = "replaced in round two by the new line"
        self.write([self.req(status="superseded", superseded_by="R7", evidence=ev)])
        self.assertIn("contract.superseded-dangling", self.rules(contract.check(self.p, "final")))
        self.write([self.req(status="superseded", superseded_by=None, evidence=ev)])
        self.assertIn("contract.superseded-dangling", self.rules(contract.check(self.p, "final")))
        self.write([self.req(status="superseded", superseded_by="R1", evidence=ev)])
        self.assertIn("contract.superseded-dangling", self.rules(contract.check(self.p, "final")))
        self.write([self.req(status="superseded", superseded_by="R2", evidence=ev),
                    self.req("R2", status="satisfied", evidence="phone fold shot shows the new line")])
        self.assertEqual(contract.check(self.p, "final")["exit"], 0)

    def test_final_waiver_names_who(self):
        self.write([self.req(status="waived", evidence="not needed after all, apparently")])
        self.assertIn("contract.waiver-unnamed", self.rules(contract.check(self.p, "final")))
        self.write([self.req(status="waived", evidence="waived by Fergus on 2026-11-05: keep the old size")])
        self.assertEqual(contract.check(self.p, "final")["exit"], 0)

    def test_cli_check_json(self):
        self.write([self.req()])
        rc, out = self.cli("check", "--phase", "final", "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["exit"], 1)
        rc, _ = self.cli("check", "--phase", "plan")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
