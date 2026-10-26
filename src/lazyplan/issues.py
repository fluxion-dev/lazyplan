"""One-way issue import: GitHub live data or a Linear JSON export.

No writeback. No raw provider payloads or tokens are stored.
"""

from __future__ import annotations

from datetime import datetime

from .models import Issue
from .store import Store


def _stamp(text: object) -> float:
    raw = str(text or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def parse_github(data: object) -> list[Issue]:
    """Normalize a GitHub issues response, skipping pull requests."""
    items = (
        data if isinstance(data, list) else data.get("issues", []) if isinstance(data, dict) else []
    )
    issues: list[Issue] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        number = str(item.get("number") or item.get("id") or "")
        if not number:
            continue
        issues.append(
            Issue(
                provider="github",
                external_id=number,
                number=number,
                url=str(item.get("html_url") or ""),
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                state=str(item.get("state") or ""),
                updated_at=_stamp(item.get("updated_at")),
            )
        )
    return issues


def parse_linear(data: object) -> list[Issue]:
    """Normalize a Linear issues export."""
    if not isinstance(data, dict):
        return []
    root = data.get("data", data)
    container = root.get("issues", {}) if isinstance(root, dict) else {}
    nodes = container.get("nodes", []) if isinstance(container, dict) else container
    issues: list[Issue] = []
    for item in nodes if isinstance(nodes, list) else []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("identifier") or item.get("id") or "")
        if not identifier:
            continue
        state = item.get("state")
        if isinstance(state, dict):
            state = state.get("name", "")
        issues.append(
            Issue(
                provider="linear",
                external_id=identifier,
                number=identifier,
                url=str(item.get("url") or ""),
                title=str(item.get("title") or ""),
                body=str(item.get("description") or ""),
                state=str(state or ""),
                updated_at=_stamp(item.get("updatedAt") or item.get("updated_at")),
            )
        )
    return issues


def import_issues(
    store: Store,
    issues: list[Issue],
    actor: str = "human",
    as_kind: str = "plan",
    milestone: int = 0,
    dry_run: bool = False,
) -> dict:
    """Create rows for new issues and refresh source metadata for existing ones."""
    if as_kind not in ("plan", "task"):
        raise ValueError("--as must be plan or task")
    if as_kind == "task" and not milestone:
        raise ValueError("--as task needs --milestone")
    report: dict = {"dry_run": dry_run, "created": [], "updated": [], "skipped": []}
    for issue in issues:
        existing = store.get_issue_link(issue.provider, issue.external_id)
        if existing is not None:
            if not dry_run:
                store.update_issue_link(
                    issue.provider,
                    issue.external_id,
                    issue.title,
                    issue.url,
                    issue.state,
                    issue.updated_at,
                )
            report["updated"].append(
                {"provider": issue.provider, "id": issue.external_id, "title": issue.title}
            )
            continue
        if dry_run:
            row_id = 0
        elif as_kind == "plan":
            row_id = store.add_plan(issue.title or "Imported issue", issue.body, actor=actor).id
        else:
            row_id = store.add_task(
                milestone, issue.title or "Imported issue", issue.body, actor=actor
            ).id
        if not dry_run:
            store.add_issue_link(
                issue.provider,
                issue.external_id,
                issue.number,
                issue.url,
                issue.title,
                issue.state,
                as_kind,
                row_id,
                issue.updated_at,
            )
        report["created"].append(
            {
                "provider": issue.provider,
                "id": issue.external_id,
                "title": issue.title,
                "row_kind": as_kind,
                "row_id": row_id,
            }
        )
    return report
