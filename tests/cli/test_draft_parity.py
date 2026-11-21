"""Draft loop parity: the CLI and MCP produce the same state and plan tree."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation import mcp
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


def document(
    key: str = "demo-plan",
    title: str = "Demo plan",
    why: str = "Why this matters.",
) -> dict:
    return {
        "plan": {
            "key": key,
            "title": title,
            "why": why,
            "what": "## Scope\n\n- One thing.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "build",
                "title": "Build it",
                "desc": "As a user, I want the change.",
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": "Approach: do the work.",
                        "criteria": ["Tests pass."],
                    }
                ],
            }
        ],
    }


def _draft_summary(payload: dict) -> dict:
    """Only the fields both surfaces must agree on."""
    return {
        key: payload[key]
        for key in (
            "id",
            "title",
            "status",
            "revision",
            "open_annotations",
            "total_annotations",
            "plan_id",
        )
    }


def _annotation_summary(payload: dict) -> dict:
    """Only the annotation fields both surfaces must agree on."""
    return {
        key: payload[key]
        for key in (
            "id",
            "draft_id",
            "block_key",
            "kind",
            "body",
            "status",
            "quote",
            "start_offset",
            "end_offset",
            "anchor_state",
            "response",
        )
    }


def _tree(payload: dict) -> dict:
    """The plan tree in a shape both surfaces return."""
    plan = payload["plan"]
    milestones = []
    for entry in payload["milestones"]:
        milestone = entry["milestone"]
        tasks = []
        for task_entry in entry["tasks"]:
            task = task_entry.get("task", task_entry)
            tasks.append(
                {
                    "title": task["title"],
                    "description": task["description"],
                    "criteria": [row["text"] for row in task_entry.get("criteria", [])],
                }
            )
        milestones.append(
            {
                "title": milestone["title"],
                "description": milestone["description"],
                "criteria": [row["text"] for row in entry["criteria"]],
                "tasks": tasks,
            }
        )
    return {
        "name": plan["name"],
        "goal": plan["goal"],
        "description": plan["description"],
        "criteria": [row["text"] for row in payload["criteria"]],
        "milestones": milestones,
    }


def _stored_tree(store: Store, plan_id: int) -> dict:
    """The persisted plan tree, including task criteria."""
    plan = store.get_plan(plan_id)
    assert plan is not None
    milestones = []
    for milestone in store.list_milestones(plan_id):
        tasks = []
        for task in store.list_tasks(milestone.id):
            tasks.append(
                {
                    "title": task.title,
                    "description": task.description,
                    "criteria": [row.text for row in store.list_criteria("task", task.id)],
                }
            )
        milestones.append(
            {
                "title": milestone.title,
                "description": milestone.description,
                "criteria": [row.text for row in store.list_criteria("milestone", milestone.id)],
                "tasks": tasks,
            }
        )
    return {
        "name": plan.name,
        "goal": plan.goal,
        "description": plan.description,
        "criteria": [row.text for row in store.list_criteria("plan", plan_id)],
        "milestones": milestones,
    }


SKETCH = (
    "# Sketch title\n\n## Why\n\nWhy review matters."
    "\n\n## What\n\n## Scope\n\n- One thing.\n\n## Done\n\n- Works."
)


def sketch_document() -> dict:
    """The structured document matching SKETCH's reviewed definition."""
    return document(key="sketch-plan", title="Sketch title", why="Why review matters.")


class DraftParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cli_db = os.path.join(self.tmp.name, "cli.db")
        self.mcp_db = os.path.join(self.tmp.name, "mcp.db")
        self.cli_store = Store(self.cli_db)
        self.mcp_store = Store(self.mcp_db)
        self.server = mcp.McpServer(self.mcp_store, actor="agent")
        self.file = os.path.join(self.tmp.name, "draft.json")
        self.revised = os.path.join(self.tmp.name, "revised.json")
        self._write(self.file, document())
        self._write(self.revised, document(title="Revised", why="A sharper Why."))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, path: str, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def _cli(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.cli_db, "--actor", "agent", *argv])
        return code, out.getvalue(), err.getvalue()

    def _cli_json(self, *argv: str) -> object:
        code, out, err = self._cli("--json", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def _tool(self, name: str, arguments: dict) -> dict:
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert response is not None
        return response["result"]

    def _tool_json(self, name: str, arguments: dict) -> object:
        result = self._tool(name, arguments)
        self.assertFalse(result.get("isError"), result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    def _run_loop(self) -> tuple[dict, dict, dict]:
        """Run the same script through both surfaces."""
        added = self._cli_json("draft", "add", "--file", self.file)
        assert isinstance(added, dict)
        cli_id = int(added["draft"]["id"])
        annotation = self._cli_json(
            "draft",
            "annotate",
            "--id",
            str(cli_id),
            "--block",
            "plan:why",
            "--kind",
            "change",
            "--text",
            "Sharpen the why",
            "--quote",
            "Why",
        )
        assert isinstance(annotation, dict)
        annotation_id = int(annotation["annotation"]["id"])
        self._cli_json(
            "draft",
            "revise",
            "--id",
            str(cli_id),
            "--file",
            self.revised,
            "--base-revision",
            "1",
            "--note",
            "addressed",
        )
        self._cli_json(
            "draft",
            "respond",
            "--id",
            str(annotation_id),
            "--response",
            "Sharpened",
        )
        self._cli_json("draft", "ready", "--id", str(cli_id))
        cli_promotion = self._cli_json("draft", "promote", "--id", str(cli_id))
        assert isinstance(cli_promotion, dict)

        added = self._tool_json("draft_add", {"document": document()})
        assert isinstance(added, dict)
        mcp_id = int(added["draft"]["id"])
        annotation = self._tool_json(
            "draft_annotate",
            {
                "id": mcp_id,
                "block": "plan:why",
                "kind": "change",
                "text": "Sharpen the why",
                "quote": "Why",
            },
        )
        assert isinstance(annotation, dict)
        mcp_annotation_id = int(annotation["annotation"]["id"])
        self._tool_json(
            "draft_revise",
            {
                "id": mcp_id,
                "document": document(title="Revised", why="A sharper Why."),
                "base_revision": 1,
                "note": "addressed",
            },
        )
        self._tool_json(
            "draft_respond",
            {"id": mcp_annotation_id, "response": "Sharpened"},
        )
        self._tool_json("draft_ready", {"id": mcp_id})
        mcp_promotion = self._tool_json("draft_promote", {"id": mcp_id})
        assert isinstance(mcp_promotion, dict)

        self.assertEqual(
            _draft_summary(cli_promotion["draft"]), _draft_summary(mcp_promotion["draft"])
        )
        self.assertEqual(cli_promotion["plan"]["id"], mcp_promotion["plan"]["id"])
        self.assertEqual(cli_promotion["counts"], mcp_promotion["counts"])

        cli_list = self._cli_json("draft", "list")
        mcp_list = self._tool_json("draft_list", {})
        assert isinstance(cli_list, list) and isinstance(mcp_list, list)
        self.assertEqual(
            [_draft_summary(row) for row in cli_list],
            [_draft_summary(row) for row in mcp_list],
        )

        cli_annotations = self._cli_json("draft", "annotations", "--id", str(cli_id))
        mcp_annotations = self._tool_json("draft_annotations", {"id": mcp_id})
        assert isinstance(cli_annotations, list) and isinstance(mcp_annotations, list)
        self.assertEqual(
            [_annotation_summary(row) for row in cli_annotations],
            [_annotation_summary(row) for row in mcp_annotations],
        )

        cli_tree = self._cli_json("plan", "show", "--id", str(cli_promotion["plan"]["id"]))
        mcp_tree = self._tool_json("show_row", {"kind": "plan", "id": mcp_promotion["plan"]["id"]})
        assert isinstance(cli_tree, dict) and isinstance(mcp_tree, dict)
        self.assertEqual(_tree(cli_tree), _tree(mcp_tree))
        self.assertEqual(
            _stored_tree(self.cli_store, int(cli_promotion["plan"]["id"])),
            _stored_tree(self.mcp_store, int(mcp_promotion["plan"]["id"])),
        )
        return cli_promotion, cli_annotations[0], _tree(cli_tree)

    def test_full_loop_matches(self) -> None:
        promotion, annotation, tree = self._run_loop()
        self.assertEqual(annotation["status"], "addressed")
        self.assertEqual(annotation["anchor_state"], "moved")
        self.assertEqual(tree["name"], "Revised")
        self.assertEqual(tree["milestones"][0]["tasks"][0]["title"], "Implement it")
        self.assertEqual(promotion["draft"]["status"], "promoted")

    def test_sketch_loop_matches(self) -> None:
        sketch_file = os.path.join(self.tmp.name, "sketch.md")
        revised_file = os.path.join(self.tmp.name, "sketch-revised.md")
        with open(sketch_file, "w", encoding="utf-8") as handle:
            handle.write(SKETCH)
        with open(revised_file, "w", encoding="utf-8") as handle:
            handle.write(SKETCH.replace("Why review matters.", "A sharper why."))

        cli_added = self._cli_json("draft", "sketch", "--file", sketch_file)
        mcp_added = self._tool_json("draft_sketch", {"markdown": SKETCH})
        assert isinstance(cli_added, dict) and isinstance(mcp_added, dict)
        cli_id = int(cli_added["draft"]["id"])
        mcp_id = int(mcp_added["draft"]["id"])
        self.assertEqual(_draft_summary(cli_added["draft"]), _draft_summary(mcp_added["draft"]))

        cli_show = self._cli_json("draft", "show", "--id", str(cli_id))
        mcp_show = self._tool_json("draft_show", {"id": mcp_id})
        assert isinstance(cli_show, dict) and isinstance(mcp_show, dict)
        self.assertEqual(cli_show["sketch"], mcp_show["sketch"])
        self.assertEqual(
            [block["key"] for block in cli_show["blocks"]],
            [block["key"] for block in mcp_show["blocks"]],
        )

        self._cli_json(
            "draft",
            "revise",
            "--id",
            str(cli_id),
            "--file",
            revised_file,
            "--base-revision",
            "1",
        )
        self._tool_json(
            "draft_revise",
            {
                "id": mcp_id,
                "document": SKETCH.replace("Why review matters.", "A sharper why."),
                "base_revision": 1,
            },
        )

        formal = sketch_document()
        formal["plan"]["why"] = "A sharper why."
        formal_file = os.path.join(self.tmp.name, "formal.json")
        self._write(formal_file, formal)
        cli_formal = self._cli_json(
            "draft",
            "formalize",
            "--id",
            str(cli_id),
            "--file",
            formal_file,
            "--base-revision",
            "2",
        )
        mcp_formal = self._tool_json(
            "draft_formalize",
            {"id": mcp_id, "document": formal, "base_revision": 2},
        )
        assert isinstance(cli_formal, dict) and isinstance(mcp_formal, dict)
        self.assertEqual(cli_formal["draft"]["format"], "document")
        self.assertEqual(_draft_summary(cli_formal["draft"]), _draft_summary(mcp_formal["draft"]))

        cli_promotion = self._cli_json("draft", "promote", "--id", str(cli_id))
        mcp_promotion = self._tool_json("draft_promote", {"id": mcp_id})
        assert isinstance(cli_promotion, dict) and isinstance(mcp_promotion, dict)
        self.assertEqual(cli_promotion["counts"], mcp_promotion["counts"])
        self.assertEqual(
            _stored_tree(self.cli_store, int(cli_promotion["plan"]["id"])),
            _stored_tree(self.mcp_store, int(mcp_promotion["plan"]["id"])),
        )

    def test_stale_revision_fails_identically(self) -> None:
        self._cli_json("draft", "add", "--file", self.file)
        code, _out, cli_err = self._cli(
            "--json",
            "draft",
            "revise",
            "--id",
            "1",
            "--file",
            self.revised,
            "--base-revision",
            "0",
        )
        self.assertEqual(code, 2)
        cli_message = cli_err.strip()

        self._tool_json("draft_add", {"document": document()})
        result = self._tool(
            "draft_revise",
            {
                "id": 1,
                "document": document(),
                "base_revision": 0,
            },
        )
        self.assertTrue(result.get("isError"))
        mcp_message = result["content"][0]["text"]
        self.assertIn("draft #1 is at revision 1, not 0", cli_message)
        self.assertIn("draft #1 is at revision 1, not 0", mcp_message)

    def test_open_annotation_promotion_fails_identically(self) -> None:
        self._cli_json("draft", "add", "--file", self.file)
        self._cli_json(
            "draft",
            "annotate",
            "--id",
            "1",
            "--block",
            "plan:why",
            "--kind",
            "change",
            "--text",
            "Sharpen",
        )
        code, _out, cli_err = self._cli("--json", "draft", "promote", "--id", "1")
        self.assertEqual(code, 2)

        self._tool_json("draft_add", {"document": document()})
        self._tool_json(
            "draft_annotate",
            {
                "id": 1,
                "block": "plan:why",
                "kind": "change",
                "text": "Sharpen",
            },
        )
        result = self._tool("draft_promote", {"id": 1})
        self.assertTrue(result.get("isError"))
        cli_message = cli_err.strip()
        mcp_message = result["content"][0]["text"]
        self.assertIn("has 1 open annotation", cli_message)
        self.assertIn("has 1 open annotation", mcp_message)


if __name__ == "__main__":
    unittest.main()
