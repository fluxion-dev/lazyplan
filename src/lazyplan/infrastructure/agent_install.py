"""Install managed agent profiles for supported hosts.

Profiles are Markdown subagent files with generated frontmatter. A managed
file carries a marker comment; an unmarked user file is kept untouched unless
it is a managed profile being refreshed. Stdlib only.
"""

from __future__ import annotations

import json
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
GEMINI_READ_TOOLS = {
    "scout": ("read_file", "grep_search", "glob", "list_directory"),
    "reviewer": ("read_file", "grep_search", "glob", "list_directory", "run_shell_command"),
}
COPILOT_READ_TOOLS = {
    "scout": ("read", "grep", "glob"),
    "reviewer": ("read", "grep", "glob", "execute"),
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


def codex_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One Codex custom-agent path per role for a scope."""
    return _targets("codex", scope, repo_root, home)


def install_codex(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every Codex profile for a scope."""
    return _install_host(
        "codex",
        scope,
        codex_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_codex(role, profile, models, tiers),
    )


def gemini_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One Gemini subagent path per role for a scope."""
    return _targets("gemini", scope, repo_root, home)


def install_gemini(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every Gemini profile for a scope."""
    return _install_host(
        "gemini",
        scope,
        gemini_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_gemini(role, profile, models, tiers),
    )


def cursor_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One Cursor subagent path per role for a scope."""
    return _targets("cursor", scope, repo_root, home)


def install_cursor(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every Cursor profile for a scope."""
    return _install_host(
        "cursor",
        scope,
        cursor_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_cursor(role, profile, models, tiers),
    )


def copilot_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """One Copilot agent path per role for a scope."""
    return _targets("copilot", scope, repo_root, home)


def install_copilot(
    scope: str,
    repo_root: Path | None,
    home: Path,
    profiles: dict[str, Profile],
    models: dict[str, str] | None = None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> AgentInstallResult:
    """Write or refresh every Copilot profile for a scope."""
    return _install_host(
        "copilot",
        scope,
        copilot_targets(scope, repo_root, home),
        profiles,
        lambda role, profile: render_copilot(role, profile, models, tiers),
    )


def _markdown_file(role: str, host: str, front: list[str], body: str) -> str:
    """Render one managed Markdown profile with a shared marker."""
    lines = ["---", *front, "---", "", body.rstrip(), "", f"{MARKER} {host} {role} -->", ""]
    return "\n".join(lines)


def _role_for(path: Path) -> str:
    """Recover the role from a managed profile filename."""
    name = path.name
    prefix = "lazyplan-"
    if not name.startswith(prefix):
        return ""
    rest = name[len(prefix) :]
    for suffix in (".agent.md", ".md", ".toml"):
        if rest.endswith(suffix):
            return rest[: -len(suffix)]
    return rest


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
        role = _role_for(dest)
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
    front = [
        f"name: lazyplan-{role}",
        f"description: {meta['description']}",
        f"tools: {tools}",
    ]
    if resolved["model"]:
        front.append(f"model: {resolved['model']}")
    if resolved["effort"]:
        front.append(f"effort: {resolved['effort']}")
    if meta["edit"] == "deny":
        front.append("permissionMode: plan")
    return _markdown_file(role, "claude", front, data_text(f"agents/common/{role}.md"))


def render_copilot(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed Copilot CLI agent file."""
    resolved = resolve(profile, "copilot", models, tiers)
    meta = ROLE_META[role]
    front = [
        f"name: lazyplan-{role}",
        f"description: {meta['description']}",
    ]
    if resolved["model"]:
        front.append(f"model: {resolved['model']}")
    tools = COPILOT_READ_TOOLS.get(role)
    if tools:
        rendered = ", ".join(f'"{tool}"' for tool in tools)
        front.append(f"tools: [{rendered}]")
        front.append("strict-tools-list: true")
    return _markdown_file(role, "copilot", front, data_text(f"agents/common/{role}.md"))


def render_cursor(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed Cursor subagent file."""
    resolved = resolve(profile, "cursor", models, tiers)
    meta = ROLE_META[role]
    front = [
        f"name: lazyplan-{role}",
        f"description: {meta['description']}",
        f"model: {resolved['model'] or 'inherit'}",
    ]
    if meta["edit"] == "deny":
        front.append("readonly: true")
    return _markdown_file(role, "cursor", front, data_text(f"agents/common/{role}.md"))


def render_gemini(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed Gemini CLI subagent file."""
    resolved = resolve(profile, "gemini", models, tiers)
    meta = ROLE_META[role]
    front = [
        f"name: lazyplan-{role}",
        f"description: {meta['description']}",
        f"model: {resolved['model'] or 'inherit'}",
    ]
    tools = GEMINI_READ_TOOLS.get(role)
    if tools:
        front.append("tools:")
        front.extend(f"  - {tool}" for tool in tools)
    return _markdown_file(role, "gemini", front, data_text(f"agents/common/{role}.md"))


def _toml_string(value: str) -> str:
    """One TOML basic string, escaped like JSON."""
    return json.dumps(value, ensure_ascii=False)


def render_codex(
    role: str,
    profile: Profile,
    models: dict[str, str] | None,
    tiers: dict[str, dict[str, str]] | None = None,
) -> str:
    """One managed Codex custom-agent TOML file."""
    resolved = resolve(profile, "codex", models, tiers)
    meta = ROLE_META[role]
    lines = [
        f"# managed by lazyplan: codex {role}",
        f"name = {_toml_string(f'lazyplan-{role}')}",
        f"description = {_toml_string(meta['description'])}",
    ]
    if resolved["model"]:
        lines.append(f"model = {_toml_string(resolved['model'])}")
    if resolved["effort"]:
        lines.append(f"model_reasoning_effort = {_toml_string(resolved['effort'])}")
    if meta["edit"] == "deny":
        lines.append('sandbox_mode = "read-only"')
    instructions = data_text(f"agents/common/{role}.md").rstrip()
    lines.extend(
        [
            f"developer_instructions = {_toml_string(instructions)}",
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
    front = [
        f"description: {meta['description']}",
        "mode: subagent",
    ]
    if resolved["model"]:
        front.append(f"model: {resolved['model']}")
    if resolved["effort"]:
        front.append(f"variant: {resolved['effort']}")
    front.extend(
        [
            "permission:",
            f"  edit: {meta['edit']}",
            f"  bash: {meta['bash']}",
        ]
    )
    return _markdown_file(role, "opencode", front, data_text(f"agents/common/{role}.md"))


def profile_paths(scope: str, repo_root: Path | None, home: Path, agents: list[str]) -> list[Path]:
    """Every profile file the selected hosts would write."""
    return [path for host in agents for path in _targets(host, scope, repo_root, home)]


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
    for host in agents:
        installer = INSTALLERS.get(host)
        if installer is None:
            continue
        models = opencode_defaults if host == "opencode" else None
        results.append(installer(scope, repo_root, home, loaded, models, tiers))
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
    if "managed by lazyplan:" in existing:
        textfile.write(dest, content)
        return True, "refreshed"
    return False, "kept user file"


INSTALLERS: dict[str, Callable[..., AgentInstallResult]] = {
    "opencode": install_opencode,
    "claude": install_claude,
    "codex": install_codex,
    "gemini": install_gemini,
    "cursor": install_cursor,
    "copilot": install_copilot,
}
