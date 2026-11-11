"""Hook behavior modes: strict, advisory, and off.

A mode decides whether a lifecycle hook may deny an action. The installed host
entry carries its mode as ``--mode``; the environment can override it without
reinstalling, and ``LAZYPLAN_NO_HOOKS`` silences everything.
"""

from __future__ import annotations

from collections.abc import Mapping

MODES = ("strict", "advisory", "off")
DEFAULT_MODE = "strict"
MODE_ENV = "LAZYPLAN_HOOKS"
NO_HOOKS_ENV = "LAZYPLAN_NO_HOOKS"


def normalize_mode(text: object, default: str = DEFAULT_MODE) -> str:
    """Return one of :data:`MODES`, falling back to *default*."""
    body = str(text or "").strip().lower()
    return body if body in MODES else default


def mode_from_env(environ: Mapping[str, str]) -> str | None:
    """Mode requested by the environment, or None when it is unset or invalid."""
    if str(environ.get(NO_HOOKS_ENV, "")).strip():
        return "off"
    wanted = str(environ.get(MODE_ENV, "")).strip().lower()
    return wanted if wanted in MODES else None


def resolve_mode(flag: str | bool | None, stored: str, environ: Mapping[str, str]) -> str:
    """Resolve one mode: environment, then explicit flag, then stored state."""
    if flag is False or str(environ.get(NO_HOOKS_ENV, "")).strip():
        return "off"
    if isinstance(flag, str) and flag:
        explicit = normalize_mode(flag, "")
        if explicit:
            return explicit
    from_env = mode_from_env(environ)
    if from_env is not None:
        return from_env
    return normalize_mode(stored)
