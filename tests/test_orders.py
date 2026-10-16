"""st unit tests: orders."""
import json
import os
import subprocess
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestOrders(StTestCase):
    def test_ids_are_monotonic_and_unique(self):
        ids = [self.draft(title=f"t{i}") for i in range(3)]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual([i[-3:] for i in ids], ["001", "002", "003"])

    def test_parallel_drafts_never_collide(self):
        procs = [subprocess.Popen([str(ST), "draft"], cwd=self.repo, env=self.env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for _ in range(8)]
        outs = [p.communicate(json.dumps(order_spec()))[0].strip().splitlines()[-1]
                for p in procs]
        self.assertEqual(len(set(outs)), 8, outs)

    def test_rejects_malformed_orders(self):
        cases = [({"role": "administrator"}, "not a team role"),
                 ({"authority": "L3"}, "L3 is the surgeon's"),
                 ({"acceptance": []}, "acceptance"),
                 ({"budget": {}}, "budget.minutes"),
                 ({"push": True}, "push is only possible at L2"),
                 ({"depends_on": ["WO-20990101-001"]}, "no such order"),
                 ({"inputs": {"decisions": ["DEC-099"]}}, "DEC-099 is missing")]
        for over, msg in cases:
            with self.subTest(over=over):
                self.st_fails("draft", stdin=json.dumps(order_spec(**over)), contains=msg)

    def test_warns_when_no_executable_check(self):
        r = self.run_st("draft", stdin=json.dumps(order_spec(acceptance=["it works"])))
        self.assertEqual(r.returncode, 0)
        self.assertIn("no acceptance criterion has a `check`", r.stderr)

    def test_unapproved_order_does_not_dispatch(self):
        wo = self.draft()
        self.st_fails("dispatch", wo, contains="not approved")

    def test_worktree_is_outside_the_repo(self):
        wo, ws = self.dispatched()
        self.assertTrue(ws.is_dir())
        self.assertFalse(str(ws).startswith(str(self.repo) + os.sep))
        self.assertTrue(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=ws).startswith(f"st/{wo}-"))

    def test_st_finds_main_ledger_from_worktree(self):
        wo, ws = self.dispatched()
        self.assertIn(wo, self.st("list", cwd=ws))

    def test_report_must_cover_every_criterion(self):
        wo, _ = self.dispatched()
        self.st_fails("report", wo, stdin=json.dumps(
            {"status": "DONE", "summary": "x", "criteria": [{"met": True}]}),
            contains="exactly 2 entries")
        self.st_fails("report", wo, stdin=json.dumps(
            {"status": "DONE", "summary": "x", "criteria": [{"met": True}, {"met": False}]}),
            contains="use PARTIAL")
        self.st_fails("report", wo, stdin=json.dumps({"status": "BLOCKED", "summary": "x"}),
                      contains="requires a blocker")

    def test_full_lifecycle_and_verdict(self):
        wo, _ = self.dispatched()
        self.report(wo)
        self.st("accept", wo, "-m", "merged by hand")
        o = self.order(wo)
        self.assertEqual(o["state"], "accepted")
        self.assertEqual([h["to"] for h in o["history"]],
                         ["approved", "dispatched", "reported", "accepted"])
        self.assertIn("ledger signatures verified", self.st("verify"))

    def test_batch_verdicts(self):
        a, _ = self.dispatched(title="a")
        b, _ = self.dispatched(title="b")
        self.report(a)
        self.report(b)
        self.st("accept", a, b)
        self.assertEqual({self.order(a)["state"], self.order(b)["state"]}, {"accepted"})

    def test_blocked_then_revise_then_redispatch_is_attempt_2(self):
        wo, _ = self.dispatched()
        self.st("report", wo, stdin=json.dumps(
            {"status": "BLOCKED", "summary": "no spec", "blocker": "need DEC on limits"}))
        self.st("revise", wo, stdin=json.dumps(order_spec(intent="limits are 5MB")))
        self.assertEqual(self.order(wo)["state"], "drafted")
        self.st_fails("dispatch", wo, contains="not approved")
        self.st("approve", wo)
        self.st("dispatch", wo)
        self.assertEqual(self.order(wo)["attempt"], 2)
        self.report(wo)  # one report per attempt, not per order
        rep_dir = self.repo / ".surgical-team" / "reports"
        self.assertEqual(sorted(p.name for p in rep_dir.iterdir()),
                         [f"{wo}.a1.json", f"{wo}.a2.json"])

    def test_reclaim_stuck_order(self):
        wo, ws = self.dispatched()
        self.st("reclaim", wo, "--reason", "agent session died")
        self.assertEqual(self.order(wo)["state"], "approved")
        self.st("dispatch", wo)  # reuses the worktree
        self.assertEqual(self.order(wo)["attempt"], 2)

    def test_stale_dispatch_is_flagged(self):
        wo, _ = self.dispatched()
        env = {**self.env, "ST_NOW": "2099-01-01T00:00:00Z"}
        out = self.run_st("status", env=env).stdout
        self.assertIn("STALE", out)

    def test_dependencies_gate_dispatch(self):
        first, _ = self.dispatched(title="first")
        second = self.draft(title="second", depends_on=[first])
        self.st("approve", second)
        self.st_fails("dispatch", second, contains="depends on")
        self.report(first)
        self.st("accept", first)
        self.st("dispatch", second)

    def test_path_overlap_serializes(self):
        self.dispatched(title="a", paths=["src/upload"])
        b = self.draft(title="b", paths=["src/upload/retry.rs"])
        self.st("approve", b)
        self.st_fails("dispatch", b, contains="overlaps")
        self.st("dispatch", b, "--allow-overlap")

    def test_status_is_generated(self):
        wo, _ = self.dispatched()
        self.report(wo)
        status = (self.repo / ".surgical-team" / "STATUS.md").read_text()
        self.assertIn("Do not edit", status)
        self.assertIn(f"verdict: {wo}", status)
        self.assertIn("checks NOT RUN", status)


