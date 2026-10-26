import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

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
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        self.tmp.cleanup()

    def test_find_root_via_git_dir(self):
        import pathlib

        self.assertEqual(find_repo_root(os.path.join(self.repo, "sub")), pathlib.Path(self.repo))
        self.assertIsNone(find_repo_root(os.path.join(self.tmp.name, "noroot")))

    def test_resolve_zero_touch_falls_back_to_global(self):
        import pathlib

        # Fresh repo, no team dir, no agent DBs: every agent shares the home DB.
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "home" / ".lazyplan" / "lazyplan.db",
        )

    def test_resolve_prefers_team_repo_dir(self):
        import pathlib

        os.makedirs(os.path.join(self.repo, ".agents", "lazyplan"))
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.repo) / ".agents/lazyplan" / "lazyplan.db",
        )

    def test_resolve_ignores_agent_local_db(self):
        import pathlib

        from lazyplan.skills import skill_db_path

        # Per-tool skill DBs are legacy import sources, not resolution targets.
        os.chdir(self.repo)
        skill = (
            pathlib.Path(self.tmp.name) / "home" / ".agents" / "skills" / "lazyplan" / "SKILL.md"
        )
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("x", encoding="utf-8")
        db = skill_db_path(skill)
        db.touch()
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "home" / ".lazyplan" / "lazyplan.db",
        )

    def test_explicit_and_env_win(self):
        os.chdir(self.repo)
        import pathlib

        custom = str(pathlib.Path(self.tmp.name) / "custom.db")
        self.assertEqual(str(resolve_db_path(custom)), custom)
        os.environ["LAZYPLAN_DB"] = custom
        self.assertEqual(str(resolve_db_path()), custom)

    def test_store_creates_plan_dir_and_config(self):
        # Zero-touch: Store(None) in a fresh repo uses the shared home DB.
        os.chdir(self.repo)
        s = Store(None)
        self.assertTrue(
            os.path.isfile(os.path.join(self.tmp.name, "home", ".lazyplan", "lazyplan.db"))
        )
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        # Team repo dir still gets config.json when explicitly targeted.
        team_db = os.path.join(self.repo, ".agents", "lazyplan", "lazyplan.db")
        s = Store(team_db)
        self.assertTrue(os.path.isfile(team_db))
        cfg = os.path.join(self.repo, ".agents", "lazyplan", "config.json")
        self.assertTrue(os.path.isfile(cfg))
        self.assertEqual(json.load(open(cfg, encoding="utf-8"))["db"], "lazyplan.db")
        self.assertEqual(repo_label(s.path), "myproj")
        p = s.add_plan("P", actor="t")
        self.assertEqual(p.id, 1)

    def test_stale_lazyplan_warns_and_ignored(self):
        import pathlib

        from lazyplan.repo import stale_plan_dirs

        stale = os.path.join(self.repo, ".lazyplan")
        os.makedirs(stale)
        with open(os.path.join(stale, "lazyplan.db"), "w", encoding="utf-8") as fh:
            fh.write("data")
        also_stale = os.path.join(self.repo, ".agents", "plan")
        os.makedirs(also_stale)
        os.chdir(self.repo)
        # resolution ignores the stale dirs: shared home wins by default
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(self.tmp.name) / "home" / ".lazyplan" / "lazyplan.db",
        )
        self.assertEqual(
            stale_plan_dirs(self.repo), [pathlib.Path(stale), pathlib.Path(also_stale)]
        )
        self.assertEqual(stale_plan_dirs(os.path.join(self.tmp.name, "noroot")), [])
        # setup never migrates stale dirs on its own; it writes no repo DB
        self.assertEqual(lpui_main(["setup", "--yes", "--no-skills"]), 0)
        self.assertEqual(open(os.path.join(stale, "lazyplan.db"), encoding="utf-8").read(), "data")
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
            pathlib.Path(self.tmp.name) / "home" / ".lazyplan" / "lazyplan.db",
        )
        self.assertEqual(repo_label(resolve_db_path()), "global")

    def test_setup_and_info_in_repo(self):
        os.chdir(self.repo)
        # Zero-touch default leaves the repo alone, DB lives in the shared home.
        self.assertEqual(lpui_main(["setup", "--yes", "--no-skills"]), 0)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        self.assertEqual(lpui_main(["info"]), 0)
        # Repo placement writes the repo-shared DB.
        self.assertEqual(lpui_main(["setup", "--placement", "repo", "--yes", "--no-skills"]), 0)
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
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        self.tmp.cleanup()

    def test_legacy_ignored_in_resolution(self):
        import pathlib

        # A legacy .plan/ dir never resolves by itself anymore.
        os.makedirs(os.path.join(self.repo, ".plan"))
        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()),
            pathlib.Path(os.environ["HOME"]) / ".lazyplan" / "lazyplan.db",
        )
        self.assertEqual(repo_label(resolve_db_path()), "global")

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
        with open(os.path.join(legacy, "lazyplan.db"), "w", encoding="utf-8") as fh:
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

    def test_setup_noninteractive_keeps_legacy(self):
        os.makedirs(os.path.join(self.repo, ".plan"))
        os.chdir(self.repo)
        self.assertEqual(lpui_main(["--json", "setup", "--yes", "--no-skills"]), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".plan")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents/lazyplan")))


class TestSharedHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_home_unix(self):
        import pathlib

        from lazyplan import repo as repo_mod

        self.assertEqual(repo_mod.shared_home(), pathlib.Path(os.environ["HOME"]) / ".lazyplan")

    def test_shared_db_lives_beside_home(self):
        import pathlib

        from lazyplan import repo as repo_mod

        base = pathlib.Path(os.environ["HOME"]) / ".lazyplan"
        self.assertEqual(repo_mod.shared_db_path(), base / "lazyplan.db")

    def test_shared_home_windows_localappdata(self):
        import pathlib
        from unittest import mock

        from lazyplan import repo as repo_mod

        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "local")
        with mock.patch.object(repo_mod, "_os_name", return_value="nt"):
            self.assertEqual(
                repo_mod.shared_home(),
                pathlib.Path(self.tmp.name) / "local" / "lazyplan",
            )

    def test_shared_home_windows_real_home_matches_no_home(self):
        import pathlib
        from unittest import mock

        from lazyplan import repo as repo_mod

        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "local")
        with mock.patch.object(repo_mod, "_os_name", return_value="nt"):
            self.assertEqual(repo_mod.shared_home(pathlib.Path.home()), repo_mod.shared_home())
            sandbox = pathlib.Path(self.tmp.name) / "other"
            self.assertEqual(repo_mod.shared_home(sandbox), sandbox / ".lazyplan")

    def test_windows_reports_the_stray_home_database(self):
        import pathlib
        from unittest import mock

        from lazyplan import repo as repo_mod

        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "local")
        stray = pathlib.Path.home() / ".lazyplan" / "lazyplan.db"
        with mock.patch.object(repo_mod, "_os_name", return_value="nt"):
            self.assertIn(stray, repo_mod.legacy_db_candidates())
        with mock.patch.object(repo_mod, "_os_name", return_value="posix"):
            self.assertNotIn(stray, repo_mod.legacy_db_candidates())

    def test_shared_home_windows_falls_back(self):
        import pathlib
        from unittest import mock

        from lazyplan import repo as repo_mod

        os.environ.pop("LOCALAPPDATA", None)
        with (
            mock.patch.object(repo_mod, "_os_name", return_value="nt"),
            mock.patch.object(pathlib.Path, "home", return_value=pathlib.Path(os.environ["HOME"])),
        ):
            self.assertEqual(repo_mod.shared_home(), pathlib.Path(os.environ["HOME"]) / ".lazyplan")

    def test_walk_up_finds_nested_team_dir_without_git(self):
        import pathlib

        from lazyplan.repo import walk_up_team_db

        outer = os.path.join(self.tmp.name, "outer")
        inner = os.path.join(outer, "inner", "deep")
        os.makedirs(os.path.join(outer, ".agents", "lazyplan"))
        os.makedirs(inner)
        self.assertEqual(
            walk_up_team_db(inner),
            pathlib.Path(outer) / ".agents" / "lazyplan" / "lazyplan.db",
        )

    def test_walk_up_prefers_nearest(self):
        import pathlib

        from lazyplan.repo import walk_up_team_db

        outer = os.path.join(self.tmp.name, "outer")
        inner = os.path.join(outer, "inner")
        os.makedirs(os.path.join(outer, ".agents", "lazyplan"))
        os.makedirs(os.path.join(inner, ".agents", "lazyplan"))
        self.assertEqual(
            walk_up_team_db(inner),
            pathlib.Path(inner) / ".agents" / "lazyplan" / "lazyplan.db",
        )

    def test_walk_up_none_when_absent(self):
        from lazyplan.repo import walk_up_team_db

        plain = os.path.join(self.tmp.name, "plain", "sub")
        os.makedirs(plain)
        self.assertIsNone(walk_up_team_db(plain))


class TestSharedSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        self.tmp.cleanup()

    def _old_db(self, rel: str, title: str, mtime: float) -> str:
        import pathlib

        from lazyplan.store import Store

        path = str(pathlib.Path(os.environ["HOME"]) / rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Store(path).add_plan(title, actor="t")
        os.utime(path, (mtime, mtime))
        return path

    def test_seed_imports_newest_old_db_once(self):

        from lazyplan.repo import shared_db_path
        from lazyplan.store import Store

        old = self._old_db(".local/share/lazyplan/lazyplan.db", "Old plans", 1000.0)
        self._old_db(".agents/skills/lazyplan/lazyplan.db", "Skill plans", 2000.0)
        assert not shared_db_path().exists()
        seeded = Store(None)
        self.assertEqual([p.name for p in seeded.list_plans()], ["Skill plans"])
        # Originals untouched; shared DB now exists so no second import.
        self.assertEqual([p.name for p in Store(old).list_plans()], ["Old plans"])
        seeded.add_plan("New", actor="t")
        self.assertEqual(
            sorted(p.name for p in Store(None).list_plans()),
            ["New", "Skill plans"],
        )

    def test_seed_never_overwrites_shared(self):
        from lazyplan.repo import shared_db_path
        from lazyplan.store import Store

        self._old_db(".local/share/lazyplan/lazyplan.db", "Old plans", 1000.0)
        first = Store(None)
        first.add_plan("Mine", actor="t")
        self._old_db(".agents/skills/lazyplan/lazyplan.db", "Skill plans", 9999.0)
        self.assertEqual(sorted(p.name for p in Store(None).list_plans()), ["Mine"])
        self.assertTrue(shared_db_path().is_file())

    def test_seed_empty_without_old_dbs(self):
        from lazyplan.repo import shared_db_path
        from lazyplan.store import Store

        seeded = Store(None)
        self.assertEqual(seeded.list_plans(), [])
        self.assertTrue(shared_db_path().is_file())


class TestInitParity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "myproj")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(self.bare)
        self.old_cwd = os.getcwd()
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        self.tmp.cleanup()

    def _init_db(self, cwd: str) -> str:
        import io
        import json
        from contextlib import redirect_stdout

        os.chdir(cwd)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--json", "setup", "--yes", "--no-skills"]), 0)
        return json.loads(buf.getvalue())["db"]

    def test_non_team_init_identical_in_repo_and_bare(self):
        import pathlib

        shared = str(pathlib.Path(os.environ["HOME"]) / ".lazyplan" / "lazyplan.db")
        self.assertEqual(self._init_db(self.repo), shared)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        self.assertEqual(self._init_db(self.bare), shared)

    def test_repo_setup_writes_repo_dir(self):
        import io
        import json
        import pathlib
        from contextlib import redirect_stdout

        os.chdir(self.repo)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(
                lpui_main(["--json", "setup", "--placement", "repo", "--yes", "--no-skills"]), 0
            )
        payload = json.loads(buf.getvalue())
        self.assertEqual(
            payload["db"], str(pathlib.Path(self.repo) / ".agents/lazyplan" / "lazyplan.db")
        )
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".agents/lazyplan", "lazyplan.db")))


if __name__ == "__main__":
    unittest.main()
