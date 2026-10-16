"""Tests for Cursor-aware guard mutation discovery (I1)."""
from __future__ import annotations

import unittest

import mutate_guard


class TestMutationHarness(unittest.TestCase):
    def sites(self, rel: str):
        sites = list(mutate_guard.refusal_sites(rel))
        self.assertTrue(sites, rel)
        for site in sites:
            # Stable identities make survivors auditable instead of silently skipped.
            self.assertEqual(site.rel, rel)
            self.assertTrue(site.function)
            self.assertTrue(site.line_text)
            self.assertTrue(site.operator)
        return sites

    def test_cursor_modules_and_suites_are_in_the_harness(self):
        self.assertEqual(
            mutate_guard.TARGETS,
            [
                "guard/core.py",
                "guard/shellcheck.py",
                "guard/cursor.py",
                "guard/sessions.py",
                "guard/hosts.py",
                "tools.py",
            ],
        )
        self.assertIn("test_hosts", mutate_guard.SUITES)
        self.assertIn("test_guard_corpus_suite", mutate_guard.SUITES)

    def test_resolve_role_tuple_refusals_become_pass_throughs(self):
        sites = [
            site
            for site in self.sites("guard/cursor.py")
            if site.function == "resolve_role" and site.operator == "tuple-refusal"
        ]
        self.assertEqual(len(sites), 3)
        self.assertTrue(all(site.replacement == "None, None" for site in sites))
        source = "\n".join(site.source for site in sites)
        self.assertIn("valid conversation_id", source)
        self.assertIn("not bound to a team role", source)
        self.assertIn("cannot tell whether", source)

    def test_cursor_response_refusals_become_allows(self):
        sites = [
            site
            for site in self.sites("guard/cursor.py")
            if site.operator == "cursor-response"
        ]
        self.assertEqual(len(sites), 6)
        self.assertTrue(all(site.replacement == "None" for site in sites))
        source = "\n".join(site.source for site in sites)
        for expected in (
            "unparseable hook event",
            "hook event is not a JSON object",
            "st guard handles sessionStart, beforeSubmitPrompt, and preToolUse",
            "agents run only from a team session",
            "refusal",
            "why",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_session_allow_gates_are_mutated_toward_allow(self):
        sites = self.sites("guard/sessions.py")
        by_source = {
            site.source: site
            for site in sites
            if site.operator in {"expiry-gate", "claim-gate"}
        }
        expected = {
            "now - at > PENDING_TTL_S": ("expiry-gate", "False"),
            "now - path.stat().st_mtime > max_age_s": ("expiry-gate", "False"),
            "prompt in opening": ("claim-gate", "True"),
            "len(candidates) != 1": ("claim-gate", "False"),
        }
        for source, (operator, replacement) in expected.items():
            with self.subTest(source=source):
                self.assertIn(source, by_source)
                self.assertEqual(by_source[source].operator, operator)
                self.assertEqual(by_source[source].replacement, replacement)

    def test_cursor_host_denial_gate_becomes_allow(self):
        sites = self.sites("guard/hosts.py")
        matches = [
            site
            for site in sites
            if site.function == "CursorHost.respond"
            and site.operator == "response-gate"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0].source, matches[0].replacement), ("why", "False"))

    def test_equivalent_allowlist_has_auditable_keys_and_reasons(self):
        for key, reason in mutate_guard.EQUIVALENT.items():
            with self.subTest(key=key):
                self.assertIsInstance(key, tuple)
                self.assertEqual(len(key), 3)
                rel, function, line_text = key
                self.assertIn(rel, mutate_guard.TARGETS)
                self.assertTrue(function)
                self.assertTrue(line_text)
                self.assertTrue(reason.strip())


if __name__ == "__main__":
    unittest.main()
