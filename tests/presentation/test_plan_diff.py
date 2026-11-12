"""Plan-scope diffs group by kind and trim long scope text."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import PlanRevision
from lazyplan.core.policies.revisions import Change
from lazyplan.services.revisions import DiffEntry, DiffResult

try:
    from lazyplan.presentation.tui.views.diff import build_plan_diff, diff_text
except ImportError:  # pragma: no cover - textual not installed
    build_plan_diff = diff_text = None  # type: ignore[assignment]

REVISION = PlanRevision(
    id=1,
    plan_id=1,
    revision=3,
    approved_at=0.0,
    digest="a" * 64,
    snapshot="{}",
)


def _entry(
    kind: str,
    action: str,
    title: str,
    *,
    before: str = "",
    after: str = "",
    reason: str = "",
) -> DiffEntry:
    return DiffEntry(
        change=Change(
            kind=kind,
            action=action,
            obj_id=1,
            identity=f"{kind}:1",
            title=title,
            before=before,
            after=after,
        ),
        reason=reason,
    )


def _result(entries: tuple[DiffEntry, ...], summary: dict[str, int] | None = None) -> DiffResult:
    counts = summary or {"add": 0, "remove": 0, "change": 0, "move": 0, "total": len(entries)}
    return DiffResult(
        plan_id=1,
        from_revision=REVISION,
        to_revision=None,
        entries=entries,
        summary=counts,
    )


@unittest.skipUnless(build_plan_diff is not None, "textual not installed")
class PlanDiffModelTest(unittest.TestCase):
    def test_groups_follow_kind_order(self) -> None:
        result = _result(
            (
                _entry(
                    "criterion",
                    "add",
                    "Works offline",
                ),
                _entry("task", "change", "Read the diff", after="new text"),
                _entry("plan", "change", "Plan title", after="renamed"),
                _entry("milestone", "remove", "Old slice"),
            )
        )
        view = build_plan_diff(result)
        self.assertEqual(
            [group.kind for group in view.groups],
            [
                "plan",
                "milestone",
                "task",
                "criterion",
            ],
        )
        self.assertEqual(view.total, 4)

    def test_long_text_is_flattened_and_trimmed(self) -> None:
        result = _result(
            (
                _entry(
                    "plan",
                    "change",
                    "Plan",
                    before="old\nline",
                    after="word " * 200,
                    reason="because " * 100,
                ),
            )
        )
        row = build_plan_diff(result, max_text=40).groups[0].rows[0]
        self.assertLessEqual(len(row.after), 41)
        self.assertIn("…", row.after)
        self.assertNotIn("\n", row.after)
        self.assertNotIn("\n", row.reason)
        self.assertEqual(row.before, "old line")

    def test_empty_diff_reports_in_sync(self) -> None:
        result = _result(())
        view = build_plan_diff(result)
        self.assertTrue(view.empty)
        self.assertIn("in sync with the approved revision", diff_text(result))

    def test_text_keeps_summary_and_group_headers(self) -> None:
        result = _result(
            (_entry("task", "change", "Read the diff", after="new text", reason="scope"),),
            summary={"add": 0, "remove": 0, "change": 1, "move": 0, "total": 1},
        )
        text = diff_text(result)
        self.assertIn("1 changes", text)
        self.assertIn("TASKS", text)
        self.assertIn("~ task 1 Read the diff", text)
        self.assertIn("reason: scope", text)


if __name__ == "__main__":
    unittest.main()
