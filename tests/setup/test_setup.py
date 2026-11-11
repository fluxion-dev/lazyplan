"""First-run setup state, choices, findings, and migrations."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure.repo import PLAN_DIR, repo_plan_db_path
from lazyplan.presentation import setup
from lazyplan.store import Store


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_state_returns_defaults(self):
        state = setup.load_state(self.home)
        self.assertEqual(state.placement, setup.HOME)
        self.assertEqual(state.agents, [])
        self.assertEqual(state.decisions, {})
        self.assertEqual(state.hooks_mode, "strict")
        self.assertEqual(state.effective_mode(), "strict")

    def test_round_trip(self):
        state = setup.SetupState(
            placement=setup.REPO,
            agents=["opencode", "claude"],
            last_version="0.22.0",
            skills_enabled=False,
            hooks_enabled=False,
            decisions={"repo-db:/x": {"decision": "keep"}},
            integration_choices={
                "skill:lazyplan": {
                    "decision": "deferred",
                    "fingerprint": "abc123",
                    "version": "0.35.0",
                    "seen_at": "20261107-120000-000000",
                }
            },
        )
        path = setup.save_state(state, self.home)
        self.assertTrue(path.is_file())
        self.assertEqual(setup.load_state(self.home).to_dict(), state.to_dict())

    def test_old_state_derives_opt_outs(self):
        self._write_raw('{"hooks": false, "last_version": "0.22.0"}')
        state = setup.load_state(self.home)
        self.assertFalse(state.hooks_enabled)
        self.assertEqual(state.hooks_mode, "off")
        self.assertTrue(state.skills_enabled)
        self.assertEqual(state.integration_choices, {})

    def test_old_state_without_mode_becomes_strict(self):
        self._write_raw('{"hooks": true, "last_version": "0.22.0"}')
        state = setup.load_state(self.home)
        self.assertTrue(state.hooks_enabled)
        self.assertEqual(state.hooks_mode, "strict")

    def test_unknown_mode_falls_back_to_strict(self):
        self._write_raw('{"hooks_mode": "loud", "hooks": true}')
        self.assertEqual(setup.load_state(self.home).hooks_mode, "strict")

    def test_invalid_integration_choices_are_dropped(self):
        self._write_raw(
            '{"integration_choices": {'
            '"good": {"decision": "never", "fingerprint": "f"},'
            '"bad-decision": {"decision": "maybe"},'
            '"bad-shape": "never"'
            "}}"
        )
        choices = setup.load_state(self.home).integration_choices
        self.assertEqual(list(choices), ["good"])
        self.assertEqual(choices["good"]["decision"], "never")
        self.assertEqual(choices["good"]["version"], "")

    def _write_raw(self, text: str) -> None:
        path = setup.state_path(self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_corrupt_state_returns_defaults(self):
        self._write_raw("{not json")
        self.assertEqual(setup.load_state(self.home).to_dict(), setup.SetupState().to_dict())

    def test_unknown_placement_falls_back_home(self):
        self._write_raw('{"placement": "elsewhere"}')
        self.assertEqual(setup.load_state(self.home).placement, setup.HOME)

    def test_save_replaces_atomically(self):
        setup.save_state(setup.SetupState(last_version="1"), self.home)
        setup.save_state(setup.SetupState(last_version="2"), self.home)
        self.assertEqual(setup.load_state(self.home).last_version, "2")
        self.assertEqual(list(setup.state_path(self.home).parent.glob("*.tmp")), [])


class TestChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True, timeout=10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_home_outside_repo(self):
        choice = setup.default_choice(Path(self.tmp.name), self.home)
        self.assertEqual(choice.placement, setup.HOME)

    def test_existing_team_db_keeps_repo_placement(self):
        (self.repo / PLAN_DIR).mkdir(parents=True)
        Store(repo_plan_db_path(self.repo))
        choice = setup.default_choice(self.repo, self.home)
        self.assertEqual(choice.placement, setup.REPO)

    def test_remembers_state_agents(self):
        state = setup.SetupState(agents=["opencode"], skills_dir="/tmp/skills")
        choice = setup.default_choice(Path(self.tmp.name), self.home, state)
        self.assertEqual(choice.agents, ["opencode"])
        self.assertEqual(choice.skills_dir, "/tmp/skills")


class TestFindings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True, timeout=10)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "T"], check=True)
        (self.repo / "README").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "init"], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _repo_db(self, plans: int = 0):
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        store = Store(repo_plan_db_path(self.repo))
        for index in range(plans):
            store.add_plan(f"P{index}")
        return repo_plan_db_path(self.repo)

    def test_untracked_repo_db_is_a_finding(self):
        self._repo_db()
        findings = setup.detect_findings(self.repo, self.home)
        repo = [f for f in findings if f.kind == "repo-db"]
        self.assertEqual(len(repo), 1)
        self.assertEqual(repo[0].state, "untracked")

    def test_ignored_repo_db_is_a_finding(self):
        (self.repo / ".gitignore").write_text("*.db\n", encoding="utf-8")
        self._repo_db()
        repo = [f for f in setup.detect_findings(self.repo, self.home) if f.kind == "repo-db"]
        self.assertEqual(repo[0].state, "ignored")

    def test_tracked_repo_db_is_still_a_finding(self):
        self._repo_db()
        subprocess.run(["git", "-C", self.repo, "add", "-f", f"{PLAN_DIR}/lazyplan.db"], check=True)
        repo = [f for f in setup.detect_findings(self.repo, self.home) if f.kind == "repo-db"]
        self.assertEqual(repo[0].state, "tracked")

    def test_conflict_when_both_have_plans(self):
        self._repo_db(plans=1)
        Store(setup.shared_db_path(self.home)).add_plan("home")
        kinds = [f.kind for f in setup.detect_findings(self.repo, self.home)]
        self.assertIn("db-conflict", kinds)

    def testexplicit_db_skips_findings(self):
        self._repo_db()
        self.assertEqual(setup.detect_findings(self.repo, self.home, explicit_db="/tmp/x.db"), [])

    def test_repo_resources_without_db_are_a_finding(self):
        (self.repo / PLAN_DIR / "templates").mkdir(parents=True)
        state = setup.SetupState(placement=setup.HOME)
        kinds = [f.kind for f in setup.detect_findings(self.repo, self.home, state)]
        self.assertIn("repo-resources", kinds)

    def test_legacy_per_agent_database_is_a_finding(self):
        legacy = self.home / ".config/opencode/skills/lazyplan/lazyplan.db"
        legacy.parent.mkdir(parents=True)
        Store(legacy)
        kinds = [f.kind for f in setup.detect_findings(self.repo, self.home)]
        self.assertIn("legacy-db", kinds)

    def test_outdated_skill_copy_is_a_finding(self):
        skill = self.home / ".agents/skills/lazyplan/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: lazyplan\n---\nold instructions\n", encoding="utf-8")
        findings = [
            f for f in setup.detect_findings(self.repo, self.home) if f.kind == "stale-skill"
        ]
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].state)


if __name__ == "__main__":
    unittest.main()
