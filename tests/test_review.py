"""st unit tests: review."""
import json
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestReviewTarget(StTestCase):
    """E-4: an order can name a commit range to review, pinned to SHAs."""

    def setUp(self):
        super().setUp()
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "feature")
        (self.repo / "app.py").write_text("def f(x):\n    return x.y\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "feature")
        self.head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")

    def test_refs_are_pinned_to_commits_at_draft(self):
        wo = self.draft(inputs={"review": {"base": "main", "head": "feature"}})
        rv = self.order(wo)["spec"]["inputs"]["review"]
        self.assertEqual(rv, {"base": self.base, "head": self.head})
        # moving the branch later does not move the order
        (self.repo / "late.txt").write_text("x")
        self.git("checkout", "-q", "feature")
        self.git("add", "late.txt")
        self.git("commit", "-q", "-m", "late")
        self.git("checkout", "-q", "main")
        self.assertEqual(self.order(wo)["spec"]["inputs"]["review"]["head"], self.head)

    def test_rejects_bad_targets(self):
        cases = [({"base": "main"}, "must be"),
                 ({"base": "main", "head": "feature", "extra": 1}, "must be"),
                 ({"base": "--output=/tmp/x", "head": "feature"}, "not a git ref"),
                 ({"base": "main", "head": "no-such-branch"}, "not a commit"),
                 ({"base": "main", "head": "main"}, "same commit")]
        for rv, msg in cases:
            with self.subTest(rv=rv):
                self.st_fails("draft", stdin=json.dumps(order_spec(inputs={"review": rv})),
                              contains=msg)

    def test_L0_briefing_names_the_range_and_git_reads_are_allowed(self):
        wo = self.draft(role="language-lawyer-rust", authority="L0",
                        inputs={"review": {"base": "main", "head": "feature"}})
        self.st("approve", wo)
        brief = self.st("dispatch", wo)
        self.assertIn("## Review target", brief)
        self.assertIn(f"git diff {self.base}...{self.head}", brief)
        self.assertFalse((self.repo.parent / "proj.st" / wo).exists())
        for cmd in (f"git diff {self.base}...{self.head}", f"git log {self.base}..{self.head}",
                    f"git show {self.head}:app.py"):
            self.assertAllowed("language-lawyer-rust", "shell", {"command": cmd})
        self.assertBlocked("language-lawyer-rust", "shell", {"command": f"git checkout {self.head}"})

    def test_L1_workspace_is_checked_out_at_head(self):
        wo, ws = self.dispatched(inputs={"review": {"base": "main", "head": "feature"}})
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=ws), self.head)
        self.assertTrue((ws / "app.py").exists())

if __name__ == "__main__":
    unittest.main()
