"""What each host's role agents are told: the prompt and the inlined skills."""
from __future__ import annotations

import re
from pathlib import Path

from .model import AGENT_PREFIX
from .roles import team_roles

ROLE_DESCRIPTIONS = {
    "copilot": "Surgical team copilot: the surgeon's design partner and the only dispatcher",
    "editor": "Surgical team editor: finishes the surgeon's documents",
    "toolsmith": "Surgical team toolsmith: dev environment, scripts, CI, agent tooling",
    "tester": "Surgical team tester: adversarial tests from the spec",
}
FAMILY_DESCRIPTIONS = {
    "language-lawyer": "language specialist",
    "platform-lawyer": "platform specialist",
    "reviewer": "independent reviewer",
    "analyst": "evidence analyst",
    "archivist": "keeps the knowledge corpus consistent",
}


def role_description(role: str, team_root: Path) -> str:
    return ROLE_DESCRIPTIONS.get(role) or (
        f"Surgical team {role}: "
        f"{FAMILY_DESCRIPTIONS.get(team_roles(team_root).get(role, ''), 'specialist')}"
    )


def role_prompt(role: str, team_root: Path, host: str = "kiro") -> str:
    st = str(team_root / "bin" / "st")
    prompt = (
        f"You are the surgical team's {role}. The surgeon is the human; you serve them. "
        "Follow the protocol and your role skill, both loaded as context. The control "
        f"plane is `{st}` (also `st` if on PATH). A preToolUse guard enforces your "
        "authority from the ledger. A blocked call is outside your order: never try to "
        "get the same effect another way. Continue with the work that is within the "
        "order, and quote the block in your report."
    )
    if role != "copilot":
        prompt += (
            " You were dispatched with a briefing naming exactly one work order. "
            "Work only in its workspace, and finish by filing `st report <WO>` and "
            "returning the same report as your summary."
        )
        if host == "cursor":
            prompt += " Do not launch subagents; the guard refuses them for specialists."
    else:
        prompt += (
            " You are the only agent that dispatches. Specialists run only as "
            f"{AGENT_PREFIX}<role> subagents carrying an `st dispatch` briefing."
        )
        if host == "cursor":
            prompt += (
                " Cursor team sessions are supported and verified on the Cursor Agent CLI "
                "only. Do not run this team session in the Cursor IDE until it is verified; "
                "this project's IDE probe did not route tool calls through user-level guard "
                "hooks, so the guard may be absent. Never use Cursor cloud/background agents "
                "on a team project; Cursor does not load this user-level guard there."
                f" Launch each one with the Task tool: subagent_type `{AGENT_PREFIX}<role>`, "
                "prompt the briefing verbatim. Every other subagent type, including the "
                "built-in explore and generalPurpose agents, is refused."
            )
    return prompt


def copilot_command(team_root: Path) -> str:
    """The Cursor Agent CLI `/st` command: typing it starts a team session.

    The guard recognizes the session from the expanded command in the chat's
    transcript, so this text is also the opt-in; everything else in a project
    with a ledger stays a plain chat.
    """
    return "\n\n".join([
        "This Cursor Agent CLI chat is now a surgical team session: you are st-copilot.",
        ("Cursor team sessions are supported and verified on the Cursor Agent CLI only. "
         "Do not run this team session in the Cursor IDE until it is verified; its tool "
         "calls were not observed reaching user-level hooks, so the guard may be absent. "
         f"See `{team_root / 'README.md'}#limits-and-open-questions`."),
        role_prompt("copilot", team_root, host="cursor"),
        inlined_skills("copilot", team_root),
        f"Begin by running `{team_root / 'bin' / 'st'} status`, then scrub in as your skill "
        "describes. Anything the surgeon typed after /st follows below.",
    ]) + "\n"


def skill_body(skill_md: Path) -> str:
    """A SKILL.md without its frontmatter."""
    text = skill_md.read_text()
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


def inlined_skills(role: str, team_root: Path) -> str:
    """The protocol and the role skill as one context block, for hosts that
    cannot load skill files by reference (Cursor)."""
    skills = team_root / "skills"
    protocol = skills / "surgical-team-protocol"
    references = sorted((protocol / "references").glob("*.md"))
    parts = [
        f"The skills below are inlined from `{skills}`; relative links in them resolve "
        "against that directory. Read the protocol references when the protocol points "
        "to them:\n" + "\n".join(f"- `{path}`" for path in references),
    ]
    for skill in (protocol, skills / role):
        parts.append(f"# Skill: {skill.name} (`{skill / 'SKILL.md'}`)\n\n"
                     + skill_body(skill / "SKILL.md"))
    return "\n\n".join(parts)
