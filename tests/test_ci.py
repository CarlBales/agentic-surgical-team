"""st unit tests: the CI workflow refers to things that exist (M-7).

GitHub Actions only runs remotely, so this checks what can be checked here:
the workflow parses, every repo-relative script it runs exists, every tool
it calls is pinned in requirements-dev.txt, and the matrix covers the
supported Python floor.
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from base import ROOT

try:
    import yaml
except ImportError:  # pyyaml is a dev requirement; skip rather than fail without it
    yaml = None


@unittest.skipIf(yaml is None, "pyyaml not installed (pip install -r requirements-dev.txt)")
class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        self.runs = [step["run"] for job in self.wf["jobs"].values()
                     for step in job["steps"] if "run" in step]

    def test_scripts_it_runs_exist(self):
        paths = {m for r in self.runs for m in re.findall(r"(?<![\w/])(?:tests|scripts|bin)/[\w./-]+", r)}
        self.assertTrue(paths)
        for p in paths:
            with self.subTest(path=p):
                self.assertTrue((ROOT / p).exists(), p)

    def test_tools_are_pinned(self):
        pinned = {line.split("==")[0].strip() for line in
                  (ROOT / "requirements-dev.txt").read_text().splitlines()
                  if "==" in line and not line.startswith("#")}
        for tool in ("mypy", "ruff", "coverage"):
            with self.subTest(tool=tool):
                self.assertIn(tool, pinned)
                self.assertTrue(any(re.search(rf"(^|\s){tool}\b", r, re.M) for r in self.runs))

    def test_ci_covers_the_floor_on_linux(self):
        # macOS is the local gate's platform (scripts/check); CI vouches for Linux.
        job = self.wf["jobs"]["test"]
        self.assertIn("3.9", job["strategy"]["matrix"]["python"])  # the supported floor
        self.assertEqual(job["runs-on"], "ubuntu-latest")

    def test_least_privilege(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        for job in self.wf["jobs"].values():
            for step in job["steps"]:
                if step.get("uses", "").startswith("actions/checkout"):
                    self.assertIs(step["with"]["persist-credentials"], False)

    def test_only_pull_requests_and_manual_runs_trigger_it(self):
        triggers = self.wf.get("on", self.wf.get(True))  # YAML 1.1 reads `on` as true
        self.assertEqual(set(triggers), {"pull_request", "workflow_dispatch"})

    def test_hosted_runners_only_on_github_com_unless_started_by_hand(self):
        for name, job in self.wf["jobs"].items():
            with self.subTest(job=name):
                self.assertIn("github.server_url == 'https://github.com'", job["if"])
                self.assertIn("workflow_dispatch", job["if"])
                self.assertNotIn("self-hosted", str(job["runs-on"]))

    def test_live_scenarios_and_mutation_stay_local(self):
        # They spend tokens or minutes; scripts/check runs them before a push.
        for run in self.runs:
            self.assertNotIn("scenarios.py", run)
            self.assertNotIn("mutate_guard.py", run)
        check = (ROOT / "scripts" / "check").read_text()
        for step in ("tests/scenarios.py", "tests/mutate_guard.py", "tests/bench_guard.py",
                     "validate-skills.sh", '"mypy"', '"ruff"', "ST_TEST_MODE"):
            with self.subTest(step=step):
                self.assertIn(step, check)


def load_check():
    """scripts/check as a module (it has no .py suffix)."""
    loader = importlib.machinery.SourceFileLoader("st_check", str(ROOT / "scripts" / "check"))
    spec = importlib.util.spec_from_loader("st_check", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GateRepo:
    """A temp repository with scripts/check loaded as a module pointed at it."""

    def setUp(self):
        self.check = load_check()
        self.tmp = Path(tempfile.mkdtemp(prefix="st-check-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull)
        self.repo = self.tmp / "repo"
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=self.tmp)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, name, text):
        (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", name)
        return self.git("rev-parse", "HEAD")


class TestLocalGate(GateRepo, unittest.TestCase):
    """The pre-push gate: what it checks, on which tree, and where its hook lives."""

    def test_mutation_targets_match_the_harness(self):
        harness = (ROOT / "tests" / "mutate_guard.py").read_text()
        for target in self.check.MUTATION_TARGETS:
            self.assertIn(f'"{target}"', harness)

    def test_only_changed_guard_files_are_mutated(self):
        files = self.check.mutation_files(["src/surgical_team/guard/cursor.py", "README.md"])
        self.assertEqual(files, ["guard/cursor.py"])
        self.assertEqual(self.check.mutation_files(["README.md"]), [])
        self.assertEqual(self.check.mutation_files(None), list(self.check.MUTATION_TARGETS))

    def test_scenarios_run_only_for_changes_agents_see(self):
        self.assertFalse(self.check.affects_agents(["README.md", "tests/test_ci.py"]))
        for path in ("skills/tester/SKILL.md", "src/surgical_team/cli.py", "bin/st",
                     "tests/scenarios.py"):
            self.assertTrue(self.check.affects_agents([path]), path)
        self.assertTrue(self.check.affects_agents(None))  # unknown: run them

    def test_gate_checks_the_pushed_commit_not_the_working_tree(self):
        sha = self.commit("a.txt", "committed\n")
        (self.repo / "a.txt").write_text("uncommitted\n")
        (self.repo / "untracked.txt").write_text("x\n")
        self.check.ROOT = self.repo
        tree = self.check.clean_clone(sha, self.tmp)
        self.assertEqual((tree / "a.txt").read_text(), "committed\n")
        self.assertFalse((tree / "untracked.txt").exists())
        hooks = [p.name for p in (tree / ".git" / "hooks").glob("*") if not p.name.endswith(".sample")]
        self.assertEqual(hooks, [])

    def test_push_plan_dedupes_commits_and_skips_deletions(self):
        base = self.commit("README.md", "x\n")
        head = self.commit("src/surgical_team/guard/core.py", "x\n")
        self.check.ROOT = self.repo
        zero = self.check.ZERO
        plan = self.check.plan_pushes("origin", [
            f"refs/heads/main {head} refs/heads/main {base}",
            f"refs/heads/b {head} refs/heads/b {base}",
            f"(delete) {zero} refs/heads/old {base}",
        ])
        self.assertEqual(plan, {head: ["src/surgical_team/guard/core.py"]})
        unknown = self.check.plan_pushes("origin", [f"refs/heads/new {head} refs/heads/new {zero}"])
        self.assertEqual(unknown, {head: None})  # no remote base: check everything

    def test_hook_installs_into_git_dir_and_refuses_linked_worktrees(self):
        base = self.commit("x", "x\n")
        self.check.ROOT = self.repo
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            self.assertEqual(self.check.install_hook(), 0)
        finally:
            os.chdir(cwd)
        hook = self.repo / ".git" / "hooks" / "pre-push"
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertIn("linked worktree", hook.read_text())
        self.git("worktree", "add", "-q", str(self.tmp / "wt"), "-b", "st/WO-1")
        r = subprocess.run(["sh", str(hook), "origin", "url"], cwd=self.tmp / "wt", env=self.env,
                           input=f"refs/heads/st/WO-1 {base} refs/heads/st/WO-1 {self.check.ZERO}\n",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing to push from a linked worktree", r.stderr)

    def test_hook_install_never_overwrites_a_foreign_hook(self):
        hook = self.repo / ".git" / "hooks" / "pre-push"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho mine\n")
        self.check.ROOT = self.repo
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            with self.assertRaises(SystemExit):
                self.check.install_hook()
        finally:
            os.chdir(cwd)
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho mine\n")


class TestPushFlow(GateRepo, unittest.TestCase):
    """Live scenarios outlast the push connection, so they run before git connects."""

    def setUp(self):
        super().setUp()
        self.base = self.commit("README.md", "x\n")
        self.remote = self.tmp / "remote.git"
        self.git("init", "-q", "--bare", str(self.remote), cwd=self.tmp)
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "-u", "origin", "main")
        self.check.ROOT = self.repo
        self.checked = []
        def fake_check(sha, files, args):
            self.checked.append((sha, files, args.scenarios))
            self.check.stamp(sha, "scenarios" if args.scenarios else "gate")
            return 0
        self.check.check = fake_check
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        environ = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull})
        environ.start()
        self.addCleanup(environ.stop)
        for name in ("ST_SKIP_SCENARIOS", "ST_SKIP_CHECK"):
            os.environ.pop(name, None)

    def hook(self, sha):
        args = self.check.argparse.Namespace(full=False, linux=False, scenarios=False, runs=1,
                                             push_args=[])
        return self.check.pre_push("origin", [f"refs/heads/main {sha} refs/heads/main "
                                              f"{self.base}"], args)

    def test_agent_changes_are_refused_at_once_on_a_plain_push(self):
        sha = self.commit("src/surgical_team/cli.py", "x\n")
        self.assertEqual(self.hook(sha), 1)
        self.assertEqual(self.checked, [])  # refused before running anything

    def test_docs_changes_run_the_gate_in_the_hook(self):
        sha = self.commit("docs/x.md", "x\n")
        self.assertEqual(self.hook(sha), 0)
        self.assertEqual(self.checked, [(sha, ["docs/x.md"], False)])

    def test_skipping_scenarios_runs_the_gate_in_the_hook(self):
        sha = self.commit("src/surgical_team/cli.py", "x\n")
        os.environ["ST_SKIP_SCENARIOS"] = "1"
        self.assertEqual(self.hook(sha), 0)
        self.assertEqual(self.checked[0][2], False)

    def test_a_gate_stamp_does_not_cover_agent_changes(self):
        sha = self.commit("skills/x/SKILL.md", "x\n")
        self.check.stamp(sha, "gate")
        self.assertEqual(self.hook(sha), 1)
        self.check.stamp(sha, "scenarios")
        self.assertEqual(self.hook(sha), 0)
        self.assertEqual(self.checked, [])
        self.check.stamp(sha, "gate")  # never downgraded
        self.assertEqual(self.check.stamped(sha), "scenarios")

    def test_stamps_live_in_the_git_dir(self):
        sha = self.commit("x.txt", "x\n")
        self.assertEqual(self.check.stamp_path(sha).parent,
                         (self.repo / ".git" / "st-check").resolve())

    def test_check_push_runs_scenarios_first_then_pushes_through_the_hook(self):
        # The real hook runs in git's subprocess: it must accept the stamped commit.
        (self.repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "check", self.repo / "scripts" / "check")
        self.check.install_hook()
        sha = self.commit("src/surgical_team/cli.py", "x\n")
        args = self.check.argparse.Namespace(full=False, linux=False, scenarios=False, runs=1)
        self.assertEqual(self.check.check_then_push([], args), 0)
        self.assertEqual(self.checked, [(sha, ["src/surgical_team/cli.py"], True)])
        self.assertEqual(self.git("rev-parse", "main", cwd=self.remote), sha)


class TestHookShimRunsTheChecker(unittest.TestCase):
    def test_hook_execs_scripts_check_from_the_checkout(self):
        check = load_check()
        self.assertIn('exec python3 "$top/scripts/check" pre-push "$@"', check.HOOK)


if __name__ == "__main__":
    unittest.main()
