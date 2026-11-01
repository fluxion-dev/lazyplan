"""Planning rules: status rollup, transitions, archiving, and progress."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..entities import Plan, Status

#: A finished plan leaves the default view after this idle window.
ARCHIVE_AFTER_SECS = 24 * 3600

_STATUS_ORDER: tuple[Status, Status, Status] = (Status.TODO, Status.DOING, Status.DONE)


def next_status(current: Status) -> Status:
    """Advance todo -> doing -> done -> todo."""
    return _STATUS_ORDER[(_STATUS_ORDER.index(current) + 1) % len(_STATUS_ORDER)]


def rollup_target(statuses: Sequence[Status]) -> Status:
    """Parent state from children: all done -> done, any doing -> doing, else todo."""
    if not statuses:
        return Status.TODO
    if all(status == Status.DONE for status in statuses):
        return Status.DONE
    if any(status == Status.DOING for status in statuses):
        return Status.DOING
    return Status.TODO


def is_archived(plan: Plan, events: Mapping[int, tuple[float, str]], now: float) -> bool:
    """True when a done plan has held that state longer than the archive window."""
    if plan.status != Status.DONE:
        return False
    last = events.get(plan.id)
    if last is None:
        return False
    timestamp, target = last
    return target == Status.DONE.value and (now - timestamp) > ARCHIVE_AFTER_SECS
