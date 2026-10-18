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

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is not None:
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

    def test_resolve_prefers_repo_plan(self):
        import pathlib

        os.chdir(self.repo)
        self.assertEqual(
            pathlib.Path(resolve_db_path()), pathlib.Path(self.repo) / ".plan" / "lazyplan.db"
        )

    def test_explicit_and_env_win(self):
        os.chdir(self.repo)
        import pathlib

        custom = str(pathlib.Path(self.tmp.name) / "custom.db")
        self.assertEqual(str(resolve_db_path(custom)), custom)
        os.environ["LAZYPLAN_DB"] = custom
        self.assertEqual(str(resolve_db_path()), custom)

    def test_store_creates_plan_dir_and_config(self):
        os.chdir(self.repo)
        s = Store(None)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".plan", "lazyplan.db")))
        cfg = os.path.join(self.repo, ".plan", "config.json")
        self.assertTrue(os.path.isfile(cfg))
        self.assertEqual(json.load(open(cfg))["db"], "lazyplan.db")
        self.assertEqual(repo_label(s.path), "myproj")
        p = s.add_project("P", actor="t")
        self.assertEqual(p.id, 1)

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
        self.assertEqual(lpui_main(["init"]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".plan", "lazyplan.db")))
        self.assertEqual(lpui_main(["info"]), 0)
        # data added via cwd resolves to the same repo db
        self.assertEqual(lpui_main(["add-project", "--name", "RP"]), 0)
        s = Store(None)
        self.assertEqual(len(s.list_projects()), 1)


if __name__ == "__main__":
    unittest.main()
