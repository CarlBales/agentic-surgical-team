"""st unit tests: st doctor (X-2)."""
import unittest

from base import StTestCase


class TestDoctor(StTestCase):
    def doctor(self):
        # doctor exits 1 here (the test key is unencrypted), so don't use self.st
        r = self.run_st("doctor", "--quick", env={**self.env, "HOME": str(self.tmp)})
        return r

    def test_reports_environment(self):
        out = self.doctor().stdout
        for row in ("python", "git", "ssh-keygen", "signing", "allowed_signers",
                    "installed agents", "ledger", "host"):
            with self.subTest(row=row):
                self.assertIn(row, out)

    def test_flags_the_unencrypted_test_key(self):
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("signs with no passphrase", r.stdout)

    def test_reports_missing_role_agents(self):
        # HOME is the empty tmp dir, so no agents are installed
        self.assertIn("st install", self.doctor().stdout)

    def test_reports_a_cursor_install_and_its_hooks(self):
        env = {**self.env, "HOME": str(self.tmp), "ST_CURSOR_DIR": str(self.tmp / "cursor")}
        self.assertEqual(self.run_st("install", "--host", "cursor", env=env).returncode, 0)
        out = self.run_st("doctor", "--quick", env=env).stdout
        self.assertIn("[ok  ] installed agents (cursor)", out)
        self.assertIn("[ok  ] cursor hooks", out)
        self.assertIn("[ok  ] cursor cloud agents", out)
        self.assertIn("never use them on team projects", out)
        self.assertIn("supported and verified on the Cursor Agent CLI only", out)
        self.assertIn("do not run team sessions in the Cursor IDE", out)
        self.assertIn("[ok  ] cursor /st command", out)
        (self.tmp / "cursor" / "hooks.json").write_text('{"version": 1, "hooks": {}}')
        (self.tmp / "cursor" / "agents" / "st-tester.md").write_text("old\n")
        (self.tmp / "cursor" / "commands" / "st.md").write_text("old\n")
        out = self.run_st("doctor", "--quick", env=env).stdout
        self.assertIn("[FAIL] cursor hooks", out)
        self.assertIn("out of date st-tester", out)
        self.assertIn("[warn] cursor /st command", out)
        (self.tmp / "cursor" / "commands" / "st.md").unlink()
        self.assertIn("[FAIL] cursor /st command", self.run_st("doctor", "--quick", env=env).stdout)

    def test_flags_an_unreadable_ledger_format(self):
        (self.repo / ".surgical-team" / "format.json").write_text('{"format": 99}')
        self.assertIn("not readable", self.doctor().stdout)

    def test_specialists_may_run_doctor(self):
        wo, ws = self.dispatched()
        self.assertAllowed("tester", "shell", {"command": "st doctor"}, cwd=ws)


if __name__ == "__main__":
    unittest.main()
