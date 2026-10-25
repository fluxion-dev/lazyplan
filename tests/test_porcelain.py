"""The porcelain contract: row grammar, escaping, and the global switch."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import porcelain  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.cli_parser import build_parser  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.services import set_status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestRows(unittest.TestCase):
    def test_row_uses_the_documented_six_columns(self):
        self.assertEqual(
            porcelain.row("task", 12, "doing", "Design hero", "milestone:3", "-"),
            "task\t12\tdoing\tDesign hero\tmilestone:3\t-",
        )

    def test_missing_fields_use_a_dash(self):
        self.assertEqual(
            porcelain.row("plan", 1, "todo", "Website"), "plan\t1\ttodo\tWebsite\t-\t-"
        )

    def test_tabs_and_newlines_flatten_to_spaces(self):
        row = porcelain.row("task", 1, "todo", "Line one\tLine\ntwo\rthree", "milestone:1")
        self.assertEqual(row, "task\t1\ttodo\tLine one Line two three\tmilestone:1\t-")
        self.assertEqual(len(row.split("\t")), 6)

    def test_no_glyphs_or_ansi_are_emitted(self):
        row = porcelain.row("plan", 1, "doing", "Plan", "-", "1/2")
        for text in ("○", "◐", "●", "\x1b"):
            self.assertNotIn(text, row)


class TestSwitch(unittest.TestCase):
    def test_flag_enables(self):
        self.assertTrue(porcelain.enabled(Namespace(porcelain=True, json=False)))

    def test_json_wins_over_the_flag(self):
        self.assertFalse(porcelain.enabled(Namespace(porcelain=True, json=True)))

    def test_environment_truthy_values(self):
        for value in ("1", "true", "YES", " on "):
            with self.subTest(value=value):
                self.assertTrue(porcelain.env_enabled(value))

    def test_environment_falsey_values(self):
        for value in ("", "0", "false", "no", "off", "anything else"):
            with self.subTest(value=value):
                self.assertFalse(porcelain.env_enabled(value))

    def test_environment_reaches_enabled(self):
        with mock.patch.dict(os.environ, {porcelain.ENV: "1"}):
            self.assertTrue(porcelain.enabled(Namespace(json=False)))
        with mock.patch.dict(os.environ, {porcelain.ENV: "0"}):
            self.assertFalse(porcelain.enabled(Namespace(json=False)))


class TestParser(unittest.TestCase):
    def test_flag_works_before_and_after_the_verb(self):
        parser = build_parser()
        self.assertTrue(parser.parse_args(["--porcelain", "list"]).porcelain)
        self.assertTrue(parser.parse_args(["list", "--porcelain"]).porcelain)

    def test_flag_is_off_by_default(self):
        parser = build_parser()
        self.assertFalse(getattr(parser.parse_args(["list"]), "porcelain", False))

    def test_help_names_the_flag(self):
        text = build_parser().format_help()
        self.assertIn("--porcelain", text)
        self.assertIn("tab-separated", text)


class TestWriteRows(unittest.TestCase):
    """One record per write, in the documented column order."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "g.db")
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "fixture", *argv])
        return code, buf.getvalue()

    def _row(self, *argv: str) -> list[str]:
        code, out = self._run("--porcelain", *argv)
        self.assertEqual(code, 0, out)
        self.assertNotIn("{", out)
        self.assertEqual(out.count("\n"), 1, out)
        return out.rstrip("\n").split("\t")

    def test_plan_milestone_and_task_lifecycle(self):
        self.assertEqual(
            self._row("plan", "add", "--title", "Website", "--why", "Convert", "--what", "Site"),
            ["plan", "1", "todo", "Website", "-", "0/0"],
        )
        self.assertEqual(
            self._row("milestone", "add", "--plan", "1", "--title", "Homepage", "--desc", "Hero"),
            ["milestone", "1", "todo", "Homepage", "plan:1", "0/0"],
        )
        self.assertEqual(
            self._row(
                "task", "add", "--milestone", "1", "--title", "Design hero", "--desc", "Hero"
            ),
            ["task", "1", "todo", "Design hero", "milestone:1", "-"],
        )
        self.assertEqual(
            self._row("task", "move", "--id", "1", "--to", "doing"),
            ["task", "1", "doing", "Design hero", "milestone:1", "-"],
        )
        self.assertEqual(
            self._row("task", "edit", "--id", "1", "--title", "Build hero", "--desc", "Hero"),
            ["task", "1", "doing", "Build hero", "milestone:1", "-"],
        )
        self.assertEqual(
            self._row("task", "delete", "--id", "1"),
            ["task", "1", "deleted", "Build hero", "milestone:1", "-"],
        )

    def test_criteria_rows(self):
        self._row("plan", "add", "--title", "Website", "--why", "Convert", "--what", "Site")
        self.assertEqual(
            self._row("criterion", "add", "--kind", "plan", "--id", "1", "--text", "Loads fast"),
            ["criterion", "1", "open", "Loads fast", "plan:1", "-"],
        )
        code, out = self._run("--porcelain", "criterion", "list", "--kind", "plan", "--id", "1")
        self.assertEqual(code, 0)
        self.assertEqual(out, "criterion\t1\topen\tLoads fast\tplan:1\t-\n")
        self.assertEqual(
            self._row("criterion", "tick", "--id", "1"),
            ["criterion", "1", "done", "Loads fast", "plan:1", "-"],
        )
        self.assertEqual(
            self._row("criterion", "untick", "--id", "1"),
            ["criterion", "1", "open", "Loads fast", "plan:1", "-"],
        )
        self.assertEqual(
            self._row("criterion", "delete", "--id", "1"),
            ["criterion", "1", "deleted", "-", "-", "-"],
        )

    def test_flag_after_the_verb(self):
        code, out = self._run(
            "plan", "add", "--title", "Website", "--why", "Convert", "--what", "Site", "--porcelain"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "plan\t1\ttodo\tWebsite\t-\t0/0\n")

    def test_environment_switch_enables(self):
        with mock.patch.dict(os.environ, {porcelain.ENV: "1"}):
            code, out = self._run(
                "plan", "add", "--title", "Website", "--why", "Convert", "--what", "Site"
            )
        self.assertEqual(code, 0)
        self.assertEqual(out, "plan\t1\ttodo\tWebsite\t-\t0/0\n")

    def test_json_wins_over_porcelain(self):
        code, out = self._run(
            "--porcelain",
            "--json",
            "plan",
            "add",
            "--title",
            "Website",
            "--why",
            "Convert",
            "--what",
            "Site",
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["plan"]["id"], 1)


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


