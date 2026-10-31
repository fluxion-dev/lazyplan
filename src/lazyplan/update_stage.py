"""Stage a verified PyPI wheel and apply it on the next TUI launch.

Downloads happen only when the user explicitly asks. The cached wheel is
verified twice: once against the PyPI JSON digest, and again before install.
A single slot lives under the shared home so a newer download replaces an older
one. Apply is claimed with one atomic rename, which also serialises two TUI
instances on the same machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import textfile
from .repo import shared_home
from .upgrade import (
    PIPX,
    PYPI_PKG,
    UPGRADEABLE,
    VENV,
    UpgradeError,
    parse_version,
    require_newer,
)

UPDATE_DIR = "updates"
STAGED = "staged.json"
APPLYING = "applying.json"
FAILED = "failed.json"
SCHEMA = 1
MAX_WHEEL_BYTES = 20 * 1024 * 1024
WHEEL_HOST = "files.pythonhosted.org"
PYPI_JSON = "https://pypi.org/pypi/{package}/{version}/json"
USER_AGENT = "lazyplan-update/1.0 (+https://github.com/fluxion-dev/lazyplan)"
DOWNLOAD_TIMEOUT = 60.0
APPLY_TIMEOUT = 300.0
CHUNK = 64 * 1024


class StageError(Exception):
    """A staged update is missing, malformed, or cannot be applied."""


@dataclass(frozen=True)
class StagedUpdate:
    """One verified wheel waiting for the next launch."""

    version: str
    method: str
    filename: str
    url: str
    sha256: str
    size: int
    staged_at: float

    def payload(self) -> dict[str, Any]:
        """JSON-safe record; the schema is part of the cache contract."""
        return {
            "schema": SCHEMA,
            "version": self.version,
            "method": self.method,
            "filename": self.filename,
            "url": self.url,
            "sha256": self.sha256,
            "size": self.size,
            "staged_at": self.staged_at,
        }


def update_dir(home: str | Path | None = None) -> Path:
    """Directory for the wheel and its state files."""
    return shared_home(home) / UPDATE_DIR


def _state_path(name: str, home: str | Path | None = None) -> Path:
    return update_dir(home) / name


def wheel_path(update: StagedUpdate, home: str | Path | None = None) -> Path:
    """The cached wheel path, confined to the update directory."""
    root = update_dir(home).resolve()
    path = (root / update.filename).resolve()
    if root not in path.parents:
        raise StageError("staged wheel escapes the update directory")
    return path


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _valid_filename(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith(".whl"):
        return False
    if not value.startswith("lazyplan_tui-"):
        return False
    return value == Path(value).name and ".." not in value


def _valid_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == WHEEL_HOST


def stage_from_payload(data: object) -> StagedUpdate | None:
    """Parse one staged record; return None for anything untrusted."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    version = data.get("version")
    method = data.get("method")
    filename = data.get("filename")
    url = data.get("url")
    sha256 = data.get("sha256")
    size = data.get("size")
    staged_at = data.get("staged_at")
    if not isinstance(version, str) or not isinstance(method, str) or method not in UPGRADEABLE:
        return None
    try:
        parse_version(version)
    except UpgradeError:
        return None
    if not _valid_filename(filename) or not _valid_url(url) or not _valid_sha(sha256):
        return None
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_WHEEL_BYTES:
        return None
    if isinstance(staged_at, bool) or not isinstance(staged_at, (int, float)):
        return None
    return StagedUpdate(
        version, method, str(filename), str(url), str(sha256), size, float(staged_at)
    )


def read_stage(path: Path | None = None, home: str | Path | None = None) -> StagedUpdate | None:
    """Read one state file, returning None when it is absent or malformed."""
    target = path or _state_path(STAGED, home)
    try:
        data = json.loads(textfile.read(target))
    except (OSError, ValueError):
        return None
    return stage_from_payload(data)


