"""Install and remove lazyplan lifecycle hooks for detected agent hosts.

Every write is idempotent, backed up, and marked by the command it writes.
Unmarked user hooks are never touched. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import hook_hosts, skills, textfile
from .setup_layout import _backup_file, _new_backup_dir

HOSTS = ("opencode", "claude", "gemini", "codex", "cursor")
MARKER = "lpui hook"
PLUGIN_NAME = "lazyplan.js"


@dataclass(frozen=True)
class Spec:
    """One host surface that receives managed hook entries."""

    host: str
    path: Path
    kind: str  # nested | flat | plugin


def command(host: str, event: str) -> str:
    """The exact managed command written into host config."""
    return f"{MARKER} {event} --host {host}"


def specs(home: Path | None = None) -> list[Spec]:
    """Every supported host surface under this home."""
    home = home or Path.home()
    return [
        Spec("opencode", home / ".config" / "opencode" / "plugins" / PLUGIN_NAME, "plugin"),
        Spec("claude", home / ".claude" / "settings.json", "nested"),
        Spec("gemini", home / ".gemini" / "settings.json", "nested"),
        Spec("codex", home / ".codex" / "hooks.json", "nested"),
        Spec("cursor", home / ".cursor" / "hooks.json", "flat"),
    ]


def preview(home: Path | None = None, hosts: list[str] | None = None) -> list[Spec]:
    """Host hook surfaces that install would touch, without writing."""
    home = home or Path.home()
    wanted = set(hosts) if hosts is not None else set(detected(home))
    return [spec for spec in specs(home) if spec.host in wanted]


def detected(home: Path | None = None) -> list[str]:
    """Supported hosts that are actually present, in stable order."""
    found = {host.key for host in skills.detect_agents(home) if host.detected}
    return [host for host in HOSTS if host in found]


def _managed(entry: object, host: str) -> bool:
    if not isinstance(entry, dict):
        return False
    text = json.dumps(entry)
    return MARKER in text and f"--host {host}" in text


def _nested_entries(host: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for event, native in hook_hosts.EVENTS[host].items():
        out[native] = [
            {
                "matcher": hook_hosts.matcher(host, native),
                "hooks": [{"type": "command", "command": command(host, event)}],
            }
        ]
    return out


def _flat_entries(host: str) -> dict[str, list[dict]]:
    return {
        native: [{"command": command(host, event)}]
        for event, native in hook_hosts.EVENTS[host].items()
    }


def _add_entries(data: dict, entries: dict[str, list[dict]]) -> dict:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    for native, managed in entries.items():
        existing = hooks.get(native)
        hooks[native] = (existing if isinstance(existing, list) else []) + managed
    data["hooks"] = hooks
    return data


def _merge_nested(data: dict, host: str) -> dict:
    return _add_entries(_strip_nested(data, host), _nested_entries(host))


def _merge_flat(data: dict, host: str) -> dict:
    data = _add_entries(_strip_flat(data, host), _flat_entries(host))
    data.setdefault("version", 1)
    return data


def _strip_nested(data: dict, host: str) -> dict:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data
    for native in list(hooks):
        existing = hooks[native]
        if not isinstance(existing, list):
            continue
        kept: list[object] = []
        for group in existing:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group["hooks"] = [h for h in group["hooks"] if not _managed(h, host)]
                if not group["hooks"]:
                    continue
            if not _managed(group, host):
                kept.append(group)
        if kept:
            hooks[native] = kept
        else:
            hooks.pop(native)
    if not hooks:
        data.pop("hooks", None)
    return data


def _strip_flat(data: dict, host: str) -> dict:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data
    for native in list(hooks):
        existing = hooks[native]
        if isinstance(existing, list):
            kept = [item for item in existing if not _managed(item, host)]
            if kept:
                hooks[native] = kept
            else:
                hooks.pop(native)
    if not hooks:
        data.pop("hooks", None)
    return data


def _plugin_text() -> str:
    return """// lazyplan lifecycle plugin (managed by lpui setup; remove with --no-hooks)
import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

