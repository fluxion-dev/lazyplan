import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def _run(argv):
    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        rc = lpui_main(argv)
    return rc, buf.getvalue(), err.getvalue()


@unittest.skipUnless(_git_available(), "git CLI required")
class TestVcsCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "t@t.t"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "Tester"],
            check=True,
            timeout=10,
        )
        with open(os.path.join(self.repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "cli commit"],
            check=True,
            timeout=10,
        )
        self.plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(self.plain)
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        p = store.add_plan("P")
        s = store.add_milestone(p.id, "S")
        store.add_task(s.id, "T")
        self.old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_link_commits_show_roundtrip(self):
        os.chdir(self.repo)
        rc, out, _ = _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "show", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("commits:", out)
        self.assertIn("cli commit", out)
        # explicit sha + unlink
        store = Store(self.db)
        sha = store.list_links("task", 1)[0].sha
        rc, _, _ = _run(["--db", self.db, "link", "--kind", "task", "--id", "1", "--sha", sha])
        self.assertEqual(rc, 0)  # idempotent
        rc, _, _ = _run(["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", sha])
        self.assertEqual(rc, 0)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("(no commits linked)", out)

    def test_status_done_auto_captures(self):
        os.chdir(self.repo)
        rc, _, _ = _run(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"])
        self.assertEqual(rc, 0)
        store = Store(self.db)
        links = store.list_links("task", 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(len(links[0].sha), 40)
        # second done is a no-op dedupe
        rc, _, _ = _run(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(Store(self.db).list_links("task", 1)), 1)

    def test_unknown_sha_and_missing_link(self):
        os.chdir(self.repo)
        rc, _, err = _run(
            ["--db", self.db, "link", "--kind", "task", "--id", "1", "--sha", "0" * 40]
        )
        self.assertEqual(rc, 2)
        self.assertIn("unknown commit", err)
        rc, _, _ = _run(
            ["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", "0" * 40]
        )
        self.assertEqual(rc, 1)

    def test_show_and_commits_files_flag(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        rc, out, _ = _run(["--db", self.db, "show", "--kind", "task", "--id", "1", "--files"])
        self.assertEqual(rc, 0)
        self.assertIn("f.txt", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--files"])
        self.assertEqual(rc, 0)
        self.assertIn("f.txt", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertNotIn("f.txt", out)
        rc, out, _ = _run(["--db", self.db, "show", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["links"][0]["files"], ["f.txt"])

    def test_outside_git_disabled(self):
        os.chdir(self.plain)
        rc, _, err = _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 2)
        self.assertIn("no VCS backend", err)
        rc, _, err = _run(
            ["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", "a" * 40]
        )
        self.assertEqual(rc, 2)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("(no commits linked)", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "[]")

    def test_list_json_includes_links(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        rc, out, _ = _run(["--db", self.db, "list", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("links", out)

    def test_plan_and_milestone_show_roll_up_task_commits(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        subprocess.run(["git", "init", "-q", "-b", "main", other], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", other, "config", "user.email", "t@t.t"], check=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", other, "config", "user.name", "Tester"], check=True, timeout=10
        )
        with open(os.path.join(other, "g.txt"), "w", encoding="utf-8") as fh:
            fh.write("other\n")
        subprocess.run(["git", "-C", other, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", other, "commit", "-qm", "other commit"],
            check=True,
            timeout=10,
        )
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1", "--repo", other])
        for kind in ("milestone", "plan"):
            rc, out, _ = _run(["--db", self.db, "show", "--kind", kind, "--id", "1"])
            self.assertEqual(rc, 0)
            self.assertIn("commits:", out)
            self.assertIn("cli commit", out)
            self.assertIn("other commit", out)
            self.assertIn(os.path.basename(self.repo), out)
            self.assertIn(os.path.basename(other), out)

    def test_git_status_row_and_repo(self):
        os.chdir(self.plain)
        rc, out, _ = _run(
            ["--db", self.db, "git", "status", "--kind", "task", "--id", "1", "--json"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "[]")

        Store(self.db).add_repo_link("task", 1, self.repo, "https://example.test/repo")
        rc, out, _ = _run(
            ["--db", self.db, "git", "status", "--kind", "task", "--id", "1", "--json"]
        )
        self.assertEqual(rc, 0)
        entries = __import__("json").loads(out)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["repo_path"], os.path.realpath(self.repo))
        self.assertEqual(entries[0]["repo_remote"], "https://example.test/repo")
        self.assertEqual(entries[0]["branch"], "main")
        self.assertEqual(entries[0]["subject"], "cli commit")
        self.assertFalse(entries[0]["dirty"])

        with open(os.path.join(self.repo, "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        rc, out, _ = _run(["--db", self.db, "git", "status", "--repo", self.repo])
        self.assertEqual(rc, 0)
        self.assertIn("branch main", out)
        self.assertIn("dirty", out)

    def test_task_start_records_current_branch_without_touching_git(self):
        os.chdir(self.repo)
        head = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        rc, out, _ = _run(["--db", self.db, "task", "start", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        started = json.loads(out)
        self.assertEqual(started["branch"], "main")
        self.assertEqual(started["base_sha"], head)
        self.assertNotIn("created", started)
        self.assertNotIn("worktree", started)
        self.assertEqual(
            subprocess.run(
                ["git", "-C", self.repo, "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            ).stdout.strip(),
            "main",
        )
        self.assertEqual(
            subprocess.run(
                ["git", "-C", self.repo, "rev-parse", "HEAD"],
                capture_output=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            ).stdout.strip(),
            head,
        )
        self.assertEqual(Store(self.db).get_task(1).status, Status.DOING)

    def test_task_start_records_existing_branch_without_checkout(self):
        os.chdir(self.repo)
        subprocess.run(
            ["git", "-C", self.repo, "branch", "feature"],
            check=True,
            timeout=10,
        )
        rc, out, _ = _run(
            ["--db", self.db, "task", "start", "--id", "1", "--branch", "feature", "--json"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["branch"], "feature")
        self.assertEqual(
            subprocess.run(
                ["git", "-C", self.repo, "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            ).stdout.strip(),
            "main",
        )

    def test_task_start_refuses_missing_branch(self):
        os.chdir(self.repo)
        rc, _, err = _run(
            ["--db", self.db, "task", "start", "--id", "1", "--branch", "does-not-exist"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("does not exist", err)
        self.assertEqual(Store(self.db).get_task(1).status, Status.TODO)
        self.assertEqual(Store(self.db).list_repos("task", 1), [])

    def test_task_start_refuses_detached_head(self):
        os.chdir(self.repo)
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "--detach"],
            check=True,
            timeout=10,
        )
        rc, _, err = _run(["--db", self.db, "task", "start", "--id", "1"])
        self.assertEqual(rc, 2)
        self.assertIn("detached", err)
        self.assertEqual(Store(self.db).get_task(1).status, Status.TODO)

    def test_task_start_never_invokes_mutating_git(self):
        os.chdir(self.repo)
        with mock.patch("lazyplan.vcs.subprocess.run", wraps=subprocess.run) as run:
            rc, _, _ = _run(["--db", self.db, "task", "start", "--id", "1"])
        self.assertEqual(rc, 0)

        def subcommand(cmd: list[str]) -> str:
            if not cmd or cmd[0] != "git":
                return ""
            if "-C" in cmd:
                index = cmd.index("-C")
                return cmd[index + 2] if index + 2 < len(cmd) else ""
            return cmd[1] if len(cmd) > 1 else ""

        commands = [subcommand(call.args[0]) for call in run.call_args_list]
        for forbidden in ("checkout", "switch", "worktree", "commit", "push", "merge", "fetch"):
            self.assertNotIn(forbidden, commands)

    def test_task_start_and_finish(self):
        os.chdir(self.repo)
        store = Store(self.db)
        store.add_task(1, "Second task")
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "-b", "task/1-t"],
            check=True,
            timeout=10,
        )
        base = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()

        rc, out, _ = _run(["--db", self.db, "task", "start", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        started = json.loads(out)
        self.assertEqual(started["branch"], "task/1-t")
        self.assertEqual(started["base_sha"], base)
        self.assertEqual(
            subprocess.run(
                ["git", "-C", self.repo, "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            ).stdout.strip(),
            "task/1-t",
        )
        self.assertEqual(Store(self.db).get_task(1).status, Status.DOING)

        with open(os.path.join(self.repo, "work.txt"), "w", encoding="utf-8") as fh:
            fh.write("work\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "task work"],
            check=True,
            timeout=10,
        )

        rc, out, _ = _run(["--db", self.db, "task", "finish", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        finished = json.loads(out)
        self.assertEqual(finished["linked"], 1)
        self.assertTrue(finished["done"])
        self.assertFalse(finished["dirty"])
        self.assertEqual(Store(self.db).get_task(1).status, Status.DONE)
        links = Store(self.db).list_links("task", 1)
        self.assertEqual([link.subject for link in links], ["task work"])

        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "-b", "task/2-second-task"],
            check=True,
            timeout=10,
        )
        rc, out, _ = _run(["--db", self.db, "task", "start", "--id", "2", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["branch"], "task/2-second-task")
        with open(os.path.join(self.repo, "second.txt"), "w", encoding="utf-8") as fh:
            fh.write("second\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "second work"],
            check=True,
            timeout=10,
        )
        with open(os.path.join(self.repo, "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("dirty\n")
        rc, out, _ = _run(["--db", self.db, "task", "finish", "--id", "2", "--json"])
        self.assertEqual(rc, 0)
        dirty = json.loads(out)
        self.assertEqual(dirty["linked"], 1)
        self.assertTrue(dirty["dirty"])
        self.assertFalse(dirty["done"])
        self.assertEqual(Store(self.db).get_task(2).status, Status.DOING)

    def test_status_done_skips_dirty_tree(self):
        os.chdir(self.repo)
        with open(os.path.join(self.repo, "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("dirty\n")
        rc, _, err = _run(
            ["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("working tree is dirty", err)
        self.assertEqual(Store(self.db).list_links("task", 1), [])
        self.assertEqual(Store(self.db).get_task(1).status, Status.DONE)

    def test_status_done_skips_head_linked_to_another_row(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        Store(self.db).add_task(1, "Second task")
        rc, _, err = _run(
            ["--db", self.db, "status", "--kind", "task", "--id", "2", "--to", "done"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("already linked to task #1", err)
        self.assertEqual(Store(self.db).list_links("task", 2), [])

    def test_status_done_skips_unrelated_branch(self):
        os.chdir(self.repo)
        Store(self.db).add_task(1, "Second task")
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "-b", "task/2-second-task"],
            check=True,
            timeout=10,
        )
        _run(["--db", self.db, "task", "start", "--id", "2"])
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "main"], check=True, timeout=10)
        with open(os.path.join(self.repo, "main.txt"), "w", encoding="utf-8") as fh:
            fh.write("main\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "main work"],
            check=True,
            timeout=10,
        )
        rc, _, err = _run(
            ["--db", self.db, "status", "--kind", "task", "--id", "2", "--to", "done"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("expected branch", err)
        self.assertEqual(Store(self.db).list_links("task", 2), [])

    def test_finish_refuses_wrong_branch(self):
        os.chdir(self.repo)
        Store(self.db).add_task(1, "Second task")
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "-b", "task/2-second-task"],
            check=True,
            timeout=10,
        )
        _run(["--db", self.db, "task", "start", "--id", "2"])
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "main"], check=True, timeout=10)
        rc, _, err = _run(["--db", self.db, "task", "finish", "--id", "2"])
        self.assertEqual(rc, 2)
        self.assertIn("expected branch", err)
        self.assertEqual(Store(self.db).list_links("task", 2), [])

    def test_finish_never_commits_pushes_or_merges(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "task", "start", "--id", "1"])
        with open(os.path.join(self.repo, "work.txt"), "w", encoding="utf-8") as fh:
            fh.write("work\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "task work"],
            check=True,
            timeout=10,
        )
        with mock.patch("lazyplan.vcs.subprocess.run", wraps=subprocess.run) as run:
            rc, _, _ = _run(["--db", self.db, "task", "finish", "--id", "1"])
        self.assertEqual(rc, 0)

        def subcommand(cmd: list[str]) -> str:
            if not cmd or cmd[0] != "git":
                return ""
            if "-C" in cmd:
                index = cmd.index("-C")
                return cmd[index + 2] if index + 2 < len(cmd) else ""
            return cmd[1] if len(cmd) > 1 else ""

        commands = [subcommand(call.args[0]) for call in run.call_args_list]
        for forbidden in ("commit", "push", "merge", "reset", "rebase"):
            self.assertNotIn(forbidden, commands)

    def test_git_scan_trailers_and_branch(self):
        os.chdir(self.repo)
        store = Store(self.db)
        store.add_task(1, "Second task")
        with open(os.path.join(self.repo, "trailer.txt"), "w", encoding="utf-8") as fh:
            fh.write("trailer\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "trailer work\n\nLazyplan: T1"],
            check=True,
            timeout=10,
        )

        rc, out, _ = _run(["--db", self.db, "git", "scan", "--dry-run", "--json"])
        self.assertEqual(rc, 0)
        matches = json.loads(out)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["ref"], "T1")
        self.assertEqual(matches[0]["action"], "would-link")
        self.assertEqual(Store(self.db).list_links("task", 1), [])

        rc, out, _ = _run(["--db", self.db, "git", "scan", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)[0]["action"], "linked")
        self.assertEqual(len(Store(self.db).list_links("task", 1)), 1)

        # A branch name attributes only commits after the recorded base.
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "-b", "task/2-second-task"],
            check=True,
            timeout=10,
        )
        rc, _, _ = _run(["--db", self.db, "task", "start", "--id", "2"])
        self.assertEqual(rc, 0)
        with open(os.path.join(self.repo, "branch.txt"), "w", encoding="utf-8") as fh:
            fh.write("branch\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "branch work"],
            check=True,
            timeout=10,
        )
        rc, out, _ = _run(
            [
                "--db",
                self.db,
                "git",
                "scan",
                "--dry-run",
                "--kind",
                "task",
                "--id",
                "2",
                "--json",
            ]
        )
        self.assertEqual(rc, 0)
        branch_matches = json.loads(out)
        self.assertEqual(len(branch_matches), 1)
        self.assertEqual(branch_matches[0]["ref"], "T2")
        self.assertEqual(branch_matches[0]["action"], "would-link")

    def test_pr_refresh_reports_branch_and_merge_stats(self):
        os.chdir(self.repo)
        stats = {
            "commits": 1,
            "branches": 2,
            "merges": 1,
            "prs": 1,
            "linked": 1,
            "checks": 0,
            "reviews": 0,
            "skipped": 0,
            "stale": 0,
            "errors": [{"branch": "task/7-fix", "error": "boom"}],
        }
        with mock.patch("lazyplan.cli.services.refresh_forge", return_value=stats):
            rc, out, err = _run(["--db", self.db, "pr", "refresh", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("1 commits and 2 branches", out)
        self.assertIn("1 merges", out)
        self.assertIn("task/7-fix", err)
        self.assertIn("boom", err)

    def test_pr_link_list_show_unlink(self):
        os.chdir(self.repo)
        url = "https://github.com/org/repo/pull/7"
        rc, out, _ = _run(
            [
                "--db",
                self.db,
                "pr",
                "link",
                "--kind",
                "task",
                "--id",
                "1",
                "--url",
                url,
                "--title",
                "Fix login",
                "--state",
                "open",
                "--json",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["link"]["number"], 7)

        rc, out, _ = _run(["--db", self.db, "pr", "list", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)), 1)
        rc, out, _ = _run(["--db", self.db, "pr", "list", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("PR #7 open Fix login", out)
        self.assertIn(url, out)

        rc, out, _ = _run(["--db", self.db, "show", "--kind", "plan", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("pull requests:", out)
        self.assertIn("PR #7 open Fix login", out)

        rc, out, _ = _run(
            [
                "--db",
                self.db,
                "pr",
                "show",
                "--kind",
                "task",
                "--id",
                "1",
                "--number",
                "7",
                "--json",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["title"], "Fix login")

        rc, out, _ = _run(
            [
                "--db",
                self.db,
                "pr",
                "unlink",
                "--kind",
                "task",
                "--id",
                "1",
                "--number",
                "7",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(Store(self.db).list_forge_links("task", 1), [])
        rc, out, _ = _run(["--db", self.db, "pr", "list", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("(no pull requests linked)", out)

    def test_pr_auth_and_status(self):
        os.chdir(self.repo)
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "remote",
                "add",
                "origin",
                "git@github.com:org/repo.git",
            ],
            check=True,
            timeout=10,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("LAZYPLAN_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
        }
        env["GITHUB_TOKEN"] = "secret-token"
        with mock.patch.dict(os.environ, env, clear=True):
            rc, out, _ = _run(["--db", self.db, "pr", "auth", "--json"])
            self.assertEqual(rc, 0)
            self.assertIn('"source": "GITHUB_TOKEN"', out)
            self.assertNotIn("secret-token", out)

            rc, out, _ = _run(["--db", self.db, "pr", "status", "--repo", self.repo, "--json"])
            self.assertEqual(rc, 0)
            entries = json.loads(out)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["provider"], "github")
            self.assertEqual(entries[0]["slug"], "org/repo")
            self.assertEqual(entries[0]["auth_source"], "GITHUB_TOKEN")
            self.assertNotIn("secret-token", out)

            rc, out, _ = _run(["--db", self.db, "pr", "status", "--repo", self.repo])
            self.assertEqual(rc, 0)
            self.assertIn("github org/repo", out)
            self.assertIn("auth GITHUB_TOKEN", out)

            Store(self.db).add_repo_link("task", 1, self.repo, "git@github.com:org/repo.git")
            rc, out, _ = _run(
                ["--db", self.db, "pr", "status", "--kind", "task", "--id", "1", "--json"]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)[0]["slug"], "org/repo")

    def test_pr_auth_without_token(self):
        with mock.patch("lazyplan.forge._gh_token", return_value=None):
            with mock.patch.dict(
                os.environ,
                {
                    key: value
                    for key, value in os.environ.items()
                    if key not in ("LAZYPLAN_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
                },
                clear=True,
            ):
                rc, out, _ = _run(["--db", self.db, "pr", "auth", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn('"source": "none"', out)
        self.assertIn('"available": false', out)

    def test_commits_refresh_marks_missing_commit_stale(self):
        fake = "0" * 40
        Store(self.db).link_commit("task", 1, fake, subject="ghost", repo_root=self.repo)
        os.chdir(self.plain)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--refresh"])
        self.assertEqual(rc, 0)
        self.assertIn("ghost", out)
        self.assertIn("[stale]", out)
        rc, out, _ = _run(
            [
                "--db",
                self.db,
                "commits",
                "--kind",
                "task",
                "--id",
                "1",
                "--json",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertIn('"stale": true', out)

    def test_link_from_another_checkout(self):
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        subprocess.run(["git", "init", "-q", "-b", "main", other], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", other, "config", "user.email", "t@t.t"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", other, "config", "user.name", "Tester"],
            check=True,
            timeout=10,
        )
        with open(os.path.join(other, "g.txt"), "w", encoding="utf-8") as fh:
            fh.write("other\n")
        subprocess.run(["git", "-C", other, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", other, "commit", "-qm", "other commit"],
            check=True,
            timeout=10,
        )

        os.chdir(self.plain)
        rc, out, _ = _run(["--db", self.db, "link", "--kind", "task", "--id", "1", "--repo", other])
        self.assertEqual(rc, 0)
        self.assertIn("other commit", out)
        links = Store(self.db).list_links("task", 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].subject, "other commit")
        self.assertEqual(links[0].repo_root, os.path.realpath(other))

        rc, _, err = _run(
            ["--db", self.db, "link", "--kind", "task", "--id", "1", "--repo", self.plain]
        )
        self.assertEqual(rc, 2)
        self.assertIn("no VCS backend", err)


if __name__ == "__main__":
    unittest.main()
