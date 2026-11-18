"""Plan document schema: one JSON tree for a plan, milestones, tasks, and criteria.

The document is the input to `lpui plan apply`. Validation is pure apart from
reading per-repo creation templates, so a dry-run and a real apply agree on the
same values. Keys are stable and unique per kind; they make a retry a no-op.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from lazyplan.infrastructure.templates import apply_template, template_criteria

from ..core.policies.lanes import (
    DEFAULT_AGENT_ROLE,
    DEFAULT_DISPATCH_MODE,
    DEFAULT_LANE_GROUP,
    DEFAULT_MAX_AGENTS,
    check_agent_role,
    check_dispatch_mode,
    check_lane_group,
    check_max_agents,
)
from ..core.ports.planning import PlanningPort

_PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME)\b")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOP_FIELDS = {"plan", "milestones"}
_PLAN_FIELDS = {"key", "title", "why", "what", "criteria", "dispatch_mode", "max_agents"}
_MILESTONE_FIELDS = {"key", "title", "desc", "criteria", "tasks", "lane_group", "agent_role"}
_TASK_FIELDS = {"key", "title", "desc", "criteria", "role"}


class PlanDocumentError(ValueError):
    """A plan document is malformed or fails validation."""


@dataclass(frozen=True)
class TaskDocument:
    """One task in a plan document."""

    key: str
    title: str
    description: str
    criteria: tuple[str, ...]
    role: str = DEFAULT_AGENT_ROLE


@dataclass(frozen=True)
class MilestoneDocument:
    """One milestone (lane) in a plan document."""

    key: str
    title: str
    description: str
    criteria: tuple[str, ...]
    tasks: tuple[TaskDocument, ...]
    lane_group: int = DEFAULT_LANE_GROUP
    agent_role: str = DEFAULT_AGENT_ROLE


@dataclass(frozen=True)
class PlanDocument:
    """A validated plan document ready to apply."""

    key: str
    title: str
    why: str
    what: str
    criteria: tuple[str, ...]
    milestones: tuple[MilestoneDocument, ...]
    dispatch_mode: str = DEFAULT_DISPATCH_MODE
    max_agents: int = DEFAULT_MAX_AGENTS


def _fail(path: str, message: str) -> NoReturn:
    raise PlanDocumentError(f"{path}: {message}")


def _object(value: Any, path: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "expected a JSON object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        _fail(path, f"unknown field(s): {', '.join(unknown)}")
    return value


def _text(value: Any, path: str, field: str) -> str:
    if not isinstance(value, str):
        _fail(path, f"{field} must be a string")
    text = value.strip()
    if not text:
        _fail(path, f"{field} must not be empty")
    if _PLACEHOLDER.search(text):
        _fail(path, f"{field} contains a placeholder marker")
    return text


def _key(value: Any, path: str) -> str:
    text = _text(value, path, "key")
    if _KEY.fullmatch(text) is None:
        _fail(path, "key must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    return text


def _criteria(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _fail(path, "criteria must be a list of strings")
    out: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        text = _text(item, f"{path}[{index}]", "criterion")
        if text in seen:
            _fail(f"{path}[{index}]", f"duplicate criterion: {text}")
        seen.add(text)
        out.append(text)
    return tuple(out)


def _checked(value: Any, path: str, check: Callable[[Any], Any], default: Any) -> Any:
    """One optional lane field validated by the shared lane policy."""
    if value is None:
        return default
    try:
        return check(value)
    except ValueError as exc:
        _fail(path, str(exc))


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def _filled(port: PlanningPort, kind: str, fields: dict[str, str], path: str) -> dict[str, str]:
    try:
        return apply_template(kind, fields, port.db_path)
    except ValueError as exc:
        raise PlanDocumentError(f"{path}: {exc}") from exc


def _with_template(
    port: PlanningPort, kind: str, explicit: tuple[str, ...], path: str
) -> tuple[str, ...]:
    try:
        defaults = template_criteria(kind, port.db_path)
    except (OSError, ValueError) as exc:
        raise PlanDocumentError(f"{path}: {exc}") from exc
    return _dedupe(tuple(defaults) + explicit)


def _milestone(
    port: PlanningPort,
    raw: Any,
    path: str,
    seen_milestones: set[str],
    seen_tasks: set[str],
) -> MilestoneDocument:
    item = _object(raw, path, _MILESTONE_FIELDS)
    key = _key(item.get("key"), f"{path}.key")
    if key in seen_milestones:
        _fail(f"{path}.key", f"duplicate milestone key: {key}")
    seen_milestones.add(key)
    title = _text(item.get("title"), f"{path}.title", "title")
    desc = _text(item.get("desc", ""), f"{path}.desc", "desc")
    filled = _filled(port, "milestone", {"title": title, "desc": desc}, path)
    criteria = _with_template(
        port, "milestone", _criteria(item.get("criteria"), f"{path}.criteria"), path
    )
    lane_group = _checked(
        item.get("lane_group", DEFAULT_LANE_GROUP),
        f"{path}.lane_group",
        check_lane_group,
        DEFAULT_LANE_GROUP,
    )
    agent_role = _checked(
        item.get("agent_role"),
        f"{path}.agent_role",
        check_agent_role,
        DEFAULT_AGENT_ROLE,
    )

    tasks_raw = item.get("tasks", [])
    if not isinstance(tasks_raw, list):
        _fail(f"{path}.tasks", "tasks must be a list")
    tasks: list[TaskDocument] = []
    for index, task_raw in enumerate(tasks_raw):
        task_path = f"{path}.tasks[{index}]"
        task = _task(port, task_raw, task_path, seen_tasks)
        tasks.append(task)
    return MilestoneDocument(
        key,
        filled["title"],
        filled["desc"],
        criteria,
        tuple(tasks),
        lane_group,
        agent_role,
    )


def _task(port: PlanningPort, raw: Any, path: str, seen_tasks: set[str]) -> TaskDocument:
    item = _object(raw, path, _TASK_FIELDS)
    key = _key(item.get("key"), f"{path}.key")
    if key in seen_tasks:
        _fail(f"{path}.key", f"duplicate task key: {key}")
    seen_tasks.add(key)
    title = _text(item.get("title"), f"{path}.title", "title")
    desc = _text(item.get("desc", ""), f"{path}.desc", "desc")
    filled = _filled(port, "task", {"title": title, "desc": desc}, path)
    criteria = _with_template(
        port, "task", _criteria(item.get("criteria"), f"{path}.criteria"), path
    )
    role = _checked(item.get("role"), f"{path}.role", check_agent_role, DEFAULT_AGENT_ROLE)
    return TaskDocument(key, filled["title"], filled["desc"], criteria, role)


def validate_document(port: PlanningPort, raw: Any) -> PlanDocument:
    """Validate one JSON object and return the resolved document."""
    document = _object(raw, "document", _TOP_FIELDS)
    if "plan" not in document:
        _fail("document", "plan is required")
    plan_raw = _object(document["plan"], "plan", _PLAN_FIELDS)
    key = _key(plan_raw.get("key"), "plan.key")
    title = _text(plan_raw.get("title"), "plan.title", "title")
    why = _text(plan_raw.get("why"), "plan.why", "why")
    what = _text(plan_raw.get("what"), "plan.what", "what")
    filled = _filled(port, "plan", {"title": title, "why": why, "what": what}, "plan")
    criteria = _with_template(
        port, "plan", _criteria(plan_raw.get("criteria"), "plan.criteria"), "plan"
    )
    dispatch_mode = _checked(
        plan_raw.get("dispatch_mode"),
        "plan.dispatch_mode",
        check_dispatch_mode,
        DEFAULT_DISPATCH_MODE,
    )
    max_agents = _checked(
        plan_raw.get("max_agents", DEFAULT_MAX_AGENTS),
        "plan.max_agents",
        check_max_agents,
        DEFAULT_MAX_AGENTS,
    )

    milestones_raw = document.get("milestones", [])
    if not isinstance(milestones_raw, list):
        _fail("milestones", "milestones must be a list")
    seen_milestones: set[str] = set()
    seen_tasks: set[str] = set()
    milestones: list[MilestoneDocument] = []
    for index, milestone_raw in enumerate(milestones_raw):
        milestones.append(
            _milestone(
                port,
                milestone_raw,
                f"milestones[{index}]",
                seen_milestones,
                seen_tasks,
            )
        )
    return PlanDocument(
        key=key,
        title=filled["title"],
        why=filled["why"],
        what=filled["what"],
        criteria=criteria,
        milestones=tuple(milestones),
        dispatch_mode=dispatch_mode,
        max_agents=max_agents,
    )


def to_json(document: PlanDocument) -> str:
    """Serialize a validated document back to the ``plan apply`` schema."""
    payload = {
        "plan": {
            "key": document.key,
            "title": document.title,
            "why": document.why,
            "what": document.what,
            "criteria": list(document.criteria),
            "dispatch_mode": document.dispatch_mode,
            "max_agents": document.max_agents,
        },
        "milestones": [
            {
                "key": milestone.key,
                "title": milestone.title,
                "desc": milestone.description,
                "criteria": list(milestone.criteria),
                "lane_group": milestone.lane_group,
                "agent_role": milestone.agent_role,
                "tasks": [
                    {
                        "key": task.key,
                        "title": task.title,
                        "desc": task.description,
                        "criteria": list(task.criteria),
                        "role": task.role,
                    }
                    for task in milestone.tasks
                ],
            }
            for milestone in document.milestones
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def load_document(path: str | Path) -> dict[str, Any]:
    """Read one JSON document from disk."""
    source = Path(path).expanduser()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanDocumentError(f"cannot read {source}: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanDocumentError(
            f"{source}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(raw, dict):
        raise PlanDocumentError(f"{source}: expected a JSON object")
    return raw


def counts(document: PlanDocument) -> dict[str, int]:
    """Row counts for one validated document."""
    tasks = sum(len(milestone.tasks) for milestone in document.milestones)
    criteria = len(document.criteria) + sum(
        len(milestone.criteria) + sum(len(task.criteria) for task in milestone.tasks)
        for milestone in document.milestones
    )
    return {"milestones": len(document.milestones), "tasks": tasks, "criteria": criteria}


def preview(document: PlanDocument) -> dict[str, Any]:
    """Compact intended tree for a dry-run."""
    return {
        "plan": {"key": document.key, "title": document.title},
        "milestones": [
            {
                "key": milestone.key,
                "title": milestone.title,
                "tasks": [{"key": task.key, "title": task.title} for task in milestone.tasks],
            }
            for milestone in document.milestones
        ],
    }
