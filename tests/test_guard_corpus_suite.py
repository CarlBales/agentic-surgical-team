"""st unit tests: the guard conformance corpus, one test per tests/guard-cases/*.json.

Each file runs twice: as Kiro events, and as Cursor events through its adapter.
"""
import unittest

import guard_corpus
import support


class TestGuardCorpus(unittest.TestCase):
    """M-4: each case file builds its fixture once and runs every case in it."""

    def run_file(self, path, host="kiro"):
        doc = guard_corpus.load([path])[0][1]
        fx = guard_corpus.Fixture(support.BIN if support.SUBPROCESS else None,
                                  doc.get("fixture", {}))
        try:
            for case in doc["cases"]:
                with self.subTest(case=case["name"]):
                    why = guard_corpus.check_case(fx, case, host)
                    self.assertIsNone(why, why)
        finally:
            fx.close()


class TestGuardCorpusCursor(TestGuardCorpus):
    pass


for _path in sorted(guard_corpus.CASES_DIR.glob("*.json")):
    _name = "test_" + _path.stem.replace("-", "_")
    setattr(TestGuardCorpus, _name, lambda self, p=_path: self.run_file(p))
    setattr(TestGuardCorpusCursor, _name, lambda self, p=_path: self.run_file(p, "cursor"))


if __name__ == "__main__":
    unittest.main()
