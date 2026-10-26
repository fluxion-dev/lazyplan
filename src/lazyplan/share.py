"""Read-only plan share: escaped HTML or safe JSON.

No tokens, auth state, cache payloads, or raw forge API records are included.
"""

from __future__ import annotations

import html
import json
from typing import Any

from . import textfile
from .store import Store


def _safe(value: Any) -> Any:
    """Recursively drop cached API payloads before sharing."""
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items() if key != "payload"}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _safe_links(items: list[dict]) -> list[dict]:
    """Drop cached API payloads before sharing."""
    return [item for item in _safe(items) if isinstance(item, dict)]


def payload(store: Store, plan_id: int) -> dict | None:
    """Plan payload for a share, without secrets or raw cache records."""
    full = store.get_full("plan", plan_id)
    if full is None:
        return None
    data = dict(full)
    data["links"] = _safe_links([vars(link) for link in store.list_links("plan", plan_id)])
    data["forge_links"] = [
        {key: value for key, value in vars(link).items() if key != "payload"}
        for link in store.list_forge_links("plan", plan_id)
    ]
    data["comments"] = [vars(comment) for comment in store.list_comments("plan", plan_id)]
    safe = _safe(data)
    assert isinstance(safe, dict)
    return safe


def _task_line(task: dict) -> str:
    suffix = " [blocked]" if task.get("blocked") else ""
    return (
        f"<li><strong>T{html.escape(str(task.get('id')))}</strong> "
        f"{html.escape(str(task.get('title')))} "
        f"<em>{html.escape(str(task.get('status')))}</em>{suffix}</li>"
    )


def render_html(store: Store, plan_id: int) -> str | None:
    """Standalone escaped HTML plan document."""
    data = payload(store, plan_id)
    if data is None:
        return None
    plan = data["plan"]
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{html.escape(str(plan.get('name')))} — lazyplan</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem}"
        "code{background:#eee;padding:.1rem .3rem}h2{margin-top:2rem}</style></head><body>",
        f"<h1>{html.escape(str(plan.get('name')))}</h1>",
        f"<p><strong>{html.escape(str(plan.get('status')))}</strong> · "
        f"P{html.escape(str(plan.get('id')))}</p>",
    ]
    if plan.get("goal"):
        out.append(f"<h2>Why</h2><p>{html.escape(str(plan.get('goal')))}</p>")
    if plan.get("description"):
        out.append(f"<h2>What</h2><pre>{html.escape(str(plan.get('description')))}</pre>")
    criteria = data.get("criteria", [])
    if criteria:
        out.append("<h2>Acceptance</h2><ul>")
        for criterion in criteria:
            mark = "x" if criterion.get("done") else " "
            out.append(f"<li>[{mark}] {html.escape(str(criterion.get('text')))}</li>")
        out.append("</ul>")
    for entry in data.get("milestones", []):
        milestone = entry["milestone"]
        out.append(
            f"<h2>M{html.escape(str(milestone.get('id')))} "
            f"{html.escape(str(milestone.get('title')))}</h2>"
        )
        if milestone.get("description"):
            out.append(f"<pre>{html.escape(str(milestone.get('description')))}</pre>")
        out.append("<ul>")
        for task in entry.get("tasks", []):
            out.append(_task_line(task))
            for comment in task.get("comments", []):
                state = "resolved" if comment.get("resolved") else "open"
                out.append(
                    f"<li>[{state}] @{html.escape(str(comment.get('actor')))}: "
                    f"{html.escape(str(comment.get('text')))}</li>"
                )
        out.append("</ul>")
    notes = data.get("notes", [])
    if notes:
        out.append("<h2>Notes</h2><ul>")
        for note in notes:
            out.append(
                f"<li>@{html.escape(str(note.get('actor')))}: "
                f"{html.escape(str(note.get('text')))}</li>"
            )
        out.append("</ul>")
    comments = data.get("comments", [])
    if comments:
        out.append("<h2>Comments</h2><ul>")
        for comment in comments:
            state = "resolved" if comment.get("resolved") else "open"
            out.append(
                f"<li>[{state}] @{html.escape(str(comment.get('actor')))}: "
                f"{html.escape(str(comment.get('text')))}</li>"
            )
        out.append("</ul>")
    out.append("</body></html>")
    return "\n".join(out)


def render_json(store: Store, plan_id: int) -> str | None:
    """Safe JSON payload for a share."""
    data = payload(store, plan_id)
    if data is None:
        return None
    return json.dumps(data, indent=2, default=str)


def write(store: Store, plan_id: int, fmt: str, dest: str | None) -> str | None:
    """Render a share and optionally write it to a file."""
    text = render_html(store, plan_id) if fmt == "html" else render_json(store, plan_id)
    if text is None:
        return None
    if dest:
        textfile.write(dest, text + ("" if text.endswith("\n") else "\n"))
    return text
