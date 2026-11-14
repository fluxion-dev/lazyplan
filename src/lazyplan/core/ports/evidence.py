"""The evidence port: proof rows for acceptance criteria."""

from __future__ import annotations

from typing import Protocol

from ..entities import CriterionEvidence


class EvidencePort(Protocol):
    """Evidence writes, reads, and the task gate built on them."""

    def add_evidence(
        self,
        criterion_id: int,
        command: str = "",
        exit_code: int | None = None,
        commit_sha: str = "",
        pr_url: str = "",
        artifact_path: str = "",
        note: str = "",
        task_id: int | None = None,
        actor: str = "human",
    ) -> CriterionEvidence: ...

    def restore_evidence(
        self,
        criterion_id: int,
        task_id: int | None = None,
        command: str = "",
        exit_code: int | None = None,
        commit_sha: str = "",
        pr_url: str = "",
        artifact_path: str = "",
        note: str = "",
        actor: str = "human",
        ts: float = 0.0,
    ) -> CriterionEvidence | None: ...

    def list_evidence(self, criterion_id: int) -> list[CriterionEvidence]: ...

    def evidence_map(self) -> dict[int, list[CriterionEvidence]]: ...

    def gate_state(self, task_id: int) -> dict: ...
