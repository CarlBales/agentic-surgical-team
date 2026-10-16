"""Tests for the container sandbox entrypoint (X-3).

The regular tests use a stub runtime to inspect the exact container command.
Set ST_CONTAINER_TESTS=1 to additionally exercise a complete order lifecycle
with Podman or Docker and a small cached Python/git image.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import textwrap
import unittest
from pathlib import Path

from base import ROOT, StTestCase, order_spec

SANDBOX = ROOT / "scripts" / "sandbox"
CONTAINER_RUNTIME = shutil.which("podman") or shutil.which("docker")
RUN_CONTAINER_TESTS = os.environ.get("ST_CONTAINER_TESTS") == "1"


class TestSandbox(StTestCase):
    def run_sandbox(self, *args, cmd=None):
        stub = self.tmp / "bin" / "faker"
        stub.parent.mkdir(parents=True, exist_ok=True)
        record = self.tmp / "argv"
        stub.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > " + str(record) + "\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        env = {**self.env, "ST_SANDBOX_RUNTIME": str(stub), "HOME": str(self.tmp)}
        env.pop("ST_CURSOR_DIR", None)  # these tests place .cursor under HOME
        extra = list(args) + (["--", *cmd] if cmd else [])
        r = subprocess.run(["bash", str(SANDBOX), *extra], cwd=self.repo, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return record.read_text().splitlines()

    def test_mounts_project_source_read_only_and_control_state_writable(self):
        argv = self.run_sandbox()
        joined = "\n".join(argv)
        name = self.repo.name
        target = f"/work/{name}"
        self.assertIn(f"type=bind,source={self.repo},target={target},readonly", argv)
        self.assertIn(
            f"type=bind,source={self.repo}/.surgical-team,target={target}/.surgical-team",
            argv,
        )
        self.assertIn(f"type=bind,source={self.repo}/.git,target={target}/.git", argv)
        self.assertNotIn(f"target={target}/.surgical-team,readonly", joined)
        self.assertNotIn(f"target={target}/.git,readonly", joined)
        git = self.repo / ".git"
        for entry in ("config", "HEAD", "hooks", "info", "refs", "packed-refs", "index"):
            with self.subTest(entry=entry):
                self.assertIn(
                    f"type=bind,source={git}/{entry},target={target}/.git/{entry},readonly", argv)
        self.assertIn(f"type=bind,source={git}/refs/heads/st,target={target}/.git/refs/heads/st",
                      argv)
        self.assertTrue((git / "packed-refs").is_file())
        self.assertIn(f"type=bind,source={self.repo.parent}/{name}.st,target=/work/{name}.st", argv)
        self.assertNotIn(f"target=/work/{name}.st,readonly", joined)
        self.assertIn("none", argv)  # --network none

    def test_trust_root_is_read_only_except_writable_state_directories(self):
        argv = self.run_sandbox()
        target = "/root/.config/surgical-team"
        self.assertIn(f"type=bind,source={self.cfg},target={target},readonly", argv)
        for state in ("leases", "cursor"):
            with self.subTest(state=state):
                source = self.cfg / state
                self.assertTrue(source.is_dir())
                self.assertIn(f"type=bind,source={source},target={target}/{state}", argv)
                self.assertNotIn(f"target={target}/{state},readonly", "\n".join(argv))

    def test_team_checkout_can_be_mounted_read_only_on_path(self):
        argv = self.run_sandbox("--team-root", str(ROOT))
        self.assertIn(f"type=bind,source={ROOT},target=/opt/surgical-team,readonly", argv)
        self.assertIn("PATH=/opt/surgical-team/bin:/usr/local/bin:/usr/bin:/bin", argv)

    def test_default_command_is_a_copilot_session(self):
        argv = self.run_sandbox()
        self.assertEqual(argv[-3:], ["chat", "--agent", "st-copilot"])

    def test_explicit_command_passes_through(self):
        argv = self.run_sandbox(cmd=["st", "status"])
        self.assertEqual(argv[-2:], ["st", "status"])

    def test_cursor_host_runs_the_cursor_cli_with_its_config_guarded(self):
        cursor = self.tmp / ".cursor"
        (cursor / "agents").mkdir(parents=True)
        (cursor / "hooks.json").write_text("{}")
        argv = self.run_sandbox("--host", "cursor")
        self.assertEqual(argv[-1], "agent")
        self.assertIn(f"type=bind,source={cursor},target=/root/.cursor", argv)
        self.assertIn(f"type=bind,source={cursor}/agents,target=/root/.cursor/agents,readonly",
                      argv)
        self.assertIn(f"type=bind,source={cursor}/hooks.json,target=/root/.cursor/hooks.json,"
                      "readonly", argv)
        argv = self.run_sandbox("--host", "cursor", cmd=["agent", "-p", "hi"])
        self.assertEqual(argv[-3:], ["agent", "-p", "hi"])

    def test_kiro_runs_without_cursor_mounts(self):
        (self.tmp / ".cursor").mkdir()
        self.assertFalse(any("/root/.cursor" in a for a in self.run_sandbox()))

    @unittest.skipUnless(
        RUN_CONTAINER_TESTS and CONTAINER_RUNTIME,
        "set ST_CONTAINER_TESTS=1 and install podman or docker",
    )
    def test_real_container_runs_an_order_without_writing_main_source(self):
        runtime = str(CONTAINER_RUNTIME)
        image = self._container_image(runtime)
        wo = self.draft(
            title="Container lifecycle",
            acceptance=[{"text": "workspace artifact exists"}],
        )
        self.st("approve", wo)

        project = f"/work/{self.repo.name}"
        workspace = f"/work/{self.repo.name}.st/{wo}"
        inner_draft = order_spec(
            title="Drafted in container",
            acceptance=[{"text": "draft persisted"}],
        )
        report = {
            "status": "DONE",
            "summary": "container lifecycle completed",
            "criteria": [{"met": True, "evidence": "artifact.txt written"}],
        }
        program = textwrap.dedent(
            f"""
            import json
            import subprocess
            from pathlib import Path

            project = Path({project!r})
            workspace = Path({workspace!r})

            def run_st(arguments, payload=None, cwd=project):
                result = subprocess.run(
                    ["st"] + arguments,
                    cwd=cwd,
                    input=json.dumps(payload) if payload is not None else None,
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    raise RuntimeError(
                        "st %s failed (%s):\\nstdout: %s\\nstderr: %s"
                        % (" ".join(arguments), result.returncode, result.stdout, result.stderr)
                    )
                return result.stdout

            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", str(project)],
                check=True,
            )
            drafted = run_st(["draft"], json.loads({json.dumps(inner_draft)!r}))
            if "WO-" not in drafted:
                raise RuntimeError("container draft did not return an order ID")

            source = project / "README.md"
            before = source.read_text()
            try:
                source.write_text("tampered\\n")
            except OSError:
                pass
            else:
                raise RuntimeError("main-checkout source was writable")
            if source.read_text() != before:
                raise RuntimeError("main-checkout source changed")

            run_st(["dispatch", {wo!r}])
            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", str(workspace)],
                check=True,
            )
            (workspace / "artifact.txt").write_text("created in sandbox\\n")
            run_st(["report", {wo!r}], json.loads({json.dumps(report)!r}), cwd=workspace)
            """
        )
        result = subprocess.run(
            [
                "bash", str(SANDBOX),
                "--runtime", runtime,
                "--image", image,
                "--project", str(self.repo),
                "--team-root", str(ROOT),
                "--no-tty",
                "--", "python3", "-c", program,
            ],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual((self.repo / "README.md").read_text(), "hello\n")
        self.assertEqual(self.order(wo)["state"], "reported")
        workspace_on_host = self.repo.parent / f"{self.repo.name}.st" / wo
        self.assertEqual(
            (workspace_on_host / "artifact.txt").read_text(),
            "created in sandbox\n",
        )
        reports = self.repo / ".surgical-team" / "reports"
        self.assertTrue((reports / f"{wo}.a1.json").is_file())
        drafted = [order for order in self.repo.joinpath(".surgical-team", "orders").glob("*.json")
                   if order.stem != wo]
        self.assertEqual(len(drafted), 1)
        self.assertEqual(json.loads(drafted[0].read_text())["state"], "drafted")

    @unittest.skipUnless(
        RUN_CONTAINER_TESTS and CONTAINER_RUNTIME,
        "set ST_CONTAINER_TESTS=1 and install podman or docker",
    )
    def test_real_container_cannot_plant_host_side_git_code_or_move_main(self):
        """Workspace code must not reach the host through the shared .git: hooks
        and config run on the surgeon's next git command, and moving main or
        adding a replace ref changes what the host checks out."""
        runtime = str(CONTAINER_RUNTIME)
        image = self._container_image(runtime)
        wo = self.draft(title="Git escapes", acceptance=[{"text": "x"}])
        self.st("approve", wo)
        main_before = self.git("rev-parse", "refs/heads/main")
        config_before = (self.repo / ".git" / "config").read_text()
        project = f"/work/{self.repo.name}"
        workspace = f"/work/{self.repo.name}.st/{wo}"
        program = textwrap.dedent(
            f"""
            import json
            import subprocess
            from pathlib import Path

            project, workspace = Path({project!r}), Path({workspace!r})
            git_dir = project / ".git"
            for path in (project, workspace):
                subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(path)],
                               check=True)
            subprocess.run(["st", "dispatch", {wo!r}], cwd=project, check=True,
                           capture_output=True)

            def git(*args, cwd=workspace):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", *args],
                                      cwd=cwd, capture_output=True, text=True)

            (workspace / "work.txt").write_text("legit\\n")
            git("add", "work.txt")
            results = {{"branch commit": git("commit", "-qm", "work").returncode == 0}}

            def attempt(name, action):
                try:
                    action()
                except OSError:
                    results[name] = False
                else:
                    results[name] = True

            attempt("hook", lambda: (git_dir / "hooks" / "post-checkout").write_text(
                "#!/bin/sh\\necho pwned\\n"))
            attempt("config", lambda: open(git_dir / "config", "a").write(
                "[core]\\n\\tfsmonitor = echo pwned\\n"))
            attempt("HEAD", lambda: (git_dir / "HEAD").write_text("ref: refs/heads/evil\\n"))
            attempt("index", lambda: (git_dir / "index").write_bytes(b"x"))
            attempt("info", lambda: (git_dir / "info" / "attributes").write_text("* filter=x\\n"))
            head = git("rev-parse", "HEAD").stdout.strip()
            main = git("rev-parse", "refs/heads/main").stdout.strip()
            results["move main"] = git("update-ref", "refs/heads/main", head).returncode == 0
            results["replace ref"] = git("replace", main, head).returncode == 0
            results["new branch"] = git("branch", "evil", head).returncode == 0
            print(json.dumps(results))
            """
        )
        result = subprocess.run(
            ["bash", str(SANDBOX), "--runtime", runtime, "--image", image,
             "--project", str(self.repo), "--team-root", str(ROOT), "--no-tty",
             "--", "python3", "-c", program],
            cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        results = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(results.pop("branch commit"), "the order's branch must stay writable")
        self.assertEqual({name for name, wrote in results.items() if wrote}, set())
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), main_before)
        self.assertEqual((self.repo / ".git" / "config").read_text(), config_before)
        self.assertFalse((self.repo / ".git" / "hooks" / "post-checkout").exists())
        self.assertEqual(self.git("replace", "-l"), "")

    def _container_image(self, runtime):
        image = "localhost/surgical-team-sandbox-test:python313-git-openssh-v1"
        inspected = subprocess.run(
            [runtime, "image", "inspect", image],
            capture_output=True,
            text=True,
        )
        if inspected.returncode == 0:
            return image
        context = self.tmp / "sandbox-image"
        context.mkdir()
        (context / "Dockerfile").write_text(
            "FROM docker.io/library/python:3.13-slim\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client "
            "&& rm -rf /var/lib/apt/lists/*\n"
        )
        built = subprocess.run(
            [runtime, "build", "--tag", image, str(context)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(built.returncode, 0, built.stderr + built.stdout)
        return image


if __name__ == "__main__":
    unittest.main()
