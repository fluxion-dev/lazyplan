"""Install managed agent profiles for supported hosts.

Profiles are Markdown subagent files with generated frontmatter. A managed
file carries a marker comment; an unmarked user file is kept untouched unless
it is a managed profile being refreshed. Stdlib only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..core.policies.lanes import AGENT_ROLES
from . import textfile
from .data_text import data_text
from .host_models import HOST_SPECS, effective_tiers
from .profiles import Profile, load_all, opencode_models, resolve

MARKER = "<!-- managed by lazyplan:"
CLAUDE_TOOLS = "Read, Grep, Glob, Edit, Write, Bash"
CLAUDE_READ_TOOLS = {
    "scout": "Read, Grep, Glob",
    "reviewer": "Read, Grep, Glob, Bash",
}

ROLE_META: dict[str, dict[str, str]] = {
    "scout": {
        "description": "Read-only explorer for a lazyplan lane; reports facts, never edits.",
        "edit": "deny",
        "bash": "ask",
    },
    "implementer": {
        "description": "Implements one lane task with focused, cheap edits.",
        "edit": "allow",
        "bash": "allow",
    },
    "qa": {
        "description": "Runs lane suites, adds regression tests, and records evidence.",
        "edit": "allow",
        "bash": "allow",
    },
    "refactor": {
        "description": "Makes behavior-preserving cleanups inside one lane.",
        "edit": "allow",
        "bash": "allow",
    },
    "docs": {
        "description": "Updates the documentation a lane touched.",
        "edit": "allow",
        "bash": "allow",
    },
    "reviewer": {
        "description": "Read-only review of a lane diff against its criteria.",
        "edit": "deny",
        "bash": "allow",
    },
    "integrator": {
        "description": "Merges lane branches, resolves conflicts, and runs the full gates.",
        "edit": "allow",
        "bash": "allow",
    },
}


@dataclass
class AgentInstallResult:
    """Outcome of installing one host's profiles."""

    host: str
    scope: str
    installed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe payload."""
        return {
            "host": self.host,
            "scope": self.scope,
            "installed": list(self.installed),
            "kept": list(self.kept),
        }


def _targets(host: str, scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One profile path per role for a scope from the host registry."""
    spec = HOST_SPECS[host]
    return [path for role in AGENT_ROLES for path in spec.targets(scope, repo_root, home, role)]


def opencode_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One profile path per role for a scope."""
    return _targets("opencode", scope, repo_root, home)


def install_opencode(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every OpenCode profile for a scope."""
    return _install_host(
        "opencode",
        scope,
        opencode_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_opencode(role, profile, models, tiers),
    )


def claude_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One Claude Code profile path per role for a scope."""
    return _targets("claude", scope, repo_root, home)


def install_claude(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every Claude Code profile for a scope."""
    return _install_host(
        "claude",
        scope,
        claude_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_claude(role, profile, models, tiers),
    )


def _install_host(
    host: str,
    scope: str,
    targets: list[Path],
    profiles: dict[str, Profile],
    render: Callable[[str, Profile], str],
) -> AgentInstallResult:
    """Shared install loop: render one file per role and record its status."""
    result = AgentInstallResult(host, scope)
    for dest in targets:
        role = dest.stem.removeprefix("lazyplan-")
        written, status = _install_file(dest, render(role, profiles[role]))
        line = f"{dest} ({status})"
        if written:
            result.installed.append(line)
        else:
            result.kept.append(line)
    return result


def render_claude(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed Claude Code subagent file."""
    resolved = resolve(profile, "claude", models, tiers)
    meta = ROLE_META[role]
    tools = CLAUDE_READ_TOOLS.get(role, CLAUDE_TOOLS)
    lines = [
        "---",
        f"name: lazyplan-{role}",
        f"description: {meta['description']}",
        f"tools: {tools}",
    ]
    if resolved["model"]:
        lines.append(f"model: {resolved['model']}")
    if resolved["effort"]:
        lines.append(f"effort: {resolved['effort']}")
    if meta["edit"] == "deny":
        lines.append("permissionMode: plan")
    lines.extend(
        [
            "---",
            "",
            data_text(f"agents/common/{role}.md").rstrip(),
            "",
            f"{MARKER} claude {role} -->",
            "",
        ]
    )
    return "\n".join(lines)


def render_opencode(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed OpenCode subagent file."""
    resolved = resolve(profile, "opencode", models, tiers)
    meta = ROLE_META[role]
    lines = [
        "---",
        f"description: {meta['description']}",
        "mode: subagent",
    ]
    if resolved["model"]:
        lines.append(f"model: {resolved['model']}")
    if resolved["effort"]:
        lines.append(f"variant: {resolved['effort']}")
    lines.extend(
        [
            "permission:",
            f"  edit: {meta['edit']}",
            f"  bash: {meta['bash']}",
            "---",
            "",
            data_text(f"agents/common/{role}.md").rstrip(),
            "",
            f"{MARKER} opencode {role} -->",
            "",
        ]
    )
    return "\n".join(lines)


def profile_paths(scope: str, repo_root: Path | None, home: Path, agents: list[str]) -> list[Path]:
    """Every profile file the selected hosts would write."""
    paths: list[Path] = []
    if "opencode" in agents:
        paths.extend(opencode_targets(scope, repo_root, home))
    if "claude" in agents:
        paths.extend(claude_targets(scope, repo_root, home))
    return paths


def install_profiles(
    scope: str,
    repo_root: Path | None,
    home: Path,
    agents: list[str],
    db_path: str | Path,
    models: dict[str, str] | None = None,
) -> list[AgentInstallResult]:
    """Install every selected host's profiles for one scope."""
    if scope == "none" or not agents:
        return []
    loaded, _saved_tiers = load_all(db_path)
    opencode_defaults = models if models is not None else opencode_models(home, repo_root)
    tiers = effective_tiers(db_path, home, repo_root, agents)
    results: list[AgentInstallResult] = []
    if "opencode" in agents:
        results.append(install_opencode(scope, repo_root, home, loaded, opencode_defaults, tiers))
    if "claude" in agents:
        results.append(install_claude(scope, repo_root, home, loaded, None, tiers))
    return results


def _install_file(dest: Path, content: str) -> tuple[bool, str]:
    """Write a managed profile; keep an unmarked user file. Returns (handled, status)."""
    if not dest.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        textfile.write(dest, content)
        return True, "wrote"
    try:
        existing = textfile.read(dest)
    except OSError:
        return False, "unreadable"
    if existing == content:
        return True, "up-to-date"
    if MARKER in existing:
        textfile.write(dest, content)
        return True, "refreshed"
    return False, "kept user file"
