"""Criterion proof rules: the latest row decides, and coverage is explicit."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from ..entities import CriterionEvidence

PROOF_NONE = "none"
PROOF_PASS = "pass"
PROOF_FAIL = "fail"


def latest(rows: Sequence[CriterionEvidence]) -> CriterionEvidence | None:
    """Newest evidence row, by timestamp then id."""
    return max(rows, key=lambda row: (row.ts, row.id), default=None)


def proof_state(rows: Sequence[CriterionEvidence]) -> str:
    """none, pass, or fail from the latest row; an older pass never hides a failure."""
    row = latest(rows)
    if row is None:
        return PROOF_NONE
    return PROOF_PASS if row.passing else PROOF_FAIL


def summarize(rows: Sequence[CriterionEvidence]) -> dict:
    """Count and latest state for one criterion's proof panel."""
    return {"count": len(rows), "state": proof_state(rows), "latest": latest(rows)}


def check_task(task_id: int | None, linked: Iterable[int]) -> None:
    """Reject a task that is not one of the criterion's proving tasks."""
    if task_id is None:
        return
    if task_id not in set(linked):
        raise ValueError(f"task #{task_id} is not linked to this criterion")


def coverage(
    evidence: Mapping[int, Sequence[CriterionEvidence]],
    criterion_ids: Iterable[int],
) -> tuple[int, int]:
    """Criteria with a latest passing row, and total criteria."""
    ids = list(criterion_ids)
    covered = sum(
        1 for criterion_id in ids if proof_state(evidence.get(criterion_id, ())) == PROOF_PASS
    )
    return covered, len(ids)
