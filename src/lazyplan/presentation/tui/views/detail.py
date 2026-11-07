"""Pure detail document builder for the read view."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast

from lazyplan.services.source import SourceTrail, build_source_trail

from .... import services
from ....core.ports.insights import InsightsPort
from ....core.ports.provenance import ProvenancePort
from ...shared.design import SECTION_ICON, escape_markup, status_word
from ...shared.render import render_forge_links

KIND_KEYS = {"plan": "plan", "milestone": "milestone", "task": "task"}


def _heading(key: str, label: str) -> str:
    """One section heading with its icon."""
    icon = SECTION_ICON.get(key, "")
    return f"[bold cyan]{icon}[/] [bold]{label}[/]" if icon else f"[bold]{label}[/]"


@dataclass(frozen=True)
class DetailDocument:
    """The detail header and read body."""

    head: str
    body: str


def detail_object(full: dict[str, Any], kind: str) -> dict[str, Any]:
    return dict(full.get(KIND_KEYS[kind], {}))


def detail_breadcrumb(store: ProvenancePort, kind: str, oid: int, obj: dict[str, Any]) -> str:
    if kind == "plan":
        return f"P{oid}"
    if kind == "milestone":
        return f"P{obj.get('plan_id')} › M{oid}"
    milestone = store.get_milestone(int(obj.get("milestone_id", 0)))
    plan_id = milestone.plan_id if milestone else "?"
    return f"P{plan_id} › M{obj.get('milestone_id')} › T{oid}"


def _read_text(lines: list[str], kind: str, obj: dict[str, Any]) -> None:
    desc = str(obj.get("description", "") or "").strip()
    goal = str(obj.get("goal", "") or "").strip() if kind == "plan" else ""
    if goal:
        lines.extend(["", _heading("why", "why"), goal])
    if desc:
        key = "what" if kind == "plan" else "details"
        heading = "what" if kind == "plan" else "details"
        lines.extend(["", _heading(key, heading), desc])


def _read_questions(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Open questions on a plan."""
    if kind != "plan":
        return
    questions = [
        question for question in full.get("questions", []) if question.get("status") == "open"
    ]
    if not questions:
        return
    lines.extend(["", _heading("questions", f"questions {len(questions)} open")])
    for question in questions[:5]:
        lines.append(
            f"  [yellow]?[/] [dim]Q{question['id']}[/] "
            f"{escape_markup(str(question.get('text', '')))}"
        )


def _read_approval(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Approval revision, policy, and drift for a plan."""
    if kind != "plan":
        return
    approval = full.get("approval")
    if not approval:
        return
    revision = int(approval.get("revision", 0) or 0)
    if not revision:
        lines.extend(["", _heading("approval", "approval"), "  [dim]no approved revision[/]"])
        return
    flags = " · enforced" if approval.get("enforced") else ""
    stamp = float(approval.get("approved_at", 0) or 0)
    day = time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"
    lines.extend(["", _heading("approval", f"approval r{revision}{flags}")])
    lines.append(f"  [dim]{day}[/] @{escape_markup(str(approval.get('actor', '')))}")
    reason = str(approval.get("reason", "") or "").strip()
    if reason:
        lines.append(f"  {escape_markup(reason)}")
    drift = int(approval.get("drift", 0) or 0)
    if drift:
        lines.append(f"  [yellow]Δ {drift} changes since approval[/]")
        for item in (approval.get("recent") or [])[:3]:
            field = str(item.get("field") or item.get("action") or "")
            why = str(item.get("reason") or "").strip()
            suffix = f" · {escape_markup(why)}" if why else ""
            lines.append(f"    [dim]{escape_markup(field)}[/]{suffix}")


def _read_readiness(lines: list[str], store: ProvenancePort, kind: str, oid: int) -> None:
    """Lint, criterion coverage, and question readiness for a plan."""
    if kind != "plan":
        return
    try:
        result = services.plan_ready(cast(InsightsPort, store), oid)
    except Exception:
        return
    if result is None:
        return
    if result.ready:
        lines.extend(["", _heading("ready", "ready"), "  [green]✓ ready[/]"])
        return
    failed = [check for check in result.checks if not check.ok]
    lines.extend(["", _heading("ready", f"ready · {len(failed)} failing")])
    for check in result.checks:
        mark = "[green]✓[/]" if check.ok else "[yellow]✗[/]"
        lines.append(f"  {mark} [dim]{check.id}[/] {escape_markup(check.detail)}")


def _task_rows(kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "plan":
        return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]
    if kind == "milestone":
        return [entry.get("task", {}) for entry in full.get("tasks", [])]
    return []


def _read_claims(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Active and stale claims rolled up from child tasks."""
    if kind == "task":
        return
    stamp = time.time()
    claims = [
        (task, claim)
        for task in _task_rows(kind, full)
        if isinstance(claim := task.get("claim"), dict)
    ]
    if not claims:
        return
    active = sum(1 for _task, claim in claims if float(claim.get("expires_at") or 0) > stamp)
    lines.extend(["", _heading("claims", f"claims {len(claims)} · {active} active")])
    for task, claim in claims[:3]:
        expires = float(claim.get("expires_at") or 0)
        state = "active" if expires > stamp else "stale"
        lines.append(
            f"  [dim]◉[/] @{escape_markup(str(claim.get('actor', '')))} · "
            f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))} ({state})"
        )
    if len(claims) > 3:
        lines.append(f"  [dim]+{len(claims) - 3} more[/]")