class TestStatusContradictions(StTestCase):
    """The board, not the copilot's eyes, flags a report its own checks contradict."""

    def board_line(self, wo):
        return next(line for line in self.st("status").splitlines() if wo in line)

    def test_done_with_failing_checks_is_flagged(self):
        wo, _ws = self.dispatched()
        self.report(wo)  # DONE, but ok.txt was never made
        self.run_st("check", wo)
        self.assertIn("CONTRADICTS: reported DONE, but checks fail", self.board_line(wo))

    def test_blocked_with_passing_check_and_manual_criterion_is_not_flagged(self):
        wo, ws = self.dispatched()
        (ws / "ok.txt").write_text("ok\n")
        self.report(wo, status="BLOCKED", blocker="manual criterion is unmet")
        self.st("check", wo)
        self.assertNotIn("CONTRADICTS", self.board_line(wo))

    def test_blocked_with_every_criterion_checked_and_passing_is_flagged(self):
        wo, _ws = self.dispatched(
            acceptance=[
                {"text": "first executable criterion", "check": "true"},
                {"text": "second executable criterion", "check": "true"},
            ]
        )
        self.report(wo, status="BLOCKED", blocker="could not finish")
        self.st("check", wo)
        self.assertIn(
            "CONTRADICTS: reported BLOCKED, but every check passes",
            self.board_line(wo),
        )

    def test_zero_executable_checks_are_described_without_a_ratio(self):
        wo, _ws = self.dispatched(acceptance=[{"text": "manual review"}])
        self.report(wo, status="BLOCKED", n=1, blocker="manual review is unmet")
        self.st("check", wo)
        line = self.board_line(wo)
        self.assertIn("no executable checks", line)
        self.assertNotIn("checks 0/0 pass", line)
        self.assertNotIn("CONTRADICTS", line)

    def test_agreeing_reports_are_not_flagged(self):
        wo, ws = self.dispatched()
        (ws / "ok.txt").write_text("ok\n")
        self.report(wo)
        self.st("check", wo)
        self.assertNotIn("CONTRADICTS", self.board_line(wo))


