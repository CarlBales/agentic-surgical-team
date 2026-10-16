"""Surgeon signatures: ssh-keygen -Y sign/verify against allowed_signers."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .model import NAMESPACE, StError, canon
from .types import JSON, Signed


def config_dir() -> Path:
    # The override exists for tests. The guard runs in the surgeon's
    # environment (the hook process), so an agent cannot redirect it.
    return Path(os.environ.get("ST_CONFIG_DIR") or Path.home() / ".config" / "surgical-team")


def load_config() -> JSON:
    path = config_dir() / "config.json"
    if not path.exists():
        return {}
    # setup writes a JSON object at this trust-root path.
    return cast(JSON, json.loads(path.read_text()))


def sign(payload: JSON) -> Signed:
    config = load_config()
    key, identity = config.get("key"), config.get("identity")
    if not key or not identity:
        raise StError("no signing key configured; run: st setup --key PATH --identity NAME")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "payload"
        path.write_bytes(canon(payload))
        result = subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE, "-q", str(path)],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode:
            raise StError(f"signing failed: {result.stderr.strip()}")
        signature = (Path(directory) / "payload.sig").read_text()
    return {"signer": identity, "payload": payload, "sig": signature}


_verify_cache: dict[tuple[str, str, bytes], tuple[bool, str]] = {}


def verify(signed: object, expect: Mapping[str, object] | None = None) -> tuple[bool, str]:
    if not isinstance(signed, dict) or not {"signer", "payload", "sig"} <= signed.keys():
        return False, "unsigned"
    # The key-presence check establishes the signed-record protocol. Values
    # retain their existing point-of-use failures if a record is malformed.
    record = cast(Signed, signed)
    payload = record["payload"]
    if expect:
        for key, value in expect.items():
            if payload.get(key) != value:
                return False, f"signed {key} does not match"
    allowed = config_dir() / "allowed_signers"
    if not allowed.exists():
        return False, f"no allowed_signers at {allowed}"
    cache_key = (record["signer"], record["sig"], canon(payload))
    if cache_key in _verify_cache:
        return _verify_cache[cache_key]
    with tempfile.TemporaryDirectory() as directory:
        signature_path = Path(directory) / "sig"
        signature_path.write_text(record["sig"])
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                str(record["signer"]),
                "-n",
                NAMESPACE,
                "-s",
                str(signature_path),
            ],
            check=False, input=canon(payload),
            capture_output=True,
        )
    verification = (True, "ok") if result.returncode == 0 else (False, "bad signature")
    _verify_cache[cache_key] = verification
    return verification
