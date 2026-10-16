"""st unit tests: the release tarball is a working checkout (X-4)."""
import re
import subprocess
import tarfile
import unittest
from pathlib import Path

from base import ROOT


class TestRelease(unittest.TestCase):
    def setUp(self):
        if not (ROOT / ".git").exists():
            self.skipTest("not a git checkout (e.g. an extracted release tree)")

    def test_version_is_consistent(self):
        model = (ROOT / "src" / "surgical_team" / "model.py").read_text()
        version = re.search(r'VERSION = "([^"]+)"', model).group(1)
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn(f"## {version}", changelog)

    def test_tarball_unpacks_to_a_working_tree(self):
        import os
        import shutil
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="st-rel-"))
        self.addCleanup(shutil.rmtree, work, True)
        r = subprocess.run(["bash", str(ROOT / "scripts" / "release.sh")],
                           cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
                                "ST_DIST_DIR": str(work / "dist")})
        self.assertEqual(r.returncode, 0, r.stderr)
        tarball = Path(re.search(r"built (\S+)", r.stdout).group(1))
        if not tarball.is_absolute():
            tarball = ROOT / tarball
        with tarfile.open(tarball) as tf:
            names = tf.getnames()
            tf.extractall(work)
        prefix = names[0].split("/")[0]
        self.assertIn(f"{prefix}/README.md", names)
        self.assertNotIn(f"{prefix}/docs/backlog.md", names)
        tree = work / prefix
        # the pieces the guard needs must be in the archive
        for needed in ("bin/st", "src/surgical_team/cli.py", "schema/order.json",
                       "skills/surgical-team-protocol/SKILL.md", "CHANGELOG.md"):
            with self.subTest(path=needed):
                self.assertTrue((tree / needed).exists(), needed)
        self.assertFalse((tree / ".venv").exists())
        # Exercise the packaged CLI through its own launcher: a complete ledger
        # lifecycle, schema/code agreement, and the role registry populated
        # from the packaged skills directory.
        env = {**os.environ, "ST_BIN": str(tree / "bin" / "st"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([
            "python3", "-m", "unittest",
            "test_orders.TestOrders.test_full_lifecycle_and_verdict",
            "test_format.TestSchemas.test_schema_and_code_agree_on_spec_fields",
            "test_roles.TestRoleRegistry.test_every_shipped_role_skill_is_draftable",
        ], cwd=tree / "tests", capture_output=True, text=True, env=env)
        output = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, output[-2000:])
        self.assertIn("Ran 3 tests", output, output)
        self.assertIn("\nOK\n", output, output)

        # Keep guard packaging independent of unittest discovery: drive the
        # extracted binary through representative allow and fail-closed cases.
        r = subprocess.run([
            "python3", str(tree / "tests" / "guard_corpus.py"),
            "--st", str(tree / "bin" / "st"),
            str(tree / "tests" / "guard-cases" / "01-no-order.json"),
        ], cwd=tree, capture_output=True, text=True, env=env)
        output = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, output[-2000:])
        self.assertIn("39/39 guard cases passed (kiro)", output, output)


if __name__ == "__main__":
    unittest.main()
