"""Shared static types for control-plane records and JSON boundaries."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

# Persisted hook events, decision payloads, and heterogeneous attempt records
# are genuine JSON object boundaries whose keys vary by record kind.
JSON = dict[str, Any]

State = Literal[
    "drafted",
    "approved",
    "dispatched",
    "reported",
    "deferred",
    "accepted",
    "rejected",
    "cancelled",
]
Level = Literal["L0", "L1", "L2"]
ReportStatus = Literal["DONE", "PARTIAL", "BLOCKED", "DECLINED"]


class _AcceptanceCriterionRequired(TypedDict):
    text: str


class AcceptanceCriterion(_AcceptanceCriterionRequired, total=False):
    check: str


class Budget(TypedDict):
    minutes: int


class _SpecRequired(TypedDict):
    title: str
    role: str
    authority: Level
    intent: str
    scope: JSON
    acceptance: list[AcceptanceCriterion]
    budget: Budget
    depends_on: list[str]
    paths: list[str]


class Spec(_SpecRequired, total=False):
    push: bool
    inputs: JSON
    standing: str
    blind: list[str]
    check_timeout: int
    base: str


class Signed(TypedDict):
    signer: str
    payload: JSON
    sig: str


class Dispatch(TypedDict):
    at: str
    attempt: int
    authority_source: str
    workspace: str | None
    branch: str | None
    not_after: str


class _OrderRequired(TypedDict):
    id: str
    spec: Spec
    state: State
    revision: int
    attempt: int
    created: str
    history: list[JSON]


class Order(_OrderRequired, total=False):
    approval: Signed
    dispatch: Dispatch
    cancellation: Signed


class _LeaseEventRequired(TypedDict):
    at: str
    event: str


class LeaseEvent(_LeaseEventRequired, total=False):
    order: str
    attempt: int
    grant: str
    spec_sha: str
    role: str
    not_after: str
    reason: str


class ReportCriterion(TypedDict, total=False):
    met: bool
    evidence: str


class _ReportRequired(TypedDict):
    status: ReportStatus
    summary: str


class Report(_ReportRequired, total=False):
    criteria: list[ReportCriterion]
    evidence: str
    risks: str
    recommended: str
    out_of_scope: list[str]
    blocker: str
    cost: JSON
