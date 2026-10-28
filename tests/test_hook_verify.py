"""Every host adapter, through the real CLI, stays valid and read-only."""

import hashlib
import io
import json
import os
import statistics
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from support.home import sandbox_home  # noqa: E402

from lazyplan import hook_hosts, hooks, services  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402

HOSTS = ("claude", "gemini", "codex", "cursor", "opencode")


class VerifyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nohooks = os.environ.pop(hooks.NO_HOOKS_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)
        self.db = self.home / ".lazyplan/lazyplan.db"
        self._seed()

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (hooks.NO_HOOKS_ENV, self.old_nohooks),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _seed(self) -> None:
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "Doing task", "desc")
        services.set_status(store, "task", task.id, Status.DOING, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="t")

    def _digest(self) -> str:
        return hashlib.sha256(self.db.read_bytes()).hexdigest()

    def _run_hook(self, host: str) -> tuple[int, str]:
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"hook_event_name": "SessionStart"}))
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "session-start", "--host", host])
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue().strip()

    def test_every_host_emits_valid_output_and_no_write(self):
        before = self._digest()
        for host in HOSTS:
            code, text = self._run_hook(host)
            self.assertEqual(code, 0)
            self.assertIn("Doing task", text)
            if host != "opencode":
                body = json.loads(text)
                self.assertTrue(body)
            self.assertEqual(self._digest(), before, host)

    def test_every_direct_render_has_no_ansi(self):
        result = hooks.build_result("session-start", {}, self.repo, commits=[])
        for host in HOSTS:
            text = hook_hosts.render(host, "session-start", result)
            self.assertNotIn("\x1b", text)

    def test_unreadable_payload_degrades_without_an_error(self):
        self.assertEqual(hooks.read_payload(io.StringIO("{")), {})
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("{")
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "session-start", "--host", "claude"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("additionalContext", out.getvalue())

    def test_p95_overhead_stays_under_budget(self):
        payload = {}
        for _ in range(3):
            hooks.build_result("session-start", payload, self.repo, commits=[])
        samples = []
        for _ in range(40):
            start = time.perf_counter()
            hooks.build_result("session-start", payload, self.repo, commits=[])
            samples.append(time.perf_counter() - start)
        p95 = statistics.quantiles(samples, n=20)[18]
        self.assertLess(p95, 0.3)


if __name__ == "__main__":
    unittest.main()
