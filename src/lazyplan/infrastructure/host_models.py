"""Host model catalogs for setup.

Each adapter answers the same question without failing setup: which models
does this host expose, and which of them should the fast, standard, and deep
tiers use by default? Live catalogs are read from local binaries and config;
nothing here touches the network. Stdlib only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import textfile
from .profiles import HOSTS, TIERS

LABELS: dict[str, str] = {
    "opencode": "OpenCode",
    "claude": "Claude Code",
    "codex": "Codex",
    "gemini": "Gemini CLI",
    "cursor": "Cursor",
    "copilot": "Copilot CLI",
}

CLAUDE_ALIASES: tuple[str, ...] = ("haiku", "sonnet", "opus", "fable", "best", "opusplan")
TIMEOUT = 5
Which = Callable[[str], str | None]
Run = Callable[[list[str], int], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class HostCatalog:
    """One host's model candidates and tier defaults."""

    host: str
    label: str
    models: tuple[str, ...] = ()
    tier_defaults: dict[str, str] = field(default_factory=dict)
    source: str = ""
    warning: str = ""

    def to_dict(self) -> dict[str, object]:
        """JSON-safe payload."""
        return {
            "host": self.host,
            "label": self.label,
            "models": list(self.models),
            "tier_defaults": dict(self.tier_defaults),
            "source": self.source,
            "warning": self.warning,
        }


def discover(
    host: str,
    home: Path,
    repo_root: Path | None = None,
    *,
    which: Which | None = None,
    run: Run | None = None,
) -> HostCatalog:
    """Discover one host without raising on a missing binary or bad config."""
    if host not in HOSTS:
        raise ValueError(f"unknown host {host!r}; expected {'|'.join(HOSTS)}")
    finder = which or shutil.which
    runner = run or _run
    try:
        if host == "opencode":
            return _opencode(home, repo_root, finder, runner)
        if host == "claude":
            return _claude(home)
        if host == "codex":
            return _codex(home, finder, runner)
        if host == "gemini":
            return _gemini(home)
        if host == "cursor":
            return _cursor(home, repo_root)
        return _copilot(home)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return HostCatalog(
            host=host,
            label=LABELS[host],
            warning=f"could not read {LABELS[host]} models: {exc}",
        )


def discover_all(
    hosts: Iterable[str],
    home: Path,
    repo_root: Path | None = None,
    *,
    which: Which | None = None,
    run: Run | None = None,
) -> dict[str, HostCatalog]:
    """Discover every requested host, preserving the canonical host order."""
    wanted = set(hosts)
    return {
        host: discover(host, home, repo_root, which=which, run=run)
        for host in HOSTS
        if host in wanted
    }


def tier_defaults(host: str) -> dict[str, str]:
    """The packaged tier defaults for one host, before discovery."""
    from .profiles import DEFAULT_MODELS

    return {tier: DEFAULT_MODELS[tier].get(host, "") for tier in TIERS}


def effective_tiers(
    db_path: str | Path,
    home: Path,
    repo_root: Path | None,
    hosts: Iterable[str],
) -> dict[str, dict[str, str]]:
    """Merge the saved tier map with discovered defaults for one setup."""
    from .profiles import load_all

    _profiles, tiers = load_all(db_path)
    out = {tier: dict(tiers.get(tier, {})) for tier in TIERS}
    for host, catalog in discover_all(hosts, home, repo_root).items():
        for tier, model in catalog.tier_defaults.items():
            if model and not out[tier].get(host):
                out[tier][host] = model
    return out


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run one local catalog command with a short timeout."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _merge_models(primary: Iterable[str], fallback: Iterable[str]) -> tuple[str, ...]:
    """Keep the configured or live list first, then fall back to the rest."""
    return _unique(list(primary) + list(fallback))


