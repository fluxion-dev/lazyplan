"""Criterion proof use cases: record evidence and gate task finish."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.entities import Criterion, CriterionEvidence
from ..core.policies.evidence import PROOF_PASS, proof_state
from ..core.policies.evidence import coverage as coverage_policy
from ..core.ports.provenance import ProvenancePort


@dataclass(frozen=True)
class ProofResult:
    """One recorded proof row and whether it ticked the criterion."""

    evidence: CriterionEvidence
    criterion: Criterion
    ticked: bool


def prove(
    port: ProvenancePort,
    criterion_id: int,
    command: str = "",
    exit_code: int | None = None,
    commit_sha: str = "",
    pr_url: str = "",
    artifact_path: str = "",
    note: str = "",
    task_id: int | None = None,
    actor: str = "human",
    tick: bool = True,
) -> ProofResult:
    """Record evidence; tick only when the row passes and ticking is allowed."""
    criterion = port.get_criterion(criterion_id)
    if criterion is None:
        raise KeyError(f"criterion #{criterion_id} not found")
    row = port.add_evidence(
        criterion_id,
        command=command,
        exit_code=exit_code,
        commit_sha=commit_sha,
        pr_url=pr_url,
        artifact_path=artifact_path,
        note=note,
        task_id=task_id,
        actor=actor,
    )
    ticked = False
    if tick and row.passing:
        updated = port.set_criteria(criterion_id, True, actor=actor)
        if updated is not None:
            criterion = updated
            ticked = True
    return ProofResult(row, criterion, ticked)


def list_evidence(port: ProvenancePort, criterion_id: int) -> list[CriterionEvidence]:
    """Evidence rows for one criterion, oldest first."""
    return port.list_evidence(criterion_id)


def task_gate(port: ProvenancePort, task_id: int) -> str | None:
    """Reason a task cannot finish for lack of passing evidence, or None."""
    missing = [
        criterion
        for criterion in port.list_criteria("task", task_id)
        if proof_state(port.list_evidence(criterion.id)) != PROOF_PASS
    ]
    if not missing:
        return None
    names = ", ".join(f"#{criterion.id}" for criterion in missing[:5])
    more = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
    return (
        f"task #{task_id} needs passing evidence for criteria {names}{more};"
        " run lpui criterion prove --id <criterion> ..."
    )


def coverage(port: ProvenancePort, plan_ids: list[int]) -> tuple[int, int]:
    """Criteria with a latest passing row, and total criteria, for these plans."""
    criteria = port.criteria_map()
    milestones = port.milestones_map()
    tasks = port.tasks_map()
    ids: list[int] = []
    for plan_id in plan_ids:
        ids.extend(item.id for item in criteria.get(("plan", plan_id), ()))
        for milestone in milestones.get(plan_id, ()):
            ids.extend(item.id for item in criteria.get(("milestone", milestone.id), ()))
            for task in tasks.get(milestone.id, ()):
                ids.extend(item.id for item in criteria.get(("task", task.id), ()))
    return coverage_policy(port.evidence_map(), ids)
