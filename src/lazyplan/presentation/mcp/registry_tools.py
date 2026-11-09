"""Registry-derived MCP tool metadata.

The tool table keeps its explicit input schemas, but every tool name must map
back to one registry action. Tests compare the registry mapping to the live
tool list so a tool cannot appear without an action or a recorded exception.
"""

from __future__ import annotations

from ..shared.registry_actions import ACTIONS
from ..shared.registry_surfaces import MCP_ACTIONS


def tool_actions() -> dict[str, str]:
    """Return MCP tool name to canonical action id."""
    return dict(MCP_ACTIONS)


def tool_labels() -> dict[str, str]:
    """Return MCP tool name to the registry action label."""
    by_id = {action.id: action.label for action in ACTIONS}
    return {tool: by_id.get(action_id, "") for action_id, tool in MCP_ACTIONS.items()}
