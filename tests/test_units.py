"""st unit tests: pure functions, in-process, no repository or key needed."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (puts src/ on sys.path)
from surgical_team import gitutil, ledger, model, roles, tools
from surgical_team.guard import shell
from surgical_team.spec import validate_sources


class TestShellTokenizing(unittest.TestCase):
    def test_segments_split_on_operators(self):
        self.assertEqual(shell.shell_segments("a b && c | d; e"),
                         [["a", "b"], ["c"], ["d"], ["e"]])
        self.assertEqual(shell.shell_segments("echo 'a && b'"), [["echo", "a && b"]])
        self.assertEqual(shell.shell_segments("a\nb"), [["a"], ["b"]])

    def test_heredoc_bodies_are_not_commands(self):
        cmd = "cat <<'EOF' > x\nrm -rf /\nEOF\nls"
        self.assertNotIn(["rm", "-rf", "/"], shell.shell_segments(cmd))
        self.assertIn(["ls"], shell.shell_segments(cmd))

    def test_unbalanced_quotes_raise(self):
        with self.assertRaises(ValueError):
            shell.shell_segments("echo 'oops")

    def test_shell_inline(self):
        cases = {("-c", "ls"): "ls", ("-lc", "ls"): "ls", ("-fc", "x"): "x",
                 ("-o", "posix", "-c", "x"): "x", ("-e", "run.sh"): None,
                 ("run.sh", "-c", "x"): None, ("--", "-c"): None, ("-c",): ""}
        for args, want in cases.items():
            with self.subTest(args=args):
                self.assertEqual(shell.shell_inline(list(args)), want)

    def test_shell_reads_stdin(self):
        for args in ([], ["-s"], ["-e"], ["/dev/stdin"], ["-"], ["/dev/fd/3"], ["-o", "posix"]):
            with self.subTest(args=args):
                self.assertTrue(shell.shell_reads_stdin(args))
        for args in (["run.sh"], ["-e", "run.sh", "arg"]):
            with self.subTest(args=args):
                self.assertFalse(shell.shell_reads_stdin(args))

    def test_substitution_reason(self):
        for cmd in ("echo $(id)", "echo `id`", 'echo "$(id)"', 'echo "`id`"',
                    "x=$(id)", "echo ${y:-$(id)}", "diff <(a) b", "cmd > >(tee f)",
                    "cat <<EOF\n$(id)\nEOF"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(shell.substitution_reason(cmd))
        for cmd in ("echo $((1+2))", "echo ${HOME}", "echo '$(id)'", "ls | wc -l",
                    "a && b || c", "cat <<'EOF'\n$(id)\nEOF", "echo \\$(id)"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(shell.substitution_reason(cmd))

    def test_keywords_lead_segments(self):
        for cmd in ("for x in 1; do echo $x; done", "if true; then ls; fi", "! false",
                    "time ls", "while read l; do echo $l; done", "[[ -f x ]]"):
            with self.subTest(cmd=cmd):
                self.assertIn(shell.shell_segments(cmd)[0][0], shell.SHELL_KEYWORDS)
        for cmd in ("ls && echo done", "echo if then", "make"):
            with self.subTest(cmd=cmd):
                self.assertNotIn(shell.shell_segments(cmd)[0][0], shell.SHELL_KEYWORDS)


class TestTools(unittest.TestCase):
    def test_normalize_tool(self):
        for raw, want in (("fs_write", "write"), ("@builtin/write", "write"), ("WRITE", "write"),
                          ("execute_bash", "shell"), ("aws", "use_aws"), ("mystery", "mystery")):
            with self.subTest(raw=raw):
                self.assertEqual(tools.normalize_tool(raw), want)

    def test_aws_op(self):
        self.assertEqual(tools.aws_op("DescribeInstances"), "describe-instances")
        self.assertEqual(tools.aws_op("filter_log_events"), "filter-log-events")
        self.assertEqual(tools.aws_op("list-buckets"), "list-buckets")

    def test_aws_op_refusal(self):
        self.assertIsNone(tools.aws_op_refusal("describe-instances"))
        self.assertIsNone(tools.aws_op_refusal("ListBuckets"))
        for op in ("delete-bucket", "put-object", "run-instances", "invoke"):
            with self.subTest(op=op):
                self.assertIn("not a read", tools.aws_op_refusal(op))
        for op in ("get-secret-value", "get-parameter", "get-object", "get-session-token",
                   "describe-key-pairs", "get-login-password", "batch-get-secret-value"):
            with self.subTest(op=op):
                self.assertIn("never a source", tools.aws_op_refusal(op))

    def test_validate_sources(self):
        self.assertEqual(validate_sources([{"tool": "@t/get", "readonly": True}]), [])
        self.assertEqual(validate_sources([{"tool": "MCP:get_issue", "readonly": True}]), [])
        self.assertEqual(validate_sources(
            [{"tool": "use_aws", "service": "logs", "operations": ["filter-log-events"]}]), [])
        self.assertTrue(validate_sources([]))
        self.assertTrue(validate_sources("x"))
        self.assertTrue(validate_sources([{"tool": "@t/get", "readonly": True, "extra": 1}]))
        for tool in ("../x", "MCP:", "mcp:get_issue", "MCP:@t/get"):
            with self.subTest(tool=tool):
                self.assertTrue(validate_sources([{"tool": tool, "readonly": True}]))


class TestLedgerDiscovery(unittest.TestCase):
    """N5: paths outside any checkout are settled without a git subprocess."""

    def test_git_checkout_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "repo" / ".git").mkdir(parents=True)
            (root / "repo" / "a" / "b").mkdir(parents=True)
            (root / "plain").mkdir()
            self.assertTrue(gitutil.in_git_checkout(root / "repo" / "a" / "b"))
            self.assertFalse(gitutil.in_git_checkout(root / "plain"))

    def test_outside_a_checkout_no_git_runs_and_results_are_cached_per_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp).resolve()
            ledger.clear_ledger_cache()
            with mock.patch.object(ledger.Ledger, "at", side_effect=AssertionError):
                self.assertIsNone(ledger.ledger_at(plain))
            ledger._FOUND[plain / "x"] = "cached"  # type: ignore[assignment]
            self.assertEqual(ledger.ledger_at(plain / "x"), "cached")
            ledger.clear_ledger_cache()
            self.assertIsNone(ledger.ledger_at(plain / "x"))


class TestModel(unittest.TestCase):
    def test_canonical_hash_ignores_key_order(self):
        self.assertEqual(model.sha({"a": 1, "b": [1, 2]}), model.sha({"b": [1, 2], "a": 1}))
        self.assertNotEqual(model.sha({"a": 1}), model.sha({"a": 2}))

    def test_iso_round_trip(self):
        t = model.parse_iso("2026-10-08T10:00:00Z")
        self.assertEqual(model.iso(t), "2026-10-08T10:00:00Z")
        self.assertEqual(model.parse_iso("2026-10-08T10:00:00").tzinfo is not None, True)

    def test_st_now_needs_st_config_dir(self):
        import os
        saved = {k: os.environ.get(k) for k in ("ST_NOW", "ST_CONFIG_DIR")}
        try:
            os.environ["ST_NOW"] = "2000-01-01T00:00:00Z"
            os.environ.pop("ST_CONFIG_DIR", None)
            # a planted clock with no test config dir does not move real time
            self.assertGreater(model.now().year, 2024)
            os.environ["ST_CONFIG_DIR"] = "/tmp/st-test-cfg"
            self.assertEqual(model.now().year, 2000)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_transitions_are_closed(self):
        for frm, tos in model.TRANSITIONS.items():
            self.assertTrue(tos <= set(model.TRANSITIONS), frm)
        for t in model.TERMINAL:
            self.assertEqual(model.TRANSITIONS[t], set())


class TestSkillFamily(unittest.TestCase):
    def skill(self, text, dirname="r"):
        d = Path(tempfile.mkdtemp()) / dirname
        d.mkdir()
        (d / "SKILL.md").write_text(text)
        return d / "SKILL.md"

    def test_reads_family_from_frontmatter(self):
        f = self.skill("---\nname: r\nmetadata:\n  surgical-team-role: reviewer\n---\n")
        self.assertEqual(roles.skill_family(f), "reviewer")

    def test_rejects_malformed(self):
        for text in ("no frontmatter", "---\nname: other\nmetadata:\n  surgical-team-role: x\n---\n",
                     "---\nname: r\n---\n", "---\nname: r\nsurgical-team-role: x\n---\n"):
            with self.subTest(text=text):
                self.assertIsNone(roles.skill_family(self.skill(text)))


if __name__ == "__main__":
    unittest.main()
