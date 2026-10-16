"""st unit tests: leases."""
import json
import os
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestLeases(StTestCase):
    """v0.3: live authority comes from a lease store outside the repository."""

    def at(self, when):
        return {**self.env, "ST_NOW": when}

    def guard_env(self, env, role, tool, inp, cwd):
        ev = {"hook_event_name": "preToolUse", "cwd": str(cwd), "tool_name": tool,
              "tool_input": inp}
        return run_st(["guard", "--role", role], cwd=self.repo, env=env,
                      stdin=json.dumps(ev)).returncode

    def leases(self):
        return list((self.cfg / "leases").glob("*.jsonl"))

    def test_rollback_plus_deleted_report_grants_nothing(self):
        """The v0.2 residual: roll state back AND delete the report and verdict."""
        wo, ws = self.dispatched()
        self.report(wo)
        led = self.repo / ".surgical-team"
        o = self.order(wo)
        o["state"] = "dispatched"
        o["history"] = o["history"][:2]
        self.write_order(wo, o)
        for p in led.glob(f"reports/{wo}.*"):
            p.unlink()
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)
        self.st_fails("report", wo, stdin=json.dumps({"status": "BLOCKED", "summary": "x",
                                                      "blocker": "y"}), contains="no live dispatch")
        # Re-dispatching the same signed approval is refused: it was consumed.
        o["state"] = "approved"
        self.write_order(wo, o)
        self.st_fails("dispatch", wo, contains="already backed a reported attempt")

    def test_ledger_without_local_lease_is_inert(self):
        """A ledger pulled from another clone, or with its state forged, grants nothing."""
        wo, ws = self.dispatched()
        for p in self.leases():
            p.unlink()
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)
        self.assertIn("NO LIVE LEASE HERE", self.st("status"))

    def test_planted_order_under_standing_order_grants_nothing(self):
        dec = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "t")
        wo = "WO-20260101-001"
        fake = {"id": wo, "spec": order_spec(standing=dec), "state": "dispatched",
                "attempt": 1, "revision": 1, "history": [],
                "dispatch": {"at": "2026-01-01T00:00:00Z", "attempt": 1}}
        self.write_order(wo, fake)
        ws = self.repo.parent / "proj.st" / wo
        self.assertBlocked("tester", "write", {"path": str(ws / "x")})

    def test_spec_swapped_after_standing_dispatch_grants_nothing(self):
        dec = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "t")
        wo = self.draft(standing=dec)
        self.st("dispatch", wo)
        ws = self.repo.parent / "proj.st" / wo
        self.assertAllowed("tester", "write", {"path": str(ws / "x")}, cwd=ws)
        o = self.order(wo)
        o["spec"]["paths"] = ["anything"]
        self.write_order(wo, o)
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)

    def test_role_swapped_in_ledger_grants_nothing(self):
        wo, ws = self.dispatched()
        o = self.order(wo)
        o["spec"]["role"] = "editor"
        self.write_order(wo, o)
        self.assertBlocked("editor", "write", {"path": str(ws / "x")}, cwd=ws)

    def test_approval_expires(self):
        wo = self.draft()  # budget 30m -> default validity 90m
        self.assertEqual(self.run_st("approve", wo, env=self.at("2026-10-08T10:00:00Z")).returncode, 0)
        r = self.run_st("dispatch", wo, env=self.at("2026-10-08T10:30:00Z"))
        self.assertEqual(r.returncode, 0, r.stderr)
        ws = self.repo.parent / "proj.st" / wo
        inp = {"path": str(ws / "x")}
        self.assertEqual(self.guard_env(self.at("2026-10-08T11:00:00Z"), "tester", "write", inp, ws), 0)
        self.assertEqual(self.guard_env(self.at("2026-10-08T11:31:00Z"), "tester", "write", inp, ws), 2)
        # an approval that has expired cannot be dispatched either
        late = self.draft(title="late")
        self.assertEqual(self.run_st("approve", late, "--for", "10", env=self.at("2026-10-08T10:00:00Z")).returncode, 0)
        r = self.run_st("dispatch", late, env=self.at("2026-10-08T10:11:00Z"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expired", r.stderr)

    def test_pre_03_approval_without_expiry_is_not_honored(self):
        wo = self.draft()
        o = self.order(wo)
        # A real signature over a payload with no expiry, as v0.2 produced.
        from surgical_team import model, signing
        os.environ["ST_CONFIG_DIR"] = str(self.cfg)
        try:
            o["approval"] = signing.sign({"kind": "approve", "order": wo,
                                          "spec_sha": model.sha(o["spec"]), "authority": "L1",
                                          "push": False, "at": "2026-01-01T00:00:00Z"})
        finally:
            os.environ.pop("ST_CONFIG_DIR", None)
        o["state"] = "approved"
        self.write_order(wo, o)
        self.st_fails("dispatch", wo, contains="no expiry")

    def test_revise_and_reapprove_allows_a_new_run(self):
        wo, _ = self.dispatched()
        self.st("report", wo, stdin=json.dumps({"status": "PARTIAL", "summary": "half",
                                                "criteria": [{"met": True}, {"met": False}]}))
        self.st("revise", wo, stdin=json.dumps(order_spec(intent="finish it")))
        self.st("approve", wo)
        self.st("dispatch", wo)
        self.assertEqual(self.order(wo)["attempt"], 2)

    def test_lease_store_is_protected_from_agents(self):
        wo, ws = self.dispatched()
        lease = self.leases()[0]
        self.assertBlocked("tester", "write", {"path": str(lease)}, cwd=ws, contains="control-plane")
        self.assertBlocked("tester", "shell", {"command": f"rm {lease}"}, cwd=ws)

    def test_lease_closes_on_every_exit(self):
        a, _ = self.dispatched(title="a")
        self.st("reclaim", a, "--reason", "x")
        b, _ = self.dispatched(title="b")
        self.st("cancel", b)
        c, _ = self.dispatched(title="c")
        self.report(c)
        events = [json.loads(l) for l in self.leases()[0].read_text().splitlines()]
        closes = {(e["order"], e["reason"]) for e in events if e["event"] == "close"}
        self.assertEqual(closes, {(a, "reclaimed"), (b, "cancelled"), (c, "reported")})

if __name__ == "__main__":
    unittest.main()
