#!/usr/bin/env python3
"""Guard conformance corpus runner (M-4).

The corpus in tests/guard-cases/*.json is the specification of `st guard`:
given a ledger fixture, a role, and one host tool event, the guard must allow
or block, and a block must give a reason containing a substring. It drives
the binary as a subprocess, so it checks any implementation of `st` with the
same CLI (set ST_BIN, or pass --st).

File format:

    {"about": "...",
     "fixture": {
        "files": {"src/x.rs": "..."},          committed to the project
        "remote": true,                        add an `origin` remote
        "no_ledger": true,                     skip `st init` (and every order)
        "orders": [{"as": "A", "spec": {...},   overrides on a tester L1 order
                    "approve": true, "push": false, "dispatch": true,
                    "report": false}],
        "symlinks": {"{ws:A}/link": "{repo}/README.md"}},
     "cases": [{"name": "...", "role": "tester", "tool": "shell",
                "input": {...}, "cwd": "repo" | "tmp" | "ws:A",
                "expect": "allow" | "block", "reason": "substring"}]}

Placeholders in strings: {repo} {tmp} {cfg} {home} {st} {ws:A} {wo:A};
{ws} and {wo} mean the first order.

With --host cursor, each case runs as a Cursor preToolUse event from a
conversation bound to the case's role, through the Cursor adapter.

Run: python3 tests/guard_corpus.py [--st PATH] [--host kiro|cursor|all] [FILE ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import support  # noqa: E402

CASES_DIR = HERE / "guard-cases"

BASE_SPEC = {
    "title": "corpus order", "role": "tester", "authority": "L1",
    "intent": "conformance fixture", "scope": {"in": ["fixture"]},
    "acceptance": [{"text": "a"}, {"text": "b"}], "budget": {"minutes": 30},
}


class Fixture:
    def __init__(self, st: Path | None, spec: dict):
        """st None runs this repo's st in-process (fast); a path runs that binary."""
        self.st_bin = st
        self.tmp = Path(tempfile.mkdtemp(prefix="st-corpus-")).resolve()
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.cfg = self.tmp / "cfg"
        self.env = {**os.environ, "ST_CONFIG_DIR": str(self.cfg),
                    "ST_CURSOR_DIR": str(self.tmp / "cursor-home"),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.env.pop("ST_NOW", None)
        self.orders: dict[str, str] = {}
        self.first: str | None = None
        self._build(spec)

    def _run(self, args, stdin=None, cwd=None, check=True):
        r = subprocess.run(args, cwd=cwd or self.repo, input=stdin, env=self.env,
                           capture_output=True, text=True)
        if check and r.returncode:
            raise RuntimeError(f"{' '.join(map(str, args))}: {r.stderr.strip()}")
        return r.stdout.strip()

    def run_st(self, args, stdin=None, cwd=None):
        working_dir = cwd or self.repo
        if self.st_bin is None:
            return support.run_st(args, cwd=working_dir, env=self.env, stdin=stdin)
        r = subprocess.run([str(self.st_bin), *args], cwd=working_dir, input=stdin,
                           env=self.env, capture_output=True, text=True)
        return support.Result(r.returncode, r.stdout, r.stderr)

    def st(self, *args, stdin=None):
        r = self.run_st(args, stdin=stdin)
        if r.returncode:
            raise RuntimeError(f"st {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout.strip()

    def _build(self, spec: dict):
        git = lambda *a: self._run(["git", *a])  # noqa: E731
        git("init", "-q", "-b", "main")
        files = {"README.md": "hello\n", **spec.get("files", {})}
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        git("add", "-A")
        git("commit", "-q", "-m", "fixture")
        if spec.get("remote"):
            git("remote", "add", "origin", str(self.tmp / "remote.git"))
        key = support.surgeon_key(self.tmp / "key")
        self.st("setup", "--key", str(key), "--identity", "surgeon", "--allow-unencrypted")
        if spec.get("no_ledger"):
            return
        self.st("init")
        for i, o in enumerate(spec.get("orders", [])):
            label = o.get("as", f"O{i}")
            body = {**BASE_SPEC, "title": f"corpus {label}", **o.get("spec", {})}
            wo = self.st("draft", stdin=json.dumps(body)).splitlines()[-1]
            self.orders[label] = wo
            self.first = self.first or label
            if o.get("approve", True):
                self.st("approve", wo, *(["--push"] if o.get("push") else []))
            if o.get("dispatch", True):
                self.st("dispatch", wo)
            if o.get("report"):
                n = len(body["acceptance"])
                self.st("report", wo, stdin=json.dumps(
                    {"status": "DONE", "summary": "fixture",
                     "criteria": [{"met": True, "evidence": "x"}] * n}))
        for link, target in spec.get("symlinks", {}).items():
            Path(self.sub(link)).symlink_to(self.sub(target))

    def ws(self, label: str) -> Path:
        return self.tmp / f"{self.repo.name}.st" / self.orders[label]

    def sub(self, s: str) -> str:
        def rep(m):
            key, _, label = m.group(1).partition(":")
            label = label or self.first
            return {"repo": lambda: str(self.repo), "tmp": lambda: str(self.tmp),
                    "cfg": lambda: str(self.cfg), "home": lambda: str(Path.home()),
                    "st": lambda: str(self.st_bin or support.BIN),
                    "ws": lambda: str(self.ws(label)),
                    "wo": lambda: self.orders[label]}[key]()
        return re.sub(r"\{(repo|tmp|cfg|home|st|ws(?::\w+)?|wo(?::\w+)?)\}", rep, s)

    def subst(self, obj):
        if isinstance(obj, str):
            return self.sub(obj)
        if isinstance(obj, list):
            return [self.subst(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.subst(v) for k, v in obj.items()}
        return obj

    def guard(self, case: dict, host: str = "kiro") -> tuple[int, str]:
        cwd_name = case.get("cwd", "repo")
        if cwd_name == "repo":
            cwd = self.repo
        elif cwd_name == "tmp":
            cwd = self.tmp
        else:
            cwd = self.ws(cwd_name.partition(":")[2] or self.first)
        tool, inp = case["tool"], self.subst(case.get("input", {}))
        if host == "cursor":
            return self.guard_cursor(case["role"], tool, inp, cwd)
        ev = {"hook_event_name": "preToolUse", "cwd": str(cwd),
              "tool_name": tool, "tool_input": inp}
        r = self.run_st(
            ["guard", "--role", case["role"]], stdin=json.dumps(ev), cwd=cwd
        )
        return r.returncode, r.stderr

    def guard_cursor(self, role: str, tool: str, inp: dict, cwd: Path) -> tuple[int, str]:
        """The same case as a Cursor event from a conversation bound to `role`.

        The answer is mapped back to Kiro's contract (exit 2 and the reason on
        stderr for a block), so check_case judges both hosts the same way.
        """
        conversation = f"corpus-{role}"
        binding = self.cfg / "cursor" / "bindings" / f"{conversation}.json"
        binding.parent.mkdir(parents=True, exist_ok=True)
        binding.write_text(json.dumps({"conversation": conversation, "role": role}))
        name, cursor_input = to_cursor(tool, inp)
        ev = {"hook_event_name": "preToolUse", "conversation_id": conversation,
              "workspace_roots": [str(self.repo)], "cwd": str(cwd),
              "tool_name": name, "tool_input": cursor_input}
        r = self.run_st(["guard", "--host", "cursor"], stdin=json.dumps(ev), cwd=cwd)
        try:
            answer = json.loads(r.stdout)
        except ValueError:
            return 1, f"no JSON answer (exit {r.returncode}): {r.stdout!r} {r.stderr!r}"
        if r.returncode != 0:
            return r.returncode, r.stderr
        if answer.get("permission") == "allow":
            return 0, ""
        if answer.get("permission") == "deny":
            return 2, answer.get("agent_message", "")
        return 1, f"unexpected answer {answer!r}"

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.tmp.parent / f"{self.repo.name}.st", ignore_errors=True)


def to_cursor(tool: str, inp: dict) -> tuple[str, dict]:
    """A normalized corpus event in the shape Cursor's hook reports it.

    Only exact normalized names have a Cursor form; alias spellings (fs_write,
    WRITE, ...) and tools Cursor lacks go through raw, as an unknown Cursor
    tool would.
    """
    path = inp.get("path") or inp.get("file_path")
    if tool == "write":
        return "Write", {"file_path": path, "content": inp.get("content", "")} if path else {}
    if tool == "shell":
        out = {"command": inp.get("command", ""), "cwd": inp.get("working_dir", "")}
        return "Shell", out
    if tool == "read":
        ops = inp.get("operations") or []
        if (len(ops) == 1 and ops[0].get("path") and ops[0].get("mode") != "Directory"
                and not ops[0].get("image_paths")):
            return "Read", {"file_path": ops[0]["path"]}
    if tool == "grep" and path:
        out = {"pattern": inp.get("pattern", "x"), "path": path}
        if inp.get("include"):
            out["glob"] = inp["include"]
        return "Grep", out
    if tool == "glob" and path:
        return "Glob", {"target_directory": path, "glob_pattern": inp.get("pattern", "*")}
    if tool == "subagent" and len(inp.get("stages") or []) == 1:
        stage = inp["stages"][0]
        return "Task", {"subagent_type": stage.get("role", ""), "description": stage.get("name"),
                        "prompt": stage.get("prompt_template", "")}
    if tool == "web_search":
        return "WebSearch", {"search_term": inp.get("query", "")}
    return tool, inp


def check_case(fx: Fixture, case: dict, host: str = "kiro") -> str | None:
    """None if the guard met the case; otherwise what went wrong."""
    code, err = fx.guard(case, host)
    want = case["expect"]
    if want == "allow" and code != 0:
        return f"expected allow, got exit {code}: {err.strip()}"
    if want == "block":
        if code != 2:
            return f"expected block, got exit {code}"
        if case.get("reason") and case["reason"] not in err:
            return f"blocked, but reason lacks {case['reason']!r}: {err.strip()}"
    return None


def load(paths=None) -> list[tuple[Path, dict]]:
    files = [Path(p) for p in paths] if paths else sorted(CASES_DIR.glob("*.json"))
    return [(f, json.loads(f.read_text())) for f in files]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--st", default=os.environ.get("ST_BIN"),
                    help="st binary to check (default: this repo's st, in-process)")
    ap.add_argument("--host", choices=["kiro", "cursor", "all"], default="kiro",
                    help="host hook format to drive the cases through (default kiro)")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    hosts = ["kiro", "cursor"] if a.host == "all" else [a.host]
    total = failed = 0
    for f, doc in load(a.files):
        fx = Fixture(Path(a.st) if a.st else None, doc.get("fixture", {}))
        try:
            for host in hosts:
                for case in doc["cases"]:
                    total += 1
                    why = check_case(fx, case, host)
                    if why:
                        failed += 1
                        print(f"FAIL {f.name} [{host}]: {case['name']}: {why}")
        finally:
            fx.close()
    print(f"{total - failed}/{total} guard cases passed ({', '.join(hosts)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
