"""Pure criterion evidence rules."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import CriterionEvidence
from lazyplan.core.policies.evidence import (
    PROOF_FAIL,
    PROOF_NONE,
    PROOF_PASS,
    check_task,
    coverage,
    latest,
    proof_state,
    summarize,
)


def evidence(
    row_id: int = 1,
    criterion_id: int = 10,
    ts: float = 1.0,
    exit_code: int | None = 0,
    **kwargs: object,
) -> CriterionEvidence:
    """One evidence row with a command unless the caller overrides it."""
    if "command" not in kwargs and "commit_sha" not in kwargs and "note" not in kwargs:
        kwargs["command"] = "pytest"
    return CriterionEvidence(
        id=row_id,
        criterion_id=criterion_id,
        exit_code=exit_code,
        ts=ts,
        **kwargs,  # type: ignore[arg-type]
    )


class TestEvidenceEntity(unittest.TestCase):
    def test_passing_exit_codes(self) -> None:
        self.assertTrue(evidence(exit_code=0).passing)
        self.assertTrue(evidence(exit_code=None).passing)
        self.assertFalse(evidence(exit_code=1).passing)

    def test_empty_row_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CriterionEvidence(id=1, criterion_id=10, command="", exit_code=1)

    def test_manual_note_is_valid(self) -> None:
        row = CriterionEvidence(id=1, criterion_id=10, note="reviewed by eye")
        self.assertTrue(row.passing)

    def test_commit_hash_is_validated_and_normalized(self) -> None:
        row = evidence(command="", commit_sha="A" * 40)
        self.assertEqual(row.commit_sha, "a" * 40)
        with self.assertRaises(ValueError):
            evidence(command="", commit_sha="abc")

    def test_ids_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            CriterionEvidence(id=1, criterion_id=0, command="pytest")
        with self.assertRaises(ValueError):
            CriterionEvidence(id=1, criterion_id=10, task_id=0, command="pytest")

    def test_exit_code_must_be_an_int_or_none(self) -> None:
        with self.assertRaises(ValueError):
            CriterionEvidence(id=1, criterion_id=10, command="pytest", exit_code="0")  # type: ignore[arg-type]


class TestEvidenceRules(unittest.TestCase):
    def test_latest_uses_timestamp_then_id(self) -> None:
        rows = [evidence(1, ts=2.0), evidence(2, ts=3.0), evidence(3, ts=3.0)]
        chosen = latest(rows)
        assert chosen is not None
        self.assertEqual(chosen.id, 3)

    def test_state_without_rows_is_none(self) -> None:
        self.assertEqual(proof_state([]), PROOF_NONE)

    def test_latest_pass_or_fail_decides(self) -> None:
        self.assertEqual(proof_state([evidence(1, ts=1.0)]), PROOF_PASS)
        self.assertEqual(proof_state([evidence(1, ts=1.0, exit_code=1)]), PROOF_FAIL)
        self.assertEqual(
            proof_state([evidence(1, ts=2.0), evidence(2, ts=1.0, exit_code=1)]),
            PROOF_PASS,
        )
        self.assertEqual(
            proof_state([evidence(1, ts=1.0), evidence(2, ts=2.0, exit_code=1)]),
            PROOF_FAIL,
        )

    def test_summary_counts_rows(self) -> None:
        rows = [evidence(1, ts=1.0), evidence(2, ts=2.0, exit_code=1)]
        summary = summarize(rows)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["state"], PROOF_FAIL)
        self.assertEqual(summary["latest"].id, 2)

    def test_unrelated_task_is_rejected(self) -> None:
        check_task(None, [])
        check_task(1, [1, 2])
        with self.assertRaises(ValueError):
            check_task(3, [1, 2])

    def test_coverage_counts_latest_passes(self) -> None:
        rows = {
            10: [evidence(1, criterion_id=10)],
            11: [evidence(2, criterion_id=11, exit_code=1)],
        }
        self.assertEqual(coverage(rows, [10, 11, 12]), (1, 3))
        self.assertEqual(coverage({}, []), (0, 0))


if __name__ == "__main__":
    unittest.main()
