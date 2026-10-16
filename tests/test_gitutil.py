from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

from base import StTestCase
from surgical_team.gitutil import git


class TestGitEnvironment(StTestCase):
    def test_git_scrubs_inherited_git_environment(self):
        inherited = {
            "GIT_DIR": "/attacker/repo",
            "GIT_WORK_TREE": "/attacker/tree",
            "GIT_COMMON_DIR": "/attacker/common",
            "GIT_INDEX_FILE": "/attacker/index",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "touch MARKER",
            "GIT_EXEC_PATH": "/attacker/bin",
            "GIT_EXTERNAL_DIFF": "/attacker/diff",
        }
        completed = subprocess.CompletedProcess(["git", "status"], 0, "", "")
        with mock.patch.dict(os.environ, inherited), mock.patch(
            "surgical_team.gitutil.subprocess.run", return_value=completed
        ) as run:
            git(["status", "--porcelain"], self.repo)

        child_env = run.call_args.kwargs["env"]
        self.assertFalse(
            [name for name in child_env if name.startswith("GIT_")],
            "host Git subprocess inherited executable or repository routing",
        )


if __name__ == "__main__":
    unittest.main()
