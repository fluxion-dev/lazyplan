"""The skill, the AGENTS pointer, and every host agree on one contract."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import hooks, services, setup, skills  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402

HOSTS = ("claude", "gemini", "codex", "cursor", "opencode")


class ContractCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.old_home = os.environ.get("HOME")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nohooks = os.environ.pop(hooks.NO_HOOKS_ENV, None)
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = str(self.home)
        os.chdir(self.repo)
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "Doing task", "desc")
        for kind, obj_id in (("task", task.id), ("milestone", milestone.id), ("plan", plan.id)):
            services.set_status(store, kind, obj_id, Status.DOING, actor="t")

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("HOME", self.old_home),
            ("LAZYPLAN_DB", self.old_db),
            (hooks.NO_HOOKS_ENV, self.old_nohooks),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _hook_text(self, host: str) -> str:
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("{}")
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "session-start", "--host", host])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        text = out.getvalue().strip()
        if host == "opencode":
            return text
        body = json.loads(text)
        if "agentMessage" in body:
            return str(body["agentMessage"])
        if "systemMessage" in body:
            return str(body["systemMessage"])
        return str(body.get("hookSpecificOutput", {}).get("additionalContext", ""))

    def test_skill_teaches_the_same_loop(self):
        text = skills.render_skill()
        self.assertIn("lpui --porcelain brief", text)
        self.assertIn("lpui --porcelain next", text)
        self.assertIn("lpui --porcelain audit --since 7.days", text)
        self.assertIn("lpui trace --plan P", text)
        self.assertIn("lpui lint --plan P --strict", text)
        self.assertIn("lpui mcp", text)
        self.assertIn("lpui stats --since", text)
        self.assertIn("share --plan", text)
        self.assertIn("sync --file", text)
        self.assertIn("--require-pr", text)
        self.assertIn("--require-checks", text)
        self.assertIn("LAZYPLAN_PORCELAIN", text)
        self.assertIn("kind<TAB>id<TAB>status", text)
        self.assertNotIn("lpui init", text)

    def test_home_pointer_names_the_resolved_database(self):
        db = self.home / ".lazyplan/lazyplan.db"
        snippet = skills.render_home_agents_snippet(db)
        self.assertIn(str(db), snippet)
        self.assertIn("lpui --porcelain brief", snippet)
        self.assertNotIn(".agents/lazyplan/lazyplan.db", snippet)

    def test_every_host_gets_the_same_task_and_next_step(self):
        for host in HOSTS:
            text = self._hook_text(host)
            self.assertIn("Doing task", text, host)
            self.assertIn("task move", text, host)
            self.assertNotIn("lpui init", text, host)

    def test_home_placement_writes_no_repo_plan_dir(self):
        choice = setup.default_choice(self.repo, self.home)
        setup.apply_choice(choice, self.repo, self.home, "0.0.0")
        self.assertFalse((self.repo / ".agents/lazyplan").exists())


if __name__ == "__main__":
    unittest.main()
