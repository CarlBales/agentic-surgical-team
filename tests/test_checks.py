"""st unit tests: checks."""
import json
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestChecks(StTestCase):
    def test_checks_run_in_workspace_and_are_recorded(self):
        wo, ws = self.dispatched()
        r = self.run_st("check", wo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        (ws / "ok.txt").write_text("y")
        r = self.run_st("check", wo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.loads((self.repo / ".surgical-team" / "checks" / f"{wo}.a1.json").read_text())
        self.assertEqual(len(rec["runs"]), 2)
        self.assertTrue(rec["runs"][1]["dirty"])

    def test_accept_warns_on_unrun_or_failed_checks(self):
        wo, _ = self.dispatched()
        self.report(wo)
        r = self.run_st("accept", wo)
        self.assertIn("never run", r.stderr)

    def test_checks_refuse_without_authority(self):
        wo = self.draft()
        o = self.order(wo)
        o["state"] = "dispatched"
        o["dispatch"] = {"at": "2026-01-01T00:00:00Z", "workspace": None}
        self.write_order(wo, o)
        self.st_fails("check", wo, contains="refusing to run checks")

    def test_check_refuses_tampered_workspace_git_metadata_without_executing_it(self):
        wo, ws = self.dispatched(
            acceptance=[{"text": "safe check", "check": "true"}]
        )
        marker = self.tamper_worktree_git(ws)

        result = self.run_st("check", wo)

        self.assertFalse(marker.exists(), "workspace Git config executed on the host")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("workspace git metadata was tampered with", result.stderr)
        checks = self.repo / ".surgical-team" / "checks" / f"{wo}.a1.json"
        self.assertFalse(checks.exists(), "checks ran before metadata verification")


if __name__ == "__main__":
    unittest.main()
