"""st unit tests: on-disk format (M-3): schemas, format version, migration, strict specs."""
import json
import unittest
from pathlib import Path

import schema_check
from base import ROOT, StTestCase, order_spec
from surgical_team import spec as spec_mod
from surgical_team.ledger import FORMAT
from surgical_team.tools import SOURCE_NAME_RE

RECORD_SCHEMAS = {"orders": "order.json", "reports": "report-record.json",
                  "checks": "check-record.json", "verdicts": "verdict-record.json",
                  "decisions": "decision-record.json"}


class TestSchemas(StTestCase):
    def full_lifecycle(self):
        """Exercise every command that writes a record."""
        self.st("grant", "--role", "tester", "--max", "L1", "--scope", "tests")
        self.st("decide", "--title", "t", "--decision", "d", "--why", "w",
                "--consequence", "c", "--rejected", "r")
        self.st("revoke", "DEC-001", "-m", "done")
        a, _ = self.dispatched(title="a", acceptance=[{"text": "x", "check": "true"},
                                                      {"text": "y"}], inputs={"files": ["README.md"], "sources": [
            {"tool": "use_aws", "service": "logs", "operations": ["filter-log-events"]},
            {"tool": "@t/get", "readonly": True}]})
        self.st("check", a)
        self.report(a)
        self.st("accept", a)
        b, _ = self.dispatched(title="b")
        self.st("reclaim", b, "--reason", "x")
        self.st("cancel", b)
        c, _ = self.dispatched(title="c")
        self.st("report", c, stdin=json.dumps({"status": "BLOCKED", "summary": "s", "blocker": "x",
                                                 "risks": "r", "cost": {"tokens": 1}}))
        self.st("reject", c)
        d = self.draft(title="d", authority="L0")
        self.st("approve", d, "--for", "30")

    def test_every_record_matches_its_schema(self):
        self.full_lifecycle()
        led = self.repo / ".surgical-team"
        seen = 0
        for sub, schema in RECORD_SCHEMAS.items():
            for f in sorted((led / sub).glob("*.json")):
                seen += 1
                with self.subTest(record=f"{sub}/{f.name}"):
                    self.assertEqual(schema_check.validate(json.loads(f.read_text()), schema), [])
        self.assertGreaterEqual(seen, 12)
        self.assertEqual(schema_check.validate(json.loads((led / "format.json").read_text()),
                                               "format.json"), [])
        for line in next((self.cfg / "leases").glob("*.jsonl")).read_text().splitlines():
            with self.subTest(lease=line[:60]):
                self.assertEqual(schema_check.validate(json.loads(line), "lease-event.json"), [])

    def test_schema_rejects_what_st_rejects(self):
        self.assertEqual(schema_check.validate(order_spec(), "spec.json"), [])
        for bad in (order_spec(blnid=["src"]), order_spec(authority="L3"),
                    order_spec(acceptance=[]), order_spec(budget={"minutes": 0}),
                    order_spec(inputs={"sources": [{"tool": "@t/x"}]})):
            with self.subTest(bad=bad):
                self.assertNotEqual(schema_check.validate(bad, "spec.json"), [])
                self.st_fails("draft", stdin=json.dumps(bad))

    def test_schema_accepts_cursor_mcp_source(self):
        spec = order_spec(inputs={"sources": [{"tool": "MCP:get_issue", "readonly": True}]})
        self.assertEqual(schema_check.validate(spec, "spec.json"), [])

    def test_schema_and_code_agree_on_spec_fields(self):
        schema = json.loads((ROOT / "schema" / "spec.json").read_text())
        self.assertEqual(set(schema["properties"]), spec_mod.SPEC_KEYS)
        self.assertEqual(set(schema["properties"]["inputs"]["properties"]), spec_mod.INPUT_KEYS)
        self.assertEqual(set(schema["properties"]["scope"]["properties"]), spec_mod.SCOPE_KEYS)
        source_pattern = schema["$defs"]["source"]["oneOf"][1]["properties"]["tool"]["pattern"]
        self.assertEqual(source_pattern, SOURCE_NAME_RE.pattern)

    def test_shipped_template_is_a_valid_spec(self):
        tmpl = json.loads((ROOT / "skills" / "surgical-team-protocol" / "assets" /
                           "work-order.json").read_text())
        self.assertEqual(schema_check.validate(tmpl, "spec.json"), [])


