"""st unit tests: sources."""
import json
import unittest

from base import ROOT, ST, StTestCase, order_spec, run_st  # noqa: F401


class TestSources(StTestCase):
    """E-3: read-only external tools, granted per order under a surgeon approval."""

    AWS = {"tool": "use_aws", "service": "logs",
           "operations": ["describe-log-groups", "filter-log-events"], "region": "us-east-1"}
    MCP = {"tool": "@tracker/get_issue", "readonly": True}

    def aws(self, op, service="logs", region="us-east-1", **extra):
        return {"service_name": service, "operation_name": op, "region": region,
                "label": "x", **extra}

    def test_rejects_sources_that_are_not_reads(self):
        cases = [({"tool": "use_aws", "service": "ec2", "operations": ["terminate-instances"]},
                  "is not a read"),
                 ({"tool": "use_aws", "service": "secretsmanager",
                   "operations": ["get-secret-value"]}, "never a source"),
                 ({"tool": "use_aws", "service": "ssm", "operations": ["get-parameter"]},
                  "never a source"),
                 ({"tool": "use_aws", "service": "s3api", "operations": ["get-object"]},
                  "never a source"),
                 ({"tool": "use_aws", "service": "s3", "operations": ["list-objects"]},
                  "high-level"),
                 ({"tool": "use_aws", "service": "logs"}, "list of operations"),
                 ({"tool": "@tracker/update_issue"}, "readonly"),
                 ({"tool": "MCP:update_issue"}, "readonly"),
                 ({"tool": "write", "readonly": True}, "not an external tool"),
                 ({"tool": "shell", "readonly": True}, "not an external tool")]
        for src, msg in cases:
            with self.subTest(src=src):
                self.st_fails("draft", stdin=json.dumps(order_spec(inputs={"sources": [src]})),
                              contains=msg)

    def test_no_sources_without_a_live_approved_order(self):
        self.assertBlocked("security-reviewer", "use_aws", self.aws("filter-log-events"))
        wo = self.draft(role="security-reviewer", authority="L0",
                        inputs={"sources": [self.AWS]})
        self.st("approve", wo)
        self.st("dispatch", wo)
        self.assertAllowed("security-reviewer", "use_aws", self.aws("filter-log-events"))
        self.report(wo, n=2)
        self.assertBlocked("security-reviewer", "use_aws", self.aws("filter-log-events"))

    def test_standing_orders_never_grant_sources(self):
        dec = self.st("grant", "--role", "*", "--max", "L0", "--scope", "reads")
        wo = self.draft(role="security-reviewer", authority="L0", standing=dec,
                        inputs={"sources": [self.AWS]})
        brief = self.st("dispatch", wo)
        self.assertIn("will NOT honor them", brief)
        self.assertBlocked("security-reviewer", "use_aws", self.aws("filter-log-events"))

    def test_editing_sources_after_approval_voids_the_grant(self):
        wo = self.draft(role="security-reviewer", authority="L0", inputs={"sources": [self.AWS]})
        self.st("approve", wo)
        self.st("dispatch", wo)
        o = self.order(wo)
        o["spec"]["inputs"]["sources"][0]["operations"].append("describe-log-streams")
        self.write_order(wo, o)
        self.assertBlocked("security-reviewer", "use_aws", self.aws("describe-log-streams"))
        self.assertBlocked("security-reviewer", "use_aws", self.aws("filter-log-events"))

if __name__ == "__main__":
    unittest.main()