class TestReadRows(unittest.TestCase):
    """Plan, tree, and show reads are plain rows with no provenance noise."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "g.db")
        store = Store(self.db)
        plan = store.add_plan("Website", "Marketing site", goal="Convert", actor="fixture")
        milestone = store.add_milestone(plan.id, "Homepage", "Hero work", actor="fixture")
        task = store.add_task(milestone.id, "Design hero", "Hero section", actor="fixture")
        store.add_criteria("plan", plan.id, "Loads fast", actor="fixture")
        store.add_criteria("milestone", milestone.id, "Hero works", actor="fixture")
        store.add_criteria("task", task.id, "Ships", actor="fixture")
        store.add_repo_link("task", task.id, self.tmp.name, "git@example.com:org/repo.git")
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _lines(self, *argv: str) -> list[list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "fixture", "--porcelain", *argv])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertNotIn("{", buf.getvalue())
        lines = [line.split("\t") for line in buf.getvalue().rstrip("\n").splitlines()]
        for line in lines:
            self.assertEqual(len(line), 6, line)
        return lines

    def test_list_summary_is_plan_rows(self):
        self.assertEqual(
            self._lines("list"),
            [["plan", "1", "todo", "Website", "-", "0/1"]],
        )

    def test_list_tree_adds_milestone_and_task_rows(self):
        self.assertEqual(
            self._lines("list", "--tree"),
            [
                ["plan", "1", "todo", "Website", "-", "0/1"],
                ["milestone", "1", "todo", "Homepage", "plan:1", "0/1"],
                ["task", "1", "todo", "Design hero", "milestone:1", "-"],
            ],
        )

    def test_show_keeps_definition_and_children_without_repos(self):
        lines = self._lines("plan", "show", "--id", "1")
        self.assertEqual(
            lines,
            [
                ["plan", "1", "todo", "Website", "-", "0/1"],
                ["why", "-", "-", "Convert", "-", "-"],
                ["what", "-", "-", "Marketing site", "-", "-"],
                ["criterion", "1", "open", "Loads fast", "plan:1", "-"],
                ["milestone", "1", "todo", "Homepage", "plan:1", "0/1"],
                ["criterion", "2", "open", "Hero works", "milestone:1", "-"],
                ["task", "1", "todo", "Design hero", "milestone:1", "-"],
            ],
        )
        output = "\n".join("\t".join(line) for line in lines)
        self.assertNotIn(self.tmp.name, output)
        self.assertNotIn("git@example.com", output)

    def test_task_show_keeps_desc_and_criteria(self):
        self.assertEqual(
            self._lines("task", "show", "--id", "1"),
            [
                ["task", "1", "todo", "Design hero", "milestone:1", "-"],
                ["desc", "-", "-", "Hero section", "-", "-"],
                ["criterion", "3", "open", "Ships", "task:1", "-"],
            ],
        )


@unittest.skipUnless(_git_available(), "git CLI required")
class TestLinkRows(unittest.TestCase):
    """Commit, repo, PR, and task-start confirmations stay one parseable row."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "t@t.t"], check=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "Tester"], check=True, timeout=10
        )
        with open(os.path.join(self.repo, "f.txt"), "w") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "cli commit"], check=True, timeout=10
        )
        self.db = os.path.join(self.tmp.name, "g.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T", actor="fixture")
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

    def _row(self, *argv: str) -> list[str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "fixture", "--porcelain", *argv])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertNotIn("{", buf.getvalue())
        self.assertEqual(buf.getvalue().count("\n"), 1, buf.getvalue())
        return buf.getvalue().rstrip("\n").split("\t")

    def test_commit_link_and_unlink(self):
        sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        self.assertEqual(
            self._row("link", "--kind", "task", "--id", "1"),
            ["commit", sha, "linked", "cli commit", "task:1", "-"],
        )
        self.assertEqual(
            self._row("unlink", "--kind", "task", "--id", "1", "--sha", sha),
            ["commit", sha, "unlinked", "-", "task:1", "-"],
        )

    def test_repo_link_and_unlink(self):
        self.assertEqual(
            self._row(
                "link-repo",
                "--kind",
                "task",
                "--id",
                "1",
                "--repo",
                self.repo,
                "--remote",
                "git@example.com:org/repo.git",
            ),
            ["repo", self.repo, "linked", "git@example.com:org/repo.git", "task:1", "-"],
        )
        self.assertEqual(
            self._row("unlink-repo", "--kind", "task", "--id", "1", "--repo", self.repo),
            ["repo", self.repo, "unlinked", "-", "task:1", "-"],
        )

    def test_pr_link_and_unlink(self):
        url = "https://github.com/org/repo/pull/7"
        self.assertEqual(
            self._row("pr", "link", "--kind", "task", "--id", "1", "--url", url),
            ["pr", "7", "linked", url, "task:1", "-"],
        )
        self.assertEqual(
            self._row("pr", "unlink", "--kind", "task", "--id", "1", "--number", "7"),
            ["pr", "7", "unlinked", "-", "task:1", "-"],
        )

    def test_task_start_and_finish_rows(self):
        self.assertEqual(
            self._row("task", "start", "--id", "1"),
            ["task", "1", "doing", "T", "milestone:1", "-"],
        )
        self.assertEqual(
            self._row("task", "finish", "--id", "1"),
            ["task", "1", "done", "T", "milestone:1", "-"],
        )

    def test_commit_read_rows(self):
        sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        self._row("link", "--kind", "task", "--id", "1")
        lines = self._lines("commits", "--kind", "task", "--id", "1")
        self.assertEqual(
            lines,
            [["commit", sha, "linked", "cli commit", "task:1", self.repo]],
        )

    def test_repo_read_rows(self):
        remote = "git@example.com:org/repo.git"
        self._row(
            "link-repo", "--kind", "task", "--id", "1", "--repo", self.repo, "--remote", remote
        )
        self.assertEqual(
            self._lines("repos", "--kind", "task", "--id", "1"),
            [["repo", self.repo, "explicit", remote, "task:1", "-"]],
        )

    def test_git_status_rows(self):
        sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        self._row("link-repo", "--kind", "task", "--id", "1", "--repo", self.repo)
        lines = self._lines("git", "status", "--kind", "task", "--id", "1")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][:5], ["status", self.repo, "clean", "main", "task:1"])
        self.assertEqual(lines[0][5], f"head={sha} ahead=0 behind=0 upstream=- subject=cli commit")

    def test_pr_read_rows(self):
        url = "https://github.com/org/repo/pull/7"
        self._row("pr", "link", "--kind", "task", "--id", "1", "--url", url)
        expected = [["pr", "7", "unknown", "PR #7", "task:1", url]]
        self.assertEqual(self._lines("pr", "list", "--kind", "task", "--id", "1"), expected)
        self.assertEqual(
            self._lines("pr", "show", "--kind", "task", "--id", "1", "--number", "7"), expected
        )

    def _lines(self, *argv: str) -> list[list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "fixture", "--porcelain", *argv])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertNotIn("{", buf.getvalue())
        lines = [line.split("\t") for line in buf.getvalue().rstrip("\n").splitlines()]
        for line in lines:
            self.assertEqual(len(line), 6, line)
        return lines


