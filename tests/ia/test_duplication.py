"""The duplication report covers every action and names today's duplicates.

``BASELINE_*`` records the duplicates the thinning plan collapses, so each
slice shrinks a number instead of arguing about intent. A group leaves the
baseline only by sharing one implementation.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lazyplan.presentation.shared import registry
from tests.ia import duplication

#: add_* parser builders that wire the same flags, sorted by name.
BASELINE_PARSER_DUPLICATES: tuple[tuple[str, ...], ...] = (
    ("coordination:add_claims", "coordination:add_who"),
    ("coordination:add_mcp", "work:add_reconcile"),
    ("coordination:add_review", "coordination:add_ship"),
    ("proof:add_link_repo", "proof:add_unlink_repo"),
)

#: MCP _tool_* handlers whose normalized bodies are identical, sorted by name.
BASELINE_HANDLER_DUPLICATES: tuple[tuple[str, ...], ...] = (
    (
        "collaboration_tools:_tool_criterion_list",
        "provenance_tools:_tool_commit_list",
        "provenance_tools:_tool_pull_request_list",
    ),
    ("collaboration_tools:_tool_reference_list", "evidence_tools:_tool_criterion_evidence"),
    ("maintenance_tools:_tool_maintenance_archive", "maintenance_tools:_tool_maintenance_trim"),
    ("provenance_tools:_tool_commit_refresh", "provenance_tools:_tool_pull_request_refresh"),
    ("question_tools:_tool_question_reopen", "question_tools:_tool_question_resolve"),
    ("review_tools:_tool_review", "review_tools:_tool_ship"),
)

#: Action ids typed as literals outside the Action rows, and their occurrences.
BASELINE_RETYPED_IDS = 75
BASELINE_RETYPED_OCCURRENCES = 194


class DuplicationReportTest(unittest.TestCase):
    def test_every_declared_action_has_one_row(self) -> None:
        rows = duplication.surface_rows()
        self.assertEqual([row["action"] for row in rows], sorted(a.id for a in registry.ACTIONS))

    def test_every_row_names_its_reachable_surfaces(self) -> None:
        covered = [row["action"] for row in duplication.surface_rows() if row["cli"] or row["mcp"]]
        self.assertGreater(len(covered), 50)

    def test_parser_duplicate_baseline_is_recorded(self) -> None:
        self.assertEqual(duplication.parser_duplicates(), list(BASELINE_PARSER_DUPLICATES))

    def test_handler_duplicate_baseline_is_recorded(self) -> None:
        self.assertEqual(duplication.handler_duplicates(), list(BASELINE_HANDLER_DUPLICATES))

    def test_retyped_action_baseline_is_recorded(self) -> None:
        retyped = duplication.retyped_actions()
        self.assertEqual(len(retyped), BASELINE_RETYPED_IDS)
        self.assertEqual(sum(retyped.values()), BASELINE_RETYPED_OCCURRENCES)

    def test_detectors_find_a_seeded_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "seed.py").write_text(
                "def add_left(sub, common):\n"
                "    p = sub.add_parser('left')\n"
                "    p.add_argument('--id', type=int, required=True)\n"
                "    p.add_argument('--note', required=True)\n"
                "\n"
                "\n"
                "def add_right(sub, common):\n"
                "    q = sub.add_parser('right')\n"
                "    q.add_argument('--id', type=int, required=True)\n"
                "    q.add_argument('--note', required=True)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                duplication.parser_duplicates(root), [("seed:add_left", "seed:add_right")]
            )

    def test_report_renders_every_section(self) -> None:
        report = duplication.render()
        self.assertIn("# Adapter duplication report", report)
        self.assertIn("## Parser builders that share wiring", report)
        self.assertIn("## MCP handlers that share a body", report)
        self.assertIn("## Action ids typed outside the Action rows", report)
        for action in registry.ACTIONS:
            self.assertIn(action.id, report)


if __name__ == "__main__":
    unittest.main()
