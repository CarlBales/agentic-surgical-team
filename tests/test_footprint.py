"""st unit tests: the team's footprint around a project, and removing it (goal 3)."""
import json
import unittest

from base import StTestCase


class TestFootprint(StTestCase):
    def finish(self, verdict="accept", commit=True, dirty=False, **spec):
        """A dispatched, reported order; work committed and/or left uncommitted."""
        wo, ws = self.dispatched(**spec)
        if commit:
            (ws / "work.txt").write_text("work\n")
            self.git("add", "work.txt", cwd=ws)
            self.git("commit", "-qm", "work", cwd=ws)
        if dirty:
            (ws / "draft.txt").write_text("uncommitted\n")
        self.report(wo)
        out = self.st(verdict, wo, *(["-m", "no"] if verdict == "reject" else []))
        return wo, ws, out

    def branches(self):
        return self.git("for-each-ref", "--format=%(refname:short)", "refs/heads/st/").split()

    def test_a_verdict_removes_a_clean_worktree_and_keeps_its_branch(self):
        wo, ws, out = self.finish()
        self.assertFalse(ws.exists())
        self.assertIn("removed", out)
        self.assertEqual(len(self.branches()), 1)
        self.assertFalse(ws.parent.exists(), "the empty ../proj.st was left behind")

    def test_a_verdict_keeps_a_worktree_with_uncommitted_work(self):
        # At L1 the agent cannot commit: the uncommitted files are the work.
        wo, ws, out = self.finish(commit=False, dirty=True)
        self.assertTrue((ws / "draft.txt").exists())
        self.assertIn("uncommitted changes", out)

    def test_cancel_releases_the_workspace(self):
        wo, ws = self.dispatched()
        self.st("cancel", wo)
        self.assertFalse(ws.exists())

    def test_prune_deletes_branches_only_when_nothing_is_lost(self):
        rejected, _, _ = self.finish("reject")
        accepted, _, _ = self.finish(title="Second order", paths=["b/"])
        names = self.branches()
        self.assertEqual(len(names), 2)
        dry = self.st("prune", "--dry-run")
        self.assertIn("would delete branch", dry)
        self.assertEqual(self.branches(), names)

        out = self.st("prune")
        left = self.branches()
        self.assertTrue(all(accepted in name for name in left), left)
        self.assertIn("accepted but not merged", out)

        self.git("merge", "-q", "--no-edit", left[0])
        self.st("prune")
        self.assertEqual(self.branches(), [])

    def test_prune_removes_a_dirty_closed_worktree_only_with_force(self):
        wo, ws, _ = self.finish(commit=False, dirty=True)
        self.assertIn("keep", self.st("prune"))
        self.assertTrue(ws.exists())
        self.st("prune", "--force")
        self.assertFalse(ws.exists())
        self.assertEqual(self.branches(), [])  # accepted, and no commits beyond main

    def test_open_orders_are_never_pruned(self):
        wo, ws = self.dispatched()
        self.assertEqual(self.st("prune"), "nothing to prune")
        self.assertTrue(ws.exists())

    def test_prune_requires_signed_evidence_for_forged_terminal_states(self):
        forged = []
        for index, terminal in enumerate(("rejected", "cancelled")):
            wo, ws = self.dispatched(
                title=f"Forged {terminal} order", paths=[f"forged-{index}/"]
            )
            order = self.order(wo)
            order["state"] = terminal
            self.write_order(wo, order)
            forged.append((terminal, ws))
        branches = self.branches()

        out = self.st("prune")

        self.assertEqual(self.branches(), branches)
        for terminal, workspace in forged:
            with self.subTest(terminal=terminal):
                self.assertTrue(workspace.exists())
        self.assertIn("no matching surgeon-signed verdict verifies", out)
        self.assertIn("surgeon-signed cancellation does not verify", out)

    def test_agents_cannot_prune_or_uninstall(self):
        wo, ws = self.dispatched()
        for command in ("st prune", "st prune --force", "st uninstall"):
            with self.subTest(command=command):
                self.assertBlocked("tester", "shell", {"command": command}, cwd=ws)
                self.assertBlocked("copilot", "shell", {"command": command})

    def test_doctor_reports_the_footprint(self):
        self.finish(commit=False, dirty=True)
        out = self.run_st("doctor", "--quick").stdout
        self.assertIn("footprint", out)
        self.assertIn("1 closed order(s) still have a workspace", out)


