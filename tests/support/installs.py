"""Build the on-disk install layouts that detection and updates probe.

Each helper writes the marker file the real tool writes, so tests exercise the
same paths production reads instead of duplicating scaffolding per test.
"""

from __future__ import annotations

import json
from pathlib import Path

PACKAGE = "lazyplan-tui"


def uv_tool_venv(root: str | Path, package: str = PACKAGE) -> Path:
    """A uv tool venv with its receipt, as ``uv tool install`` writes it."""
    venv = Path(root) / "uv" / "tools" / package
    venv.mkdir(parents=True)
    (venv / "uv-receipt.toml").write_text(
        f'[tool]\nrequirements = [{{ name = "{package}" }}]\n', encoding="utf-8"
    )
    return venv


def pipx_venv(root: str | Path, backend: str | None = None) -> Path:
    """A pipx venv, optionally recording the backend pipx used."""
    venv = Path(root) / "pipx" / "venvs" / PACKAGE
    venv.mkdir(parents=True)
    if backend is not None:
        (venv / "pipx_metadata.json").write_text(json.dumps({"backend": backend}), encoding="utf-8")
    return venv


def source_checkout(root: str | Path) -> Path:
    """A checkout whose pyproject names this distribution."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "{PACKAGE}"\n', encoding="utf-8")
    return root
