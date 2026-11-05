import contextlib
import copy
import io
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import review  # noqa: E402

RUN = "20261105T120000Z-ab12"
AREAS = ["idea", "hierarchy", "copy", "craft", "brand", "fit", "truth", "distinctiveness", "load"]


def scores(n=4, **over):
    s = {a: [n, f"{a} evidence"] for a in AREAS}
    for k, v in over.items():
        s[k] = [v, f"{k} evidence"]
    return s


class Rule(unittest.TestCase):
    def test_ship_when_all_four_and_no_must_fix(self):
        self.assertEqual(review.verdict_for(scores(4), []), "ship")
        self.assertEqual(review.verdict_for(scores(5), [{"severity": "nice-to-have"}]), "ship")

    def test_rework_when_idea_two_or_less(self):
        self.assertEqual(review.verdict_for(scores(5, idea=2), []), "rework")

    def test_rework_when_any_score_is_one(self):
        self.assertEqual(review.verdict_for(scores(5, load=1), []), "rework")

    def test_fix_then_ship_when_a_three(self):
        self.assertEqual(review.verdict_for(scores(4, craft=3), []), "fix-then-ship")

    def test_fix_then_ship_when_must_fix(self):
        self.assertEqual(review.verdict_for(scores(5), [{"severity": "must-fix"}]), "fix-then-ship")

    def test_idea_three_with_others_high_is_fix_then_ship(self):
        self.assertEqual(review.verdict_for(scores(5, idea=3), []), "fix-then-ship")


