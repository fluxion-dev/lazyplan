"""External reference use cases."""

from __future__ import annotations

from ..core.entities import ExternalRef
from ..core.ports.refs import RefsPort


def link_ref(
    port: RefsPort,
    plan_id: int,
    url: str,
    provider: str = "",
    kind: str = "issue",
    external_id: str = "",
    title: str = "",
    state: str = "",
    actor: str = "human",
) -> ExternalRef:
    """Link one external URL to a plan."""
    return port.link_ref(
        plan_id,
        url,
        provider=provider,
        kind=kind,
        external_id=external_id,
        title=title,
        state=state,
        actor=actor,
    )


def list_refs(port: RefsPort, plan_id: int) -> list[ExternalRef]:
    """References on one plan."""
    return port.list_refs(plan_id)


def unlink_ref(
    port: RefsPort, plan_id: int, ref_id: int = 0, url: str = "", actor: str = "human"
) -> bool:
    """Remove a reference by id or URL."""
    return port.unlink_ref(plan_id, ref_id=ref_id, url=url, actor=actor)
