"""Shared fixture for the st unit tests: a fresh git repo, config dir, and ledger per test.

Run everything: python3 -m unittest discover -s tests
The signing key is generated once per run (support.surgeon_key) and copied.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import BIN as ST, ROOT, run_st, surgeon_key  # noqa: F401


def order_spec(**over):
    spec = {
        "title": "Add retry tests",
        "role": "tester",
        "authority": "L1",
        "intent": "Uploads fail silently under packet loss.",
        "scope": {"in": ["tests for upload retry"], "out": ["changing the client"]},
        "acceptance": [{"text": "suite passes", "check": "test -f ok.txt"},
                       {"text": "names state claims"}],
        "budget": {"minutes": 30},
    }
    spec.update(over)
    return spec


class StTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="st-test-")).resolve()
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.cfg = self.tmp / "cfg"
        self.env = {**os.environ, "ST_CONFIG_DIR": str(self.cfg),
                    # Never the real ~/.cursor: installs and transcripts stay in tmp.
                    "ST_CURSOR_DIR": str(self.tmp / "cursor-home"),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.env.pop("ST_NOW", None)
        self.git("init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "init")
        key = surgeon_key(self.tmp / "key")
        self.st("setup", "--key", str(key), "--identity", "surgeon", "--allow-unencrypted")
        self.st("init")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def run_st(self, *args, stdin=None, cwd=None, env=None):
        return run_st(args, cwd=cwd or self.repo, env=env or self.env, stdin=stdin)

    def st(self, *args, stdin=None, cwd=None):
        r = self.run_st(*args, stdin=stdin, cwd=cwd)
        if r.returncode:
            self.fail(f"st {' '.join(args)} failed ({r.returncode}):\n{r.stderr}")
        return r.stdout.strip()

    def st_fails(self, *args, stdin=None, contains=None):
        r = self.run_st(*args, stdin=stdin)
        self.assertNotEqual(r.returncode, 0, f"expected failure: st {' '.join(args)}\n{r.stdout}")
        if contains:
            self.assertIn(contains, r.stderr)
        return r

    def draft(self, **over):
        return self.st("draft", stdin=json.dumps(order_spec(**over))).splitlines()[-1]

    def order(self, wo):
        return json.loads((self.repo / ".surgical-team" / "orders" / f"{wo}.json").read_text())

    def tamper_worktree_git(self, ws):
        """Replace a linked worktree's gitfile with host-executed metadata.

        A build script can perform these filesystem writes without the guard
        seeing their targets. Any st-owned Git command that trusts ws/.git
        will execute core.fsmonitor and create the marker.
        """
        marker = self.tmp / f"{ws.name}-host-code-ran"
        evil = ws / ".evil"
        self.git("init", "--bare", "-q", str(evil), cwd=self.tmp)
        (evil / "config").write_text(
            "[core]\n"
            "\trepositoryformatversion = 0\n"
            "\tfilemode = true\n"
            "\tbare = false\n"
            f"\tfsmonitor = touch {marker}; false\n"
        )
        (ws / ".git").write_text("gitdir: .evil\n")
        return marker

    def write_order(self, wo, o):
        (self.repo / ".surgical-team" / "orders" / f"{wo}.json").write_text(json.dumps(o))

    def report(self, wo, status="DONE", n=2, **extra):
        rep = {"status": status, "summary": "did it",
               "criteria": [{"met": status == "DONE", "evidence": "x"}] * n, **extra}
        return self.st("report", wo, stdin=json.dumps(rep))

    def guard(self, role, tool, tool_input, cwd=None):
        ev = {"hook_event_name": "preToolUse", "cwd": str(cwd or self.repo),
              "tool_name": tool, "tool_input": tool_input}
        r = run_st(["guard", "--role", role], cwd=self.repo, env=self.env,
                   stdin=json.dumps(ev))
        return r.returncode, r.stderr

    def assertAllowed(self, role, tool, inp, cwd=None):
        code, err = self.guard(role, tool, inp, cwd)
        self.assertEqual(code, 0, f"expected allow, got block: {err}")

    def assertBlocked(self, role, tool, inp, cwd=None, contains=None):
        code, err = self.guard(role, tool, inp, cwd)
        self.assertEqual(code, 2, f"expected block for {tool} {inp}")
        if contains:
            self.assertIn(contains, err)

    def dispatched(self, **over):
        wo = self.draft(**over)
        self.st("approve", wo, *(["--push"] if over.get("push") else []))
        self.st("dispatch", wo)
        return wo, self.repo.parent / "proj.st" / wo
