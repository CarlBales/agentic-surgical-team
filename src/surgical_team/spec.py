"""Order spec validation, review targets (E-4), and sources (E-3)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import cast

from .authority import decision_status
from .gitutil import git
from .ledger import Ledger
from .model import DEC_RE, LEVELS, WO_RE, StError
from .roles import is_role, team_roles
from .tools import AWS_TOOL, KNOWN_TOOLS, SOURCE_NAME_RE, aws_op_refusal, normalize_tool
from .types import JSON, Spec

REF_RE = re.compile(r"^[A-Za-z0-9._/@^~{}-]+$")


def pin_review_target(ledger: Ledger, inputs: JSON) -> list[str]:
    """E-4: resolve inputs.review {base, head} to commit SHAs, in place.

    Pinning at draft time means the surgeon's approval (which hashes the spec)
    covers exact commits, not refs that can move after approval.
    """
    review = inputs.get("review")
    if (
        not isinstance(review, dict)
        or set(review) - {"base", "head"}
        or not review.get("base")
        or not review.get("head")
    ):
        return ['inputs.review must be {"base": <ref>, "head": <ref>}']
    errors: list[str] = []
    pinned: dict[str, str] = {}
    for key in ("base", "head"):
        ref = str(review[key])
        if ref.startswith("-") or not REF_RE.match(ref):
            errors.append(f"inputs.review.{key}: {ref!r} is not a git ref")
            continue
        output = git(
            ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            ledger.root,
            check=False,
        )
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", output):
            errors.append(
                f"inputs.review.{key}: {ref!r} is not a commit in this repository"
            )
            continue
        pinned[key] = output
    if errors:
        return errors
    if pinned["base"] == pinned["head"]:
        return ["inputs.review: base and head are the same commit; there is nothing to review"]
    if not git(["merge-base", pinned["base"], pinned["head"]], ledger.root, check=False):
        return ["inputs.review: base and head share no history"]
    inputs["review"] = pinned
    return []


def validate_sources(sources: object) -> list[str]:
    """E-3: inputs.sources names the read-only external tools an order may use."""
    if not isinstance(sources, list) or not sources:
        return ["inputs.sources must be a non-empty list"]
    errors: list[str] = []
    for index, source in enumerate(sources, 1):
        where = f"inputs.sources[{index}]"
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("tool"), str)
            or not source["tool"]
        ):
            errors.append(f"{where} needs a tool name")
            continue
        tool = source["tool"]
        if normalize_tool(tool) == AWS_TOOL:
            if set(source) - {"tool", "service", "operations", "region", "profile"}:
                errors.append(f"{where}: use_aws takes service, operations, region, profile")
            if (
                not re.fullmatch(r"[a-z0-9-]+", str(source.get("service", "")))
                or source.get("service") == "s3"
            ):
                errors.append(
                    f"{where}: use_aws needs a service (the high-level `s3` "
                    "command copies files and is not a source; use s3api)"
                )
            operations = source.get("operations")
            if not isinstance(operations, list) or not operations:
                errors.append(f"{where}: use_aws needs a list of operations")
            else:
                errors += [
                    f"{where}: {why}"
                    for why in filter(None, map(aws_op_refusal, operations))
                ]
        elif normalize_tool(tool) in KNOWN_TOOLS or not SOURCE_NAME_RE.match(tool):
            errors.append(f"{where}: {tool!r} is not an external tool name")
        elif source.get("readonly") is not True or set(source) - {"tool", "readonly", "note"}:
            errors.append(
                f'{where}: an MCP tool source must say "readonly": true; the '
                "surgeon attests to that by approving the spec"
            )
    return errors


SPEC_KEYS = {"title", "role", "authority", "push", "intent", "scope", "inputs", "acceptance",
             "budget", "paths", "depends_on", "blind", "standing", "base", "check_timeout"}
SCOPE_KEYS = {"in", "out"}
INPUT_KEYS = {"files", "decisions", "orders", "review", "sources"}


def unknown_keys(obj: JSON, allowed: set[str], where: str) -> list[str]:
    extra = sorted(set(obj) - allowed)
    return [f"{where}: unknown field {k!r} (allowed: {', '.join(sorted(allowed))})"
            for k in extra]


def validate_spec(ledger: Ledger, spec: object) -> Spec:
    errors: list[str] = []
    if not isinstance(spec, dict):
        raise StError("order spec must be a JSON object")
    # M-3: unknown keys are refused, not ignored. A misspelled `blind` or
    # `standing` would otherwise drop a constraint without a word.
    errors += unknown_keys(spec, SPEC_KEYS, "spec")
    for key, allowed in (("scope", SCOPE_KEYS), ("inputs", INPUT_KEYS), ("budget", {"minutes"})):
        if isinstance(spec.get(key), dict):
            errors += unknown_keys(spec[key], allowed, key)
    for i, item in enumerate(spec.get("acceptance") or [], 1):
        if isinstance(item, dict):
            errors += unknown_keys(item, {"text", "check"}, f"acceptance[{i}]")
    title = spec.get("title", "")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    role = spec.get("role", "")
    if not is_role(str(role)):
        errors.append(f"role {role!r} is not a team role ({', '.join(team_roles())})")
    authority = spec.get("authority", "L0")
    if authority == "L3":
        errors.append(
            "L3 is the surgeon's; no order can grant it. Stage the work at L2 "
            "and describe what the surgeon must run"
        )
    elif authority not in LEVELS:
        errors.append(f"authority must be L0, L1 or L2, not {authority!r}")
    if not str(spec.get("intent", "")).strip():
        errors.append("intent is required")
    scope = spec.get("scope") or {}
    if not isinstance(scope, dict) or not scope.get("in"):
        errors.append("scope.in must list what is in scope")
    acceptance = spec.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        errors.append("acceptance must be a non-empty list")
    else:
        for index, acceptance_item in enumerate(acceptance, 1):
            criterion = acceptance_item
            if isinstance(criterion, str):
                criterion = {"text": criterion}
                acceptance[index - 1] = criterion
            if not isinstance(criterion, dict) or not str(criterion.get("text", "")).strip():
                errors.append(f"acceptance[{index}] needs text")
            elif "check" in criterion and not (
                isinstance(criterion["check"], str) and criterion["check"].strip()
            ):
                errors.append(f"acceptance[{index}].check must be a non-empty command")
    budget = spec.get("budget") or {}
    if not isinstance(budget.get("minutes"), int) or budget["minutes"] <= 0:
        errors.append("budget.minutes must be a positive integer")
    if spec.get("push") and authority != "L2":
        errors.append("push is only possible at L2")
    for dependency in spec.get("depends_on", []) or []:
        if not WO_RE.match(str(dependency)) or not ledger.order_path(dependency).exists():
            errors.append(f"depends_on: no such order {dependency}")
    inputs = spec.get("inputs") or {}
    for decision in inputs.get("decisions", []) or []:
        status, _ = decision_status(ledger, decision)
        if status != "active":
            errors.append(f"inputs.decisions: {decision} is {status}")
    if "review" in inputs:
        errors += pin_review_target(ledger, inputs)
    if "sources" in inputs:
        errors += validate_sources(inputs["sources"])
    if spec.get("standing") and not DEC_RE.match(str(spec["standing"])):
        errors.append("standing must be a DEC-NNN id")
    blind = spec.get("blind", [])
    if not isinstance(blind, list) or not all(
        isinstance(path, str) and path and not path.startswith("/") and ".." not in path
        for path in blind
    ):
        errors.append("blind must be a list of repo-relative paths or globs")
    if errors:
        raise StError("invalid order:\n  - " + "\n  - ".join(errors))
    spec.setdefault("authority", "L0")
    spec.setdefault("depends_on", [])
    spec.setdefault("paths", [])
    spec.setdefault("scope", {}).setdefault("out", [])
    # The checks above establish all required Spec fields and normalize defaults.
    return cast(Spec, spec)


def read_json_input(args: argparse.Namespace) -> object:
    source = Path(args.file).read_text() if getattr(args, "file", None) else sys.stdin.read()
    try:
        value: object = json.loads(source)
        return value
    except json.JSONDecodeError as error:
        raise StError(f"input is not valid JSON: {error}")
