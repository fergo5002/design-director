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


class Project(unittest.TestCase):
    """A gate run with a phone fold and a mac fold, and helpers to validate and record."""

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


class Record(Project):

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



def critic(**over):
    r = {"reviewer": "independent", "critic": "a fresh agent",
         "cold_read": {"what_it_is": "a booking page for a sauna", "who_for": "people nearby",
                       "next_action": "book a slot", "first_noticed": "the photo", "confusing": []},
         "cold_read_matches": True,
         "ask": [{"item": "make the button say Book", "met": "yes", "evidence": "phone fold, hero"}],
         "defects": [{"where": "phone fold, footer", "what": "links crowd", "fix": "stack them",
                      "severity": "nice-to-have"}]}
    r.update(over)
    return r


class CriticRule(unittest.TestCase):
    def test_ship_when_cold_read_matches_every_ask_met_and_no_open_must_fix(self):
        self.assertEqual(review.critic_verdict(critic()), "ship")

    def test_rework_when_the_cold_read_misses(self):
        self.assertEqual(review.critic_verdict(critic(cold_read_matches=False)), "rework")

    def test_an_unmet_ask_is_a_fix_not_a_rework(self):
        # In 18 critic passes on real work the cold read always matched; all 14 reworks came from an
        # ask marked no, and the owner approved four of the five pages as they stood. A miss on purpose is
        # the cold read's job; an unmet ask is a fix.
        r = critic(ask=[{"item": "x", "met": "no", "evidence": "phone fold"}])
        self.assertEqual(review.critic_verdict(r), "fix-then-ship")

    def test_an_unmet_ask_closed_on_evidence_ships(self):
        r = critic(ask=[{"item": "x", "met": "no", "evidence": "phone fold", "resolved": "r2: phone fold"}])
        self.assertEqual(review.critic_verdict(r), "ship")

    def test_an_ask_only_the_deploy_can_meet_does_not_hold_the_ship(self):
        r = critic(ask=[{"item": "post it to example.com/v10", "met": "after-ship", "evidence": "404 before deploy"}])
        self.assertEqual(review.critic_verdict(r), "ship")

    def test_cannot_tell_is_not_a_no(self):
        r = critic(ask=[{"item": "x", "met": "cannot-tell", "evidence": "not in any shot"}])
        self.assertEqual(review.critic_verdict(r), "ship")

    def test_open_must_fix_is_fix_then_ship_and_a_resolved_one_is_not(self):
        d = {"where": "a", "what": "b", "fix": "c", "severity": "must-fix"}
        self.assertEqual(review.critic_verdict(critic(defects=[d])), "fix-then-ship")
        self.assertEqual(review.critic_verdict(critic(defects=[dict(d, resolved="gate run r2, phone fold")])), "ship")


