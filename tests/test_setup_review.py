"""Upgrade review: untracked repo databases, remembered decisions, safe moves."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import setup  # noqa: E402
from lazyplan.repo import PLAN_DIR, repo_plan_db_path  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class ReviewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "T"], check=True)
        (self.repo / "README").write_text("x")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "init"], check=True)
        self.repo_db = self._make_repo_db(1)
        self.state = setup.SetupState(placement="home", last_version="0.22.0")

    def tearDown(self):
        self.tmp.cleanup()

    def _make_repo_db(self, plans: int) -> Path:
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        store = Store(repo_plan_db_path(self.repo))
        for index in range(plans):
            store.add_plan(f"P{index}")
        return repo_plan_db_path(self.repo)

    def _review(self, answer: str, allow_prompt: bool = True) -> tuple[list[str], str]:
        import io

        out = io.StringIO()
        findings = setup.detect_findings(self.repo, self.home, self.state)
        notes = setup.review_findings(
            findings,
            self.state,
            self.home,
            self.repo,
            read=lambda: answer,
            write=out,
            allow_prompt=allow_prompt,
        )
        return notes, out.getvalue()

    def test_move_relocates_database_and_keeps_plans(self):
        notes, out = self._review("1")
        home_db = setup.shared_db_path(self.home)
        self.assertTrue(home_db.is_file())
        self.assertFalse(self.repo_db.exists())
        self.assertEqual(setup.plans_in(home_db), 1)
        self.assertEqual(setup.load_state(self.home).placement, "home")
        self.assertIn("Move it", out)
        self.assertTrue(any("backup" in note for note in notes))

    def test_keep_is_remembered_and_does_not_repeat(self):
        self._review("2")
        self.assertTrue(self.repo_db.is_file())
        decisions = setup.load_state(self.home).decisions
        self.assertTrue(any(d["decision"] == "keep" for d in decisions.values()))
        notes, out = self._review("1")
        self.assertEqual(out, "")
        self.assertTrue(self.repo_db.is_file())

    def test_never_is_remembered(self):
        self._review("3")
        self.assertTrue(self.repo_db.is_file())
        decisions = setup.load_state(self.home).decisions
        self.assertTrue(any(d["decision"] == "never" for d in decisions.values()))

    def test_tracked_database_is_not_offered(self):
        subprocess.run(["git", "-C", self.repo, "add", "-f", f"{PLAN_DIR}/lazyplan.db"], check=True)
        notes, out = self._review("1")
        self.assertTrue(self.repo_db.is_file())
        self.assertIn("tracked", " ".join(notes))
        self.assertNotIn("Move it", out)

    def test_conflicting_databases_are_refused(self):
        Store(setup.shared_db_path(self.home)).add_plan("home")
        ok, message = setup.move_repo_db(self.repo_db, self.home, self.repo)
        self.assertFalse(ok)
        self.assertIn("export", message)
        self.assertTrue(self.repo_db.is_file())

    def test_refused_move_stays_armed(self):
        Store(setup.shared_db_path(self.home)).add_plan("home")
        notes, _ = self._review("1")
        self.assertIn("export", " ".join(notes))
        self.assertTrue(self.repo_db.is_file())
        self.assertEqual(setup.load_state(self.home).decisions, {})

    def test_move_does_not_strip_markers_from_a_non_plan_parent(self):
        outer = Path(self.tmp.name) / "outer"
        stray = outer / "nested" / "lazyplan"
        stray.mkdir(parents=True)
        Store(stray / "lazyplan.db").add_plan("P")
        agents = outer / "AGENTS.md"
        agents.write_text("keep\n<!-- lazyplan:start -->\nmanaged\n<!-- lazyplan:end -->\n")
        ok, _ = setup.move_repo_db(stray / "lazyplan.db", self.home)
        self.assertTrue(ok)
        self.assertIn("managed", agents.read_text())

    def test_non_interactive_note_does_not_record(self):
        notes, out = self._review("", allow_prompt=False)
        self.assertTrue(self.repo_db.is_file())
        self.assertIn("lpui setup", " ".join(notes))
        self.assertEqual(out, "")
        self.assertEqual(setup.load_state(self.home).decisions, {})

    def test_state_change_rearms_the_prompt(self):
        self._review("2")
        # The same untracked state stays decided.
        self.assertEqual(self._review("1")[1], "")
        # A different state (tracked) fingerprints differently, but tracked skips.
        subprocess.run(["git", "-C", self.repo, "add", "-f", f"{PLAN_DIR}/lazyplan.db"], check=True)
        notes, _ = self._review("1")
        self.assertIn("tracked", " ".join(notes))


if __name__ == "__main__":
    unittest.main()