class Record(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = pathlib.Path(self.tmp.name)
        shots = self.proj / ".design" / "gate" / RUN / "shots"
        shots.mkdir(parents=True)
        self.phone = f".design/gate/{RUN}/shots/site__phone-390x844__motion__fold.png"
        self.mac = f".design/gate/{RUN}/shots/site__mac-1512x820__motion__fold.png"
        for p in (self.phone, self.mac):
            (self.proj / p).write_bytes(b"png")
        receipt = {"version": 1, "run_id": RUN, "verdict": "pass"}
        (self.proj / ".design" / "gate" / "receipt.json").write_text(json.dumps(receipt))
        (self.proj / ".design" / "gate" / RUN / "receipt.json").write_text(json.dumps(receipt))
        self.good = {"run_id": RUN, "reviewer": "independent", "scores": scores(4),
                     "notes": [{"where": "phone fold, hero", "what": "CTA wraps", "why": "reads broken",
                                "fix": "shorten to two words", "severity": "nice-to-have"}],
                     "strengths": ["the masthead scale"], "viewed": [self.phone, self.mac],
                     "compared_with": [], "verdict": "ship"}

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, rec, run=RUN):
        return [f["message"] for f in review.validate(rec, self.proj, run) if f["severity"] == "error"]

    def record(self, rec, run="latest"):
        f = self.proj / "rec.json"
        f.write_text(json.dumps(rec))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = review.main(["record", "--project", str(self.proj), "--run", run, "--json", str(f)])
        return rc, out.getvalue()

    def test_good_record_validates_and_stores(self):
        self.assertEqual(self.errors(self.good), [])
        rc, out = self.record(self.good)
        self.assertEqual(rc, 0, out)
        stored = json.loads((self.proj / ".design" / "review" / f"{RUN}.json").read_text())
        self.assertEqual(stored["verdict"], "ship")
        self.assertEqual(stored["run_id"], RUN)

    def test_missing_area(self):
        rec = copy.deepcopy(self.good)
        del rec["scores"]["truth"]
        self.assertTrue(any("truth" in e for e in self.errors(rec)))

    def test_score_out_of_range(self):
        for bad in (0, 6, 3.5, "4", True):
            rec = copy.deepcopy(self.good)
            rec["scores"]["craft"] = [bad, "evidence"]
            self.assertTrue(any("craft" in e for e in self.errors(rec)), bad)

    def test_score_needs_evidence(self):
        rec = copy.deepcopy(self.good)
        rec["scores"]["copy"] = [4, "  "]
        self.assertTrue(any("copy" in e for e in self.errors(rec)))
        rec["scores"]["copy"] = [4]
        self.assertTrue(any("copy" in e for e in self.errors(rec)))

    def test_too_many_notes(self):
        rec = copy.deepcopy(self.good)
        rec["notes"] = [dict(self.good["notes"][0]) for _ in range(13)]
        self.assertTrue(any("12" in e for e in self.errors(rec)))

    def test_note_needs_where_what_why_fix_and_severity(self):
        for field in ("where", "what", "why", "fix"):
            rec = copy.deepcopy(self.good)
            rec["notes"][0][field] = ""
            self.assertTrue(any(field in e for e in self.errors(rec)), field)
        rec = copy.deepcopy(self.good)
        rec["notes"][0]["severity"] = "urgent"
        self.assertTrue(any("severity" in e for e in self.errors(rec)))

    def test_viewed_path_must_exist(self):
        rec = copy.deepcopy(self.good)
        rec["viewed"].append(f".design/gate/{RUN}/shots/ghost__phone-390x844__motion__fold.png")
        self.assertTrue(any("ghost" in e for e in self.errors(rec)))

    def test_needs_a_phone_fold_from_this_run(self):
        rec = copy.deepcopy(self.good)
        rec["viewed"] = [self.mac]
        self.assertTrue(any("phone" in e for e in self.errors(rec)))

    def test_needs_a_desktop_or_mac_fold_from_this_run(self):
        rec = copy.deepcopy(self.good)
        rec["viewed"] = [self.phone]
        self.assertTrue(any("desktop" in e for e in self.errors(rec)))

    def test_folds_from_another_run_do_not_count(self):
        other = ".design/gate/20261101T000000Z-0000/shots/site__phone-390x844__motion__fold.png"
        (self.proj / other).parent.mkdir(parents=True)
        (self.proj / other).write_bytes(b"png")
        rec = copy.deepcopy(self.good)
        rec["viewed"] = [other, self.mac]
        self.assertTrue(any("phone" in e for e in self.errors(rec)))

    def test_landscape_phone_is_not_the_phone_fold(self):
        land = f".design/gate/{RUN}/shots/site__phone-landscape-844x390__motion__fold.png"
        (self.proj / land).write_bytes(b"png")
        rec = copy.deepcopy(self.good)
        rec["viewed"] = [land, self.mac]
        self.assertTrue(any("phone" in e for e in self.errors(rec)))

    def test_old_viewport_names_count(self):
        ph = f".design/gate/{RUN}/shots/site__phone__motion__fold.png"
        dk = f".design/gate/{RUN}/shots/site__desktop__reduced__fold.png"
        for p in (ph, dk):
            (self.proj / p).write_bytes(b"png")
        rec = copy.deepcopy(self.good)
        rec["viewed"] = [ph, dk]
        self.assertEqual(self.errors(rec), [])

    def test_mismatched_verdict_is_an_error(self):
        rec = copy.deepcopy(self.good)
        rec["scores"]["craft"] = [3, "default spacing"]
        self.assertTrue(any("fix-then-ship" in e for e in self.errors(rec)))
        rc, out = self.record(rec)
        self.assertEqual(rc, 1)
        self.assertFalse((self.proj / ".design" / "review" / f"{RUN}.json").exists())

    def test_reviewer_must_be_self_or_independent(self):
        rec = copy.deepcopy(self.good)
        rec["reviewer"] = "me"
        self.assertTrue(any("reviewer" in e for e in self.errors(rec)))

    def test_run_id_mismatch(self):
        rec = copy.deepcopy(self.good)
        rec["run_id"] = "20261101T000000Z-0000"
        self.assertTrue(any("run_id" in e for e in self.errors(rec)))

    def test_unknown_run_is_exit_2(self):
        rc, out = self.record(self.good, run="20990101T000000Z-ffff")
        self.assertEqual(rc, 2)

    def test_latest_without_receipt_is_exit_2(self):
        (self.proj / ".design" / "gate" / "receipt.json").unlink()
        rc, out = self.record(self.good)
        self.assertEqual(rc, 2)

    def test_bad_json_file_is_exit_2(self):
        f = self.proj / "rec.json"
        f.write_text("{not json")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = review.main(["record", "--project", str(self.proj), "--run", RUN, "--json", str(f)])
        self.assertEqual(rc, 2)

    def test_show(self):
        self.record(self.good)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = review.main(["show", "--project", str(self.proj)])
        self.assertEqual(rc, 0)
        self.assertIn("ship", out.getvalue())
        self.assertIn("distinctiveness", out.getvalue())


if __name__ == "__main__":
    unittest.main()
