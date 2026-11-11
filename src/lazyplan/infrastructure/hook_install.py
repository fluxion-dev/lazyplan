"""Install and remove lazyplan lifecycle hooks for detected agent hosts.

Every write is idempotent, backed up, and marked by the command it writes.
Unmarked user hooks are never touched. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.policies.hooks import DEFAULT_MODE, normalize_mode
from . import hook_hosts, skills, textfile
from .backup import backup_file, new_backup_dir

HOSTS = ("opencode", "claude", "gemini", "codex", "cursor")
MARKER = "lpui hook"
PLUGIN_MARKER = "lazyplan lifecycle plugin"
PLUGIN_NAME = "lazyplan.js"


@dataclass(frozen=True)
class Spec:
    """One host surface that receives managed hook entries."""

    host: str
    path: Path
    kind: str  # nested | flat | plugin


def command(host: str, event: str, mode: str = DEFAULT_MODE) -> str:
    """The exact managed command written into host config."""
    return f"{MARKER} {event} --host {host} --mode {normalize_mode(mode)}"


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


def installed_events(home: Path | None = None, host: str = "") -> set[str]:
    """Return the managed events present for one host, read-only."""
    home = home or Path.home()
    events: set[str] = set()
    for spec in specs(home):
        if spec.host != host or not spec.path.is_file():
            continue
        try:
            text = textfile.read(spec.path)
        except OSError:
            continue
        if spec.kind == "plugin":
            if PLUGIN_MARKER in text or MARKER in text:
                events.add("plugin")
            continue
        for event in hook_hosts.EVENTS.get(host, {}):
            if f"{MARKER} {event} --host {host}" in text:
                events.add(event)
    return events


def _managed(entry: object, host: str) -> bool:
    if not isinstance(entry, dict):
        return False
    text = json.dumps(entry)
    return MARKER in text and f"--host {host}" in text


def _nested_entries(host: str, mode: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for event, native in hook_hosts.EVENTS[host].items():
        out[native] = [
            {
                "matcher": hook_hosts.matcher(host, native),
                "hooks": [{"type": "command", "command": command(host, event, mode)}],
            }
        ]
    return out


def _flat_entries(host: str, mode: str) -> dict[str, list[dict]]:
    return {
        native: [{"command": command(host, event, mode)}]
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


def _merge_nested(data: dict, host: str, mode: str) -> dict:
    return _add_entries(_strip_nested(data, host), _nested_entries(host, mode))


def _merge_flat(data: dict, host: str, mode: str) -> dict:
    data = _add_entries(_strip_flat(data, host), _flat_entries(host, mode))
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


def plugin_text(mode: str = DEFAULT_MODE) -> str:
    """Return the managed OpenCode plugin source."""
    return """// lazyplan lifecycle plugin (managed by lpui setup; remove with --no-hooks)
import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)
const MODE = "__MODE__"

const run = async (directory, event, extra = "") => {
  const args = ["hook", event, "--host", "opencode", "--mode", MODE]
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
    if (typeof ctx.event?.subscribe === "function") {
      const controller = new AbortController()
      void (async () => {
        try {
          const stream = ctx.event.subscribe({
            types: ["session.execution.started", "session.idle"],
            signal: controller.signal,
          })
          for await (const event of stream) {
            const where = event.location?.directory
            if (where && where !== directory) continue
            const hook = event.type === "session.idle" ? "stop" : "prompt-submit"
            await run(directory, hook)
          }
        } catch {
          // Plugin unload or a closed stream: session tracking stays best-effort.
        }
      })()
      return () => controller.abort()
    }
  },
}
""".replace("__MODE__", normalize_mode(mode))


def _read(path: Path) -> dict:
    try:
        raw = textfile.read(path)
    except OSError:
        return {}
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _install_spec(spec: Spec, backup_dir: Path, mode: str) -> bool:
    if spec.kind == "plugin":
        if spec.path.is_file() and textfile.read(spec.path) == plugin_text(mode):
            return False
        if spec.path.is_file():
            backup_file(backup_dir, spec.path)
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        textfile.write(spec.path, plugin_text(mode))
        return True
    data = _read(spec.path)
    before = json.dumps(data, sort_keys=True)
    merged = (
        _merge_nested(data, spec.host, mode)
        if spec.kind == "nested"
        else _merge_flat(data, spec.host, mode)
    )
    if json.dumps(merged, sort_keys=True) == before:
        return False
    if spec.path.is_file():
        backup_file(backup_dir, spec.path)
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    textfile.write(spec.path, json.dumps(merged, indent=2) + "\n")
    return True


def _remove_spec(spec: Spec, backup_dir: Path) -> bool:
    if not spec.path.is_file():
        return False
    if spec.kind == "plugin":
        backup_file(backup_dir, spec.path)
        spec.path.unlink()
        return True
    data = _read(spec.path)
    before = json.dumps(data, sort_keys=True)
    stripped = (
        _strip_nested(data, spec.host) if spec.kind == "nested" else _strip_flat(data, spec.host)
    )
    if json.dumps(stripped, sort_keys=True) == before:
        return False
    backup_file(backup_dir, spec.path)
    textfile.write(spec.path, json.dumps(stripped, indent=2) + "\n")
    return True


def install(
    home: Path | None = None,
    hosts: list[str] | None = None,
    mode: str = DEFAULT_MODE,
) -> dict:
    """Write managed hook entries for the chosen hosts, backing up every file."""
    home = home or Path.home()
    backup_dir = new_backup_dir(home)
    changed: list[str] = []
    skipped: list[dict] = []
    for spec in preview(home, hosts):
        try:
            if _install_spec(spec, backup_dir, mode):
                changed.append(str(spec.path))
        except (OSError, ValueError) as exc:
            skipped.append({"path": str(spec.path), "reason": str(exc)})
    backups = [str(backup_dir)] if backup_dir.exists() else []
    return {"installed": changed, "backups": backups, "skipped": skipped}


def remove(home: Path | None = None, hosts: list[str] | None = None) -> dict:
    """Remove only managed entries, backing up every touched file."""
    home = home or Path.home()
    wanted = set(hosts) if hosts is not None else set(HOSTS)
    backup_dir = new_backup_dir(home)
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
