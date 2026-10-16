"""st unit tests: roles."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestRoleRegistry(StTestCase):
    """E-1: roles come from the team's skills/ frontmatter, not a hardcoded list."""

    def team_copy(self):
        team = self.tmp / "team"
        (team / "bin").mkdir(parents=True)
        shutil.copy2(ST, team / "bin" / "st")
        shutil.copytree(ROOT / "skills", team / "skills")
        shutil.copytree(ROOT / "src", team / "src")
        return team

    def add_skill(self, team, dirname, name=None, family="reviewer"):
        d = team / "skills" / dirname
        d.mkdir()
        meta = f"  surgical-team-role: {family}\n" if family else ""
        (d / "SKILL.md").write_text(f"---\nname: {name or dirname}\ndescription: x\n"
                                    f"metadata:\n  author: t\n{meta}---\n# x\n")

    def run_team_st(self, team, *args, stdin=None):
        return subprocess.run([str(team / "bin" / "st"), *args], cwd=self.repo, input=stdin,
                              env=self.env, capture_output=True, text=True)

    def test_every_shipped_role_skill_is_draftable(self):
        for role in ("reviewer", "security-reviewer", "archaeologist", "archivist",
                     "platform-lawyer-react-native", "language-lawyer-typescript",
                     "copilot", "tester"):
            with self.subTest(role=role):
                self.draft(role=role)
        self.st_fails("draft", stdin=json.dumps(order_spec(role="surgical-team-protocol")),
                      contains="not a team role")

    def test_new_skill_with_family_becomes_a_role(self):
        team = self.team_copy()
        spec = json.dumps(order_spec(role="perf-reviewer"))
        r = self.run_team_st(team, "draft", stdin=spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a team role", r.stderr)
        self.add_skill(team, "perf-reviewer")
        r = self.run_team_st(team, "draft", stdin=spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        dest = self.tmp / "agents"
        self.run_team_st(team, "install", "--dir", str(dest))
        cfg = json.loads((dest / "st-perf-reviewer.json").read_text())
        self.assertIn("guard --role perf-reviewer", cfg["hooks"]["preToolUse"][0]["command"])
        self.assertIn("independent reviewer", cfg["description"])

    def test_skills_that_do_not_declare_a_role_are_not_roles(self):
        team = self.team_copy()
        self.add_skill(team, "no-family", family=None)
        self.add_skill(team, "mismatch", name="reviewer2")
        self.add_skill(team, "proto2", family="protocol")
        for role in ("no-family", "mismatch", "reviewer2", "proto2"):
            with self.subTest(role=role):
                r = self.run_team_st(team, "draft", stdin=json.dumps(order_spec(role=role)))
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("not a team role", r.stderr)

    def test_agents_cannot_add_a_role_by_writing_a_skill(self):
        wo, ws = self.dispatched()
        target = ROOT / "skills" / "evil" / "SKILL.md"
        self.assertBlocked("tester", "write", {"path": str(target)}, cwd=ws)
        self.assertBlocked("copilot", "write", {"path": str(target)})

class TestHookFailsClosed(StTestCase):
    """Kiro allows a tool call when a preToolUse hook exits non-zero but not 2.

    The installed hook command must turn every guard failure into exit 2.
    It is run here through sh -c, as a host runs it.
    """

    def hook(self, team, role="tester"):
        dest = self.tmp / "agents"
        r = subprocess.run([str(team / "bin" / "st"), "install", "--dir", str(dest)],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads((dest / f"st-{role}.json").read_text())["hooks"]["preToolUse"][0]["command"]

    def run_hook(self, cmd, tool="write", inp=None):
        ev = {"hook_event_name": "preToolUse", "cwd": str(self.repo), "tool_name": tool,
              "tool_input": inp or {"path": str(self.repo / "README.md")}}
        return subprocess.run(["sh", "-c", cmd], input=json.dumps(ev), env=self.env,
                              capture_output=True, text=True)

    def test_healthy_guard_allows_and_blocks(self):
        cmd = self.hook(TestRoleRegistry.team_copy(self))
        self.assertEqual(self.run_hook(cmd).returncode, 2)  # L0 write: blocked by the guard
        self.assertEqual(self.run_hook(cmd, "read", {"operations": [
            {"mode": "Line", "path": str(self.repo / "README.md")}]}).returncode, 0)

    def test_broken_guard_blocks(self):
        for breakage in ("syntax", "import", "missing", "not-executable"):
            with self.subTest(breakage=breakage):
                team = TestRoleRegistry.team_copy(self)
                cmd = self.hook(team)
                shell = team / "src" / "surgical_team" / "guard" / "shellcheck.py"
                if breakage == "syntax":
                    shell.write_text(shell.read_text() + "\ndef (:\n")
                elif breakage == "import":
                    shell.write_text("import no_such_module_xyz\n" + shell.read_text())
                elif breakage == "missing":
                    (team / "bin" / "st").unlink()
                else:
                    (team / "bin" / "st").chmod(0o644)
                r = self.run_hook(cmd, "read", {"operations": [
                    {"mode": "Line", "path": str(self.repo / "README.md")}]})
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("BLOCKED", r.stderr)
                shutil.rmtree(team)


class TestCursorInstall(StTestCase):
    """st install --host cursor: specialist subagent files plus the global guard hook."""

    def install(self, team=None, hooks=None):
        dest, hooks = self.tmp / "cursor" / "agents", hooks or self.tmp / "cursor" / "hooks.json"
        st = team / "bin" / "st" if team else ST
        r = subprocess.run([str(st), "install", "--host", "cursor", "--dir", str(dest),
                            "--hooks", str(hooks)], env=self.env, capture_output=True, text=True)
        return r, dest, hooks

    def test_writes_a_subagent_per_specialist_and_none_for_the_copilot(self):
        r, dest, _ = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((dest / "st-copilot.md").exists())
        text = (dest / "st-tester.md").read_text()
        front = text.split("---\n")[1]
        self.assertIn("name: st-tester\n", front)
        self.assertIn("model: inherit\n", front)
        description = front.split("description: ", 1)[1].splitlines()[0]
        self.assertIn("Surgical team only", json.loads(description))
        for marker in ("You are the surgical team's tester", "# Skill: surgical-team-protocol",
                       "# Skill: tester", "authority-levels.md"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_writes_the_st_command_that_starts_a_team_session(self):
        r, _dest, hooks = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        command = Path(self.env["ST_CURSOR_DIR"]) / "commands" / "st.md"
        text = command.read_text()
        for marker in ("you are st-copilot", "You are the surgical team's copilot",
                       "# Skill: copilot", "status`, then scrub in",
                       "supported and verified on the Cursor Agent CLI only",
                       "Do not run this team session in the Cursor IDE"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertIn('agent "/st"', r.stdout)
        self.assertIn("Cursor Agent CLI only", r.stdout)
        events = json.loads(hooks.read_text())["hooks"]
        self.assertTrue(any("guard --host cursor" in e["command"]
                            for e in events["beforeSubmitPrompt"]))
        self.assertNotIn("failClosed", events["beforeSubmitPrompt"][0])
        custom = self.tmp / "project-commands"
        r = subprocess.run([str(ST), "install", "--host", "cursor", "--dir", str(self.tmp / "a"),
                            "--hooks", str(hooks), "--commands", str(custom)],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((custom / "st.md").is_file())

    def test_hooks_merge_keeps_other_hooks_and_is_idempotent(self):
        hooks = self.tmp / "cursor" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        other_hooks = [{"command": "fmt.sh"}, "opaque-entry", 17, None]
        hooks.write_text(json.dumps({"version": 1, "hooks": {
            "afterFileEdit": other_hooks, "preToolUse": [{"command": "audit.sh"}]}}))
        self.install(hooks=hooks)
        first = hooks.read_text()
        self.install(hooks=hooks)
        self.assertEqual(hooks.read_text(), first)
        doc = json.loads(first)["hooks"]
        self.assertEqual(doc["afterFileEdit"], other_hooks)
        self.assertEqual(doc["preToolUse"][0], {"command": "audit.sh"})
        guard = doc["preToolUse"][1]
        self.assertTrue(guard["command"].endswith("st guard --host cursor"))
        self.assertTrue(guard["failClosed"])
        self.assertEqual(doc["sessionStart"][0]["command"], guard["command"])

    def test_refuses_to_rewrite_a_hooks_event_that_is_not_a_list(self):
        hooks = self.tmp / "cursor" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        original = b'{"version": 1, "hooks": {"preToolUse": {"bad": 1}}}\n'
        hooks.write_bytes(original)
        r, dest, _ = self.install(hooks=hooks)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("`preToolUse`", r.stderr)
        self.assertIn("fix it by hand first", r.stderr)
        self.assertEqual(hooks.read_bytes(), original)
        self.assertFalse(dest.exists())

    def test_refuses_to_rewrite_a_broken_hooks_file(self):
        hooks = self.tmp / "cursor" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_text("{not json")
        r, dest, _ = self.install(hooks=hooks)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not valid JSON", r.stderr)
        self.assertEqual(hooks.read_text(), "{not json")
        self.assertFalse(dest.exists())

    def test_a_new_role_skill_gets_a_subagent(self):
        team = TestRoleRegistry.team_copy(self)
        TestRoleRegistry.add_skill(self, team, "perf-reviewer")
        r, dest, _ = self.install(team)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("independent reviewer", (dest / "st-perf-reviewer.md").read_text())

    def test_a_broken_guard_blocks(self):
        team = TestRoleRegistry.team_copy(self)
        _, _, hooks = self.install(team)
        cmd = json.loads(hooks.read_text())["hooks"]["preToolUse"][0]["command"]
        shell = team / "src" / "surgical_team" / "guard" / "shellcheck.py"
        shell.write_text("import no_such_module_xyz\n" + shell.read_text())
        ev = {"hook_event_name": "preToolUse", "conversation_id": "c",
              "workspace_roots": [str(self.repo)], "tool_name": "Read",
              "tool_input": {"file_path": str(self.repo / "README.md")}}
        r = subprocess.run(["sh", "-c", cmd], input=json.dumps(ev), env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("BLOCKED", r.stderr)


if __name__ == "__main__":
    unittest.main()