def write_stage(
    update: StagedUpdate,
    path: Path | None = None,
    home: str | Path | None = None,
) -> None:
    """Atomically write one state file."""
    target = path or _state_path(STAGED, home)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.tmp")
    textfile.write(temp, json.dumps(update.payload(), indent=2, sort_keys=True) + "\n")
    os.replace(temp, target)


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def _read_json(url: str, timeout: float, opener: Callable[..., Any]) -> Any:
    with opener(_request(url), timeout=timeout) as response:
        raw = response.read()
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise StageError(f"invalid JSON from {url}: {exc}") from exc


def fetch_metadata(
    version: str,
    timeout: float = DOWNLOAD_TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Select the pure-Python wheel and its digest from the PyPI JSON API."""
    payload = _read_json(PYPI_JSON.format(package=PYPI_PKG, version=version), timeout, opener)
    if not isinstance(payload, dict):
        raise StageError("PyPI payload is not an object")
    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise StageError("PyPI payload has no file list")
    for item in urls:
        if not isinstance(item, dict) or item.get("yanked"):
            continue
        if item.get("packagetype") != "bdist_wheel":
            continue
        filename = item.get("filename")
        url = item.get("url")
        digests = item.get("digests")
        size = item.get("size")
        if not _valid_filename(filename) or not _valid_url(url):
            continue
        if not isinstance(digests, dict) or not _valid_sha(digests.get("sha256")):
            continue
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_WHEEL_BYTES:
            continue
        return {"filename": filename, "url": url, "sha256": digests["sha256"], "size": size}
    raise StageError(f"no verified wheel for v{version} on PyPI")


def download_wheel(
    metadata: dict[str, Any],
    destination: Path,
    timeout: float = DOWNLOAD_TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> int:
    """Stream, cap, hash, and atomically place the wheel."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(destination.parent), prefix="wheel.")
    digest = hashlib.sha256()
    total = 0
    try:
        with (
            os.fdopen(fd, "wb") as handle,
            opener(_request(str(metadata["url"])), timeout=timeout) as response,
        ):
            while chunk := response.read(CHUNK):
                total += len(chunk)
                if total > MAX_WHEEL_BYTES:
                    raise StageError("wheel exceeds the size cap")
                digest.update(chunk)
                handle.write(chunk)
        if total != metadata["size"]:
            raise StageError("wheel size does not match PyPI")
        if digest.hexdigest() != metadata["sha256"]:
            raise StageError("wheel digest does not match PyPI")
        os.replace(temporary, destination)
        return total
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _cleanup(home: str | Path | None, keep: str) -> None:
    directory = update_dir(home)
    for child in directory.iterdir() if directory.is_dir() else ():
        if child.is_file() and child.name not in (keep, STAGED, APPLYING, FAILED):
            child.unlink(missing_ok=True)


def stage_update(
    version: str,
    method: str,
    home: str | Path | None = None,
    timeout: float = DOWNLOAD_TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: float | None = None,
    installed: str | None = None,
) -> StagedUpdate:
    """Download and verify one newer wheel, replacing any older stage."""
    if method not in UPGRADEABLE:
        raise StageError(f"no download path for a {method} install")
    try:
        require_newer(version, installed)
    except UpgradeError as exc:
        raise StageError(str(exc)) from exc
    metadata = fetch_metadata(version, timeout, opener)
    destination = update_dir(home) / str(metadata["filename"])
    size = download_wheel(metadata, destination, timeout, opener)
    update = StagedUpdate(
        version=version,
        method=method,
        filename=str(metadata["filename"]),
        url=str(metadata["url"]),
        sha256=str(metadata["sha256"]),
        size=size,
        staged_at=time.time() if now is None else now,
    )
    write_stage(update, home=home)
    _state_path(FAILED, home).unlink(missing_ok=True)
    _cleanup(home, update.filename)
    return update


def claim_stage(home: str | Path | None = None) -> StagedUpdate | None:
    """Atomically move staged to applying; a second caller gets nothing."""
    applying = _state_path(APPLYING, home)
    if applying.exists():
        return None
    try:
        os.replace(_state_path(STAGED, home), applying)
    except FileNotFoundError:
        return None
    update = read_stage(applying, home)
    if update is None:
        applying.unlink(missing_ok=True)
    return update


def verify_wheel(update: StagedUpdate, home: str | Path | None = None) -> bool:
    """Check the cached file again before install."""
    try:
        path = wheel_path(update, home)
        if not path.is_file() or path.stat().st_size != update.size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                digest.update(chunk)
        return digest.hexdigest() == update.sha256
    except (OSError, StageError):
        return False


def _install_command(update: StagedUpdate, home: str | Path | None, exe: str) -> list[str]:
    wheel = str(wheel_path(update, home))
    if update.method == PIPX:
        if shutil.which("pipx") is None:
            raise StageError("pipx is not on PATH")
        return ["pipx", "install", wheel, "--force"]
    if update.method == VENV:
        return [exe, "-m", "pip", "install", wheel]
    raise StageError(f"no apply path for a {update.method} install")


def apply_update(
    update: StagedUpdate,
    home: str | Path | None = None,
    exe: str | None = None,
    timeout: float = APPLY_TIMEOUT,
    runner: Callable[..., Any] = subprocess.run,
    installed: str | None = None,
) -> None:
    """Install the cached wheel; raise StageError with a short detail on failure."""
    try:
        require_newer(update.version, installed)
    except UpgradeError as exc:
        raise StageError(str(exc)) from exc
    command = _install_command(update, home, exe or sys.executable)
    try:
        result = runner(command, capture_output=True, text=True, timeout=timeout)
    except OSError as exc:
        raise StageError(f"cannot run {command[0]}: {exc}") from exc
    if result.returncode != 0:
        detail = "; ".join((result.stderr or result.stdout or "").strip().splitlines()[:3])
        raise StageError(f"install failed: {detail}")


def clear_stage(update: StagedUpdate, home: str | Path | None = None) -> None:
    """Delete the state file and cached wheel after success or a skip."""
    _state_path(APPLYING, home).unlink(missing_ok=True)
    _state_path(STAGED, home).unlink(missing_ok=True)
    try:
        wheel_path(update, home).unlink(missing_ok=True)
    except StageError:
        pass


def mark_failed(update: StagedUpdate, error: str, home: str | Path | None = None) -> None:
    """Park the record so the next launch does not retry in a loop."""
    payload = update.payload()
    payload["error"] = error
    target = _state_path(FAILED, home)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.tmp")
    textfile.write(temp, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temp, target)
    _state_path(APPLYING, home).unlink(missing_ok=True)


def read_failure(home: str | Path | None = None) -> str | None:
    """The last parked apply error, if any."""
    target = _state_path(FAILED, home)
    try:
        data = json.loads(textfile.read(target))
    except (OSError, ValueError):
        return None
    error = data.get("error") if isinstance(data, dict) else None
    return error if isinstance(error, str) and error.strip() else None


def clear_failure(home: str | Path | None = None) -> None:
    """Forget a parked error after it has been shown."""
    _state_path(FAILED, home).unlink(missing_ok=True)


def apply_on_launch(
    installed: str,
    home: str | Path | None = None,
    exe: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[str, str]:
    """Claim and apply one stage; return (state, detail)."""
    update = claim_stage(home)
    if update is None:
        return ("none", "")
    try:
        target = parse_version(update.version)
        running = parse_version(installed)
    except UpgradeError as exc:
        mark_failed(update, str(exc), home)
        return ("error", str(exc))
    if target < running:
        clear_stage(update, home)
        return ("downgrade", update.version)
    if target == running:
        clear_stage(update, home)
        return ("skipped", update.version)
    if not verify_wheel(update, home):
        error = "cached wheel is missing or corrupt"
        mark_failed(update, error, home)
        return ("error", error)
    try:
        apply_update(update, home, exe, runner=runner, installed=installed)
    except StageError as exc:
        mark_failed(update, str(exc), home)
        return ("error", str(exc))
    clear_stage(update, home)
    return ("applied", update.version)
