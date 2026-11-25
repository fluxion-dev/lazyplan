"""CLI dispatch output: JSON, porcelain, human text, and errors."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


class DispatchCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.db = os.path.join(self.root, "dispatch.db")
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        self.env = {"LAZYPLAN_NO_SETUP": "1", "LAZYPLAN_NO_UPDATE_CHECK": "1"}
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        store = Store(self.db)
        self.plan = store.add_plan("Lanes", dispatch_mode="parallel", max_agents=2)
        store.add_repo_link("plan", self.plan.id, self.repo)
        self.lanes = []
        for title in ("Alpha", "Beta"):
            milestone = store.add_milestone(self.plan.id, title, lane_group=1)
            store.add_task(
                milestone.id,
                f"Work {title}",
                "Approach: do it.\n\nCommit: one slice.\n\nVerify: tests.",
            )
            path = os.path.join(self.root, f"repo--{title}")
            os.makedirs(path)
            store.register_plan_worktree(
                self.plan.id,
                self.repo,
                path,
                branch=f"plan/{title}",
                milestone_id=milestone.id,
            )
            self.lanes.append(milestone.id)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_json_manifest(self) -> None:
        code, out, err = self._run("--json", "dispatch", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["capacity"]["available"], 2)
        self.assertEqual([lane["state"] for lane in data["lanes"]], ["ready", "ready"])
        self.assertEqual(len(data["dispatchable"]), 2)
        self.assertEqual(data["profiles"]["reviewer"]["claude"], "opus")
        self.assertEqual(data["profiles"]["reviewer"]["models"]["claude"], "opus")
        for host in ("opencode", "claude", "codex", "gemini", "cursor", "copilot"):
            self.assertIn(host, data["profiles"]["reviewer"]["models"])
        self.assertEqual(data["dispatchable"][0]["profile"]["tier"], "fast")
        self.assertTrue(data["fresh_session"])
        self.assertTrue(data["dispatchable"][0]["fresh_session"])
        self.assertTrue(data["dispatchable"][0]["context"]["fits"])
        self.assertIn("Start a new session for this task", data["dispatchable"][0]["prompt"])
        self.assertEqual(data["profiles"]["reviewer"]["context_window"], 200_000)

    def test_porcelain_rows(self) -> None:
        code, out, err = self._run("--porcelain", "dispatch", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.splitlines()]
        self.assertEqual([row[0] for row in rows], ["lane", "lane"])
        self.assertEqual([row[1] for row in rows], [str(self.lanes[0]), str(self.lanes[1])])

    def test_human_text(self) -> None:
        code, out, err = self._run("dispatch", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("parallel · max 2", out)
        self.assertIn("lanes:", out)
        self.assertIn("dispatchable:", out)
        self.assertIn("actions:", out)

    def test_lane_filter_and_prompt_budget(self) -> None:
        code, out, err = self._run(
            "--json",
            "dispatch",
            "--plan",
            str(self.plan.id),
            "--lane",
            str(self.lanes[0]),
            "--max-chars",
            "120",
        )
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual([lane["milestone_id"] for lane in data["lanes"]], [self.lanes[0]])
        (item,) = data["dispatchable"]
        self.assertLessEqual(len(item["prompt"]), 120)

    def test_oversize_brief_blocks_dispatch(self) -> None:
        Path(self.root, "agents.json").write_text(
            json.dumps(
                {
                    "schema": 2,
                    "context": {
                        "fast": {
                            "opencode": 500,
                            "claude": 500,
                            "codex": 500,
                            "gemini": 500,
                            "cursor": 500,
                            "copilot": 500,
                        }
                    },
                    "profiles": {},
                }
            ),
            encoding="utf-8",
        )
        code, _out, err = self._run("dispatch", "--plan", str(self.plan.id))
        self.assertEqual(code, 2)
        self.assertIn("fresh brief uses", err)

    def test_missing_plan_is_an_error(self) -> None:
        code, _, err = self._run("dispatch", "--plan", "999")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