class TestSessionRows(unittest.TestCase):
    """Brief, audit, feed, and info reads keep their facts in plain rows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "g.db")
        store = Store(self.db)
        plan = store.add_plan("Website", "Marketing site", goal="Convert", actor="fixture")
        milestone = store.add_milestone(plan.id, "Homepage", "Hero work", actor="fixture")
        task = store.add_task(milestone.id, "Design hero", "Hero section", actor="fixture")
        store.add_criteria("plan", plan.id, "Loads fast", actor="fixture")
        set_status(store, "plan", plan.id, Status.DOING, actor="fixture")
        set_status(store, "milestone", milestone.id, Status.DOING, actor="fixture")
        set_status(store, "task", task.id, Status.DOING, actor="fixture")
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        work = os.path.join(self.tmp.name, "work")
        os.makedirs(work, exist_ok=True)
        os.chdir(work)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _lines(self, *argv: str) -> list[list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lpui_main(["--db", self.db, "--actor", "fixture", "--porcelain", *argv])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertNotIn("{", buf.getvalue())
        lines = [line.split("\t") for line in buf.getvalue().rstrip("\n").splitlines()]
        for line in lines:
            self.assertEqual(len(line), 6, line)
        return lines

    def test_brief_rows(self):
        self.assertEqual(
            self._lines("brief", "--plan", "1"),
            [
                ["metric", "active", "-", "1", "-", "-"],
                ["plan", "1", "doing", "Website", "-", "0/1"],
                ["task", "1", "doing", "Design hero", "milestone:1", "-"],
                ["criterion", "1", "open", "Loads fast", "plan:1", "-"],
            ],
        )

    def test_audit_rows(self):
        lines = self._lines("audit", "--plan", "1", "--since", "2026-01-01")
        metrics = {line[1]: line[3] for line in lines if line[0] == "metric"}
        self.assertEqual(metrics["plans"], "P1")
        self.assertEqual(metrics["coverage"], "1.0")
        self.assertEqual(metrics["gaps"], "0")
        self.assertIn("commits_total", metrics)

    def test_feed_rows(self):
        lines = self._lines("feed", "--limit", "1")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][0], "feed")
        self.assertEqual(lines[0][2], "fixture")
        self.assertIn("/", lines[0][4])

    def test_info_rows(self):
        lines = self._lines("info")
        values = {line[1]: line[3] for line in lines}
        self.assertEqual(values["db"], self.db)
        self.assertEqual(values["plans"], "1")
        self.assertEqual(values["tasks"], "1")


if __name__ == "__main__":
    unittest.main()
