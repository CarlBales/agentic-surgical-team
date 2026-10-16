"""st unit tests: signing."""
import json
import shutil
import subprocess
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestSigning(StTestCase):
    def test_forged_approval_is_rejected(self):
        wo = self.draft()
        o = self.order(wo)
        o["approval"] = {"signer": "surgeon", "payload": {"kind": "approve", "order": wo},
                         "sig": "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----"}
        o["state"] = "approved"
        self.write_order(wo, o)
        self.st_fails("dispatch", wo, contains="approval")
        self.assertNotEqual(self.run_st("verify").returncode, 0)

    def test_editing_spec_after_approval_voids_it(self):
        wo = self.draft()
        self.st("approve", wo)
        o = self.order(wo)
        o["spec"]["authority"] = "L2"
        o["spec"]["push"] = True
        self.write_order(wo, o)
        self.st_fails("dispatch", wo, contains="does not match")

    def test_planted_standing_order_grants_nothing(self):
        dec = {"id": "DEC-001", "signed": {"signer": "surgeon", "sig": "bogus", "payload": {
            "kind": "standing", "id": "DEC-001", "role": "*", "max_authority": "L2"}}}
        (self.repo / ".surgical-team" / "decisions" / "DEC-001.json").write_text(json.dumps(dec))
        wo = self.draft(standing="DEC-001")
        self.st_fails("dispatch", wo, contains="unverified")

    def test_signature_from_unknown_key_rejected(self):
        wo = self.draft()
        other = self.tmp / "other"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)],
                       check=True)
        cfg2 = self.tmp / "cfg2"
        cfg2.mkdir()
        (cfg2 / "config.json").write_text(json.dumps({"key": str(other), "identity": "surgeon"}))
        env2 = {**self.env, "ST_CONFIG_DIR": str(cfg2)}
        r = self.run_st("approve", wo, env=env2)
        self.assertEqual(r.returncode, 0, r.stderr)  # signs, but with the wrong key
        self.st_fails("dispatch", wo, contains="bad signature")

    def test_standing_order_dispatches_within_limits(self):
        dec = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "tests",
                      "--budget", "30")
        wo = self.draft(standing=dec)
        self.st("dispatch", wo)
        too_big = self.draft(standing=dec, authority="L2")
        self.st_fails("dispatch", too_big, contains="at most L1")
        wrong_role = self.draft(standing=dec, role="editor")
        self.st_fails("dispatch", wrong_role, contains="does not cover role")
        over = self.draft(standing=dec, budget={"minutes": 90})
        self.st_fails("dispatch", over, contains="budget ceiling")

    def test_revoked_and_expired_standing_orders(self):
        dec = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "tests")
        self.st("revoke", dec)
        self.st_fails("dispatch", self.draft(standing=dec), contains="revoked")
        old = self.st("grant", "--role", "tester", "--max", "L1", "--scope", "t",
                      "--expires", "2000-01-01")
        self.st_fails("dispatch", self.draft(standing=old), contains="expired")

    def test_default_standing_order_covers_L0_only(self):
        shutil.rmtree(self.repo / ".surgical-team")
        out = self.st("init", "--default-standing")
        self.assertIn("DEC-001", out)
        self.st("dispatch", self.draft(authority="L0", standing="DEC-001"))
        self.st_fails("dispatch", self.draft(authority="L1", standing="DEC-001"),
                      contains="at most L0")

    def test_supersede_decision(self):
        d1 = self.st("decide", "--title", "retry in transport", "--decision", "x")
        d2 = self.st("decide", "--title", "retry per call", "--decision", "y",
                     "--supersedes", d1)
        self.st_fails("draft", stdin=json.dumps(order_spec(inputs={"decisions": [d1]})),
                      contains="superseded")
        self.draft(inputs={"decisions": [d2]})

    def test_no_L3_standing_order(self):
        self.st_fails("grant", "--role", "tester", "--max", "L3", "--scope", "x",
                      contains="never L3")

if __name__ == "__main__":
    unittest.main()
