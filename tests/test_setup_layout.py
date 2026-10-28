"""Setup layout: placement resolution, writes, doctor, and state."""

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

from support.home import sandbox_home  # noqa: E402

from lazyplan import setup, setup_layout, skills  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.repo import PLAN_DIR  # noqa: E402


class LayoutCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def choice(self, placement="home", **kwargs) -> setup_layout.SetupChoice:
        return setup_layout.SetupChoice(placement=placement, agents=["opencode"], **kwargs)

    def preview(self, choice, root=None):
        plan = skills.plan_choice(choice, root or self.repo, self.home)
        return setup_layout.resolve_choice(choice, root or self.repo, plan, self.home)


class TestResolution(LayoutCase):
    def test_home_layout_writes_nothing(self):
        layout = self.preview(self.choice("home"))
        self.assertEqual(layout.storage, "home")
        self.assertEqual(layout.db, self.home / ".lazyplan/lazyplan.db")
        self.assertIsNone(layout.config)
        self.assertEqual(layout.gitignore_entries, ())
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_repo_layout_is_repo_owned(self):
        layout = self.preview(self.choice("repo"))
        self.assertEqual(layout.storage, "repo")
        self.assertEqual(layout.db, self.repo / PLAN_DIR / "lazyplan.db")
        self.assertIsNotNone(layout.config)
        self.assertIn(".agents/lazyplan/lazyplan.db", layout.gitignore_entries)

    def test_explicit_db_wins(self):
        target = Path(self.tmp.name) / "custom.db"
        choice = self.choice("repo", explicit_db=str(target))
        layout = self.preview(choice)
        self.assertEqual(layout.storage, "explicit")
        self.assertEqual(layout.db, target)
        self.assertTrue(layout.explicit)

    def test_explicit_choice_has_no_skills(self):
        choice = self.choice("home", explicit_db=str(Path(self.tmp.name) / "x.db"))
        self.assertEqual(skills.plan_choice(choice, self.repo, self.home).skill_files, [])

    def test_repo_skill_files_are_gitignored(self):
        layout = self.preview(self.choice("repo"))
        sources = [p.as_posix() for p in layout.skill_plan.skill_files]
        self.assertTrue(any(".agents/skills/lazyplan" in p for p in sources))
        self.assertTrue(any(".agents/skills/lazyplan/" in e for e in layout.gitignore_entries))

    def test_resolution_creates_nothing(self):
        layout = self.preview(self.choice("repo"))
        self.assertFalse((self.home / ".lazyplan").exists())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertTrue(setup_layout.inventory(layout)["clean"])


class TestApply(LayoutCase):
    def test_home_placement_writes_no_repo_files(self):
        result = setup.apply_choice(self.choice("home"), self.repo, self.home, "0.23.0")
        self.assertTrue(Path(result["db"]).is_file())
        self.assertTrue((self.home / ".lazyplan/templates/plan.md").is_file())
        self.assertFalse((self.repo / ".agents").exists())
        state = setup.load_state(self.home)
        self.assertEqual(state.placement, "home")
        self.assertEqual(state.last_version, "0.23.0")

    def test_repo_placement_writes_config_templates_agents_and_gitignore(self):
        setup.apply_choice(self.choice("repo"), self.repo, self.home, "0.23.0")
        self.assertTrue((self.repo / PLAN_DIR / "lazyplan.db").is_file())
        self.assertTrue((self.repo / PLAN_DIR / "config.json").is_file())
        self.assertTrue((self.repo / PLAN_DIR / "templates/plan.md").is_file())
        self.assertTrue((self.repo / "AGENTS.md").is_file())
        gitignore = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".agents/lazyplan/lazyplan.db", gitignore)
        self.assertNotIn(".agents/lazyplan/templates", gitignore)
        self.assertNotIn(".agents/lazyplan/config.json", gitignore)
        self.assertEqual(setup.load_state(self.home).placement, "repo")

    def test_second_apply_is_idempotent(self):
        first = setup.apply_choice(self.choice("home"), self.repo, self.home, "0.23.0")
        second = setup.apply_choice(self.choice("home"), self.repo, self.home, "0.23.0")
        self.assertEqual(first["db"], second["db"])
        self.assertTrue(second["installed"])
        self.assertTrue(all("up-to-date" in line for line in second["installed"]))
        self.assertTrue(setup.state_path(self.home).is_file())

    def test_explicit_db_writes_no_layout_files(self):
        target = Path(self.tmp.name) / "custom.db"
        result = setup.apply_choice(
            self.choice("home", explicit_db=str(target)), self.repo, self.home, "0.23.0"
        )
        self.assertEqual(result["db"], str(target))
        self.assertTrue(target.is_file())
        self.assertFalse((self.home / ".lazyplan/templates").exists())

    def test_old_skill_copy_is_backed_up_and_refreshed(self):
        target = self.home / ".config/opencode/skills/lazyplan/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text(
            "---\nname: lazyplan\ndescription: old\n---\nrun an old command\n", encoding="utf-8"
        )
        result = setup.apply_choice(self.choice("home"), self.repo, self.home, "0.23.0")
        self.assertIn(str(target), result["refreshed"])
        self.assertEqual(target.read_text(encoding="utf-8"), skills.render_skill())
        self.assertTrue(any("SKILL.md" in path for path in result["backups"]))


class TestDoctor(LayoutCase):
    def _run(self, argv) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = lpui_main(argv)
        return code, buf.getvalue()

    def test_doctor_is_read_only_and_clean_after_setup(self):
        setup.apply_choice(self.choice("home"), self.repo, self.home, "0.23.0")
        code, out = self._run(["doctor"])
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".lazyplan/plan.db").exists())

    def test_doctor_reports_repo_findings(self):
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        (plan_dir / "lazyplan.db").write_bytes(b"")
        code, out = self._run(["doctor"])
        self.assertIn("finding:", out)

    def test_json_setup_and_doctor(self):
        code, out = self._run(["setup", "--yes", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["placement"], "home")
        code, out = self._run(["doctor", "--json"])
        self.assertEqual(code, 0)
        self.assertIn("expected", json.loads(out))


class TestCommandSurface(LayoutCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = lpui_main(argv)
        return code, buf.getvalue()

    def test_init_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(["init"])

    def test_first_run_creates_defaults(self):
        code, out = self._run(["list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertTrue(setup.state_path(self.home).is_file())

    def test_second_run_does_not_reinstall(self):
        self._run(["list", "--json"])
        before = setup.load_state(self.home).to_dict()
        self._run(["list", "--json"])
        self.assertEqual(setup.load_state(self.home).to_dict(), before)

    def test_install_helpers_do_not_setup(self):
        self._run(["completion", "--shell", "bash"])
        self._run(["doctor"])
        self.assertFalse(setup.state_path(self.home).exists())
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())

    def test_no_setup_env_skips_state(self):
        old = os.environ.get(setup.NO_SETUP_ENV)
        os.environ[setup.NO_SETUP_ENV] = "1"
        try:
            self._run(["list", "--json"])
        finally:
            if old is None:
                os.environ.pop(setup.NO_SETUP_ENV, None)
            else:
                os.environ[setup.NO_SETUP_ENV] = old
        self.assertFalse(setup.state_path(self.home).exists())

    def test_setup_repo_placement_in_a_git_repo(self):
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        code, out = self._run(["setup", "--placement", "repo", "--yes", "--json"])
        self.assertEqual(code, 0, out)
        self.assertTrue((self.repo / PLAN_DIR / "lazyplan.db").is_file())


if __name__ == "__main__":
    unittest.main()
