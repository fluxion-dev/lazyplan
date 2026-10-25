"""End-to-end agent loop and the hot-loop reduction promised by the plan."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.services import set_status  # noqa: E402
from lazyplan.store import Store  # noqa: E402

GLYPHS = ("○", "◐", "●", "◓", "◑", "◒")


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def _fixture(db: str) -> None:
    """One plan, milestone, and todo task; enough for the hot-loop comparison."""
    store = Store(db)
    plan = store.add_plan("Website", "Marketing site", goal="Convert", actor="qa")
    milestone = store.add_milestone(plan.id, "Homepage", "Hero work", actor="qa")
    task = store.add_task(milestone.id, "Design hero", "Hero section", actor="qa")
    set_status(store, "task", task.id, Status.TODO, actor="qa")


class TestHotLoopReduction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = os.path.join(self.tmp.name, "work")
        os.makedirs(self.work)
        self.old_cwd = os.getcwd()
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        os.chdir(self.work)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, db: str, *argv: str) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", db, "--actor", "qa", *argv])
        self.assertEqual(code, 0, buf.getvalue())
        return buf.getvalue()

    def _measure(self, *argv: str) -> tuple[int, int, int, int]:
        default_db = os.path.join(self.tmp.name, "default.db")
        terse_db = os.path.join(self.tmp.name, "terse.db")
        _fixture(default_db)
        _fixture(terse_db)
        default = self._run(default_db, *argv)
        terse = self._run(terse_db, "--porcelain", *argv)
        return (
            len(default.splitlines()),
            len(default.encode()),
            len(terse.splitlines()),
            len(terse.encode()),
        )

    def test_hot_loop_prints_at_least_60_percent_fewer_lines(self):
        commands = [
            ("list",),
            ("plan", "show", "--id", "1"),
            ("task", "add", "--milestone", "1", "--title", "Build nav", "--desc", "Nav work"),
            ("task", "move", "--id", "1", "--to", "doing"),
        ]
        default_lines = terse_lines = 0
        for argv in commands:
            d_lines, _d_bytes, t_lines, _t_bytes = self._measure(*argv)
            default_lines += d_lines
            terse_lines += t_lines
        self.assertGreater(default_lines, 0)
        self.assertLessEqual(
            terse_lines,
            default_lines * 0.4,
            f"porcelain printed {terse_lines} lines vs {default_lines} default lines",
        )

    def test_write_half_prints_at_least_60_percent_fewer_lines_and_bytes(self):
        commands = [
            ("task", "add", "--milestone", "1", "--title", "Build nav", "--desc", "Nav work"),
            ("task", "move", "--id", "1", "--to", "doing"),
        ]
        default_lines = default_bytes = terse_lines = terse_bytes = 0
        for argv in commands:
            d_lines, d_bytes, t_lines, t_bytes = self._measure(*argv)
            default_lines += d_lines
            default_bytes += d_bytes
            terse_lines += t_lines
            terse_bytes += t_bytes
        self.assertLessEqual(terse_lines, default_lines * 0.4)
        self.assertLessEqual(
            terse_bytes,
            default_bytes * 0.4,
            f"porcelain wrote {terse_bytes} bytes vs {default_bytes} default bytes",
        )


@unittest.skipUnless(_git_available(), "git CLI required")
class TestPorcelainAgentLoop(unittest.TestCase):
    """A full loop from porcelain stdout alone, with no JSON parser."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "qa@qa.qa"], check=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "QA"], check=True, timeout=10
        )
        with open(os.path.join(self.repo, "f.txt"), "w") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "first"], check=True, timeout=10)
        self.db = os.path.join(self.tmp.name, "qa.db")
        self.old_cwd = os.getcwd()
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> list[list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "qa", "--porcelain", *argv])
        out = buf.getvalue()
        self.assertEqual(code, 0, out)
        self.assertNotIn("{", out)
        for glyph in GLYPHS:
            self.assertNotIn(glyph, out)
        rows = [line.split("\t") for line in out.rstrip("\n").splitlines()]
        for row in rows:
            self.assertEqual(len(row), 6, row)
        return rows

    def _run_raw(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "qa", "--porcelain", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_full_loop_from_porcelain_stdout(self):
        self.assertEqual(
            self._run("plan", "add", "--title", "Agent loop", "--why", "Ship", "--what", "Rows")[0],
            ["plan", "1", "todo", "Agent loop", "-", "0/0"],
        )
        self.assertEqual(
            self._run("criterion", "add", "--kind", "plan", "--id", "1", "--text", "Works")[0],
            ["criterion", "1", "open", "Works", "plan:1", "-"],
        )
        self.assertEqual(
            self._run("milestone", "add", "--plan", "1", "--title", "Slice", "--desc", "Value")[0],
            ["milestone", "1", "todo", "Slice", "plan:1", "0/0"],
        )
        self.assertEqual(
            self._run(
                "task", "add", "--milestone", "1", "--title", "Build row", "--desc", "Approach"
            )[0],
            ["task", "1", "todo", "Build row", "milestone:1", "-"],
        )
        self.assertEqual(
            self._run("task", "move", "--id", "1", "--to", "doing")[0],
            ["task", "1", "doing", "Build row", "milestone:1", "-"],
        )
        self.assertEqual(
            self._run("task", "start", "--id", "1")[0],
            ["task", "1", "doing", "Build row", "milestone:1", "-"],
        )
        with open(os.path.join(self.repo, "row.txt"), "w") as fh:
            fh.write("row\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "build row"], check=True, timeout=10
        )
        linked = self._run("link", "--kind", "task", "--id", "1")
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0][:2], ["commit", linked[0][1]])
        self.assertEqual(linked[0][2], "linked")
        self.assertEqual(linked[0][4], "task:1")

        show = self._run("plan", "show", "--id", "1")
        show_kinds = [row[0] for row in show]
        for kind in ("plan", "why", "what", "criterion", "milestone", "task"):
            self.assertIn(kind, show_kinds)
        show_text = "\n".join("\t".join(row) for row in show)
        self.assertNotIn(self.repo, show_text)
        self.assertNotIn(linked[0][1], show_text)

        brief = self._run("brief", "--plan", "1")
        self.assertIn(["metric", "active", "-", "1", "-", "-"], brief)
        self.assertIn(["task", "1", "doing", "Build row", "milestone:1", "-"], brief)

        audit = self._run("audit", "--plan", "1", "--since", "2026-01-01")
        metrics = {row[1]: row[3] for row in audit if row[0] == "metric"}
        self.assertEqual(metrics["plans"], "P1")
        self.assertIn("coverage", metrics)

    def test_missing_row_keeps_the_exit_code_and_stderr(self):
        code, out, err = self._run_raw("task", "show", "--id", "999")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("task 999 not found", err)

    def test_open_criteria_warning_stays_on_stderr(self):
        self._run("plan", "add", "--title", "Agent loop", "--why", "Ship", "--what", "Rows")
        self._run("milestone", "add", "--plan", "1", "--title", "Slice", "--desc", "Value")
        self._run("task", "add", "--milestone", "1", "--title", "Build row", "--desc", "Approach")
        self._run("criterion", "add", "--kind", "task", "--id", "1", "--text", "Works")
        code, out, err = self._run_raw("task", "move", "--id", "1", "--to", "done")
        self.assertEqual(code, 0)
        self.assertEqual(out, "task\t1\tdone\tBuild row\tmilestone:1\t-\n")
        self.assertIn("open acceptance criteria", err)


if __name__ == "__main__":
    unittest.main()
