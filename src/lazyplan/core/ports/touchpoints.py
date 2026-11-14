"""The touch-point port: path patterns that scope a task."""

from __future__ import annotations

from typing import Protocol


class TouchpointReadPort(Protocol):
    """Read-only touch-point lookup used for overlap and context reads."""

    def list_touchpoints(self, task_id: int) -> list[str]: ...

    def touchpoints_map(self) -> dict[int, list[str]]: ...


class TouchpointPort(TouchpointReadPort, Protocol):
    """Touch-point writes used by the task commands."""

    def add_touchpoint(self, task_id: int, pattern: str, actor: str = "human") -> str: ...

    def remove_touchpoint(self, task_id: int, pattern: str, actor: str = "human") -> bool: ...
