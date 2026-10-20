import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main as lpui_main
from lazyplan.repo import find_repo_root, repo_label, resolve_db_path
from lazyplan.store import Store


class TestRepoScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "myproj")
        os.makedirs(os.path.join(self.repo, ".git"))  # fake repo root (fallback walk)
        os.makedirs(os.path.join(self.repo, "sub"))
        self.old_cwd = os.getcwd()
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = os.path.join(self.tmp.name, "home")
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is not None:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_find_root_via_git_dir(self):
        import pathlib

        self.assertEqual(find_repo_root(os.path.join(self.repo, "sub")), pathlib.Path(self.repo))
        self.assertIsNone(find_repo_root(os.path.join(self.tmp.name, "noroot")))

    def test_resolve_zero_touch_falls_back_to_global(self):
        import pathlib

        # Fresh repo, no team dir, no agent DBs: never resolve into the repo.
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "xdg" / "lazyplan" / "lazyplan.db",
        )

    def test_resolve_prefers_team_repo_dir(self):
        import pathlib

        os.makedirs(os.path.join(self.repo, ".agents", "lazyplan"))
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.repo) / ".agents/lazyplan" / "lazyplan.db",
        )

    def test_resolve_prefers_agent_local_db(self):
        import pathlib

        from lazyplan.skills import skill_db_path

        os.chdir(self.repo)
        skill = (
            pathlib.Path(self.tmp.name) / "home" / ".agents" / "skills" / "lazyplan" / "SKILL.md"
        )
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("x")
        db = skill_db_path(skill)
        db.touch()
        self.assertEqual(pathlib.Path(resolve_db_path()), db)

    def test_explicit_and_env_win(self):
        os.chdir(self.repo)
        import pathlib

        custom = str(pathlib.Path(self.tmp.name) / "custom.db")
        self.assertEqual(str(resolve_db_path(custom)), custom)
        os.environ["LAZYPLAN_DB"] = custom
        self.assertEqual(str(resolve_db_path()), custom)

    def test_store_creates_plan_dir_and_config(self):
        # Zero-touch: Store(None) in a fresh repo uses the global fallback.
        os.chdir(self.repo)
        s = Store(None)
        self.assertTrue(
            os.path.isfile(os.path.join(self.tmp.name, "xdg", "lazyplan", "lazyplan.db"))
        )
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        # Team repo dir still gets config.json when explicitly targeted.
        team_db = os.path.join(self.repo, ".agents", "lazyplan", "lazyplan.db")
        s = Store(team_db)
        self.assertTrue(os.path.isfile(team_db))
        cfg = os.path.join(self.repo, ".agents", "lazyplan", "config.json")
        self.assertTrue(os.path.isfile(cfg))
        self.assertEqual(json.load(open(cfg))["db"], "lazyplan.db")
        self.assertEqual(repo_label(s.path), "myproj")
        p = s.add_plan("P", actor="t")
        self.assertEqual(p.id, 1)

    def test_stale_lazyplan_warns_and_ignored(self):
        import io
        import pathlib
        from contextlib import redirect_stderr

        from lazyplan.repo import stale_plan_dirs

        stale = os.path.join(self.repo, ".lazyplan")
        os.makedirs(stale)
        with open(os.path.join(stale, "lazyplan.db"), "w") as fh:
            fh.write("data")
        also_stale = os.path.join(self.repo, ".agents", "plan")
        os.makedirs(also_stale)
        os.chdir(self.repo)
        # resolution ignores the stale dirs: zero-touch falls back to global
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "xdg" / "lazyplan" / "lazyplan.db",
        )
        self.assertEqual(
            stale_plan_dirs(self.repo), [pathlib.Path(stale), pathlib.Path(also_stale)]
        )
        self.assertEqual(stale_plan_dirs(os.path.join(self.tmp.name, "noroot")), [])
        # zero-touch init warns on stderr, never migrates, writes no repo DB
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(lpui_main(["init", "--skills-scope", "none"]), 0)
        self.assertIn(".lazyplan", err.getvalue())
        self.assertIn(os.path.join(".agents", "plan"), err.getvalue())
        self.assertEqual(open(os.path.join(stale, "lazyplan.db")).read(), "data")
        self.assertFalse(
            os.path.exists(os.path.join(self.repo, ".agents", "lazyplan", "lazyplan.db"))
        )

    def test_global_fallback_outside_repo(self):
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        os.chdir(plain)
        import pathlib

        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "xdg" / "lazyplan" / "lazyplan.db",
        )
        self.assertEqual(repo_label(resolve_db_path()), "global")

    def test_lp_init_and_info_in_repo(self):
        os.chdir(self.repo)
        # Zero-touch default leaves the repo alone, DB lives in XDG fallback.
        self.assertEqual(lpui_main(["init"]), 0)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        self.assertEqual(lpui_main(["info"]), 0)
        # Team opt-in writes the repo-shared DB.
        self.assertEqual(lpui_main(["init", "--skills-scope", "project"]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".agents/lazyplan", "lazyplan.db")))


class TestLegacyPlanDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "myproj")
        os.makedirs(os.path.join(self.repo, ".git"))  # fake repo root (fallback walk)
        self.old_cwd = os.getcwd()
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = os.path.join(self.tmp.name, "home")
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is not None:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_legacy_resolves_when_no_lazyplan(self):
        import pathlib

        os.makedirs(os.path.join(self.repo, ".plan"))
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.repo) / ".plan" / "lazyplan.db",
        )
        self.assertEqual(repo_label(resolve_db_path()), "myproj")

    def test_lazyplan_wins_when_both(self):
        import pathlib

        os.makedirs(os.path.join(self.repo, ".plan"))
        os.makedirs(os.path.join(self.repo, ".agents/lazyplan"))
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.repo) / ".agents/lazyplan" / "lazyplan.db",
        )

    def test_move_legacy(self):
        import pathlib

        from lazyplan.repo import move_legacy_plan_dir

        legacy = os.path.join(self.repo, ".plan")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "lazyplan.db"), "w") as fh:
            fh.write("data")
        self.assertEqual(
            move_legacy_plan_dir(self.repo), pathlib.Path(self.repo) / ".agents/lazyplan"
        )
        self.assertFalse(os.path.exists(legacy))
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".agents/lazyplan", "lazyplan.db")))
        # nothing left to move, and never clobber an existing .agents/lazyplan/
        self.assertIsNone(move_legacy_plan_dir(self.repo))
        os.makedirs(os.path.join(self.repo, ".plan"))
        self.assertIsNone(move_legacy_plan_dir(self.repo))

    def test_init_noninteractive_keeps_legacy(self):
        os.makedirs(os.path.join(self.repo, ".plan"))
        os.chdir(self.repo)
        self.assertEqual(lpui_main(["--json", "init", "--skills-scope", "none"]), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".plan")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents/lazyplan")))


if __name__ == "__main__":
    unittest.main()