class CriticRecord(Project):
    """The default review: one critic, a cold read first, the ask checked in the owner's words, no scores."""

    def setUp(self):
        super().setUp()
        self.good = dict(critic(), viewed=[self.phone, self.mac])

    def test_good_critic_record_stores_with_computed_verdict(self):
        rec = dict(self.good)
        rec.pop("verdict", None)
        rc, out = self.record(rec)
        self.assertEqual(rc, 0, out)
        stored = json.loads((self.proj / ".design" / "review" / f"{RUN}.json").read_text())
        self.assertEqual(stored["verdict"], "ship")
        self.assertEqual(stored["kind"], "critic")

    def test_no_scores_are_asked_for(self):
        self.assertFalse(any("score" in e for e in self.errors(self.good)))

    def test_empty_cold_read_is_refused(self):
        rec = copy.deepcopy(self.good)
        rec["cold_read"]["what_it_is"] = " "
        self.assertTrue(any("cold_read.what_it_is" in e for e in self.errors(rec)))

    def test_every_ask_needs_met_and_evidence(self):
        rec = copy.deepcopy(self.good)
        rec["ask"] = [{"item": "x", "met": "mostly", "evidence": ""}]
        errs = self.errors(rec)
        self.assertTrue(any("met" in e for e in errs))
        self.assertTrue(any("evidence" in e for e in errs))
        rec["ask"] = []
        self.assertTrue(any("ask" in e for e in self.errors(rec)))

    def test_at_most_ten_defects(self):
        rec = copy.deepcopy(self.good)
        rec["defects"] = [{"where": "a", "what": "b", "fix": "c", "severity": "nice"}] * 11
        self.assertTrue(any("ten" in e for e in self.errors(rec)))

    def test_after_ship_is_a_valid_answer_for_an_ask(self):
        rec = copy.deepcopy(self.good)
        rec["ask"].append({"item": "post it to example.com/v10", "met": "after-ship", "evidence": "404 before deploy"})
        self.assertEqual(self.errors(rec), [])

    def test_a_fresh_read_cannot_arrive_already_resolved(self):
        rec = copy.deepcopy(self.good)
        rec["ask"] = [{"item": "x", "met": "no", "evidence": "e", "resolved": "trust me"}]
        rec["defects"] = [{"where": "a", "what": "b", "fix": "c", "severity": "must-fix", "resolved": "trust me"}]
        errs = self.errors(rec)
        self.assertTrue(any("ask 1" in e and "resolved" in e for e in errs), errs)
        self.assertTrue(any("defect 1" in e and "resolved" in e for e in errs), errs)
        rc, out = self.record(rec)
        self.assertEqual(rc, 1)
        rec = dict(copy.deepcopy(self.good), resolved_from=RUN)
        self.assertTrue(any("resolved_from" in e for e in self.errors(rec)))

    def test_nice_is_accepted_for_nice_to_have(self):
        rec = copy.deepcopy(self.good)
        rec["defects"] = [{"where": "a", "what": "b", "fix": "c", "severity": "nice"}]
        self.assertEqual(self.errors(rec), [])

    def test_a_claimed_verdict_that_disagrees_is_refused(self):
        rec = dict(self.good, cold_read_matches=False, verdict="ship")
        self.assertTrue(any("rework" in e for e in self.errors(rec)))

    def test_still_needs_a_phone_and_a_desktop_fold(self):
        rec = dict(self.good, viewed=[self.mac])
        self.assertTrue(any("phone" in e for e in self.errors(rec)))

    def test_show_prints_the_cold_read_and_defects(self):
        self.record(self.good)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = review.main(["show", "--project", str(self.proj)])
        self.assertEqual(rc, 0)
        self.assertIn("a booking page for a sauna", out.getvalue())
        self.assertIn("links crowd", out.getvalue())