def _opencode(
    home: Path,
    repo_root: Path | None,
    which: Which,
    run: Run,
) -> HostCatalog:
    binary = which("opencode")
    live: tuple[str, ...] = ()
    source = ""
    warning = ""
    if binary:
        try:
            proc = run([binary, "models"], TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            warning = f"`opencode models` failed: {exc}"
        else:
            if proc.returncode == 0:
                live = _unique(line for line in proc.stdout.splitlines() if line.strip())
                source = "opencode models"
            else:
                warning = f"`opencode models` exited {proc.returncode}"
    configured = _opencode_config(home, repo_root)
    main = configured.get("model", "")
    small = configured.get("small_model", "") or main
    defaults = {
        "fast": small,
        "standard": main or small,
        "deep": main or small,
    }
    models = _merge_models([small, main], live)
    if not source and configured:
        source = configured.get("source", "")
    if not models:
        warning = warning or "OpenCode is not detected; enter model IDs or keep the host default."
    return HostCatalog(
        host="opencode",
        label=LABELS["opencode"],
        models=models,
        tier_defaults=defaults,
        source=source,
        warning=warning,
    )


def _opencode_config(home: Path, repo_root: Path | None) -> dict[str, str]:
    """Read the first OpenCode config with a model or small_model."""
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.extend([repo_root / "opencode.json", repo_root / "opencode.jsonc"])
    candidates.extend(
        [
            home / ".config" / "opencode" / "opencode.json",
            home / ".config" / "opencode" / "opencode.jsonc",
        ]
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = _read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        model = _string(raw.get("model"))
        small = _string(raw.get("small_model"))
        if model or small:
            return {"model": model, "small_model": small, "source": str(path)}
    return {}


def _claude(home: Path) -> HostCatalog:
    settings = home / ".claude" / "settings.json"
    configured = ""
    source = "Claude Code aliases"
    if settings.is_file():
        try:
            raw = _read_json(settings)
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            configured = _string(raw.get("model"))
            if configured:
                source = str(settings)
    env_model = os.environ.get("ANTHROPIC_MODEL", "").strip()
    models = _merge_models([configured, env_model], CLAUDE_ALIASES)
    defaults = {"fast": "haiku", "standard": "sonnet", "deep": "opus"}
    return HostCatalog(
        host="claude",
        label=LABELS["claude"],
        models=models,
        tier_defaults=defaults,
        source=source,
    )


def _codex(home: Path, which: Which, run: Run) -> HostCatalog:
    binary = which("codex")
    live: tuple[str, ...] = ()
    source = ""
    warning = ""
    if binary:
        try:
            proc = run([binary, "debug", "models", "--bundled"], TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            warning = f"`codex debug models` failed: {exc}"
        else:
            if proc.returncode == 0:
                live = _codex_models(proc.stdout)
                source = "codex debug models"
            else:
                warning = f"`codex debug models` exited {proc.returncode}"
    configured = _codex_config(home)
    model = configured.get("model", "")
    defaults = {
        "fast": "",
        "standard": configured.get("default_subagent_model", "") or model,
        "deep": model,
    }
    models = _merge_models([model, configured.get("default_subagent_model", "")], live)
    if not source and configured:
        source = configured.get("source", "")
    if not models:
        warning = warning or "Codex models are not available; enter IDs or keep the host default."
    return HostCatalog(
        host="codex",
        label=LABELS["codex"],
        models=models,
        tier_defaults=defaults,
        source=source,
        warning=warning,
    )


def _codex_models(text: str) -> tuple[str, ...]:
    """Model slugs from `codex debug models` JSON."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return ()
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get("models") or raw.get("data") or []
    else:
        return ()
    out: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                out.append(str(row.get("slug") or row.get("id") or row.get("model") or ""))
    return _unique(out)


def _codex_config(home: Path) -> dict[str, str]:
    path = home / ".codex" / "config.toml"
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(textfile.read(path))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    model = _string(raw.get("model"))
    agents = raw.get("agents")
    default_subagent = ""
    if isinstance(agents, dict):
        default_subagent = _string(agents.get("default_subagent_model"))
    if not model and not default_subagent:
        return {}
    return {
        "model": model,
        "default_subagent_model": default_subagent,
        "source": str(path),
    }


def _gemini(home: Path) -> HostCatalog:
    settings = home / ".gemini" / "settings.json"
    configured = ""
    definitions: list[str] = []
    source = "Gemini CLI settings"
    if settings.is_file():
        try:
            raw = _read_json(settings)
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            model = raw.get("model")
            if isinstance(model, dict):
                configured = _string(model.get("name"))
            configs = raw.get("modelConfigs")
            if isinstance(configs, dict):
                found = configs.get("modelDefinitions")
                if isinstance(found, dict):
                    definitions.extend(str(key) for key in found)
            if configured or definitions:
                source = str(settings)
    models = _merge_models([configured], definitions)
    defaults = {"fast": "", "standard": configured, "deep": configured}
    warning = (
        "" if models else "Gemini CLI model list is not available; enter an ID or keep inherit."
    )
    return HostCatalog(
        host="gemini",
        label=LABELS["gemini"],
        models=models,
        tier_defaults=defaults,
        source=source,
        warning=warning,
    )


def _cursor(home: Path, repo_root: Path | None) -> HostCatalog:
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(repo_root / ".cursor" / "settings.json")
    candidates.extend([home / ".cursor" / "settings.json", home / ".cursor.json"])
    configured = ""
    source = "Cursor subagent defaults"
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = _read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            configured = _string(raw.get("model")) or _string(raw.get("defaultModel"))
            if configured:
                source = str(path)
                break
    defaults = {
        "fast": "inherit",
        "standard": configured or "inherit",
        "deep": configured or "inherit",
    }
    models = _merge_models([configured], ["inherit"])
    warning = "" if configured else "Cursor model IDs are entered manually; inherit is the default."
    return HostCatalog(
        host="cursor",
        label=LABELS["cursor"],
        models=models,
        tier_defaults=defaults,
        source=source,
        warning=warning,
    )


def _copilot(home: Path) -> HostCatalog:
    path = home / ".copilot" / "config.json"
    configured = ""
    source = "Copilot CLI defaults"
    if path.is_file():
        try:
            raw = _read_json(path)
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            configured = _string(raw.get("model"))
            if configured:
                source = str(path)
    defaults = {"fast": "", "standard": configured, "deep": configured}
    models = _unique([configured])
    warning = (
        ""
        if configured
        else "Copilot CLI does not expose a model list; enter an ID or keep the host default."
    )
    return HostCatalog(
        host="copilot",
        label=LABELS["copilot"],
        models=models,
        tier_defaults=defaults,
        source=source,
        warning=warning,
    )


def _read_json(path: Path) -> Any:
    """Read JSON or JSONC, tolerating comments and a UTF-8 BOM."""
    return json.loads(_strip_jsonc(textfile.read(path).lstrip("\ufeff")))


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments without touching string contents."""
    out: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        if char == "/" and nxt == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and nxt == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _string(value: object) -> str:
    return str(value or "").strip()
