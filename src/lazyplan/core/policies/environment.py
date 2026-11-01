"""Pure environment rules: versions, update intervals, and wheel trust."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

UPDATE_POLL_ENV = "LAZYPLAN_UPDATE_INTERVAL"
UPDATE_NETWORK_ENV = "LAZYPLAN_UPDATE_NETWORK_INTERVAL"
NO_UPDATE_ENV = "LAZYPLAN_NO_UPDATE_CHECK"

UPDATE_POLL_INTERVAL = 60.0
UPDATE_NETWORK_INTERVAL = 5 * 60.0
UPDATE_MIN_POLL = 5.0
UPDATE_MAX_POLL = 3600.0
UPDATE_MIN_NETWORK = 60.0
UPDATE_MAX_NETWORK = 24 * 3600.0


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse the first x.y.z version in *text*."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise ValueError(f"cannot parse a version from {text!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def version_text(version: tuple[int, int, int]) -> str:
    """Render a version tuple as x.y.z."""
    return ".".join(str(number) for number in version)


def is_newer(candidate: tuple[int, int, int], installed: tuple[int, int, int]) -> bool:
    """True when *candidate* is a later version than *installed*."""
    return candidate > installed


def update_check_enabled(env: Mapping[str, str] | None = None) -> bool:
    """True unless the environment explicitly disables update checks."""
    return not (env or {}).get(NO_UPDATE_ENV, "").strip()


def env_interval(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
    env: Mapping[str, str] | None = None,
) -> float:
    """Parse a seconds override, falling back to *default* and clamping."""
    raw = (env or {}).get(name, "")
    if not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    return min(max(value, minimum), maximum)


def poll_interval(env: Mapping[str, str] | None = None) -> float:
    """Seconds between TUI update-cache polls."""
    return env_interval(
        UPDATE_POLL_ENV, UPDATE_POLL_INTERVAL, UPDATE_MIN_POLL, UPDATE_MAX_POLL, env
    )


def network_interval(env: Mapping[str, str] | None = None) -> float:
    """Seconds between shared network refreshes."""
    return env_interval(
        UPDATE_NETWORK_ENV,
        UPDATE_NETWORK_INTERVAL,
        UPDATE_MIN_NETWORK,
        UPDATE_MAX_NETWORK,
        env,
    )


def valid_sha(value: object) -> bool:
    """True for a 64-character lowercase hex digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def valid_filename(value: object) -> bool:
    """True for a plain lazyplan wheel filename."""
    return (
        isinstance(value, str)
        and value.startswith("lazyplan_tui-")
        and value.endswith(".whl")
        and "/" not in value
        and "\\" not in value
        and ".." not in value
    )


def valid_url(value: object, host: str) -> bool:
    """True for an HTTPS URL on *host*."""
    if not isinstance(value, str):
        return False
    from urllib.parse import urlparse

    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == host
