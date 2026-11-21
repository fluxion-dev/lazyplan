"""Draft CLI: add, annotate, wait, revise, ready, promote, and delete."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

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


class DraftCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _write(self, name: str, payload: dict) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return path

    def _add(self, payload: dict | None = None) -> tuple[int, str, str]:
        path = self._write("draft.json", payload or document())
        return self._run("--json", "draft", "add", "--file", path)

    def _draft_id(self) -> int:
        code, out, err = self._add()
        self.assertEqual(code, 0, err)
        return int(json.loads(out)["draft"]["id"])

    def _annotate(self, draft_id: int, **flags: str) -> tuple[int, str, str]:
        argv = [
            "--json",
            "draft",
            "annotate",
            "--id",
            str(draft_id),
            "--block",
            flags.get("block", "plan:why"),
            "--kind",
            flags.get("kind", "change"),
            "--text",
            flags.get("text", "Sharpen this"),
        ]
        for name in ("quote", "start", "end"):
            if name in flags:
                argv.extend([f"--{name}", flags[name]])
        return self._run(*argv)

    def test_add_show_and_list(self) -> None:
        code, out, err = self._add()
        self.assertEqual(code, 0, err)
        draft = json.loads(out)["draft"]
        self.assertEqual(draft["status"], "review")
        self.assertEqual(draft["revision"], 1)
        self.assertEqual(draft["open_annotations"], 0)
        self.assertEqual(draft["total_annotations"], 0)

        code, out, err = self._run("--json", "draft", "show", "--id", str(draft["id"]))
        self.assertEqual(code, 0, err)
        shown = json.loads(out)
        self.assertEqual(shown["document"]["plan"]["key"], "demo-plan")
        self.assertEqual(shown["blocks"][0]["key"], "plan:title")
        self.assertEqual(shown["annotations"], [])

        code, out, err = self._run("--json", "draft", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["id"], draft["id"])

        code, out, err = self._run("--porcelain", "draft", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "draft")

        code, out, err = self._run("draft", "list")
        self.assertEqual(code, 0, err)
        self.assertIn("D1", out)

    def test_annotate_revise_resolve_promote(self) -> None:
        draft_id = self._draft_id()
        code, out, err = self._annotate(draft_id, quote="Why", text="Sharpen the why")
        self.assertEqual(code, 0, err)
        annotation = json.loads(out)["annotation"]
        self.assertEqual(annotation["quote"], "Why")
        self.assertEqual(annotation["status"], "open")

        code, out, err = self._run("--json", "draft", "show", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["draft"]["status"], "revising")

        revised = self._write(
            "revised.json",
            document(title="Revised", why="A sharper why."),
        )
        code, out, err = self._run(
            "--json",
            "draft",
            "revise",
            "--id",
            str(draft_id),
            "--file",
            revised,
            "--base-revision",
            "1",
            "--note",
            "addressed the why",
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)["draft"]
        self.assertEqual(payload["revision"], 2)
        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["title"], "Revised")

        code, out, err = self._run(
            "--json",
            "draft",
            "resolve",
            "--id",
            str(annotation["id"]),
            "--response",
            "Sharpened",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["annotation"]["status"], "addressed")

        code, out, err = self._run("--json", "draft", "ready", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["draft"]["status"], "review")

        code, out, err = self._run("--json", "draft", "promote", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        promotion = json.loads(out)
        self.assertTrue(promotion["created"])
        self.assertEqual(promotion["plan"]["name"], "Revised")
        self.assertEqual(promotion["counts"], {"milestones": 1, "tasks": 1, "criteria": 3})
        self.assertEqual(promotion["draft"]["status"], "promoted")

        code, out, err = self._run("--json", "draft", "promote", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        self.assertFalse(json.loads(out)["created"])

    def test_porcelain_show_lists_blocks_and_annotations(self) -> None:
        draft_id = self._draft_id()
        self._annotate(draft_id)
        code, out, err = self._run("--porcelain", "draft", "show", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        kinds = [line.split("\t")[0] for line in out.strip().splitlines()]
        self.assertEqual(kinds[0], "draft")
        self.assertIn("block", kinds)
        self.assertIn("annotation", kinds)
        annotation_line = next(line for line in out.splitlines() if line.startswith("annotation\t"))
        self.assertIn("change", annotation_line)
        self.assertIn("plan:why", annotation_line)

    def test_ready_refuses_open_annotations(self) -> None:
        draft_id = self._draft_id()
        self._annotate(draft_id)
        code, _out, err = self._run("--json", "draft", "ready", "--id", str(draft_id))
        self.assertEqual(code, 2)
        self.assertIn("still has 1 open", err)

    def test_dismiss_and_annotation_list(self) -> None:
        draft_id = self._draft_id()
        code, out, err = self._annotate(draft_id, kind="question", text="Why?")
        self.assertEqual(code, 0, err)
        annotation_id = json.loads(out)["annotation"]["id"]
        code, out, err = self._run(
            "--json", "draft", "dismiss", "--id", str(annotation_id), "--reason", "wontfix"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["annotation"]["status"], "dismissed")
        code, out, err = self._run(
            "--json", "draft", "annotations", "--id", str(draft_id), "--status", "dismissed"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["id"], annotation_id)

    def test_gates_and_missing_ids(self) -> None:
        existing = self.store.add_plan("Existing")
        self.store.set_entity_key("plan", existing.id, "demo-plan")
        code, _out, err = self._add()
        self.assertEqual(code, 2)
        self.assertIn("already belongs to plan", err)

        draft_id = self._draft_id_with_key("other-plan")
        code, _out, err = self._annotate(draft_id, block="missing:block")
        self.assertEqual(code, 2)
        self.assertIn("not found in draft", err)

        code, _out, err = self._run("--json", "draft", "show", "--id", "999999")
        self.assertEqual(code, 1)

        code, _out, err = self._run("--json", "draft", "delete", "--id", "999999")
        self.assertEqual(code, 1)

        self._annotate(draft_id)
        code, _out, err = self._run("--json", "draft", "promote", "--id", str(draft_id))
        self.assertEqual(code, 2)
        self.assertIn("open annotation", err)
        code, _out, err = self._run(
            "--json",
            "draft",
            "revise",
            "--id",
            str(draft_id),
            "--file",
            self._write("stale.json", document(key="other-plan")),
            "--base-revision",
            "0",
        )
        self.assertEqual(code, 2)
        self.assertIn("revision 1, not 0", err)

    def test_invalid_json_and_missing_annotation(self) -> None:
        bad = os.path.join(self.tmp.name, "bad.json")
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("{")
        code, _out, err = self._run("--json", "draft", "add", "--file", bad)
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)
        code, _out, err = self._run("--json", "draft", "annotations", "--id", "999999")
        self.assertEqual(code, 1)

    def test_delete_draft_and_refuse_promoted(self) -> None:
        draft_id = self._draft_id()
        code, out, err = self._run("--json", "draft", "delete", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["ok"])
        code, _out, err = self._run("--json", "draft", "delete", "--id", str(draft_id))
        self.assertEqual(code, 1)

        draft_id = self._draft_id_with_key("promoted-plan")
        self._run("--json", "draft", "promote", "--id", str(draft_id))
        code, _out, err = self._run("--json", "draft", "delete", "--id", str(draft_id))
        self.assertEqual(code, 2)
        self.assertIn("promoted", err)

    def _draft_id_with_key(self, key: str) -> int:
        code, out, err = self._add(document(key=key))
        self.assertEqual(code, 0, err)
        return int(json.loads(out)["draft"]["id"])


if __name__ == "__main__":
    unittest.main()
