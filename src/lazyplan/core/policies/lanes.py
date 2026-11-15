"""Lane vocabulary shared by plans, milestones, tasks, and dispatch.

A plan chooses serial or parallel dispatch and caps concurrent lanes. A
milestone is a lane: its group is its wave and its role names the agent that
owns it. A task role names the agent that runs one slice inside the lane.
Stdlib only.
"""

from __future__ import annotations

DISPATCH_SERIAL = "serial"
DISPATCH_PARALLEL = "parallel"

#: Allowed dispatch modes, safest first.
DISPATCH_MODES: tuple[str, str] = (DISPATCH_SERIAL, DISPATCH_PARALLEL)
DEFAULT_DISPATCH_MODE = DISPATCH_SERIAL
DEFAULT_MAX_AGENTS = 1

#: Allowed agent roles, planner first and worker roles after.
AGENT_ROLES: tuple[str, ...] = (
    "scout",
    "implementer",
    "qa",
    "refactor",
    "docs",
    "reviewer",
    "integrator",
)
DEFAULT_AGENT_ROLE = "implementer"
DEFAULT_LANE_GROUP = 1

DISPATCH_ERROR = f"dispatch_mode must be {'|'.join(DISPATCH_MODES)}"
ROLE_ERROR = f"agent_role must be {'|'.join(AGENT_ROLES)}"
MAX_AGENTS_ERROR = "max_agents must be a positive integer"
LANE_GROUP_ERROR = "lane_group must be a positive integer"


def check_dispatch_mode(value: str) -> str:
    """Validate a dispatch mode, naming the allowed values."""
    if value not in DISPATCH_MODES:
        raise ValueError(DISPATCH_ERROR)
    return value


def check_agent_role(value: str) -> str:
    """Validate an agent role, naming the allowed values."""
    if value not in AGENT_ROLES:
        raise ValueError(ROLE_ERROR)
    return value


def check_max_agents(value: int) -> int:
    """Validate a lane cap as a positive integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(MAX_AGENTS_ERROR)
    return value


def check_lane_group(value: int) -> int:
    """Validate a wave number as a positive integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(LANE_GROUP_ERROR)
    return value


def normalize_dispatch_mode(value: object) -> str:
    """Read a dispatch mode from legacy or imported data, defaulting to serial."""
    text = str(value or "").strip().lower()
    return text if text in DISPATCH_MODES else DEFAULT_DISPATCH_MODE


def normalize_agent_role(value: object) -> str:
    """Read an agent role from legacy or imported data, defaulting to implementer."""
    text = str(value or "").strip().lower()
    return text if text in AGENT_ROLES else DEFAULT_AGENT_ROLE


def normalize_max_agents(value: object) -> int:
    """Read a lane cap from legacy or imported data, defaulting to one."""
    return _positive_int(value, DEFAULT_MAX_AGENTS)


def normalize_lane_group(value: object) -> int:
    """Read a wave number from legacy or imported data, defaulting to one."""
    return _positive_int(value, DEFAULT_LANE_GROUP)


def _positive_int(value: object, default: int) -> int:
    """Parse a positive integer from imported text, else use *default*."""
    text = str(value).strip()
    if not text:
        return default
    try:
        number = int(text)
    except ValueError:
        return default
    return number if number >= 1 else default
