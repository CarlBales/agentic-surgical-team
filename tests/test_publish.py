"""scripts/publish: what reaches a public remote, and what never does.

Fixture strings that the scanner must catch are assembled at run time, so this
file does not itself trip the scan when the repository is published.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from base import ROOT


def load_publish():
    loader = importlib.machinery.SourceFileLoader("st_publish", str(ROOT / "scripts" / "publish"))
    spec = importlib.util.spec_from_loader("st_publish", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TestScanRules(unittest.TestCase):
    def setUp(self):
        self.p = load_publish()
        deny = [("denylist test:1", __import__("re").compile("acme" + "corp", __import__("re").I))]
        self.rules = self.p.compiled_rules(deny)

    def hits(self, text, path="f.md"):
        return {h.rule for h in self.p.scan_text(path, text, self.rules)}

    def test_secrets_and_identity_are_caught(self):
        cases = {
            "private key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
            "AWS access key": "key = AK" + "IA" + "ABCDEFGHIJKLMNOP",
            "GitHub token": "gh" + "p_" + "a" * 36,
            "home directory": "see /Us" + "ers/alice/src/x",
            "confidentiality marker": "(internal; do not " + "publish)",
            "email address": "mail alice@" + "corp-example.net today",
            "denylist test:1": "built for ACME" + "CORP rewards",
        }
        for rule, text in cases.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, self.hits(text))

    def test_placeholders_and_public_addresses_pass(self):
        for text in ("st setup --identity you@example.com", "ci@example.invalid",
                     "git@github.com:OWNER/REPO.git", "1+u@users.noreply.github.com",
                     "/Users/you/code", "/home/runner/work", "t@e.test"):
            with self.subTest(text=text):
                self.assertEqual(self.hits(text), set())

    def test_file_names_are_scanned_too(self):
        self.assertIn("denylist test:1", self.hits("", path="docs/acme" + "corp-notes.md"))

    def test_this_repository_scans_clean_under_the_built_in_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.strip()
            tree = self.p.export(sha, Path(tmp))
            builtin = self.p.compiled_rules([])
            self.assertEqual(self.p.scan_tree(tree, builtin), [])


class TestPublish(unittest.TestCase):
    """End to end against a temporary internal repository and a bare public one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="st-publish-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull,
                                           "ST_CONFIG_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        for name in [k for k in os.environ if k.startswith("GIT_") and k != "GIT_CONFIG_GLOBAL"]:
            os.environ.pop(name)
        os.environ.pop("ST_SKIP_CHECK", None)
        self.repo = self.tmp / "internal"
        self.public = self.tmp / "public.git"
        self.run_git("init", "-q", "-b", "main", str(self.repo), cwd=self.tmp)
        self.run_git("init", "-q", "--bare", "-b", "main", str(self.public), cwd=self.tmp)
        self.run_git("config", "user.name", "Internal Dev")
        self.run_git("config", "user.email", "dev@internal.test")
        # The public repository already has history (an earlier release).
        seed = self.tmp / "seed"
        self.run_git("clone", "-q", str(self.public), str(seed), cwd=self.tmp)
        (seed / "README.md").write_text("old public readme\n")
        self.run_git("add", "README.md", cwd=seed)
        self.run_git("-c", "user.name=Old", "-c", "user.email=old@example.com", "commit", "-qm",
                     "earlier release", cwd=seed)
        self.run_git("push", "-q", "origin", "main", cwd=seed)
        self.public_tip = self.run_git("rev-parse", "HEAD", cwd=seed)
        # The internal repository: scripts, a doc, and an export-ignored internal file.
        (self.repo / "scripts").mkdir()
        for name in ("check", "publish"):
            shutil.copy(ROOT / "scripts" / name, self.repo / "scripts" / name)
        (self.repo / "README.md").write_text("new readme\n")
        (self.repo / "internal.md").write_text("roadmap for acme" + "corp\n")
        (self.repo / ".gitattributes").write_text("internal.md export-ignore\n")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "internal commit one")
        (self.repo / "README.md").write_text("new readme, v2\n")
        self.run_git("commit", "-qam", "internal commit two: acme" + "corp detail")
        self.head = self.run_git("rev-parse", "HEAD")
        self.run_git("remote", "add", "public", str(self.public))
        self.run_git("config", "st.publicRemote", "public")
        self.run_git("config", "st.publishIdentity", "Pub Lisher <1+pub@users.noreply.github.com>")
        (self.repo / ".git" / "info" / "publish-denylist").write_text("acme" + "corp\n")

        self.p = load_publish()
        self.p.ROOT = self.p.check.ROOT = self.repo
        self.gated = []
        def fake_gate(sha, files, args):
            self.gated.append(sha)
            return 0
        self.p.check.check = fake_gate
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.p.check.install_hook()

    def run_git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def public_git(self, *args):
        return self.run_git(f"--git-dir={self.public}", *args, cwd=self.tmp)

    def publish(self, *args):
        with mock.patch("sys.stdout"):
            try:
                return self.p.main(list(args))
            except SystemExit as stop:
                return stop.code

    def test_a_snapshot_on_the_public_tip_without_internal_history(self):
        self.p.check.stamp(self.head, "scenarios")
        self.assertEqual(self.publish("-m", "Update"), 0)
        tip = self.public_git("rev-parse", "main")
        self.assertEqual(self.public_git("rev-parse", f"{tip}^"), self.public_tip)
        self.assertEqual(self.public_git("rev-list", "--count", "main"), "2")
        self.assertEqual(self.public_git("log", "-1", "--format=%an <%ae>|%cn <%ce>|%s", "main"),
                         "Pub Lisher <1+pub@users.noreply.github.com>|"
                         "Pub Lisher <1+pub@users.noreply.github.com>|Update")
        files = self.public_git("ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertNotIn("internal.md", files)
        self.assertIn("README.md", files)
        self.assertEqual(self.public_git("show", "main:README.md"), "new readme, v2")
        for internal in (self.head, self.run_git("rev-parse", "HEAD~1")):  # never shipped
            r = subprocess.run(["git", f"--git-dir={self.public}", "cat-file", "-e", internal],
                               capture_output=True)
            self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.gated, [tip])  # the gate ran on the exact public commit

    def test_a_finding_stops_the_publish(self):
        (self.repo / "NOTES.md").write_text("ship it to acme" + "corp\n")
        self.run_git("add", "NOTES.md")
        self.run_git("commit", "-qm", "notes")
        self.p.check.stamp(self.run_git("rev-parse", "HEAD"), "scenarios")
        self.assertEqual(self.publish(), 1)
        self.assertEqual(self.public_git("rev-parse", "main"), self.public_tip)

    def test_the_commit_message_is_scanned(self):
        self.p.check.stamp(self.head, "scenarios")
        self.assertEqual(self.publish("-m", "for acme" + "corp"), 1)
        self.assertEqual(self.public_git("rev-parse", "main"), self.public_tip)

    def test_an_unchecked_commit_is_not_published(self):
        self.assertNotEqual(self.publish(), 0)
        self.assertEqual(self.public_git("rev-parse", "main"), self.public_tip)

    def test_no_denylist_no_publish(self):
        (self.repo / ".git" / "info" / "publish-denylist").unlink()
        self.p.check.stamp(self.head, "scenarios")
        self.assertNotEqual(self.publish(), 0)

    def test_an_unchanged_tree_publishes_nothing(self):
        self.p.check.stamp(self.head, "scenarios")
        self.assertEqual(self.publish("-m", "first"), 0)
        tip = self.public_git("rev-parse", "main")
        self.assertEqual(self.publish("-m", "again"), 0)
        self.assertEqual(self.public_git("rev-parse", "main"), tip)

    def test_the_hook_refuses_internal_history_on_the_public_remote(self):
        for env in ({}, {"ST_SKIP_CHECK": "1"}):
            with self.subTest(env=env):
                r = subprocess.run(["git", "push", "public", "main"], cwd=self.repo,
                                   env={**os.environ, **env}, capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("internal history", r.stdout + r.stderr)
                self.assertEqual(self.public_git("rev-parse", "main"), self.public_tip)

    def test_public_forges_are_public_without_configuration(self):
        check = self.p.check
        for url in ("git@github.com:o/r.git", "https://github.com/o/r", "ssh://git@gitlab.com/o/r"):
            self.assertTrue(check.is_public("anything", url), url)
        for url in ("git@github.internal.invalid:o/r.git", "/srv/git/r.git", "../r.git"):
            self.assertFalse(check.is_public("origin", url), url)


if __name__ == "__main__":
    unittest.main()