class Resolve(unittest.TestCase):
    """Must-fixes close on evidence: a fixed defect carries to the next gate run without a second critic."""

    R2 = "20261105T130000Z-cd34"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = pathlib.Path(self.tmp.name)
        gate = self.proj / ".design" / "gate"
        for run in (RUN, self.R2):
            (gate / run / "shots").mkdir(parents=True)
            (gate / run / "receipt.json").write_text(json.dumps({"run_id": run, "verdict": "pass"}))
        (gate / "receipt.json").write_text(json.dumps({"run_id": self.R2, "verdict": "pass"}))
        self.first = dict(critic(defects=[
            {"where": "phone fold, hero", "what": "headline clipped", "fix": "drop a size", "severity": "must-fix"},
            {"where": "mac fold", "what": "footer crowded", "fix": "stack", "severity": "nice-to-have"}]),
            run_id=RUN, kind="critic", verdict="fix-then-ship")
        (self.proj / ".design" / "review").mkdir(parents=True)
        self.write(self.first)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rec, run=RUN):
        (self.proj / ".design" / "review" / f"{run}.json").write_text(json.dumps(rec))

    def resolve(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = review.main(["resolve", "--project", str(self.proj), *args])
        return rc, out.getvalue()

    def stored(self, run):
        p = self.proj / ".design" / "review" / f"{run}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def test_evidence_for_every_must_fix_ships_the_new_run(self):
        rc, out = self.resolve("--from", RUN, "--evidence", "1=phone fold of the new run: headline on two lines")
        self.assertEqual(rc, 0, out)
        rec = self.stored(self.R2)
        self.assertEqual(rec["verdict"], "ship")
        self.assertEqual(rec["resolved_from"], RUN)
        self.assertIn("two lines", rec["defects"][0]["resolved"])
        self.assertNotIn("resolved", rec["defects"][1])

    def test_a_must_fix_without_evidence_is_refused(self):
        self.first["defects"].append({"where": "x", "what": "y", "fix": "z", "severity": "must-fix"})
        self.write(self.first)
        rc, out = self.resolve("--from", RUN, "--evidence", "1=done")
        self.assertEqual(rc, 1)
        self.assertIn("must-fix 3 has no evidence", out)
        self.assertIsNone(self.stored(self.R2))

    def test_rework_needs_a_fresh_look_not_evidence(self):  # a rework is now only a cold read that missed
        self.write(dict(self.first, cold_read_matches=False, verdict="rework"))
        rc, out = self.resolve("--from", RUN, "--evidence", "1=done")
        self.assertEqual(rc, 1)
        self.assertIn("rework", out)
        self.assertIsNone(self.stored(self.R2))

    def test_a_scored_review_cannot_be_carried(self):
        self.write({"run_id": RUN, "scores": scores(3), "verdict": "fix-then-ship"})
        rc, out = self.resolve("--from", RUN, "--evidence", "1=done")
        self.assertEqual(rc, 1)

    def test_evidence_must_name_a_must_fix(self):
        rc, out = self.resolve("--from", RUN, "--evidence", "1=fixed", "--evidence", "2=also")
        self.assertEqual(rc, 1)
        self.assertIn("must-fix", out)

    def test_an_unmet_ask_closes_on_evidence_too(self):
        self.write(dict(self.first, ask=[{"item": "make it fast", "met": "no", "evidence": "no speed claim"}]))
        rc, out = self.resolve("--from", RUN, "--evidence", "1=new hero", "--evidence", "a1=hero line now says 24 hours")
        self.assertEqual(rc, 0, out)
        rec = self.stored(self.R2)
        self.assertEqual(rec["verdict"], "ship")
        self.assertIn("24 hours", rec["ask"][0]["resolved"])

    def test_an_unmet_ask_without_evidence_is_refused(self):
        self.write(dict(self.first, ask=[{"item": "make it fast", "met": "no", "evidence": "no speed claim"}]))
        rc, out = self.resolve("--from", RUN, "--evidence", "1=new hero")
        self.assertEqual(rc, 1)
        self.assertIn("a1", out)

    def test_a_read_with_nothing_open_cannot_be_carried(self):
        self.write(dict(self.first, defects=[], verdict="ship"))
        rc, out = self.resolve("--from", RUN)
        self.assertEqual(rc, 1)
        self.assertIn("fresh critic", out)
        self.assertIsNone(self.stored(self.R2))

    def test_the_target_run_must_be_later(self):
        early = "20261105T110000Z-ee00"
        gate = self.proj / ".design" / "gate"
        (gate / early / "shots").mkdir(parents=True)
        (gate / early / "receipt.json").write_text(json.dumps({"run_id": early, "verdict": "pass"}))
        rc, out = self.resolve("--from", RUN, "--to", early, "--evidence", "1=fixed")
        self.assertEqual(rc, 1)
        self.assertIn("later", out)

    def test_the_target_run_must_have_passed_the_gate(self):
        (self.proj / ".design" / "gate" / self.R2 / "receipt.json").write_text(
            json.dumps({"run_id": self.R2, "verdict": "findings"}))
        rc, out = self.resolve("--from", RUN, "--evidence", "1=fixed")
        self.assertEqual(rc, 1)
        self.assertIn("findings", out)
        self.assertIsNone(self.stored(self.R2))

    def test_the_same_item_twice_is_refused(self):
        rc, out = self.resolve("--from", RUN, "--evidence", "1=a", "--evidence", "1=b")
        self.assertEqual(rc, 1)
        self.assertIn("twice", out)

    def gate(self, run, verdict="pass"):
        d = self.proj / ".design" / "gate" / run
        (d / "shots").mkdir(parents=True, exist_ok=True)
        (d / "receipt.json").write_text(json.dumps({"run_id": run, "verdict": verdict}))

    def test_a_later_fresh_read_is_never_overwritten(self):
        r3 = "20261105T140000Z-ef56"
        self.gate(r3)
        self.write(dict(critic(cold_read_matches=False), run_id=r3, kind="critic", verdict="rework"), run=r3)
        rc, out = self.resolve("--from", RUN, "--to", r3, "--evidence", "1=fixed")
        self.assertEqual(rc, 1)
        self.assertIn("has its own review", out)
        self.assertEqual(self.stored(r3)["verdict"], "rework")

    def test_one_read_carries_once(self):
        rc, out = self.resolve("--from", RUN, "--to", self.R2, "--evidence", "1=fixed")
        self.assertEqual(rc, 0, out)
        r3 = "20261105T140000Z-ef56"
        self.gate(r3)
        rc, out = self.resolve("--from", RUN, "--to", r3, "--evidence", "1=fixed")
        self.assertEqual(rc, 1)
        self.assertIsNone(self.stored(r3))
        rc, out = self.resolve("--from", self.R2, "--to", r3)       # the carried read has nothing open
        self.assertEqual(rc, 1)
        self.assertIsNone(self.stored(r3))

    def test_carrying_onto_the_same_run_is_refused(self):
        rc, out = self.resolve("--from", RUN, "--to", RUN, "--evidence", "1=fixed")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
