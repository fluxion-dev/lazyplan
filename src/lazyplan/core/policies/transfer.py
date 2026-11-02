"""Pure transfer rules: export schema, sync summaries, redaction, and stamps."""

from __future__ import annotations

from datetime import datetime
from typing import Any

EXPORT_VERSION = 1


def is_export(data: object) -> bool:
    """True for a lazyplan JSON export of the supported version."""
    return isinstance(data, dict) and data.get("lazyplan") == EXPORT_VERSION


def summary(entry: dict) -> dict:
    """Comparable plan shape for sync conflict decisions."""
    plan = entry.get("plan", {})
    milestones = entry.get("milestones", [])
    tasks = sum(len(item.get("tasks", [])) for item in milestones)
    criteria = len(entry.get("criteria", []))
    for milestone in milestones:
        criteria += len(milestone.get("criteria", []))
        for task in milestone.get("tasks", []):
            criteria += len(task.get("criteria", []))
    return {
        "name": str(plan.get("name", "")),
        "why": str(plan.get("goal", "")),
        "what": str(plan.get("description", "")),
        "status": str(plan.get("status", "")),
        "milestones": len(milestones),
        "tasks": tasks,
        "criteria": criteria,
    }


def differences(local: dict, incoming: dict) -> list[str]:
    """Fields that differ between a local export and an incoming plan."""
    left = summary(local)
    right = summary(incoming)
    return [key for key in left if left[key] != right[key]]


def safe_payload(value: Any) -> Any:
    """Recursively drop cached API payloads before sharing."""
    if isinstance(value, dict):
        return {key: safe_payload(item) for key, item in value.items() if key != "payload"}
    if isinstance(value, list):
        return [safe_payload(item) for item in value]
    return value


def issue_stamp(text: object) -> float:
    """Parse a provider timestamp, returning 0 for missing or invalid text."""
    raw = str(text or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