class TestStrictSpec(StTestCase):
    def test_unknown_fields_are_refused(self):
        for over, msg in (({"blnid": ["src"]}, "unknown field 'blnid'"),
                          ({"scope": {"in": ["x"], "outt": []}}, "scope: unknown field 'outt'"),
                          ({"inputs": {"source": []}}, "inputs: unknown field 'source'"),
                          ({"budget": {"minutes": 5, "hours": 1}}, "budget: unknown field"),
                          ({"acceptance": [{"text": "a", "chek": "true"}]}, "acceptance[1]")):
            with self.subTest(over=over):
                self.st_fails("draft", stdin=json.dumps(order_spec(**over)), contains=msg)


class TestFormat(StTestCase):
    def make_format0(self):
        """Turn this ledger into what a pre-v0.5 st wrote: no format markers."""
        wo, ws = self.dispatched()
        led = self.repo / ".surgical-team"
        (led / "format.json").unlink()
        for f in led.glob("*/*.json"):
            rec = json.loads(f.read_text())
            rec.pop("format", None)
            f.write_text(json.dumps(rec))
        return wo, ws

    def test_new_ledgers_are_current_format(self):
        led = self.repo / ".surgical-team"
        self.assertEqual(json.loads((led / "format.json").read_text()), {"format": FORMAT})
        wo = self.draft()
        self.assertEqual(self.order(wo)["format"], FORMAT)

    def test_format0_is_readable_but_not_writable_until_migrated(self):
        wo, ws = self.make_format0()
        self.st("status")
        self.st("show", wo)
        self.assertAllowed("tester", "write", {"path": str(ws / "x")}, cwd=ws)  # authority intact
        self.st_fails("draft", stdin=json.dumps(order_spec(title="new")), contains="st migrate")
        self.st_fails("report", wo, stdin="{}", contains="st migrate")
        out = self.st("migrate", "--dry-run")
        self.assertIn("format 0 -> 1", out)
        self.assertFalse((self.repo / ".surgical-team" / "format.json").exists())
        self.st("migrate")
        self.assertEqual(self.order(wo)["format"], FORMAT)
        self.assertIn("already format", self.st("migrate"))
        self.assertAllowed("tester", "write", {"path": str(ws / "x")}, cwd=ws)  # approval survived
        self.report(wo)
        self.st("draft", stdin=json.dumps(order_spec(title="new")))

    def test_migrate_keeps_spec_hashes(self):
        wo, _ = self.make_format0()
        before = self.order(wo)["spec"]
        self.st("migrate")
        self.assertEqual(self.order(wo)["spec"], before)
        self.st("verify")

    def test_newer_format_is_refused_and_grants_nothing(self):
        wo, ws = self.dispatched()
        (self.repo / ".surgical-team" / "format.json").write_text('{"format": 99}')
        self.st_fails("status", contains="newer than this st")
        self.st_fails("draft", stdin=json.dumps(order_spec()), contains="newer than this st")
        self.st_fails("migrate", contains="newer than this st")
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)
        (self.repo / ".surgical-team" / "format.json").write_text("not json")
        self.assertBlocked("tester", "write", {"path": str(ws / "x")}, cwd=ws)

    def test_init_refuses_to_restamp_an_old_ledger(self):
        self.make_format0()
        self.st_fails("init", contains="st migrate")

    def test_migrate_is_surgeon_only(self):
        self.assertBlocked("copilot", "shell", {"command": "st migrate"}, contains="surgeon-only")


if __name__ == "__main__":
    unittest.main()
