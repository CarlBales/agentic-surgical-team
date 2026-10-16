#!/usr/bin/env python3
"""Guard latency benchmark (P-1): one real `st guard` process per tool call.

Builds a ledger with N live orders (half for the calling role, half for
others, plus standing-order L0 orders and ordinary decisions), then times
read, write, and shell guard calls as a host would make them: a fresh
process per call. Reports p50 and p90 in milliseconds.

Run: python3 tests/bench_guard.py [--orders 10] [--calls 25] [--budget-ms 50]
Exit status is 1 if the p50 of any call kind exceeds --budget-ms.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import support  # noqa: E402


def spec(title: str, role: str, authority: str = "L1", **extra: object) -> str:
    return json.dumps({"title": title, "role": role, "authority": authority, "intent": "bench",
                       "scope": {"in": ["x"]}, "acceptance": [{"text": "a"}],
                       "budget": {"minutes": 30}, **extra})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=10)
    ap.add_argument("--calls", type=int, default=25)
    ap.add_argument("--budget-ms", type=float, default=50)
    ap.add_argument("--st", default=str(support.BIN))
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="st-bench-")).resolve()
    repo = tmp / "proj"
    repo.mkdir()
    env = {**os.environ, "ST_CONFIG_DIR": str(tmp / "cfg"), "GIT_AUTHOR_NAME": "b",
           "GIT_AUTHOR_EMAIL": "b@e", "GIT_COMMITTER_NAME": "b", "GIT_COMMITTER_EMAIL": "b@e"}
    env.pop("ST_NOW", None)

    def run(*args: str, stdin: str | None = None) -> str:
        r = subprocess.run([a.st, *args], cwd=repo, env=env, input=stdin,
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"st {' '.join(args)}: {r.stderr}")
        return r.stdout.strip()

    try:
        subprocess.run("git init -qb main && echo x > README.md && git add . && "
                       "git commit -qm i", shell=True, cwd=repo, env=env, check=True)
        key = support.surgeon_key(tmp / "key")
        run("setup", "--key", str(key), "--identity", "s", "--allow-unencrypted")
        run("init", "--default-standing")
        for i in range(5):
            run("decide", "--title", f"d{i}", "--decision", "x")
        mine = None
        for i in range(a.orders):
            role = "tester" if i % 2 == 0 else "editor"
            wo = run("draft", stdin=spec(f"o{i}", role, paths=[f"p{i}"])).splitlines()[-1]
            run("approve", wo)
            run("dispatch", wo)
            mine = mine or (wo if role == "tester" else None)
        for i in range(max(1, a.orders // 4)):
            wo = run("draft", stdin=spec(f"s{i}", "reviewer", "L0", standing="DEC-001")
                     ).splitlines()[-1]
            run("dispatch", wo)
        ws = tmp / "proj.st" / str(mine)
        events = {
            "read": ("read", {"operations": [{"mode": "Line", "path": str(ws / "README.md")}]}),
            "write": ("write", {"path": str(ws / "out.txt")}),
            "shell": ("shell", {"command": "ls -la && git status && python3 -m pytest -q"}),
            # Path-like arguments outside the workspace drive ledger discovery (D10).
            "shell-out": ("shell", {"command": "ls /usr/bin /etc /tmp ./src ../x"}),
        }
        worst = 0.0
        for name, (tool, inp) in events.items():
            ev = json.dumps({"hook_event_name": "preToolUse", "cwd": str(ws),
                             "tool_name": tool, "tool_input": inp})
            times = []
            for _ in range(a.calls):
                t = time.perf_counter()
                r = subprocess.run([a.st, "guard", "--role", "tester"], input=ev, env=env,
                                   capture_output=True, text=True)
                times.append((time.perf_counter() - t) * 1000)
                if r.returncode:
                    raise SystemExit(f"guard blocked the benchmark's {name}: {r.stderr}")
            times.sort()
            p50, p90 = statistics.median(times), times[int(len(times) * 0.9) - 1]
            worst = max(worst, p50)
            print(f"{name:9s} p50 {p50:6.1f} ms   p90 {p90:6.1f} ms")
        print(f"{a.orders} live orders (+{max(1, a.orders // 4)} standing); "
              f"budget p50 <= {a.budget_ms:.0f} ms: {'OK' if worst <= a.budget_ms else 'OVER'}")
        return 0 if worst <= a.budget_ms else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp.parent / "proj.st", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