class TestTamperedWorktreeMetadata(StTestCase):
    TAMPERED = "workspace git metadata was tampered with"

    def assert_refused_without_execution(self, result, marker, *, succeeds=False):
        self.assertFalse(marker.exists(), "workspace Git config executed on the host")
        self.assertEqual(result.returncode, 0 if succeeds else 1, result.stdout + result.stderr)
        self.assertIn(self.TAMPERED, result.stdout + result.stderr)

    def test_cancel_refuses_to_release_through_tampered_metadata(self):
        wo, ws = self.dispatched()
        marker = self.tamper_worktree_git(ws)

        result = self.run_st("cancel", wo)

        # Cancellation remains recorded even when safe cleanup is refused.
        self.assert_refused_without_execution(result, marker, succeeds=True)
        self.assertEqual(self.order(wo)["state"], "cancelled")
        self.assertTrue(ws.exists())

    def test_verdicts_refuse_to_release_through_tampered_metadata(self):
        for index, verdict in enumerate(("accept", "reject")):
            with self.subTest(verdict=verdict):
                wo, ws = self.dispatched(title=f"tampered verdict {index}")
                self.report(wo)
                marker = self.tamper_worktree_git(ws)

                result = self.run_st(verdict, wo)

                self.assert_refused_without_execution(result, marker, succeeds=True)
                self.assertEqual(
                    self.order(wo)["state"],
                    "accepted" if verdict == "accept" else "rejected",
                )
                self.assertTrue(ws.exists())

    def test_prune_refuses_tampered_metadata_even_with_force(self):
        wo, ws = self.dispatched()
        draft = ws / "draft.txt"
        draft.write_text("keep before tampering\n")
        self.report(wo)
        self.st("reject", wo, "-m", "fixture")
        draft.unlink()
        marker = self.tamper_worktree_git(ws)

        for force in (False, True):
            with self.subTest(force=force):
                result = self.run_st("prune", *(["--force"] if force else []))
                self.assert_refused_without_execution(result, marker)
                self.assertTrue(ws.exists())
                marker.unlink(missing_ok=True)


class TestUninstall(StTestCase):
    def test_uninstall_removes_only_what_install_wrote(self):
        cursor = self.tmp / "cursor-home"
        cursor.mkdir(parents=True, exist_ok=True)
        (cursor / "hooks.json").write_text(json.dumps(
            {"version": 1, "hooks": {"preToolUse": [{"command": "audit.sh"}]}}))
        kiro = self.tmp / "kiro"
        self.st("install", "--host", "cursor")
        self.st("install", "--dir", str(kiro))
        (cursor / "agents" / "mine.md").write_text("not ours\n")

        self.st("uninstall", "--host", "cursor")
        self.assertEqual(sorted(p.name for p in (cursor / "agents").iterdir()), ["mine.md"])
        self.assertFalse((cursor / "commands" / "st.md").exists())
        hooks = json.loads((cursor / "hooks.json").read_text())["hooks"]
        self.assertEqual(hooks, {"preToolUse": [{"command": "audit.sh"}]})
        self.assertTrue(any(kiro.iterdir()), "uninstall --host cursor touched Kiro")

        self.st("uninstall", "--host", "kiro", "--dir", str(kiro))
        self.assertEqual(list(kiro.iterdir()), [])
        self.assertTrue((self.repo / ".surgical-team" / "orders").is_dir(), "ledger touched")
        self.assertEqual(self.st("uninstall", "--host", "cursor"), (
            "nothing installed\nledgers are untouched; to drop the team from a project: "
            "st prune, then git rm -r .surgical-team"))


if __name__ == "__main__":
    unittest.main()
