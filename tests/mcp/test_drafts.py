"""MCP draft tools and resources."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan.presentation import mcp
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
                "desc": (
                    "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
                    "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
                    "Inputs: The approved definition and the scouted code path.\n\n"
                    "Slices: Implement, verify, refactor, and document in separate green commits."
                ),
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": (
                            "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
                            "Touch: src/app.py, tests/test_app.py\n\n"
                            "Inputs: The approved definition; none beyond the plan scope.\n\n"
                            "Commit: One implementation slice.\n\n"
                            "Verify: The relevant test suite passes.\n\n"
                            "Guardrails: Keep behavior outside the reviewed scope unchanged."
                        ),
                        "criteria": ["Tests pass."],
                    }
                ],
            }
        ],
    }


SKETCH = (
    "# Sketch title\n\n## Why\n\nWhy review matters."
    "\n\n## What\n\n## Scope\n\n- One thing.\n\n## Done\n\n- Works."
)


def sketch_document() -> dict:
    """The structured document matching SKETCH's reviewed definition."""
    return document(key="sketch-plan", title="Sketch title", why="Why review matters.")


class DraftMcpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.server = mcp.McpServer(self.store, actor="agent")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _tool(self, name: str, arguments: dict | None = None) -> dict:
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        assert response is not None
        return response["result"]

    def _payload(self, name: str, arguments: dict | None = None) -> object:
        result = self._tool(name, arguments)
        self.assertFalse(result.get("isError"), result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    def _add(self, payload: dict | None = None) -> int:
        result = self._payload("draft_add", {"document": payload or document()})
        assert isinstance(result, dict)
        return int(result["draft"]["id"])

    def _sketch(self) -> int:
        result = self._payload("draft_sketch", {"markdown": SKETCH})
        assert isinstance(result, dict)
        return int(result["draft"]["id"])

    def test_tools_and_resources_are_discoverable(self) -> None:
        names = {
            tool["name"]
            for tool in self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[
                "result"
            ]["tools"]
        }
        self.assertTrue(
            {
                "draft_list",
                "draft_show",
                "draft_annotations",
                "draft_add",
                "draft_sketch",
                "draft_formalize",
                "draft_revise",
                "draft_ready",
                "draft_annotate",
                "draft_respond",
                "draft_resolve",
                "draft_dismiss",
                "draft_promote",
                "draft_delete",
            }
            <= names
        )
        uris = {
            resource["uri"]
            for resource in self.server.handle(
                {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
            )["result"]["resources"]
        }
        self.assertIn("lazyplan://drafts", uris)
        self.assertIn("lazyplan://draft/1", uris)

    def test_read_only_omits_every_write(self) -> None:
        read_only = mcp.McpServer(self.store, actor="agent", read_only=True)
        names = {
            tool["name"]
            for tool in read_only.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[
                "result"
            ]["tools"]
        }
        self.assertIn("draft_list", names)
        self.assertIn("draft_show", names)
        self.assertNotIn("draft_add", names)
        self.assertNotIn("draft_sketch", names)
        self.assertNotIn("draft_formalize", names)
        self.assertNotIn("draft_promote", names)
        result = read_only.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "draft_add", "arguments": {"document": document()}},
            }
        )
        assert result is not None
        self.assertEqual(result["error"]["code"], -32601)

    def test_full_draft_loop(self) -> None:
        draft_id = self._add()
        listed = self._payload("draft_list")
        assert isinstance(listed, list)
        self.assertEqual(listed[0]["id"], draft_id)
        self.assertEqual(listed[0]["open_annotations"], 0)

        shown = self._payload("draft_show", {"id": draft_id})
        assert isinstance(shown, dict)
        self.assertEqual(shown["document"]["plan"]["key"], "demo-plan")
        self.assertTrue(shown["blocks"])

        annotation = self._payload(
            "draft_annotate",
            {
                "id": draft_id,
                "block": "plan:why",
                "kind": "change",
                "text": "Sharpen",
                "quote": "Why",
            },
        )
        assert isinstance(annotation, dict)
        annotation_id = annotation["annotation"]["id"]
        self.assertEqual(annotation["annotation"]["quote"], "Why")

        shown = self._payload("draft_show", {"id": draft_id})
        assert isinstance(shown, dict)
        self.assertEqual(shown["draft"]["status"], "revising")

        revised = self._payload(
            "draft_revise",
            {
                "id": draft_id,
                "document": document(title="Revised", why="A sharper why."),
                "base_revision": 1,
                "note": "addressed",
            },
        )
        assert isinstance(revised, dict)
        self.assertEqual(revised["draft"]["revision"], 2)
        self.assertEqual(revised["draft"]["status"], "review")

        resolved = self._payload("draft_resolve", {"id": annotation_id, "response": "Sharpened"})
        assert isinstance(resolved, dict)
        self.assertEqual(resolved["annotation"]["status"], "addressed")
        ready = self._payload("draft_ready", {"id": draft_id})
        assert isinstance(ready, dict)
        self.assertEqual(ready["draft"]["status"], "review")

        promoted = self._payload("draft_promote", {"id": draft_id})
        assert isinstance(promoted, dict)
        self.assertTrue(promoted["created"])
        self.assertEqual(promoted["plan"]["name"], "Revised")
        self.assertEqual(promoted["counts"], {"milestones": 1, "tasks": 1, "criteria": 3})
        self.assertEqual(promoted["draft"]["status"], "promoted")

        again = self._payload("draft_promote", {"id": draft_id})
        assert isinstance(again, dict)
        self.assertFalse(again["created"])
        refused = self._tool("draft_delete", {"id": draft_id})
        self.assertTrue(refused.get("isError"))

        annotations = self._payload("draft_annotations", {"id": draft_id, "status": "addressed"})
        assert isinstance(annotations, list)
        self.assertEqual(annotations[0]["id"], annotation_id)

    def test_sketch_revise_formalize_promote(self) -> None:
        draft_id = self._sketch()
        shown = self._payload("draft_show", {"id": draft_id})
        assert isinstance(shown, dict)
        self.assertEqual(shown["draft"]["format"], "sketch")
        self.assertIn("# Sketch title", shown["sketch"])
        self.assertNotIn("document", shown)
        self.assertEqual(shown["blocks"][0]["key"], "sketch:title")

        annotation = self._payload(
            "draft_annotate",
            {
                "id": draft_id,
                "block": "sketch:why",
                "kind": "change",
                "text": "Sharpen",
                "quote": "review",
            },
        )
        assert isinstance(annotation, dict)
        revised = self._payload(
            "draft_revise",
            {
                "id": draft_id,
                "document": SKETCH.replace("Why review matters.", "A sharper why."),
                "base_revision": 1,
            },
        )
        assert isinstance(revised, dict)
        self.assertEqual(revised["draft"]["format"], "sketch")
        self.assertEqual(revised["draft"]["revision"], 2)
        self._payload(
            "draft_resolve",
            {"id": annotation["annotation"]["id"], "response": "Sharpened"},
        )

        formal = sketch_document()
        formal["plan"]["why"] = "A sharper why."
        formalized = self._payload(
            "draft_formalize",
            {"id": draft_id, "document": formal, "base_revision": 2},
        )
        assert isinstance(formalized, dict)
        self.assertEqual(formalized["draft"]["format"], "document")
        self.assertEqual(formalized["draft"]["revision"], 3)
        promoted = self._payload("draft_promote", {"id": draft_id})
        assert isinstance(promoted, dict)
        self.assertTrue(promoted["created"])
        self.assertEqual(promoted["plan"]["name"], "Sketch title")

    def test_sketch_gates(self) -> None:
        draft_id = self._sketch()
        refused = self._tool("draft_promote", {"id": draft_id})
        self.assertTrue(refused.get("isError"))
        self.assertIn("formalize it before promoting", refused["content"][0]["text"])

        drifted = sketch_document()
        drifted["plan"]["title"] = "Other title"
        refused = self._tool(
            "draft_formalize",
            {"id": draft_id, "document": drifted, "base_revision": 1},
        )
        self.assertTrue(refused.get("isError"))
        self.assertIn("reviewed title", refused["content"][0]["text"])

        refused = self._tool(
            "draft_formalize",
            {"id": draft_id, "document": sketch_document(), "base_revision": 0},
        )
        self.assertTrue(refused.get("isError"))
        self.assertIn("revision 1, not 0", refused["content"][0]["text"])

    def test_resources_expose_drafts(self) -> None:
        draft_id = self._add()
        self._payload(
            "draft_annotate",
            {"id": draft_id, "block": "plan:what", "kind": "question", "text": "Why?"},
        )
        listed = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": "lazyplan://drafts"},
            }
        )
        assert listed is not None
        queue = json.loads(listed["result"]["contents"][0]["text"])
        self.assertEqual(queue[0]["id"], draft_id)
        shown = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": f"lazyplan://draft/{draft_id}"},
            }
        )
        assert shown is not None
        detail = json.loads(shown["result"]["contents"][0]["text"])
        self.assertEqual(detail["document"]["plan"]["key"], "demo-plan")
        self.assertEqual(detail["annotations"][0]["kind"], "question")

    def test_invalid_document_and_missing_annotation(self) -> None:
        invalid = self._tool("draft_add", {"document": {"plan": {}}})
        self.assertTrue(invalid.get("isError"))
        missing = self._tool("draft_respond", {"id": 999_999, "response": "why"})
        self.assertTrue(missing.get("isError"))
        self.assertIn("not found", missing["content"][0]["text"])

    def test_errors_are_tool_errors(self) -> None:
        missing = self._tool("draft_show", {"id": 999_999})
        self.assertTrue(missing.get("isError"))
        self.assertIn("not found", missing["content"][0]["text"])

        draft_id = self._add()
        bad_block = self._tool(
            "draft_annotate",
            {"id": draft_id, "block": "missing:block", "kind": "comment", "text": "Body"},
        )
        self.assertTrue(bad_block.get("isError"))
        self.assertIn("not found in draft", bad_block["content"][0]["text"])

        stale = self._tool(
            "draft_revise",
            {"id": draft_id, "document": document(), "base_revision": 0},
        )
        self.assertTrue(stale.get("isError"))
        self.assertIn("revision 1, not 0", stale["content"][0]["text"])