def _read_coverage(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Evidence coverage across the plan criteria."""
    if kind != "plan":
        return
    criteria = full.get("criteria", [])
    if not criteria:
        return
    if not any((criterion.get("evidence") or {}).get("count") for criterion in criteria):
        return
    proven = sum(
        1 for criterion in criteria if (criterion.get("evidence") or {}).get("state") == "pass"
    )
    lines.extend(["", _heading("coverage", f"evidence {proven}/{len(criteria)}")])


def _plan_id_for(store: ProvenancePort, kind: str, oid: int, obj: dict[str, Any]) -> int | None:
    if kind == "plan":
        return oid
    if kind == "milestone":
        return int(obj.get("plan_id") or 0) or None
    milestone = store.get_milestone(int(obj.get("milestone_id", 0)))
    return milestone.plan_id if milestone is not None else None


def _read_handoff(
    lines: list[str], store: ProvenancePort, kind: str, oid: int, obj: dict[str, Any]
) -> None:
    """The previous session's summary and handoff for the owning plan."""
    plan_id = _plan_id_for(store, kind, oid, obj)
    try:
        session = services.previous_session(cast(InsightsPort, store), plan_id=plan_id)
    except Exception:
        return
    if not session:
        return
    lines.extend(["", _heading("session", f"session S{session['id']} @{session['actor']}")])
    if session.get("summary"):
        lines.append(f"  [dim]summary[/] {escape_markup(str(session['summary']))}")
    if session.get("handoff"):
        lines.append(f"  [dim]handoff[/] {escape_markup(str(session['handoff']))}")


def _read_references(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Read-only external references on a plan."""
    if kind != "plan":
        return
    refs = full.get("refs", [])
    if not refs:
        return
    lines.extend(["", _heading("references", f"references {len(refs)}")])
    for ref in refs[:5]:
        label = ref.get("title") or ref.get("url", "")
        lines.append(
            f"  [dim]{escape_markup(str(ref.get('provider', 'other')))}/"
            f"{escape_markup(str(ref.get('kind', 'issue')))}[/] "
            f"{escape_markup(str(label))}"
        )


def _read_coordination(lines: list[str], full: dict[str, Any], obj: dict[str, Any]) -> None:
    if obj.get("blocked"):
        reason = str(obj.get("blocked_reason", "") or "").strip()
        lines.append(f"\n[red]⚑ blocked[/] {escape_markup(reason) if reason else ''}".rstrip())
    gate = obj.get("gate")
    if gate:
        lines.append(
            f"\n[dim]⚑ gate[/] {escape_markup(str(gate.get('state')))} · {gate.get('prs', 0)} PRs"
        )
    claim = obj.get("claim")
    if claim:
        expires = int(float(claim.get("expires_at") or 0))
        state = "expired" if expires and expires <= int(time.time()) else "active"
        lines.append(f"\n[dim]◉ claim[/] @{escape_markup(str(claim.get('actor', '')))} ({state})")
    touchpoints = full.get("touchpoints") or []
    if touchpoints:
        shown = ", ".join(str(item) for item in touchpoints[:4])
        more = f" +{len(touchpoints) - 4}" if len(touchpoints) > 4 else ""
        lines.append(f"\n[dim]touch[/] {escape_markup(shown)}{more}")
    comments = [
        comment
        for comment in (full.get("comments") or obj.get("comments") or [])
        if not comment.get("resolved")
    ]
    if comments:
        lines.extend(["", _heading("comments", f"comments {len(comments)}")])
        for comment in comments[-3:]:
            lines.append(
                f"  [dim]@{escape_markup(str(comment.get('actor', '')))}[/] "
                f"{escape_markup(str(comment.get('text', '')))}"
            )
    notes = full.get("notes") or obj.get("notes") or []
    if notes:
        lines.extend(["", _heading("notes", f"notes {len(notes)}")])
        for note in notes[-3:]:
            lines.append(
                f"  [dim]@{escape_markup(str(note.get('actor', '')))}[/] "
                f"{escape_markup(str(note.get('text', '')))}"
            )


def _proof_chip(evidence: dict[str, Any] | None) -> str:
    """Compact evidence state for one criterion."""
    data = evidence or {}
    state = str(data.get("state") or "none")
    count = int(data.get("count", 0) or 0)
    if state == "pass":
        return f"[green]✓ {count}[/]"
    if state == "fail":
        return f"[red]✗ {count}[/]"
    return "[dim]—[/]"


def _read_criteria(lines: list[str], full: dict[str, Any]) -> None:
    criteria = full.get("criteria", [])
    if not criteria:
        return
    done = sum(1 for criterion in criteria if criterion.get("done"))
    lines.extend(["", _heading("acceptance", f"acceptance {done}/{len(criteria)}")])
    for criterion in criteria:
        mark = "[green]●[/]" if criterion.get("done") else "[dim]○[/]"
        lines.append(
            f"  {mark} {escape_markup(str(criterion.get('text', '')))} "
            f"{_proof_chip(criterion.get('evidence'))}"
        )


def _read_proof(lines: list[str], full: dict[str, Any]) -> None:
    """Proof rows for criteria that have evidence."""
    criteria = [
        criterion
        for criterion in full.get("criteria", [])
        if (criterion.get("evidence") or {}).get("count")
    ]
    if not criteria:
        return
    total = sum(int((criterion.get("evidence") or {}).get("count", 0)) for criterion in criteria)
    lines.extend(["", _heading("proof", f"proof {total} rows")])
    for criterion in criteria:
        evidence = criterion.get("evidence") or {}
        latest = evidence.get("latest") or {}
        state = str(evidence.get("state") or "none")
        if state == "pass":
            mark = "[green]✓[/]"
        elif state == "fail":
            mark = "[red]✗[/]"
        else:
            mark = "[dim]—[/]"
        label = (
            latest.get("command")
            or latest.get("note")
            or str(latest.get("commit_sha", ""))[:12]
            or "-"
        )
        exit_code = latest.get("exit_code")
        exit_text = f" exit {exit_code}" if exit_code is not None else ""
        lines.append(
            f"  {mark} [dim]#{criterion['id']}[/] {escape_markup(str(label))}"
            f"{exit_text} · {evidence.get('count', 0)} rows"
        )


def _read_children(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    if kind == "plan":
        milestones = full.get("milestones", [])
        if not milestones:
            return
        lines.extend(["", _heading("milestones", f"milestones {len(milestones)}")])
        for entry in milestones:
            milestone = entry["milestone"]
            tasks = entry.get("tasks", [])
            tasks_done = sum(1 for task in tasks if task.get("status") == "done")
            lines.append(
                f"  {status_word(str(milestone.get('status', '')), 'rich')} "
                f"[dim]◇ M{milestone.get('id')}[/] "
                f"{escape_markup(str(milestone.get('title', '')))} "
                f"[dim]{tasks_done}/{len(tasks)}[/]"
            )
        return
    if kind != "milestone":
        return
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    if not tasks:
        return
    lines.extend(["", _heading("tasks", f"tasks {len(tasks)}")])
    for task in tasks:
        lines.append(
            f"  {status_word(str(task.get('status', '')), 'rich')} "
            f"[dim]▹ T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
        )


def _read_forge(lines: list[str], full: dict[str, Any]) -> None:
    links = full.get("effective_forge_links") or full.get("forge_links") or []
    if not links:
        return
    lines.extend(["", _heading("pulls", "pull requests")])
    for line in render_forge_links(links).splitlines():
        lines.append(f"  [magenta]⇄[/] {escape_markup(line)}")


def _commit_lines(commit: Any) -> list[str]:
    files = f" · {len(commit.files)} files" if commit.files else ""
    stale = " · [red]\\[stale][/]" if commit.stale else ""
    rows = [
        f"    [dim]◆ {commit.short}[/] "
        f"{escape_markup(commit.subject or '(no subject)')}[dim]{files}[/]{stale}"
    ]
    if commit.url:
        rows.append(f"      [dim]{escape_markup(commit.url)}[/]")
    return rows


def _repo_lines(repo: Any) -> list[str]:
    state = "dirty" if repo.dirty else "clean"
    branch = repo.branch or ("detached" if repo.detached else "unknown")
    icon = "●" if repo.dirty else "○"
    tracking = f" · {repo.ahead} ahead, {repo.behind} behind" if repo.branch else ""
    rows = [
        f"  {icon} [bold]{escape_markup(repo.name)}[/] · "
        f"{escape_markup(branch)} · {state}{tracking} · "
        f"{len(repo.commits)}c · {len(repo.pulls)}PR"
    ]
    for commit in repo.commits[:3]:
        rows.extend(_commit_lines(commit))
    if repo.error:
        rows.append(f"    [red]{escape_markup(repo.error)}[/]")
    return rows


def _orphan_lines(links: list[dict[str, Any]]) -> list[str]:
    rows = ["", _heading("git", f"git · source · {len(links)} commits")]
    for link in links[:3]:
        short = str(link.get("sha", ""))[:12]
        subject = escape_markup(str(link.get("subject", "") or "(no subject)"))
        rows.append(f"    [dim]◆ {short}[/] {subject}")
    rows.append("  [dim]g source trail[/]")
    return rows


def _source_lines(trail: SourceTrail, links: list[dict[str, Any]]) -> list[str]:
    if trail.empty:
        if links:
            return _orphan_lines(links)
        return [
            "",
            _heading("git", "git · source"),
            "  [dim]no linked commits or PRs · link a commit or run task finish[/]",
        ]
    summary = f"{trail.commit_count} commits · {trail.file_count} files · {trail.pull_count} PRs"
    if trail.stale_count:
        summary += f" · {trail.stale_count} stale"
    rows = ["", _heading("git", f"git · source · {summary}")]
    for repo in trail.repos[:3]:
        rows.extend(_repo_lines(repo))
    if len(trail.repos) > 3:
        rows.append(f"  [dim]+{len(trail.repos) - 3} more repos[/]")
    rows.append("  [dim]g source trail[/]")
    return rows


def _read_source(
    lines: list[str],
    store: ProvenancePort,
    kind: str,
    oid: int,
    full: dict[str, Any],
    trail: SourceTrail | None,
) -> None:
    trail = trail or build_source_trail(store, kind, oid)
    links = full.get("effective_links") or full.get("links") or []
    lines.extend(_source_lines(trail, links))


def build_detail(
    store: ProvenancePort,
    kind: str,
    oid: int,
    full: dict[str, Any],
    trail: SourceTrail | None,
) -> DetailDocument:
    """Build the read view for one plan, milestone, or task."""
    obj = detail_object(full, kind)
    title = str(obj.get("title", obj.get("name", "")))
    status = str(obj.get("status", ""))
    pill = f" [reverse] {status.upper()} [/]" if status else ""
    head = (
        f"{status_word(status, 'rich')} [bold]{escape_markup(title)}[/]{pill}\n"
        f"[dim]{detail_breadcrumb(store, kind, oid, obj)}[/]"
    )
    lines: list[str] = []
    _read_text(lines, kind, obj)
    _read_approval(lines, kind, full)
    _read_readiness(lines, store, kind, oid)
    _read_questions(lines, kind, full)
    _read_references(lines, kind, full)
    _read_coordination(lines, full, obj)
    _read_claims(lines, kind, full)
    _read_criteria(lines, full)
    _read_coverage(lines, kind, full)
    _read_proof(lines, full)
    _read_handoff(lines, store, kind, oid, obj)
    _read_children(lines, kind, full)
    _read_forge(lines, full)
    _read_source(lines, store, kind, oid, full, trail)
    return DetailDocument(head=head, body="\n".join(lines).lstrip("\n"))