class TestDecisionsInBriefings(StTestCase):
    """Uniform design: every decision in force reaches every briefing."""

    def decide(self, title, decision):
        return self.st("decide", "--title", title, "--decision", decision).split()[-1]

    def test_every_decision_in_force_is_briefed_and_bound_ones_are_marked(self):
        errors = self.decide("Errors", "Return Result types; never raise across the API")
        naming = self.decide("Naming", "snake_case for modules")
        self.st("grant", "--role", "tester", "--max", "L1", "--budget", "30", "--scope", "tests")
        wo = self.draft(inputs={"decisions": [errors]})
        brief = self.st("brief", wo)
        section = brief.split("## Decisions in force", 1)[1]
        self.assertIn(f"- {errors} [binding for this order] Errors:", section)
        self.assertIn(f"- {naming} Naming: snake_case for modules", section)
        self.assertNotIn("standing", section.split("##")[0].lower())

        self.st("revoke", naming, "-m", "dropped")
        self.st("revoke", errors, "-m", "dropped")
        section = self.st("brief", wo).split("## Decisions in force", 1)[1].split("##")[0]
        self.assertNotIn(naming, section)
        self.assertIn(f"- {errors} [revoked] [binding for this order]", section)

    def test_unverified_binding_withholds_content_and_blocks_dispatch(self):
        decision = self.st(
            "decide", "--title", "Signed title", "--decision", "Signed constraint",
            "--dissent", "signed objection",
        ).split()[-1]
        wo = self.draft(inputs={"decisions": [decision]})
        self.st("approve", wo)

        path = self.repo / ".surgical-team" / "decisions" / f"{decision}.json"
        record = json.loads(path.read_text())
        record["signed"]["payload"].update(
            {
                "title": "FORGED TITLE",
                "decision": "FORGED INSTRUCTION",
                "dissent": ["FORGED DISSENT"],
            }
        )
        path.write_text(json.dumps(record))

        brief = self.st("brief", wo)
        self.assertNotIn("## Decisions in force", brief)
        self.assertIn("## Decisions that do not verify", brief)
        self.assertIn(f"- {decision} [unverified]", brief)
        self.assertIn(
            "signature does not verify: content withheld; do not rely on it and report it",
            brief,
        )
        self.assertNotIn("FORGED TITLE", brief)
        self.assertNotIn("FORGED INSTRUCTION", brief)
        self.assertNotIn("FORGED DISSENT", brief)
        self.st_fails("dispatch", wo, contains=f"binding decision {decision} is unverified")
        self.assertFalse((self.repo.parent / "proj.st" / wo).exists())
        self.assertEqual(self.order(wo)["state"], "approved")
        self.assertEqual(self.order(wo)["attempt"], 0)

    def test_missing_binding_is_withheld_and_blocks_dispatch(self):
        decision = self.decide("Present", "Use the signed rule")
        wo = self.draft(inputs={"decisions": [decision]})
        self.st("approve", wo)
        (self.repo / ".surgical-team" / "decisions" / f"{decision}.json").unlink()

        brief = self.st("brief", wo)
        self.assertNotIn("## Decisions in force", brief)
        self.assertIn(f"- {decision} [missing]", brief)
        self.assertIn("content withheld; do not rely on it and report it", brief)
        self.st_fails("dispatch", wo, contains=f"binding decision {decision} is missing")

    def test_valid_binding_still_dispatches_with_signed_content(self):
        decision = self.st(
            "decide", "--title", "Errors", "--decision", "Return Result values",
            "--dissent", "exceptions are shorter",
        ).split()[-1]
        wo = self.draft(inputs={"decisions": [decision]})
        self.st("approve", wo)

        brief = self.st("dispatch", wo)
        self.assertIn("## Decisions in force", brief)
        self.assertNotIn("## Decisions that do not verify", brief)
        self.assertIn(
            f"- {decision} [binding for this order] Errors: Return Result values", brief
        )
        self.assertIn("  - Overruled objection: exceptions are shorter", brief)

    def test_an_overruled_objection_is_signed_into_the_decision(self):
        dec = self.st("decide", "--title", "Sync IO", "--decision", "Keep the client synchronous",
                      "--dissent", "copilot: async would halve tail latency",
                      "--dissent", "tester: retries will block the UI thread").split()[-1]
        record = json.loads((self.repo / ".surgical-team" / "decisions" / f"{dec}.json")
                            .read_text())
        self.assertEqual(record["signed"]["payload"]["dissent"],
                         ["copilot: async would halve tail latency",
                          "tester: retries will block the UI thread"])
        self.st("verify")  # the objection is under the surgeon's signature
        self.assertIn("decided over 2 objection(s)", self.st("status"))
        brief = self.st("brief", self.draft())
        self.assertIn("  - Overruled objection: copilot: async would halve tail latency", brief)
        plain = self.st("decide", "--title", "Plain", "--decision", "x").split()[-1]
        record = json.loads((self.repo / ".surgical-team" / "decisions" / f"{plain}.json")
                            .read_text())
        self.assertEqual(record["signed"]["payload"]["dissent"], [])

    def test_no_decisions_no_section(self):
        self.assertNotIn("## Decisions in force", self.st("brief", self.draft()))


if __name__ == "__main__":
    unittest.main()
