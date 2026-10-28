"""Switching placement removes the generated resources of the old layout."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from support.home import sandbox_home  # noqa: E402

from lazyplan import setup, templates  # noqa: E402
from lazyplan.repo import PLAN_DIR, repo_plan_db_path  # noqa: E402
from lazyplan.setup_layout import SetupChoice  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class SwitchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        sandbox_home(self, str(self.home))

    def tearDown(self):
        self.tmp.cleanup()

    def seed_repo_layout(self):
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        Store(repo_plan_db_path(self.repo)).add_plan("P")
        (plan_dir / "config.json").write_text('{"db": "lazyplan.db"}\n', encoding="utf-8")
        template = plan_dir / "templates"
        template.mkdir()
        (template / "plan.md").write_text(templates.STARTERS["plan"], encoding="utf-8")
        skill = self.repo / ".agents/skills/lazyplan/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("old skill\n", encoding="utf-8")
        (self.repo / "AGENTS.md").write_text(
            "# Mine\n\n<!-- lazyplan:start -->\nold block\n<!-- lazyplan:end -->\n",
            encoding="utf-8",
        )
        (self.repo / ".gitignore").write_text("*.db\n.agents/lazyplan/\n", encoding="utf-8")
        setup.save_state(
            setup.SetupState(placement="repo", agents=["claude"], last_version="1.0"),
            self.home,
        )

    def test_repo_to_home_removes_generated_resources(self):
        self.seed_repo_layout()
        setup.apply_choice(
            SetupChoice(placement="home", agents=["claude"]), self.repo, self.home, "1.0"
        )
        plan_dir = self.repo / PLAN_DIR
        self.assertFalse((plan_dir / "config.json").exists())
        self.assertFalse((plan_dir / "templates/plan.md").exists())
        self.assertFalse((self.repo / ".agents/skills/lazyplan/SKILL.md").exists())
        self.assertNotIn("lazyplan:start", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("# Mine", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertNotIn(".agents/lazyplan", (self.repo / ".gitignore").read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertTrue(list((self.home / ".lazyplan/backups").iterdir()))

    def test_home_to_repo_writes_the_repo_contract(self):
        setup.save_state(
            setup.SetupState(placement="home", agents=["claude"], last_version="1.0"),
            self.home,
        )
        setup.apply_choice(
            SetupChoice(placement="repo", agents=["claude"]), self.repo, self.home, "1.0"
        )
        self.assertTrue((self.repo / ".agents/lazyplan/lazyplan.db").is_file())
        self.assertTrue((self.repo / ".agents/lazyplan/config.json").is_file())
        self.assertTrue((self.repo / ".agents/lazyplan/templates/plan.md").is_file())
        self.assertIn("lazyplan:start", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(setup.load_state(self.home).placement, "repo")


if __name__ == "__main__":
    unittest.main()
