"""Init layout: scope-to-resource mapping, safe repair, and read-only checks."""

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import init_layout
from lazyplan.cli import main as lpui_main
from lazyplan.skills import SkillPlan, plan_init


def _args(**overrides) -> argparse.Namespace:
    base = {
        "db": None,
        "team": False,
        "skills_scope": "",
        "skills_dir": None,
        "no_skills": False,
        "yes": True,
        "json": True,
        "check": False,
        "agents": "",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def data_actions(payload: dict) -> list:
    return list((payload.get("repairs") or {}).get("actions") or [])


def _skill_plan(scope: str = "global", files: list[str] | None = None) -> SkillPlan:
    return SkillPlan(
        scope=scope,
        tools=["opencode"],
        skills_dir=None,
        skill_files=[Path(p) for p in (files or [])],
        agents_md=None,
    )


class TestLayoutResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.repo = Path(self.tmp.name) / "repo"
        self.home.mkdir()
        self.repo.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_global_layout_is_home_only(self):
        layout = init_layout.resolve(_args(), self.repo, _skill_plan(), self.home)
        self.assertEqual(layout.storage, "home")
        self.assertEqual(layout.db, self.home / ".lazyplan/lazyplan.db")
        self.assertIsNone(layout.config)
        self.assertEqual(layout.gitignore_entries, ())

    def test_team_layout_is_repo_owned(self):
        layout = init_layout.resolve(_args(team=True), self.repo, _skill_plan("project"), self.home)
        self.assertEqual(layout.storage, "repo")
        self.assertEqual(layout.db, self.repo / ".agents/lazyplan/lazyplan.db")
        self.assertEqual(layout.config, self.repo / ".agents/lazyplan/config.json")
        self.assertIn(".agents/lazyplan/", layout.gitignore_entries)

    def test_team_with_no_skills_still_uses_repo_storage(self):
        layout = init_layout.resolve(
            _args(team=True, no_skills=True), self.repo, _skill_plan("none"), self.home
        )
        self.assertEqual(layout.storage, "repo")
        self.assertEqual(layout.skill_plan.skill_files, [])

    def test_explicit_db_wins(self):
        target = Path(self.tmp.name) / "custom.db"
        layout = init_layout.resolve(
            _args(db=str(target), team=True), self.repo, _skill_plan("project"), self.home
        )
        self.assertEqual(layout.storage, "explicit")
        self.assertEqual(layout.db, target)
        self.assertTrue(layout.explicit)

    def test_skill_files_are_ignored_in_repo(self):
        skill = self.repo / ".agents/skills/lazyplan/SKILL.md"
        layout = init_layout.resolve(
            _args(team=True), self.repo, _skill_plan("project", [str(skill)]), self.home
        )
        self.assertIn(".agents/skills/lazyplan/", layout.gitignore_entries)

    def test_resolution_creates_nothing(self):
        layout = init_layout.resolve(_args(team=True), self.repo, _skill_plan("project"), self.home)
        report = init_layout.inventory(layout)
        repairs = init_layout.plan_repairs(layout)
        self.assertFalse((self.home / ".lazyplan").exists())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertTrue(report["clean"])
        self.assertEqual(repairs.actions, [])


class TestScopeMatrix(unittest.TestCase):
    """Table-driven scope/flag matrix: every destination, no writes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.repo = Path(self.tmp.name) / "repo"
        self.home.mkdir()
        self.repo.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, **overrides) -> init_layout.InitLayout:
        args = _args(agents="opencode", **overrides)
        skills = plan_init(args, self.repo, self.home)
        return init_layout.resolve(args, self.repo, skills, self.home)

    def test_scope_matrix_paths(self):
        home_db = self.home / ".lazyplan/lazyplan.db"
        repo_db = self.repo / ".agents/lazyplan/lazyplan.db"
        repo_skill = self.repo / ".agents/skills/lazyplan/SKILL.md"
        opencode_skill = self.repo / ".opencode/skills/lazyplan/SKILL.md"
        home_skill = self.home / ".config/opencode/skills/lazyplan/SKILL.md"
        custom = Path(self.tmp.name) / "custom-skills"
        explicit = Path(self.tmp.name) / "explicit.db"
        cases = [
            ("global", {}, "home", home_db, [home_skill], None, None, home_skill),
            (
                "project",
                {"skills_scope": "project"},
                "repo",
                repo_db,
                [repo_skill, opencode_skill],
                self.repo / ".agents/lazyplan/config.json",
                self.repo / "AGENTS.md",
                None,
            ),
            (
                "both",
                {"skills_scope": "both"},
                "repo",
                repo_db,
                [repo_skill, opencode_skill, home_skill],
                self.repo / ".agents/lazyplan/config.json",
                self.repo / "AGENTS.md",
                home_skill,
            ),
            (
                "team",
                {"team": True},
                "repo",
                repo_db,
                [repo_skill, opencode_skill],
                self.repo / ".agents/lazyplan/config.json",
                self.repo / "AGENTS.md",
                None,
            ),
            (
                "team-no-skills",
                {"team": True, "no_skills": True},
                "repo",
                repo_db,
                [],
                self.repo / ".agents/lazyplan/config.json",
                None,
                None,
            ),
            ("none", {"no_skills": True}, "home", home_db, [], None, None, None),
            (
                "team-global-skills",
                {"team": True, "skills_scope": "global"},
                "repo",
                repo_db,
                [home_skill],
                self.repo / ".agents/lazyplan/config.json",
                None,
                home_skill,
            ),
            (
                "custom-dir",
                {"skills_dir": str(custom)},
                "home",
                home_db,
                [custom / "lazyplan/SKILL.md"],
                None,
                None,
                custom / "lazyplan/SKILL.md",
            ),
            (
                "explicit-db",
                {"db": str(explicit)},
                "explicit",
                explicit,
                [home_skill],
                None,
                None,
                home_skill,
            ),
        ]
        for name, flags, storage, db, files, config, agents, extra in cases:
            with self.subTest(name):
                layout = self._resolve(**flags)
                self.assertEqual(layout.storage, storage)
                self.assertEqual(layout.db, db)
                self.assertEqual(layout.skill_plan.skill_files, files)
                self.assertEqual(layout.config, config)
                self.assertEqual(layout.agents_md, agents)
                if extra is not None:
                    self.assertIn(extra, layout.skill_plan.skill_files)
                if storage == "repo":
                    self.assertIn(".agents/lazyplan/", layout.gitignore_entries)
                else:
                    self.assertEqual(layout.gitignore_entries, ())

    def test_env_db_wins(self):
        target = Path(self.tmp.name) / "env.db"
        with mock.patch.dict(os.environ, {"LAZYPLAN_DB": str(target)}):
            layout = self._resolve(team=True)
        self.assertEqual(layout.storage, "explicit")
        self.assertEqual(layout.db, target)

    def test_project_scope_without_repo_skips_skills(self):
        args = _args(agents="opencode", skills_scope="project")
        skills = plan_init(args, None, self.home)
        self.assertEqual(skills.scope, "none")
        self.assertIn("git repository", skills.skipped or "")

    def test_both_scope_without_repo_falls_back_global(self):
        args = _args(agents="opencode", skills_scope="both")
        skills = plan_init(args, None, self.home)
        self.assertEqual(skills.scope, "global")
        self.assertEqual(
            skills.skill_files,
            [self.home / ".config/opencode/skills/lazyplan/SKILL.md"],
        )


class TestInitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.repo = Path(self.tmp.name) / "repo"
        self.home.mkdir()
        (self.repo / ".git").mkdir(parents=True)
        self.old_cwd = os.getcwd()
        self.old_env = {key: os.environ.get(key) for key in ("HOME", "LAZYPLAN_DB")}
        os.environ["HOME"] = str(self.home)
        os.environ.pop("LAZYPLAN_DB", None)
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, dict, str]:
        buf = io.StringIO()
        err = io.StringIO()
        old_err = sys.stderr
        sys.stderr = err
        try:
            with redirect_stdout(buf):
                code = lpui_main([*argv, "--json"])
        finally:
            sys.stderr = old_err
        payload = json.loads(buf.getvalue()) if buf.getvalue().strip() else {}
        return code, payload, err.getvalue()

    def _repo_files(self) -> set[str]:
        return {
            str(path.relative_to(self.repo))
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

    def test_global_init_writes_only_home(self):
        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(self.home / ".lazyplan/lazyplan.db"))
        self.assertEqual(self._repo_files(), set())
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertFalse((self.home / ".lazyplan/config.json").exists())

    def test_team_no_skills_uses_repo_storage(self):
        code, payload, _ = self._run("init", "--team", "--yes", "--no-skills")
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(self.repo / ".agents/lazyplan/lazyplan.db"))
        self.assertIn(".agents/lazyplan/config.json", self._repo_files())
        self.assertIn(".agents/lazyplan/templates/plan.md", self._repo_files())
        self.assertNotIn(".agents/skills/lazyplan/SKILL.md", self._repo_files())
        self.assertNotIn("AGENTS.md", self._repo_files())
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())
        self.assertFalse((self.home / ".lazyplan/templates").exists())

    def test_config_only_clone_is_repaired(self):
        plan_dir = self.repo / ".agents/lazyplan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "config.json").write_text('{"version":1,"db":"lazyplan.db"}\n')
        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self._repo_files(), set())
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertTrue(Path(payload["repairs"]["backup_dir"]).is_dir())

    def test_repo_db_moves_to_empty_home(self):
        self.assertEqual(self._run("init", "--team", "--yes")[0], 0)
        repo_db = self.repo / ".agents/lazyplan/lazyplan.db"
        lpui_main(
            [
                "--db",
                str(repo_db),
                "plan",
                "add",
                "--title",
                "Team plan",
                "--why",
                "w",
                "--what",
                "x",
            ]
        )
        lpui_main(
            [
                "--db",
                str(repo_db),
                "milestone",
                "add",
                "--plan",
                "1",
                "--title",
                "Slice",
                "--desc",
                "Slice value",
            ]
        )
        lpui_main(
            [
                "--db",
                str(repo_db),
                "task",
                "add",
                "--milestone",
                "1",
                "--title",
                "Do it",
                "--desc",
                "Do the work",
            ]
        )
        lpui_main(
            [
                "--db",
                str(repo_db),
                "criterion",
                "add",
                "--kind",
                "plan",
                "--id",
                "1",
                "--text",
                "Done",
            ]
        )
        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self._repo_files(), set())
        self.assertEqual(payload["counts"]["plans"], 1)
        self.assertEqual(payload["counts"]["milestones"], 1)
        self.assertEqual(payload["counts"]["tasks"], 1)
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        _, criteria, _ = self._run("criterion", "list", "--kind", "plan", "--id", "1")
        self.assertEqual(criteria[0]["text"], "Done")

    def test_two_populated_databases_stop_safely(self):
        self._run("plan", "add", "--title", "Home plan", "--why", "w", "--what", "x")
        self._run("init", "--team", "--yes")
        repo_db = self.repo / ".agents/lazyplan/lazyplan.db"
        lpui_main(
            [
                "--db",
                str(repo_db),
                "plan",
                "add",
                "--title",
                "Repo plan",
                "--why",
                "w",
                "--what",
                "x",
            ]
        )
        before_home = (self.home / ".lazyplan/lazyplan.db").read_bytes()
        before_repo = repo_db.read_bytes()
        code, payload, err = self._run("init", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("both databases contain plans", err)
        self.assertEqual((self.home / ".lazyplan/lazyplan.db").read_bytes(), before_home)
        self.assertEqual(repo_db.read_bytes(), before_repo)
        self.assertTrue(Path(payload["repairs"]["backup_dir"]).is_dir())

    def test_empty_repo_db_is_removed_when_home_has_plans(self):
        self._run("plan", "add", "--title", "Home plan", "--why", "w", "--what", "x")
        self.assertEqual(self._run("init", "--team", "--yes", "--no-skills")[0], 0)
        self.assertTrue((self.repo / ".agents/lazyplan/lazyplan.db").is_file())
        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(payload["counts"]["plans"], 1)
        self.assertEqual(self._repo_files(), set())
        self.assertTrue(payload["repairs"]["actions"])

    def test_team_init_does_not_touch_home_data(self):
        self._run("plan", "add", "--title", "Home plan", "--why", "w", "--what", "x")
        before = (self.home / ".lazyplan/lazyplan.db").read_bytes()
        code, _, _ = self._run("init", "--team", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual((self.home / ".lazyplan/lazyplan.db").read_bytes(), before)

    def test_check_and_doctor_do_not_write(self):
        plan_dir = self.repo / ".agents/lazyplan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "config.json").write_text('{"version":1,"db":"lazyplan.db"}\n')
        before = self._repo_files()
        check_code, check, _ = self._run("init", "--check")
        doctor_code, doctor, _ = self._run("doctor")
        self.assertEqual(check_code, 1)
        self.assertEqual(doctor_code, 1)
        self.assertFalse(check["clean"])
        self.assertFalse(doctor["clean"])
        self.assertEqual(self._repo_files(), before)
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())

    def test_both_uses_repo_storage_and_writes_global_skills(self):
        code, payload, _ = self._run(
            "init", "--skills-scope", "both", "--yes", "--agents", "opencode"
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(self.repo / ".agents/lazyplan/lazyplan.db"))
        files = self._repo_files()
        self.assertIn(".agents/skills/lazyplan/SKILL.md", files)
        self.assertIn(".opencode/skills/lazyplan/SKILL.md", files)
        self.assertIn("AGENTS.md", files)
        self.assertTrue((self.home / ".config/opencode/skills/lazyplan/SKILL.md").is_file())
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())

    def test_custom_skills_dir_keeps_home_storage(self):
        custom = Path(self.tmp.name) / "custom-skills"
        code, payload, _ = self._run("init", "--yes", "--skills-dir", str(custom))
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(self.home / ".lazyplan/lazyplan.db"))
        self.assertTrue((custom / "lazyplan/SKILL.md").is_file())
        self.assertEqual(self._repo_files(), set())

    def test_explicit_db_wins_and_is_not_repaired(self):
        plan_dir = self.repo / ".agents/lazyplan"
        plan_dir.mkdir(parents=True)
        config = plan_dir / "config.json"
        config.write_text('{"version":1,"db":"lazyplan.db"}\n')
        target = Path(self.tmp.name) / "explicit.db"
        code, payload, _ = self._run("--db", str(target), "init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(target))
        self.assertTrue(target.is_file())
        self.assertTrue(config.is_file())
        self.assertEqual(data_actions(payload), [])

    def test_env_db_wins_and_is_not_moved(self):
        target = Path(self.tmp.name) / "env.db"
        self.assertEqual(
            self._run(
                "--db", str(target), "plan", "add", "--title", "Env", "--why", "w", "--what", "x"
            )[0],
            0,
        )
        before = target.read_bytes()
        with mock.patch.dict(os.environ, {"LAZYPLAN_DB": str(target)}):
            code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(target))
        self.assertEqual(payload["layout"]["storage"], "explicit")
        self.assertEqual(target.read_bytes(), before)

    def test_json_and_yes_apply_the_same_layout(self):
        code, first, _ = self._run("init", "--yes", "--agents", "opencode")
        self.assertEqual(code, 0)
        code, second, _ = self._run("init", "--json", "--agents", "opencode")
        self.assertEqual(code, 0)
        self.assertEqual(first["layout"], second["layout"])
        self.assertTrue((self.home / ".config/opencode/skills/lazyplan/SKILL.md").is_file())

    def test_nested_dir_uses_repo_root(self):
        nested = self.repo / "pkg" / "src"
        nested.mkdir(parents=True)
        os.chdir(nested)
        code, payload, _ = self._run("init", "--team", "--yes", "--no-skills")
        self.assertEqual(code, 0)
        self.assertEqual(payload["db"], str(self.repo / ".agents/lazyplan/lazyplan.db"))

    def test_project_scope_leaves_home_db_untouched(self):
        self._run("plan", "add", "--title", "Home plan", "--why", "w", "--what", "x")
        home_db = self.home / ".lazyplan/lazyplan.db"
        before = home_db.read_bytes()
        code, payload, _ = self._run("init", "--skills-scope", "project", "--yes")
        self.assertEqual(code, 0)
        self.assertIn(".agents/skills/lazyplan/SKILL.md", self._repo_files())
        self.assertEqual(home_db.read_bytes(), before)

    def test_global_repair_removes_generated_skills_and_gitignore(self):
        self.assertEqual(self._run("init", "--team", "--yes", "--agents", "opencode")[0], 0)
        gitignore = self.repo / ".gitignore"
        gitignore.write_text(gitignore.read_text() + "node_modules/\n")
        custom = self.repo / ".agents/skills/custom/SKILL.md"
        custom.parent.mkdir(parents=True)
        custom.write_text("custom skill\n")

        code, payload, _ = self._run("init", "--yes", "--agents", "opencode")
        self.assertEqual(code, 0)
        files = self._repo_files()
        self.assertNotIn(".agents/skills/lazyplan/SKILL.md", files)
        self.assertNotIn(".opencode/skills/lazyplan/SKILL.md", files)
        self.assertNotIn("AGENTS.md", files)
        self.assertIn(".agents/skills/custom/SKILL.md", files)
        self.assertIn("node_modules/", gitignore.read_text())
        self.assertNotIn(".agents/lazyplan/", gitignore.read_text())
        self.assertTrue(payload["repairs"]["backup_dir"])
        for action in data_actions(payload):
            self.assertTrue(Path(action["backup"]).exists())

    def test_global_repair_moves_repo_templates_home(self):
        self.assertEqual(self._run("init", "--team", "--yes", "--no-skills")[0], 0)
        repo_templates = self.repo / ".agents/lazyplan/templates"
        (repo_templates / "plan.md").write_text("custom starter\n")
        home_templates = self.home / ".lazyplan/templates"
        self.assertFalse(home_templates.exists())

        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual((home_templates / "plan.md").read_text(), "custom starter\n")
        self.assertFalse((repo_templates / "plan.md").exists())
        self.assertTrue(payload["repairs"]["backup_dir"])
        template_actions = [a for a in data_actions(payload) if a["source"].endswith("plan.md")]
        self.assertEqual(template_actions[0]["action"], "move")

    def test_global_repair_backs_up_agents_block(self):
        self.assertEqual(self._run("init", "--team", "--yes", "--agents", "opencode")[0], 0)
        agents = self.repo / "AGENTS.md"
        before = agents.read_text()
        code, payload, _ = self._run("init", "--yes", "--agents", "opencode")
        self.assertEqual(code, 0)
        strip = next(
            a
            for a in data_actions(payload)
            if a["action"] == "strip" and a["source"].endswith("AGENTS.md")
        )
        self.assertEqual(Path(strip["backup"]).read_text(), before)

    def test_global_repair_preserves_other_agents_content(self):
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "# Project\n\nKeep this.\n\n<!-- lazyplan:start -->\nold\n<!-- lazyplan:end -->\n"
        )
        self._run("init", "--yes")
        text = agents.read_text()
        self.assertIn("Keep this.", text)
        self.assertNotIn("lazyplan:start", text)

    def test_check_and_doctor_agree(self):
        plan_dir = self.repo / ".agents/lazyplan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "config.json").write_text('{"version":1,"db":"lazyplan.db"}\n')
        _, check, _ = self._run("init", "--check")
        _, doctor, _ = self._run("doctor")
        self.assertEqual(check, doctor)

    def test_global_init_does_not_migrate_legacy_plan_dir(self):
        legacy = self.repo / ".plan"
        legacy.mkdir()
        (legacy / "keep.md").write_text("leave me\n")
        code, payload, _ = self._run("init", "--yes")
        self.assertEqual(code, 0)
        self.assertTrue((legacy / "keep.md").is_file())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertIsNone(payload["legacy"])

    def test_team_init_migrates_legacy_plan_dir_with_backup(self):
        legacy = self.repo / ".plan"
        legacy.mkdir()
        (legacy / "keep.md").write_text("legacy notes\n")
        code, payload, _ = self._run("init", "--team", "--yes", "--no-skills")
        self.assertEqual(code, 0)
        self.assertFalse(legacy.exists())
        self.assertEqual((self.repo / ".agents/lazyplan/keep.md").read_text(), "legacy notes\n")
        info = payload["legacy"]
        self.assertEqual(info["moved"], str(self.repo / ".agents/lazyplan"))
        backups = list(Path(info["backup"]).rglob("keep.md"))
        self.assertEqual([path.read_text() for path in backups], ["legacy notes\n"])

    def test_interactive_preflight_names_paths_and_cancels(self):
        from lazyplan.cli import _confirm_init
        from lazyplan.skills import plan_init as resolve_skills

        args = _args(agents="opencode", yes=False, json=False)
        skills = resolve_skills(args, self.repo, self.home)
        layout = init_layout.resolve(args, self.repo, skills, self.home)
        repairs = init_layout.plan_repairs(layout)
        err = io.StringIO()
        buf = io.StringIO()
        old_err = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("builtins.input", return_value="n"):
                with redirect_stdout(buf):
                    code = _confirm_init(args, self.repo, layout, repairs, True)
        finally:
            sys.stderr = old_err
        payload = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["cancelled"])
        text = err.getvalue()
        self.assertIn(str(layout.db), text)
        self.assertIn(str(layout.templates_dir), text)
        self.assertIn(str(self.home / ".config/opencode/skills/lazyplan/SKILL.md"), text)
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_doctor_clean_exit_zero(self):
        code, report, _ = self._run("doctor")
        self.assertEqual(code, 0)
        self.assertTrue(report["clean"])


class TestInitFlagErrors(unittest.TestCase):
    """Flags that cannot honor a scope fail clearly instead of guessing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.work = Path(self.tmp.name) / "work"
        self.home.mkdir()
        self.work.mkdir()
        self.old_cwd = os.getcwd()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        os.chdir(self.work)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, dict, str]:
        buf = io.StringIO()
        err = io.StringIO()
        old_err = sys.stderr
        sys.stderr = err
        try:
            with redirect_stdout(buf):
                code = lpui_main([*argv, "--json"])
        finally:
            sys.stderr = old_err
        return code, json.loads(buf.getvalue()), err.getvalue()

    def test_team_outside_repo_errors(self):
        code, payload, err = self._run("init", "--team", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("needs a git repository", err)
        self.assertEqual(payload["error"], "`--team` needs a git repository")

    def test_project_scope_outside_repo_errors(self):
        code, payload, err = self._run("init", "--skills-scope", "project", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("needs a git repository", err)
        self.assertIn("--skills-scope project", payload["error"])

    def test_doctor_team_outside_repo_errors(self):
        code, _, err = self._run("doctor", "--team")
        self.assertEqual(code, 2)
        self.assertIn("needs a git repository", err)


if __name__ == "__main__":
    unittest.main()
