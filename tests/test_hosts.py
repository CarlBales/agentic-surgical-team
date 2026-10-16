"""st unit tests: host adapters (X-1) and the guard core they feed."""
import io
import json
import os
import re
import subprocess
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

import support  # noqa: F401
from base import ST, StTestCase
from support import run_st
from surgical_team.guard import core, cursor, sessions
from surgical_team.guard.hosts import DEFAULT_HOST, HOSTS, CursorHost, KiroHost, ToolEvent
from surgical_team.tools import normalize_tool


class TestHosts(unittest.TestCase):
    def test_kiro_parses_its_event_shape(self):
        ev = KiroHost.parse('{"hook_event_name": "preToolUse", "cwd": "/w", '
                            '"tool_name": "fs_write", "tool_input": {"path": "x"}}')
        self.assertEqual((ev.tool_name, ev.cwd, ev.tool_input), ("fs_write", "/w", {"path": "x"}))

    def test_kiro_tolerates_empty_and_partial_events(self):
        for text in ("", "{}", '{"tool_name": "read"}'):
            with self.subTest(text=text):
                ev = KiroHost.parse(text)
                self.assertIsInstance(ev, ToolEvent)
                self.assertIsInstance(ev.tool_input, dict)

    def test_kiro_exit_codes(self):
        self.assertEqual((KiroHost.allow_exit, KiroHost.block_exit), (0, 2))
        self.assertIn("BLOCKED", KiroHost.block_message("why"))
        self.assertEqual(KiroHost.respond(None).exit, 0)
        blocked = KiroHost.respond("why")
        self.assertEqual((blocked.exit, blocked.stdout), (2, ""))
        self.assertIn("BLOCKED. why", blocked.stderr)

    def test_default_host_is_registered(self):
        self.assertIn(DEFAULT_HOST, HOSTS)
        self.assertIn("cursor", HOSTS)

    def test_core_takes_a_normalized_event_regardless_of_host(self):
        # The core reasons about a ToolEvent, not a Kiro payload.
        why = core.guard_decide("tester", ToolEvent("write", {"path": "/etc/x"}, "/tmp"))
        self.assertIsNotNone(why)
        why = core.guard_decide("tester", ToolEvent("web_search", {"query": "x"}, "/tmp"))
        self.assertIsNone(why)


class TestCursorTranslation(unittest.TestCase):
    """Payload shapes as Cursor's preToolUse hook reports them (recorded live)."""

    def parse(self, name, inp, **event):
        return CursorHost.parse({"tool_name": name, "tool_input": inp, **event})

    def test_file_tools(self):
        self.assertEqual(self.parse("Read", {"file_path": "/p/a"}).tool_input, {"file_path": "/p/a"})
        for name in ("Write", "Delete"):
            with self.subTest(name=name):
                ev = self.parse(name, {"file_path": "/p/a", "content": "x"})
                self.assertEqual((ev.tool_name, ev.tool_input), ("write", {"file_path": "/p/a"}))
        ev = self.parse("EditNotebook", {"target_notebook": "/p/n.ipynb"})
        self.assertEqual((ev.tool_name, ev.tool_input), ("write", {"file_path": "/p/n.ipynb"}))
        self.assertEqual(self.parse("Write", {}).tool_input, {})  # the core refuses it

    def test_shell_and_its_working_directory(self):
        ev = self.parse("Shell", {"command": "ls", "cwd": "/w", "timeout": 3}, cwd="/top")
        self.assertEqual((ev.tool_name, ev.tool_input, ev.cwd),
                         ("shell", {"command": "ls", "working_dir": "/w"}, "/top"))
        ev = self.parse("Shell", {"command": "pwd", "cwd": ""}, workspace_roots=["/root"])
        self.assertEqual((ev.tool_input, ev.cwd), ({"command": "pwd"}, "/root"))

    def test_search_tools(self):
        ev = self.parse("Grep", {"pattern": "", "file_path": "/p", "glob": "**/*.md",
                                 "output_mode": "files_with_matches"})
        self.assertEqual((ev.tool_name, ev.tool_input), ("glob", {"path": "/p", "pattern": "**/*.md"}))
        ev = self.parse("Grep", {"pattern": "x", "path": "/p", "glob": "*.py"})
        self.assertEqual((ev.tool_name, ev.tool_input),
                         ("grep", {"pattern": "x", "path": "/p", "include": "*.py"}))
        ev = self.parse("Glob", {"glob_pattern": "*.md", "target_directory": "/p"})
        self.assertEqual((ev.tool_name, ev.tool_input), ("glob", {"path": "/p", "pattern": "*.md"}))
    def test_semantic_search_without_targets_uses_the_cwd(self):
        ev = self.parse("SemanticSearch", {"query": "q", "target_directories": []})
        self.assertEqual((ev.tool_name, ev.tool_input), ("grep", {}))

    def test_semantic_search_with_one_target_keeps_its_path(self):
        ev = self.parse("SemanticSearch", {"query": "q", "target_directories": ["/p"]})
        self.assertEqual((ev.tool_name, ev.tool_input), ("grep", {"path": "/p"}))

    def test_semantic_search_with_multiple_targets_keeps_every_path(self):
        ev = self.parse("SemanticSearch", {"query": "q", "target_directories": ["/p", "/q"]})
        self.assertEqual(
            (ev.tool_name, ev.tool_input),
            ("grep", {"operations": [{"path": "/p"}, {"path": "/q"}]}),
        )

    def test_task_is_a_subagent_never_the_todo_tool(self):
        # The shared alias table reads a bare "task" as Kiro's todo tool,
        # which the core does not check at all.
        self.assertEqual(normalize_tool("task"), "todo_list")
        ev = self.parse("Task", {"subagent_type": "st-tester", "prompt": "WO-x", "description": "d"})
        self.assertEqual(ev.tool_name, "subagent")
        self.assertEqual(ev.tool_input["stages"],
                         [{"name": "d", "role": "st-tester", "prompt_template": "WO-x"}])

    def test_unknown_and_mcp_tools_pass_through_raw(self):
        ev = self.parse("MCP:tracker_update", '{"id": 1}')
        self.assertEqual((ev.tool_name, ev.tool_input), ("MCP:tracker_update", {"id": 1}))
        self.assertIsNotNone(core.guard_decide("tester", ev))

    def test_answers_are_permission_json(self):
        self.assertEqual(json.loads(CursorHost.respond(None).stdout), {"permission": "allow"})
        denied = CursorHost.respond("why")
        answer = json.loads(denied.stdout)
        self.assertEqual((denied.exit, answer["permission"]), (0, "deny"))
        self.assertIn("BLOCKED. why", answer["agent_message"])


