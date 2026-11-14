"""Golden bytes for the active-plan read paths.

The context hook injects ``context.lines`` verbatim and the CLI prints the
brief and needs_me payloads as JSON. These snapshots pin the current selection,
traversal, ordering, and values while the three private selectors collapse into
one module.

Fixtures use ``restore_note``/``restore_comment`` and pass ``now`` so the
snapshots carry no wall clock.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import brief, context, needs_me
from lazyplan.store import Store

NOW = 1_700_000_000.0


def seed(store: Store, kind: str) -> None:
    """Three scenarios plus a mixed one that pins selection precedence."""
    if kind == "empty":
        return
    plan = store.add_plan("P", "why text", goal="goal text", actor="fixture")
    milestone = store.add_milestone(plan.id, "M", "desc", actor="fixture")
    doing = store.add_task(milestone.id, "Doing task", "desc", actor="fixture")
    store.add_task(milestone.id, "Next task", "desc", actor="fixture")
    store.add_criteria("task", doing.id, "still open", actor="fixture")
    if kind in {"doing", "mixed"}:
        services.set_status(store, "task", doing.id, Status.DOING, actor="fixture")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="fixture")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="fixture")
        store.claim_task(doing.id, "fixture", now=NOW)
        store.restore_note("task", doing.id, "handoff", "fixture", 1000.0)
        store.restore_comment("task", doing.id, "review", "fixture", 1001.0, False)
        store.link_commit(
            "task", doing.id, "a" * 40, subject="work", timestamp=1000, actor="fixture"
        )
    if kind == "mixed":
        other = store.add_plan("Later", "other why", goal="other goal", actor="fixture")
        store.add_milestone(other.id, "M2", actor="fixture")


def snapshot(store: Store) -> dict[str, object]:
    """Context lines plus the two JSON payloads the surfaces render."""
    return {
        "context": context.lines(context.build(store)),
        "brief": brief.build(store, commits=[]),
        "needs_me": needs_me.build(store, now=NOW),
    }


#: Scenario name to its context lines, brief payload, and needs_me payload.
GOLDENS: dict[str, dict[str, object]] = {
    "empty": {
        "context": ["no active plans"],
        "brief": {"plans": [], "active": 0},
        "needs_me": {
            "generated_at": 1700000000.0,
            "plan_id": None,
            "plans": [],
            "attention": [],
            "agents": [],
            "claims": [],
            "overlaps": [],
            "counts": {
                "plans": 0,
                "attention": 0,
                "agents": 0,
                "claims": 0,
                "open_questions": 0,
                "drift": 0,
                "overlaps": 0,
            },
            "needs_me_task_ids": [],
            "needs_me_plan_ids": [],
        },
    },
    "todo": {
        "context": [
            "P1 P (todo)",
            "  why      goal text",
            "  doing    none",
            "  next     T1 Doing task",
            "  next     T2 Next task",
        ],
        "brief": {
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "todo",
                    "doing": [],
                    "next": {"id": 1, "title": "Doing task"},
                    "criteria": [],
                    "unlinked": [],
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "questions": [],
                    "previous_session": None,
                }
            ],
            "active": 1,
        },
        "needs_me": {
            "generated_at": 1700000000.0,
            "plan_id": None,
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "todo",
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "question_count": 0,
                    "questions": [],
                    "reference_count": 0,
                    "claim_count": 0,
                    "task_counts": {"todo": 2, "doing": 0, "done": 0},
                    "reasons": [],
                }
            ],
            "attention": [],
            "agents": [],
            "claims": [],
            "overlaps": [],
            "counts": {
                "plans": 1,
                "attention": 0,
                "agents": 0,
                "claims": 0,
                "open_questions": 0,
                "drift": 0,
                "overlaps": 0,
            },
            "needs_me_task_ids": [],
            "needs_me_plan_ids": [],
        },
    },
    "doing": {
        "context": [
            "P1 P (doing)",
            "  why      goal text",
            "  doing    T1 Doing task",
            "  update   lpui task move --id 1 --to doing|done after each commit",
            "  next     T2 Next task",
            "  gaps     1 open criteria",
            "  note     @fixture: handoff",
            "  comment  @fixture: review",
            "  commits  1 recent",
        ],
        "brief": {
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "doing",
                    "doing": [
                        {
                            "id": 1,
                            "title": "Doing task",
                            "claim": {
                                "task_id": 1,
                                "actor": "fixture",
                                "started_at": 1700000000.0,
                                "expires_at": 1700001800.0,
                                "renewed_at": 1700000000.0,
                                "note": "",
                                "worktree": "",
                                "repo_path": "",
                            },
                            "notes": [
                                {
                                    "id": 1,
                                    "parent_kind": "task",
                                    "parent_id": 1,
                                    "text": "handoff",
                                    "actor": "fixture",
                                    "ts": 1000.0,
                                }
                            ],
                            "comments": [
                                {
                                    "id": 1,
                                    "parent_kind": "task",
                                    "parent_id": 1,
                                    "text": "review",
                                    "actor": "fixture",
                                    "ts": 1001.0,
                                    "resolved": False,
                                }
                            ],
                        }
                    ],
                    "next": {"id": 2, "title": "Next task"},
                    "criteria": [{"kind": "task", "id": 1, "text": "still open"}],
                    "unlinked": [],
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "questions": [],
                    "previous_session": None,
                }
            ],
            "active": 1,
        },
        "needs_me": {
            "generated_at": 1700000000.0,
            "plan_id": None,
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "doing",
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "question_count": 0,
                    "questions": [],
                    "reference_count": 0,
                    "claim_count": 1,
                    "task_counts": {"todo": 1, "doing": 1, "done": 0},
                    "reasons": [],
                }
            ],
            "attention": [],
            "agents": [],
            "claims": [
                {
                    "task_id": 1,
                    "task_title": "Doing task",
                    "task_status": "doing",
                    "milestone_id": 1,
                    "plan_id": 1,
                    "plan_title": "P",
                    "actor": "fixture",
                    "expires_at": 1700001800.0,
                    "expires_in": 1800.0,
                    "worktree": "",
                    "repo_path": "",
                }
            ],
            "overlaps": [],
            "counts": {
                "plans": 1,
                "attention": 0,
                "agents": 0,
                "claims": 1,
                "open_questions": 0,
                "drift": 0,
                "overlaps": 0,
            },
            "needs_me_task_ids": [],
            "needs_me_plan_ids": [],
        },
    },
    "mixed": {
        "context": [
            "P1 P (doing)",
            "  why      goal text",
            "  doing    T1 Doing task",
            "  update   lpui task move --id 1 --to doing|done after each commit",
            "  next     T2 Next task",
            "  gaps     1 open criteria",
            "  note     @fixture: handoff",
            "  comment  @fixture: review",
            "  commits  1 recent",
        ],
        "brief": {
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "doing",
                    "doing": [
                        {
                            "id": 1,
                            "title": "Doing task",
                            "claim": {
                                "task_id": 1,
                                "actor": "fixture",
                                "started_at": 1700000000.0,
                                "expires_at": 1700001800.0,
                                "renewed_at": 1700000000.0,
                                "note": "",
                                "worktree": "",
                                "repo_path": "",
                            },
                            "notes": [
                                {
                                    "id": 1,
                                    "parent_kind": "task",
                                    "parent_id": 1,
                                    "text": "handoff",
                                    "actor": "fixture",
                                    "ts": 1000.0,
                                }
                            ],
                            "comments": [
                                {
                                    "id": 1,
                                    "parent_kind": "task",
                                    "parent_id": 1,
                                    "text": "review",
                                    "actor": "fixture",
                                    "ts": 1001.0,
                                    "resolved": False,
                                }
                            ],
                        }
                    ],
                    "next": {"id": 2, "title": "Next task"},
                    "criteria": [{"kind": "task", "id": 1, "text": "still open"}],
                    "unlinked": [],
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "questions": [],
                    "previous_session": None,
                }
            ],
            "active": 1,
        },
        "needs_me": {
            "generated_at": 1700000000.0,
            "plan_id": None,
            "plans": [
                {
                    "id": 1,
                    "title": "P",
                    "status": "doing",
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "question_count": 0,
                    "questions": [],
                    "reference_count": 0,
                    "claim_count": 1,
                    "task_counts": {"todo": 1, "doing": 1, "done": 0},
                    "reasons": [],
                },
                {
                    "id": 2,
                    "title": "Later",
                    "status": "todo",
                    "approval": {"revision": 0, "enforced": False, "drift": 0},
                    "question_count": 0,
                    "questions": [],
                    "reference_count": 0,
                    "claim_count": 0,
                    "task_counts": {"todo": 0, "doing": 0, "done": 0},
                    "reasons": [],
                },
            ],
            "attention": [],
            "agents": [],
            "claims": [
                {
                    "task_id": 1,
                    "task_title": "Doing task",
                    "task_status": "doing",
                    "milestone_id": 1,
                    "plan_id": 1,
                    "plan_title": "P",
                    "actor": "fixture",
                    "expires_at": 1700001800.0,
                    "expires_in": 1800.0,
                    "worktree": "",
                    "repo_path": "",
                }
            ],
            "overlaps": [],
            "counts": {
                "plans": 2,
                "attention": 0,
                "agents": 0,
                "claims": 1,
                "open_questions": 0,
                "drift": 0,
                "overlaps": 0,
            },
            "needs_me_task_ids": [],
            "needs_me_plan_ids": [],
        },
    },
}


class ActivePathGoldenTest(unittest.TestCase):
    maxDiff = None

    def store_for(self, kind: str) -> Store:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(os.path.join(tmp.name, "golden.db"))
        seed(store, kind)
        return store

    def test_snapshots_are_byte_identical(self) -> None:
        for kind, expected in GOLDENS.items():
            with self.subTest(kind=kind):
                actual = snapshot(self.store_for(kind))
                self.assertEqual(
                    json.dumps(actual, indent=2),
                    json.dumps(expected, indent=2),
                    f"{kind} payload changed",
                )

    def test_context_text_is_byte_identical(self) -> None:
        for kind, expected in GOLDENS.items():
            with self.subTest(kind=kind):
                store = self.store_for(kind)
                self.assertEqual(
                    "\n".join(context.lines(context.build(store))),
                    "\n".join(expected["context"]),
                )

    def test_doing_plan_wins_over_todo(self) -> None:
        store = self.store_for("mixed")
        self.assertEqual([plan["id"] for plan in brief.build(store, commits=[])["plans"]], [1])
        self.assertEqual([plan["id"] for plan in needs_me.build(store, now=NOW)["plans"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
