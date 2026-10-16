"""Shared test support: run `st` in-process (fast) or as a subprocess (black box).

Mode:
  default             in-process: cli.main() with argv, stdin, cwd, and env swapped in
  ST_BIN=/path/to/st  subprocess against that binary (conformance: any implementation)
  ST_TEST_MODE=subprocess
                      subprocess against this repo's bin/st

In-process runs clear the signature-verification cache before each call, so
each call sees what one real `st` process would see.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ST_SRC points the in-process mode at another copy of the package (used by
# tests/mutate_guard.py to run the suite against a mutant).
SRC = Path(os.environ.get("ST_SRC") or ROOT / "src")
BIN = Path(os.environ.get("ST_BIN") or SRC.parent / "bin" / "st")
SUBPROCESS = bool(os.environ.get("ST_BIN")) or os.environ.get("ST_TEST_MODE") == "subprocess"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.dont_write_bytecode = True


class Result:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@contextlib.contextmanager
def _swapped(env: dict, cwd: Path, stdin: str):
    old_env, old_cwd = dict(os.environ), os.getcwd()
    old_io = sys.stdin, sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    os.environ.clear()
    os.environ.update(env)
    os.chdir(cwd)
    sys.stdin, sys.stdout, sys.stderr = io.StringIO(stdin), out, err
    try:
        yield out, err
    finally:
        sys.stdin, sys.stdout, sys.stderr = old_io
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)


def run_st(args, *, cwd: Path, env: dict, stdin: str | None = None) -> Result:
    """Run one `st` command; the same contract in both modes."""
    if SUBPROCESS:
        r = subprocess.run([str(BIN), *args], cwd=cwd, env=env, input=stdin,
                           capture_output=True, text=True)
        return Result(r.returncode, r.stdout, r.stderr)
    from surgical_team import cli, signing
    signing._verify_cache.clear()
    with _swapped(env, cwd, stdin or "") as (out, err):
        try:
            code = cli.main(list(args))
        except SystemExit as e:  # argparse errors and --version
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    return Result(code, out.getvalue(), err.getvalue())


_KEY_DIR: Path | None = None


def surgeon_key(dest: Path) -> Path:
    """An unencrypted test signing key, generated once per test run and copied."""
    global _KEY_DIR
    if _KEY_DIR is None:
        _KEY_DIR = Path(tempfile.mkdtemp(prefix="st-key-"))
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "surgeon",
                        "-f", str(_KEY_DIR / "key")], check=True)
        import atexit
        atexit.register(shutil.rmtree, _KEY_DIR, True)
    for suffix in ("", ".pub"):
        shutil.copy2(_KEY_DIR / f"key{suffix}", dest.with_name(dest.name + suffix))
    os.chmod(dest, 0o600)
    return dest