const run = async (directory, event, extra = "") => {
  const args = ["hook", event, "--host", "opencode"]
  if (extra) args.push("--command", extra)
  try {
    const { stdout } = await execFileAsync("lpui", args, {
      cwd: directory,
      timeout: 5000,
    })
    return stdout.trim()
  } catch {
    return ""
  }
}

export default {
  id: "lazyplan",
  async setup(ctx) {
    const directory = ctx.location?.directory ?? process.cwd()
    const seen = new Set()
    let pending = ""
    await ctx.tool.hook("execute.after", async (event) => {
      if (String(event.tool).toLowerCase() !== "bash") return
      const command = event.input?.command ?? event.input?.args?.command ?? ""
      if (!command.includes("git commit")) return
      const text = await run(directory, "post-tool", command)
      if (text) pending = text
    })
    await ctx.session.hook("context", async (event) => {
      if (pending) {
        event.system.push({ type: "text", text: pending })
        pending = ""
        return
      }
      const key = event.sessionID ?? event.session?.id ?? "default"
      if (seen.has(key)) return
      const text = await run(directory, "session-start")
      if (text) {
        event.system.push({ type: "text", text })
        seen.add(key)
      }
    })
  },
}
"""


def _read(path: Path) -> dict:
    try:
        raw = textfile.read(path)
    except OSError:
        return {}
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _install_spec(spec: Spec, backup_dir: Path) -> bool:
    if spec.kind == "plugin":
        if spec.path.is_file() and textfile.read(spec.path) == _plugin_text():
            return False
        if spec.path.is_file():
            _backup_file(backup_dir, spec.path)
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        textfile.write(spec.path, _plugin_text())
        return True
    data = _read(spec.path)
    before = json.dumps(data, sort_keys=True)
    merged = (
        _merge_nested(data, spec.host) if spec.kind == "nested" else _merge_flat(data, spec.host)
    )
    if json.dumps(merged, sort_keys=True) == before:
        return False
    if spec.path.is_file():
        _backup_file(backup_dir, spec.path)
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    textfile.write(spec.path, json.dumps(merged, indent=2) + "\n")
    return True


def _remove_spec(spec: Spec, backup_dir: Path) -> bool:
    if not spec.path.is_file():
        return False
    if spec.kind == "plugin":
        _backup_file(backup_dir, spec.path)
        spec.path.unlink()
        return True
    data = _read(spec.path)
    before = json.dumps(data, sort_keys=True)
    stripped = (
        _strip_nested(data, spec.host) if spec.kind == "nested" else _strip_flat(data, spec.host)
    )
    if json.dumps(stripped, sort_keys=True) == before:
        return False
    _backup_file(backup_dir, spec.path)
    textfile.write(spec.path, json.dumps(stripped, indent=2) + "\n")
    return True


def install(home: Path | None = None, hosts: list[str] | None = None) -> dict:
    """Write managed hook entries for the chosen hosts, backing up every file."""
    home = home or Path.home()
    backup_dir = _new_backup_dir(home)
    changed: list[str] = []
    skipped: list[dict] = []
    for spec in preview(home, hosts):
        try:
            if _install_spec(spec, backup_dir):
                changed.append(str(spec.path))
        except (OSError, ValueError) as exc:
            skipped.append({"path": str(spec.path), "reason": str(exc)})
    backups = [str(backup_dir)] if backup_dir.exists() else []
    return {"installed": changed, "backups": backups, "skipped": skipped}


def remove(home: Path | None = None, hosts: list[str] | None = None) -> dict:
    """Remove only managed entries, backing up every touched file."""
    home = home or Path.home()
    wanted = set(hosts) if hosts is not None else set(HOSTS)
    backup_dir = _new_backup_dir(home)
    changed: list[str] = []
    skipped: list[dict] = []
    for spec in specs(home):
        if spec.host not in wanted:
            continue
        try:
            if _remove_spec(spec, backup_dir):
                changed.append(str(spec.path))
        except (OSError, ValueError) as exc:
            skipped.append({"path": str(spec.path), "reason": str(exc)})
    backups = [str(backup_dir)] if backup_dir.exists() else []
    return {"removed": changed, "backups": backups, "skipped": skipped}