class TestCursorSessions(StTestCase):
    """Role binding for Cursor's global hook: sessionStart, Task, transcript claim."""

    def setUp(self):
        super().setUp()
        self.cursor = self.tmp / "cursor"
        self.env["ST_CURSOR_DIR"] = str(self.cursor)
        self.env["ST_CURSOR_TRANSCRIPT_WAIT_S"] = "0"  # tests that need the wait set it
        self.env.pop("CURSOR_PROJECT_DIR", None)

    def hook(self, event, roots=None):
        ev = {"workspace_roots": [str(roots or self.repo)], **event}
        r = run_st(["guard", "--host", "cursor"], cwd=self.repo, env=self.env,
                   stdin=json.dumps(ev))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def tool(self, conversation, name, inp, roots=None, **extra):
        return self.hook({"hook_event_name": "preToolUse", "conversation_id": conversation,
                          "tool_name": name, "tool_input": inp, **extra}, roots)

    def start(self, conversation="top", roots=None, prompt="/st"):
        """A new top-level chat; by default the surgeon opened it with /st."""
        answer = self.hook({"hook_event_name": "sessionStart", "conversation_id": conversation,
                            "session_id": conversation}, roots)
        if prompt is not None:
            self.transcript(conversation, prompt, command=prompt.startswith("/st"),
                            project=self.slug(roots) if roots else None)
        return answer

    def slug(self, root):
        return re.sub(r"[^A-Za-z0-9]+", "-", str(root)).strip("-")

    def transcript(self, conversation, prompt, project=None, command=False):
        """A transcript opening as Cursor writes it; `command` adds the expanded /st."""
        slug = project or self.slug(self.repo)
        path = (self.cursor / "projects" / slug / "agent-transcripts" / conversation
                / f"{conversation}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f"<timestamp>now</timestamp>\n<user_query>\n{prompt}\n</user_query>"
        if command:
            text = ("<cursor_commands>\n\n--- Cursor Command: st ---\nYou are st-copilot.\n"
                    "--- End Command ---\n</cursor_commands>\n" + text)
        path.write_text(json.dumps(
            {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")

    def assertAllow(self, answer):
        self.assertEqual(answer.get("permission"), "allow", answer.get("agent_message"))

    def assertDeny(self, answer, contains=None):
        self.assertEqual(answer.get("permission"), "deny", answer)
        if contains:
            self.assertIn(contains, answer["agent_message"])

    def test_outside_a_ledger_project_the_guard_stays_out(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.assertEqual(self.start("plain", elsewhere), {})
        self.assertAllow(self.tool("plain", "Write", {"file_path": str(elsewhere / "x")},
                                   roots=elsewhere))

    def test_an_unbound_conversation_in_a_ledger_project_is_refused(self):
        self.assertDeny(self.tool("stranger", "Read", {"file_path": str(self.repo / "README.md")}),
                        "not bound to a team role")
        self.assertDeny(self.tool("../x", "Read", {"file_path": "README.md"}), "conversation_id")

    def test_a_team_file_target_supplies_missing_event_context(self):
        answer = self.tool(
            "stranger-no-context",
            "Write",
            {"file_path": str(self.repo / "README.md")},
            workspace_roots=[],
        )
        self.assertDeny(answer, "not bound to a team role")

    def test_a_team_file_target_overrides_a_window_rooted_above_the_project(self):
        answer = self.tool(
            "stranger-parent-window",
            "Write",
            {"file_path": str(self.repo / "README.md")},
            roots=self.repo.parent,
        )
        self.assertDeny(answer, "not bound to a team role")

    def test_each_tool_target_shape_can_supply_ledger_context(self):
        cases = [
            ("Write", {"file_path": str(self.repo / "new" / "nested" / "file.txt")}),
            ("Grep", {"pattern": "needle", "path": str(self.repo)}),
            ("Shell", {"command": "pwd", "cwd": str(self.repo)}),
        ]
        for index, (name, inp) in enumerate(cases):
            with self.subTest(name=name):
                answer = self.tool(
                    f"stranger-target-{index}", name, inp, workspace_roots=[]
                )
                self.assertDeny(answer, "not bound to a team role")

    def test_arbitrary_non_team_target_paths_do_not_crash_ledger_lookup(self):
        for index, target in enumerate(("bad\0path", ["not", "a", "path"])):
            with self.subTest(target=target):
                self.assertAllow(self.tool(
                    f"plain-bad-target-{index}",
                    "Write",
                    {"file_path": target},
                    workspace_roots=[],
                ))

    def test_a_pending_dispatch_without_ledger_context_fails_closed_until_expiry(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))

        answer = self.tool(
            "orphan-subagent",
            "Write",
            {"file_path": str(elsewhere / "x.txt")},
            workspace_roots=[],
        )
        self.assertDeny(answer, "pending team dispatch")
        self.assertIn("ledger context", answer["agent_message"])

        # An ordinary chat elsewhere has its own transcript, which matches no
        # dispatch: it is not held back by the pending one.
        self.transcript("plain-elsewhere", "summarize my notes", project="other-project")
        self.assertAllow(self.tool(
            "plain-elsewhere", "Read", {"file_path": str(elsewhere / "notes.md")},
            workspace_roots=[],
        ))
        self.assertFalse((self.cfg / "cursor" / "bindings" / "plain-elsewhere.json").exists())

        pending = next((self.cfg / "cursor" / "pending").glob("*.json"))
        record = json.loads(pending.read_text())
        pending.write_text(json.dumps({**record, "at": 0}))
        self.assertAllow(self.tool(
            "plain-after-expiry",
            "Write",
            {"file_path": str(elsewhere / "y.txt")},
            workspace_roots=[],
        ))

    def test_a_first_call_waits_for_a_transcript_written_late(self):
        """Seen live under load: the subagent's first tool call reached the hook
        before Cursor wrote its transcript, and was refused as unbound."""
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}))
        self.env["ST_CURSOR_TRANSCRIPT_WAIT_S"] = "5"
        writer = threading.Timer(0.5, self.transcript, args=("late-subagent", briefing))
        writer.start()
        try:
            self.assertAllow(self.tool(
                "late-subagent", "Shell", {"command": "ls", "cwd": str(ws)}))
        finally:
            writer.cancel()
        binding = json.loads(
            (self.cfg / "cursor" / "bindings" / "late-subagent.json").read_text())
        self.assertEqual(binding["role"], "tester")

    def test_a_contextless_team_subagent_still_binds_from_its_transcript(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}))
        self.transcript("contextless-subagent", briefing)
        self.assertDeny(self.tool(
            "contextless-subagent", "Write", {"file_path": str(elsewhere / "x.txt")},
            workspace_roots=[],
        ), "outside any workspace")
        binding = json.loads(
            (self.cfg / "cursor" / "bindings" / "contextless-subagent.json").read_text())
        self.assertEqual((binding["role"], binding["wo"]), ("tester", wo))

    def test_an_expired_pending_dispatch_cannot_be_claimed_and_is_removed(self):
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        pending = next((self.cfg / "cursor" / "pending").glob("*.json"))
        record = json.loads(pending.read_text())
        pending.write_text(json.dumps({**record, "at": 0}))
        self.transcript("expired-subagent", briefing)

        self.assertDeny(self.tool(
            "expired-subagent", "Write", {"file_path": str(ws / "expired.txt")}
        ), "not bound to a team role")
        self.assertFalse(pending.exists())
        self.assertFalse(
            (self.cfg / "cursor" / "bindings" / "expired-subagent.json").exists()
        )

    def test_session_start_prunes_stale_cursor_state(self):
        now = time.time()
        retention = sessions.STATE_RETENTION_S
        cursor_state = self.cfg / "cursor"
        stale_paths = [
            cursor_state / "claimed" / "stale-claim.json",
            cursor_state / "sessions" / "stale-session.json",
            cursor_state / "bindings" / "stale-binding.json",
        ]
        live_paths = [
            cursor_state / "claimed" / "live-claim.json",
            cursor_state / "sessions" / "live-session.json",
            cursor_state / "bindings" / "live-binding.json",
        ]
        for path in stale_paths + live_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"conversation": path.stem, "role": "tester", "at": now}))
        stale_ages = [sessions.PENDING_TTL_S + 60, retention + 60, retention + 60]
        for path, age in zip(stale_paths, stale_ages):
            os.utime(path, (now - age, now - age))

        self.start("cleanup-trigger")

        for path in stale_paths:
            with self.subTest(stale=path):
                self.assertFalse(path.exists())
        for path in live_paths:
            with self.subTest(live=path):
                self.assertTrue(path.exists())

    def test_using_a_binding_refreshes_its_retention_age(self):
        retention = sessions.STATE_RETENTION_S
        self.start()
        self.assertAllow(self.tool(
            "top", "Read", {"file_path": str(self.repo / "README.md")}
        ))
        binding = self.cfg / "cursor" / "bindings" / "top.json"
        stale = time.time() - retention - 60
        os.utime(binding, (stale, stale))

        self.assertAllow(self.tool(
            "top", "Read", {"file_path": str(self.repo / "README.md")}
        ))
        self.assertGreater(binding.stat().st_mtime, stale + retention)
        self.start("cleanup-trigger")
        self.assertTrue(binding.exists())

    def test_a_pruned_copilot_binding_rebinds_only_as_copilot(self):
        retention = sessions.STATE_RETENTION_S
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        binding = self.cfg / "cursor" / "bindings" / "top.json"
        stale = time.time() - retention - 60
        os.utime(binding, (stale, stale))
        # The opening still starts with /st but now also matches the pending briefing.
        self.transcript("top", f"/st\n{briefing}", command=True)

        self.start("cleanup-trigger")

        self.assertFalse(binding.exists())
        self.assertAllow(self.tool(
            "top", "Read", {"file_path": str(self.repo / "README.md")}
        ))
        self.assertEqual(json.loads(binding.read_text())["role"], "copilot")
        self.assertEqual(len(list((self.cfg / "cursor" / "pending").glob("*.json"))), 1)

    def test_a_pruned_specialist_binding_is_refused_not_rebound(self):
        retention = sessions.STATE_RETENTION_S
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("stale-specialist", briefing)
        self.assertAllow(self.tool(
            "stale-specialist", "Write", {"file_path": str(ws / "first.txt")}
        ))
        binding = self.cfg / "cursor" / "bindings" / "stale-specialist.json"
        claimed = next((self.cfg / "cursor" / "claimed").glob("*.json"))
        now = time.time()
        os.utime(binding, (now - retention - 60, now - retention - 60))
        os.utime(claimed, (
            now - sessions.PENDING_TTL_S - 60,
            now - sessions.PENDING_TTL_S - 60,
        ))

        self.start("cleanup-trigger")

        self.assertFalse(binding.exists())
        self.assertFalse(claimed.exists())
        self.assertDeny(self.tool(
            "stale-specialist", "Write", {"file_path": str(ws / "second.txt")}
        ), "not bound to a team role")
        self.assertFalse(binding.exists())

    def test_a_chat_opened_with_st_is_the_copilot(self):
        self.assertEqual(self.start(), {})  # nothing is injected; /st carries the persona
        self.assertAllow(self.tool("top", "Read", {"file_path": str(self.repo / "README.md")}))
        self.assertDeny(self.tool("top", "Write", {"file_path": str(self.repo / "README.md")}),
                        "outside any workspace")
        wo = self.draft()
        self.assertDeny(self.tool("top", "Shell", {"command": f"st approve {wo}", "cwd": ""}))
        # The literal query is enough when the expanded command block is absent.
        self.start("typed", prompt=None)
        self.transcript("typed", "/st scrub in")
        self.assertDeny(self.tool("typed", "Write", {"file_path": str(self.repo / "README.md")}),
                        "outside any workspace")

    def test_top_level_chats_rooted_in_an_order_workspace_are_refused(self):
        _wo, workspace = self.dispatched()
        readme = str(self.repo / "README.md")

        for conversation, prompt in (("workspace-plain", "tidy the README"),
                                     ("workspace-team", "/st")):
            with self.subTest(prompt=prompt):
                self.assertEqual(self.start(conversation, roots=workspace, prompt=prompt), {})
                # The session's original workspace context remains decisive if a
                # later event supplies only the main checkout as its window root.
                self.assertDeny(
                    self.tool(conversation, "Write", {"file_path": readme}, roots=self.repo),
                    "team workspaces are only for their order's agent",
                )
                binding = self.cfg / "cursor" / "bindings" / f"{conversation}.json"
                self.assertEqual(json.loads(binding.read_text())["role"], "refused")

        self.start("workspace-early", roots=workspace, prompt=None)
        self.assertEqual(
            self.hook({"hook_event_name": "beforeSubmitPrompt",
                       "conversation_id": "workspace-early", "prompt": "/st"}, workspace),
            {"continue": True},
        )
        self.assertDeny(
            self.tool("workspace-early", "Write", {"file_path": readme}, roots=workspace),
            "team workspaces are only for their order's agent",
        )
        early = self.cfg / "cursor" / "bindings" / "workspace-early.json"
        self.assertEqual(json.loads(early.read_text())["role"], "refused")

        gitfile = workspace / ".git"
        gitfile_text = gitfile.read_text()
        gitfile.unlink()
        try:
            self.assertEqual(
                self.start("workspace-unresolved", roots=workspace, prompt="ordinary chat"),
                {},
            )
            self.assertDeny(
                self.tool("workspace-unresolved", "Write", {"file_path": readme},
                          roots=self.repo),
                "team workspaces are only for their order's agent",
            )
            unresolved = (
                self.cfg / "cursor" / "bindings" / "workspace-unresolved.json"
            )
            self.assertEqual(json.loads(unresolved.read_text())["role"], "refused")
        finally:
            gitfile.write_text(gitfile_text)

    def test_any_other_chat_in_a_team_project_is_plain_cursor(self):
        """Goal 3: the team is opt-in per chat; a plain chat is ordinary Cursor."""
        self.assertEqual(self.start("mine", prompt="tidy the README"), {})
        readme = str(self.repo / "README.md")
        self.assertAllow(self.tool("mine", "Write", {"file_path": readme}))
        self.assertAllow(self.tool("mine", "Shell", {"command": "git commit -am x", "cwd": ""}))
        self.assertEqual(
            json.loads((self.cfg / "cursor" / "bindings" / "mine.json").read_text())["role"],
            "plain")
        # It cannot start the team behind the guard's back ...
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.assertDeny(self.tool("mine", "Task", {"subagent_type": "st-tester",
                                                   "prompt": briefing}), "team session")
        # ... but its own subagents work like any Cursor subagent.
        self.assertAllow(self.tool("mine", "Task", {"subagent_type": "explore",
                                                    "prompt": "find the README"}))
        self.transcript("mine-explore", "find the README")
        self.assertAllow(self.tool("mine-explore", "Write", {"file_path": readme}))
        self.assertDeny(self.tool("mine-explore", "Task", {"subagent_type": "st-tester",
                                                           "prompt": briefing}), "team session")

    def test_plain_chats_cannot_disguise_team_agent_names(self):
        self.start("variant-plain", prompt="ordinary chat")
        for agent in ("ST-tester", " st-tester"):
            with self.subTest(agent=agent):
                self.assertDeny(
                    self.tool(
                        "variant-plain",
                        "Task",
                        {"subagent_type": agent, "prompt": "not a team dispatch"},
                    ),
                    "team session",
                )

    def test_copilot_normalizes_team_agent_names_before_validation(self):
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start("variant-copilot")
        for agent in ("ST-tester", " st-tester"):
            with self.subTest(agent=agent):
                self.assertAllow(
                    self.tool(
                        "variant-copilot",
                        "Task",
                        {"subagent_type": agent, "prompt": briefing},
                    )
                )
        pending = [
            json.loads(path.read_text())
            for path in (self.cfg / "cursor" / "pending").glob("*.json")
        ]
        self.assertEqual([record["role"] for record in pending], ["tester", "tester"])

    def test_a_typed_st_prompt_binds_the_copilot_before_any_tool_call(self):
        answer = self.hook({"hook_event_name": "beforeSubmitPrompt",
                            "conversation_id": "early", "prompt": "/st"})
        self.assertEqual(answer, {"continue": True})
        # No transcript at all: the early binding decides.
        self.assertDeny(self.tool("early", "Write", {"file_path": str(self.repo / "README.md")}),
                        "outside any workspace")
        # A plain prompt binds nothing and never blocks; a later /st upgrades the chat.
        self.start("later", prompt="hello")
        self.assertEqual(self.hook({"hook_event_name": "beforeSubmitPrompt",
                                    "conversation_id": "later", "prompt": "hello"}),
                         {"continue": True})
        self.assertAllow(self.tool("later", "Write", {"file_path": str(self.repo / "README.md")}))
        self.hook({"hook_event_name": "beforeSubmitPrompt", "conversation_id": "later",
                   "prompt": "/st"})
        self.assertDeny(self.tool("later", "Write", {"file_path": str(self.repo / "README.md")}),
                        "outside any workspace")

    def test_a_top_level_chat_with_no_readable_transcript_is_refused(self):
        self.start("unreadable", prompt=None)
        self.assertDeny(self.tool("unreadable", "Read",
                                  {"file_path": str(self.repo / "README.md")}),
                        "cannot tell whether")
        self.assertFalse((self.cfg / "cursor" / "bindings" / "unreadable.json").exists())

    def test_background_session_in_a_team_project_stays_unbound(self):
        answer = self.hook({
            "hook_event_name": "sessionStart",
            "conversation_id": "background",
            "session_id": "background",
            "is_background_agent": True,
        })
        context = answer["additional_context"]
        self.assertIn("never run Cursor cloud/background agents", context)
        self.assertIn("supported and verified on the Cursor Agent CLI only", context)
        self.assertIn("Do not run team sessions in the Cursor IDE", context)
        self.assertIn("not bound as the copilot", context)
        self.assertFalse((self.cfg / "cursor" / "sessions" / "background.json").exists())
        self.assertDeny(
            self.tool("background", "Read", {"file_path": str(self.repo / "README.md")}),
            "not bound to a team role",
        )

    def test_a_dispatch_binds_exactly_one_specialist(self):
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertDeny(self.tool("top", "Task", {"subagent_type": "explore", "prompt": "look"}),
                        "guarded st-<role> agents")
        self.assertDeny(self.tool("top", "Task", {"subagent_type": "st-editor", "prompt": briefing}),
                        "exactly one order")
        self.assertAllow(self.tool("top", "Task", {"subagent_type": "st-tester", "prompt": briefing}))

        self.transcript("sub1", briefing)
        self.assertAllow(self.tool("sub1", "Write", {"file_path": str(ws / "tests" / "t.py")}))
        self.assertEqual(json.loads((self.cfg / "cursor" / "bindings" / "sub1.json").read_text())
                         ["role"], "tester")
        self.assertDeny(self.tool("sub1", "Write", {"file_path": str(self.repo / "README.md")}))
        self.assertDeny(self.tool("sub1", "Task", {"subagent_type": "st-tester", "prompt": briefing}),
                        "only the copilot")

        # The dispatch is spent: a second conversation opening with it gets nothing.
        self.transcript("sub2", briefing, project="some-other-project")
        self.assertDeny(self.tool("sub2", "Write", {"file_path": str(ws / "x")}),
                        "not bound to a team role")

    def test_a_claim_finds_transcripts_outside_the_project_slug(self):
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool("top", "Task", {"subagent_type": "st-tester", "prompt": briefing}))
        self.transcript("sub3", briefing, project="renamed-project")
        self.assertAllow(self.tool("sub3", "Write", {"file_path": str(ws / "y")}))

    def test_overlapping_prompts_bind_each_specialist_to_its_own_dispatch(self):
        tester, tester_ws = self.dispatched()
        reviewer, reviewer_ws = self.dispatched(role="reviewer")
        tester_prompt = self.st("brief", tester)
        reviewer_prompt = f"{tester_prompt}\n\n{self.st('brief', reviewer)}"
        pending = self.cfg / "cursor" / "pending"
        pending.mkdir(parents=True)
        records = {
            "000-tester.json": {"prompt": tester_prompt, "role": "tester", "wo": tester,
                                "parent": "top", "at": 9999999999},
            "999-reviewer.json": {"prompt": reviewer_prompt, "role": "reviewer", "wo": reviewer,
                                  "parent": "top", "at": 9999999999},
        }
        for name, record in records.items():
            (pending / name).write_text(json.dumps(record))

        self.transcript("reviewer-sub", reviewer_prompt)
        self.assertAllow(self.tool("reviewer-sub", "Write",
                                   {"file_path": str(reviewer_ws / "review.md")}))
        reviewer_binding = self.cfg / "cursor" / "bindings" / "reviewer-sub.json"
        self.assertEqual(json.loads(reviewer_binding.read_text())["role"], "reviewer")

        self.transcript("tester-sub", tester_prompt)
        self.assertAllow(self.tool("tester-sub", "Write",
                                   {"file_path": str(tester_ws / "tests" / "t.py")}))
        tester_binding = self.cfg / "cursor" / "bindings" / "tester-sub.json"
        self.assertEqual(json.loads(tester_binding.read_text())["role"], "tester")

    def test_specific_prompt_wins_regardless_of_pending_file_order(self):
        tester, _ = self.dispatched()
        reviewer, _ = self.dispatched(role="reviewer")
        tester_prompt = f"briefing for {tester}"
        reviewer_prompt = f"{tester_prompt}\nreview briefing for {reviewer}"
        pending = self.cfg / "cursor" / "pending"
        pending.mkdir(parents=True)
        arrangements = [
            ("000-short.json", "999-long.json"),
            ("999-short.json", "000-long.json"),
        ]
        for index, (short_name, long_name) in enumerate(arrangements):
            with self.subTest(short_name=short_name):
                for path in pending.glob("*.json"):
                    path.unlink()
                records = [
                    (short_name, tester_prompt, "tester", tester),
                    (long_name, reviewer_prompt, "reviewer", reviewer),
                ]
                for name, prompt, role, wo in records:
                    (pending / f"{index}-{name}").write_text(json.dumps(
                        {"prompt": prompt, "role": role, "wo": wo,
                         "parent": "top", "at": 9999999999}
                    ))
                conversation = f"specific-{index}"
                self.transcript(conversation, reviewer_prompt)
                self.assertAllow(self.tool(
                    conversation, "Read", {"file_path": str(self.repo / "README.md")}
                ))
                binding = self.cfg / "cursor" / "bindings" / f"{conversation}.json"
                self.assertEqual(json.loads(binding.read_text())["role"], "reviewer")

    def test_distinct_equal_length_pending_prompt_matches_are_refused_as_ambiguous(self):
        tester, _ = self.dispatched()
        first, second = f"alpha briefing {tester}", f"omega briefing {tester}"
        pending = self.cfg / "cursor" / "pending"
        pending.mkdir(parents=True)
        for name, prompt in (("first", first), ("second", second)):
            (pending / f"{name}.json").write_text(json.dumps(
                {"prompt": prompt, "role": "tester", "wo": tester, "parent": "top",
                 "at": 9999999999}))
        self.transcript("ambiguous-sub", f"{first}\n{second}")

        self.assertDeny(self.tool(
            "ambiguous-sub", "Read", {"file_path": str(self.repo / "README.md")}
        ), "not bound to a team role")
        self.assertFalse((self.cfg / "cursor" / "bindings" / "ambiguous-sub.json").exists())

    def test_a_relaunched_briefing_binds_the_oldest_identical_dispatch(self):
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        for _ in range(2):
            self.assertAllow(self.tool(
                "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}))
        records = sorted((self.cfg / "cursor" / "pending").glob("*.json"),
                         key=lambda path: json.loads(path.read_text())["at"])
        self.assertEqual(len(records), 2)

        self.transcript("relaunched", briefing)
        self.assertAllow(self.tool("relaunched", "Write", {"file_path": str(ws / "t.py")}))
        binding = json.loads((self.cfg / "cursor" / "bindings" / "relaunched.json").read_text())
        self.assertEqual((binding["role"], binding["dispatch"]), ("tester", records[0].stem))
        self.assertEqual(list((self.cfg / "cursor" / "pending").glob("*.json")), [records[1]])

    def test_cursor_grep_glob_cannot_bypass_a_blind_directory(self):
        hidden = self.repo / "src" / "hidden.py"
        public = self.repo / "public" / "interface.py"
        hidden.parent.mkdir()
        public.parent.mkdir()
        hidden.write_text("needle = 'withheld'\n")
        public.write_text("needle = 'public'\n")
        self.git("add", "src/hidden.py", "public/interface.py")
        self.git("commit", "-q", "-m", "search fixture")

        wo, ws = self.dispatched(blind=["src"])
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("blind-sub", briefing)

        for directory in (self.repo, ws):
            with self.subTest(blind_parent=directory):
                self.assertDeny(self.tool(
                    "blind-sub", "Grep",
                    {"pattern": "needle", "path": str(directory), "glob": "**/*.py"},
                ), "search a narrower path")
        for directory in (self.repo / "public", ws / "public"):
            with self.subTest(non_blind=directory):
                self.assertAllow(self.tool(
                    "blind-sub", "Grep",
                    {"pattern": "needle", "path": str(directory), "glob": "**/*.py"},
                ))

    def test_cursor_semantic_search_checks_every_target_directory(self):
        blind = self.repo / "src"
        other1 = self.repo / "public"
        other2 = self.repo / "other"
        for directory in (blind, other1, other2):
            directory.mkdir()

        wo, _ws = self.dispatched(blind=["src"])
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("semantic-sub", briefing)

        self.assertAllow(self.tool(
            "semantic-sub", "SemanticSearch",
            {"query": "needle", "target_directories": [str(other1), str(other2)]},
            cwd=str(other1),
        ))
        self.assertDeny(self.tool(
            "semantic-sub", "SemanticSearch",
            {"query": "needle", "target_directories": [str(blind), str(other2)]},
            cwd=str(other1),
        ), "blind order")

    def test_blind_discovery_ignores_inherited_git_dir_in_normal_layouts(self):
        hidden = self.repo / "src" / "impl.py"
        hidden.parent.mkdir()
        hidden.write_text("withheld\n")
        self.git("add", "src/impl.py")
        self.git("commit", "-q", "-m", "blind git environment fixture")
        wo, ws = self.dispatched(blind=["src"])
        briefing = self.st("brief", wo)
        self.start("git-env-top")
        self.assertAllow(self.tool(
            "git-env-top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("git-env-sub", briefing)
        self.assertAllow(self.tool(
            "git-env-sub", "Read", {"file_path": str(self.repo / "README.md")}
        ))
        attacker = self.tmp / "attacker.git"
        self.git("init", "--bare", "-q", str(attacker), cwd=self.tmp)
        self.env["GIT_DIR"] = str(attacker)

        for cwd, target in ((self.repo, hidden), (ws, ws / "src" / "impl.py")):
            with self.subTest(host="kiro", cwd=cwd):
                self.assertBlocked(
                    "tester",
                    "read",
                    {"operations": [{"mode": "Line", "path": str(target)}]},
                    cwd=cwd,
                    contains="blind order",
                )
        self.assertDeny(
            self.tool("git-env-sub", "Read", {"file_path": str(hidden)}),
            "blind order",
        )

    def test_blind_discovery_fails_closed_for_submodule_style_gitdir(self):
        hidden = self.repo / "src" / "impl.py"
        hidden.parent.mkdir()
        hidden.write_text("withheld\n")
        self.git("add", "src/impl.py")
        self.git("commit", "-q", "-m", "blind external gitdir fixture")
        wo, _ws = self.dispatched(blind=["src"])
        briefing = self.st("brief", wo)
        self.start("external-gitdir-top")
        self.assertAllow(self.tool(
            "external-gitdir-top",
            "Task",
            {"subagent_type": "st-tester", "prompt": briefing},
        ))
        self.transcript("external-gitdir-sub", briefing)
        self.assertAllow(self.tool(
            "external-gitdir-sub", "Read", {"file_path": str(self.repo / "README.md")}
        ))

        external = self.tmp / "super" / ".git" / "modules" / "proj"
        attacker = self.tmp / "attacker.git"
        self.git("init", "--bare", "-q", str(attacker), cwd=self.tmp)
        external.parent.mkdir(parents=True)
        (self.repo / ".git").rename(external)
        (self.repo / ".git").write_text(f"gitdir: {external}\n")
        self.assertEqual(self.git("rev-parse", "--show-toplevel"), str(self.repo))
        self.env["GIT_DIR"] = str(attacker)

        kiro_code, kiro_reason = self.guard(
            "tester",
            "read",
            {"operations": [{"mode": "Line", "path": str(hidden)}]},
            cwd=self.repo,
        )
        cursor_answer = self.tool(
            "external-gitdir-sub", "Read", {"file_path": str(hidden)}
        )
        self.assertEqual(kiro_code, 2, kiro_reason)
        self.assertIn("unsupported Git layout", kiro_reason)
        self.assertDeny(cursor_answer, "unsupported Git layout")

    def test_blind_targets_supply_guard_ledger_when_cwd_is_elsewhere(self):
        hidden = self.repo / "src" / "impl.py"
        public = self.repo / "public" / "interface.py"
        other = self.repo / "other" / "README.md"
        for path in (hidden, public, other):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture for {path.name}\n")
        self.git("add", "src/impl.py", "public/interface.py", "other/README.md")
        self.git("commit", "-q", "-m", "blind target fixture")
        far = self.tmp / "far"
        far.mkdir()

        non_team = self.tmp / "non-team"
        non_team.mkdir()
        self.git("init", "-q", "-b", "main", cwd=non_team)
        (non_team / "README.md").write_text("ordinary repository\n")
        self.git("add", "README.md", cwd=non_team)
        self.git("commit", "-q", "-m", "ordinary repository", cwd=non_team)

        wo, ws = self.dispatched(blind=["src"])
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("blind-target-sub", briefing)

        self.assertDeny(self.tool(
            "blind-target-sub", "Read", {"file_path": str(ws / "src" / "impl.py")},
            cwd=str(ws),
        ), "blind order")
        for target in (self.repo / "src" / "impl.py", ws / "src" / "impl.py"):
            with self.subTest(target=target):
                self.assertDeny(self.tool(
                    "blind-target-sub", "Read", {"file_path": str(target)}, cwd=str(far)
                ), "blind order")

        self.assertAllow(self.tool(
            "blind-target-sub", "Read", {"file_path": str(ws / "public" / "interface.py")},
            cwd=str(far),
        ))
        self.assertAllow(self.tool(
            "blind-target-sub", "Read", {"file_path": str(non_team / "README.md")},
            cwd=str(far),
        ))
        for hidden_target in (ws / "src" / "impl.py", ws / "src" / "nonexistent"):
            with self.subTest(semantic_target=hidden_target):
                self.assertDeny(self.tool(
                    "blind-target-sub", "SemanticSearch",
                    {"query": "needle", "target_directories": [
                        str(hidden_target), str(ws / "other"),
                    ]},
                    cwd=str(far),
                ), "blind order")

    def test_tool_targets_cannot_mix_team_ledgers(self):
        other_repo = self.tmp / "other-team"
        other_repo.mkdir()
        self.git("init", "-q", "-b", "main", cwd=other_repo)
        (other_repo / "README.md").write_text("another team\n")
        self.git("add", "README.md", cwd=other_repo)
        self.git("commit", "-q", "-m", "other team", cwd=other_repo)
        self.st("init", cwd=other_repo)
        far = self.tmp / "far"
        far.mkdir()

        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("mixed-ledger-sub", briefing)

        self.assertDeny(self.tool(
            "mixed-ledger-sub", "SemanticSearch",
            {"query": "needle", "target_directories": [str(ws), str(other_repo)]},
            cwd=str(far),
        ), "multiple team ledgers")
        self.assertDeny(self.tool(
            "mixed-ledger-sub", "Read", {"file_path": str(other_repo / "README.md")},
            cwd=str(self.repo),
        ), "differs from the event cwd")

        nested_repo = self.repo / "nested-team"
        nested_repo.mkdir()
        self.git("init", "-q", "-b", "main", cwd=nested_repo)
        (nested_repo / "README.md").write_text("nested team\n")
        self.git("add", "README.md", cwd=nested_repo)
        self.git("commit", "-q", "-m", "nested team", cwd=nested_repo)
        self.st("init", cwd=nested_repo)
        self.assertDeny(self.tool(
            "mixed-ledger-sub", "Read", {"file_path": str(nested_repo / "README.md")},
            cwd=str(self.repo),
        ), "differs from the event cwd")

    def test_st_through_a_variable_is_refused_with_how_to_retry(self):
        # Live sweep, 2026-10-15: `ST=<path>; $ST report ...` with a report that
        # names the ledger was refused and the lawyer gave up without a report.
        wo, ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.tool("top", "Task", {"subagent_type": "st-tester", "prompt": briefing})
        self.transcript("var-sub", briefing)
        body = '{"summary": "the ledger is .surgical-team"}'
        st = "/opt/x/bin/st"
        self.assertDeny(self.tool("var-sub", "Shell", {
            "command": f"ST={st}\n$ST report {wo} <<'EOF'\n{body}\nEOF", "cwd": str(ws)}),
            "by its literal path")
        self.assertAllow(self.tool("var-sub", "Shell", {
            "command": f"{st} report {wo} <<'EOF'\n{body}\nEOF", "cwd": str(ws)}))

    def test_cursor_config_is_protected_and_spills_are_not(self):
        wo, ws = self.dispatched()
        self.start()
        slug = re.sub(r"[^A-Za-z0-9]+", "-", str(self.repo)).strip("-")
        spill = self.cursor / "projects" / slug / "agent-tools" / "out.txt"
        self.assertAllow(self.tool("top", "Write", {"file_path": str(spill)}))
        self.assertDeny(self.tool("top", "Delete", {"file_path": str(spill)}),
                        "control-plane state")
        self.assertDeny(self.tool("top", "Write",
                                  {"file_path": str(self.cursor / "projects" / slug / "x.txt")}))
        for target in (self.cursor / "agents" / "st-tester.md", self.cursor / "hooks.json",
                       self.repo / ".cursor" / "hooks.json"):
            with self.subTest(target=target):
                self.assertDeny(self.tool("top", "Write", {"file_path": str(target)}),
                                "control-plane state")

    def test_an_unbound_conversation_cannot_write_a_project_spill(self):
        slug = re.sub(r"[^A-Za-z0-9]+", "-", str(self.repo)).strip("-")
        spill = self.cursor / "projects" / slug / "agent-tools" / "out.txt"
        self.assertDeny(self.tool("stranger-spill", "Write", {"file_path": str(spill)}),
                        "not bound to a team role")

    def test_a_bound_conversation_cannot_write_another_projects_spill(self):
        self.start()
        spill = self.cursor / "projects" / "another-project" / "agent-tools" / "out.txt"
        self.assertDeny(self.tool("top", "Write", {"file_path": str(spill)}),
                        "control-plane state")

    def test_mismatched_transcript_cannot_claim_a_live_dispatch(self):
        wo, _ws = self.dispatched()
        briefing = self.st("brief", wo)
        self.start()
        self.assertAllow(self.tool(
            "top", "Task", {"subagent_type": "st-tester", "prompt": briefing}
        ))
        self.transcript("wrong-sub", "a different task with no dispatched briefing")

        self.assertDeny(self.tool(
            "wrong-sub", "Read", {"file_path": str(self.repo / "README.md")}
        ), "not bound to a team role")
        self.assertFalse(
            (self.cfg / "cursor" / "bindings" / "wrong-sub.json").exists()
        )
        self.assertEqual(len(list((self.cfg / "cursor" / "pending").glob("*.json"))), 1)

    def test_a_missing_transcript_is_unknown_and_a_malformed_one_is_empty(self):
        old_cursor_dir = os.environ.get("ST_CURSOR_DIR")
        os.environ["ST_CURSOR_DIR"] = str(self.cursor)
        try:
            event = {"workspace_roots": [str(self.repo)]}
            self.assertIsNone(cursor.transcript_opening(event, "missing"))

            malformed = self.cursor / "malformed.jsonl"
            malformed.parent.mkdir(parents=True, exist_ok=True)
            malformed.write_text("not json\n")
            self.assertEqual(cursor.transcript_opening(
                {**event, "transcript_path": str(malformed)}, "malformed"
            ), "")
        finally:
            if old_cursor_dir is None:
                os.environ.pop("ST_CURSOR_DIR", None)
            else:
                os.environ["ST_CURSOR_DIR"] = old_cursor_dir

    def test_cursor_internal_errors_fail_closed(self):
        stdout = io.StringIO()
        with mock.patch.object(core, "cursor_handle", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO("{}")), redirect_stdout(stdout):
            code = core.guard_main(None, "cursor")
        answer = json.loads(stdout.getvalue())
        self.assertEqual((code, answer["permission"]), (0, "deny"))
        self.assertIn("guard error, failing closed: RuntimeError: boom", answer["agent_message"])

    def test_malformed_and_unhandled_events_are_refused(self):
        r = run_st(["guard", "--host", "cursor"], cwd=self.repo, env=self.env, stdin="not json")
        self.assertEqual(json.loads(r.stdout)["permission"], "deny")
        self.assertDeny(self.hook({"hook_event_name": "subagentStart"}), "not 'subagentStart'")

    def test_the_launcher_fast_path_handles_both_hosts(self):
        r = subprocess.run([str(ST), "guard", "--host", "cursor"], input="[]", env=self.env,
                           cwd=self.repo, capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["permission"]), (0, "deny"))
        r = subprocess.run([str(ST), "guard", "--host", "kiro"], input="{}", env=self.env,
                           cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("must pass --role", r.stderr)


if __name__ == "__main__":
    unittest.main()
