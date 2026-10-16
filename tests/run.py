#!/usr/bin/env python3
"""Run the unit tests in parallel, one process per test class.

Every test builds its own repository, config directory, and ledger under a
fresh temp dir, so classes are independent. In-process mode swaps os.environ
and the working directory, which is why the unit of parallelism is a process.

Run: python3 tests/run.py [-j N] [-v]          (same tests as unittest discover)
     ST_TEST_MODE=subprocess python3 tests/run.py   black-box against bin/st
     ST_BIN=/path/to/st python3 tests/run.py        black-box against another build
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_ids() -> list[str]:
    sys.path.insert(0, str(HERE))
    ids: set[str] = set()

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            elif isinstance(t, unittest.loader._FailedTest):  # import error: surface it
                ids.add(t.id().rsplit(".", 1)[-1])
            else:
                ids.add(t.id().rsplit(".", 1)[0])  # module.Class
    walk(unittest.defaultTestLoader.discover(str(HERE)))
    return sorted(ids)


def run_one(target: str, verbose: bool) -> tuple[str, int, str, float]:
    t = time.perf_counter()
    r = subprocess.run([sys.executable, "-m", "unittest", *(["-v"] if verbose else []), target],
                       cwd=HERE, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return target, r.returncode, r.stderr + r.stdout, time.perf_counter() - t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    t0 = time.perf_counter()
    targets = test_ids()
    failed = []
    ran = 0
    with ThreadPoolExecutor(a.j) as pool:
        for target, code, out, secs in pool.map(lambda x: run_one(x, a.v), targets):
            for line in out.splitlines():
                if line.startswith("Ran "):
                    ran += int(line.split()[1])
            status = "ok  " if code == 0 else "FAIL"
            print(f"{status} {secs:5.1f}s {target}")
            if code:
                failed.append((target, out))
    for target, out in failed:
        print(f"\n===== {target}\n{out}")
    print(f"\n{ran} tests in {len(targets)} classes, {time.perf_counter() - t0:.1f}s wall; "
          f"{'FAILED: ' + str(len(failed)) if failed else 'OK'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
