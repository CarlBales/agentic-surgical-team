"""Host tool names, and the read-only rules for external sources (E-3)."""
from __future__ import annotations

import re


def aws_op(name: object) -> str:
    """Normalize an AWS CLI operation name to kebab case.

    DescribeInstances -> describe-instances.
    """
    value = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", str(name)).replace("_", "-")
    return value.lower()


def aws_op_refusal(op: str) -> str | None:
    op = aws_op(op)
    if not op.startswith(AWS_READ_VERBS):
        verbs = ", ".join(verb.rstrip("-") for verb in AWS_READ_VERBS)
        return f"{op} is not a read (allowed verbs: {verbs})"
    if AWS_SENSITIVE.search(op):
        return f"{op} can expose secrets, credentials, or object contents; it is never a source"
    return None


TOOL_ALIASES: dict[str, str] = {
    "write": "write",
    "fs_write": "write",
    "fsWrite": "write",
    "read": "read",
    "fs_read": "read",
    "fsRead": "read",
    "shell": "shell",
    "execute_bash": "shell",
    "executeBash": "shell",
    "execute_cmd": "shell",
    "executeCmd": "shell",
    "subagent": "subagent",
    "agent_crew": "subagent",
    "use_subagent": "subagent",
    "task": "todo_list",
    "todo": "todo_list",
    "todo_list": "todo_list",
    "web_search": "web_search",
    "websearch": "web_search",
    "web_fetch": "web_fetch",
    "webfetch": "web_fetch",
    "grep": "grep",
    "glob": "glob",
    "code": "code",
    "summary": "summary",
    "use_aws": "use_aws",
    "aws": "use_aws",
}
KNOWN_TOOLS = {
    "read",
    "write",
    "shell",
    "subagent",
    "grep",
    "glob",
    "code",
    "web_search",
    "web_fetch",
    "todo_list",
    "summary",
}

# E-3: tools outside KNOWN_TOOLS are denied unless an order the role holds
# grants them in inputs.sources, under a surgeon approval of that exact spec.
AWS_TOOL = "use_aws"
AWS_READ_VERBS = (
    "describe-",
    "get-",
    "list-",
    "filter-",
    "lookup-",
    "search-",
    "batch-get-",
    "head-",
)

# Reads that hand out secrets, credentials, or whole objects to disk are not
# "read-only" for this purpose.
AWS_SENSITIVE = re.compile(
    r"secret|password|token|credential|login|decrypt|parameter|"
    r"private|key-pair|sign|session|get-object"
)
# Kiro reports MCP tools as names such as @server/tool; Cursor reports
# MCP:<tool> and omits the configured server name. Keep both host forms
# explicit so check_source can compare the whole raw name without a basename
# fallback across servers or hosts.
_SOURCE_PART = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
SOURCE_NAME_RE = re.compile(
    rf"^(?:@?{_SOURCE_PART}(?:/{_SOURCE_PART})?|MCP:{_SOURCE_PART})$"
)
CODE_WRITE_OPS = {"pattern_rewrite", "rename_symbol", "apply_code_action", "format"}


def normalize_tool(name: object) -> str:
    normalized = str(name or "").strip()
    if normalized.startswith("@builtin/"):
        normalized = normalized[len("@builtin/") :]
    return TOOL_ALIASES.get(
        normalized, TOOL_ALIASES.get(normalized.lower(), normalized.lower())
    )
