"""st unit tests: setup."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestSetup(unittest.TestCase):
    def test_setup_refuses_unencrypted_key(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / "k")],
                           check=True)
            env = {**os.environ, "ST_CONFIG_DIR": str(d / "cfg")}
            r = run_st(["setup", "--key", str(d / "k"), "--identity", "s"], cwd=d, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("no passphrase", r.stderr)
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "pw", "-f",
                            str(d / "k2")], check=True)
            r = run_st(["setup", "--key", str(d / "k2"), "--identity", "s"], cwd=d, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)

if __name__ == "__main__":
    unittest.main()
