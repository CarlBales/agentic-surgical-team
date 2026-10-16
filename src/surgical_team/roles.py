"""The role registry (E-1): roles are skills that declare metadata.surgical-team-role."""
from __future__ import annotations

import re
from pathlib import Path

from .model import NON_ROLE_FAMILIES, ROLE_NAME_RE

# Roles are not hardcoded: a role is any skill under the team's own skills/
# directory whose frontmatter declares `metadata.surgical-team-role` (other
# than `protocol`). That directory sits next to bin/st and is guard-protected,
# so an agent cannot add a role by writing a skill (E-1).
TEAM_ROOT = Path(__file__).resolve().parents[2]  # src/surgical_team/roles.py -> repo


def skill_family(skill_md: Path) -> str | None:
    """`metadata.surgical-team-role` from a SKILL.md frontmatter, if it is a valid team skill."""
    try:
        text = skill_md.read_text()
    except OSError:
        return None
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    frontmatter = match.group(1)
    name = re.search(r"^name:\s*(\S+)\s*$", frontmatter, re.M)
    family = re.search(
        r"^\s+surgical-team-role:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", frontmatter, re.M
    )
    if not (name and family) or name.group(1) != skill_md.parent.name:
        return None
    return family.group(1)


def team_roles(team_root: Path | None = None) -> dict[str, str]:
    """Role name -> family, read from the team's skills/ directory."""
    roles: dict[str, str] = {}
    skills = (team_root or TEAM_ROOT) / "skills"
    if not skills.is_dir():
        return roles
    for directory in sorted(skills.iterdir()):
        if not ROLE_NAME_RE.match(directory.name):
            continue
        family = skill_family(directory / "SKILL.md")
        if family and family not in NON_ROLE_FAMILIES:
            roles[directory.name] = family
    return roles


def is_role(name: str) -> bool:
    return bool(ROLE_NAME_RE.match(name)) and name in team_roles()
