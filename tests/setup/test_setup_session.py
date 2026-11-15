"""The setup session builds a draft without writes and applies one choice."""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from lazyplan.presentation.setup import session as session_module
from tests.support.home import sandbox_home


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {host: HostCatalog(host=host, label=host.title()) for host in hosts}


class SetupSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def load(self) -> setup.SetupSession:
        return setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)

    def test_loading_writes_nothing(self) -> None:
        before = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        session = self.load()
        after = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        self.assertEqual(before, after)
        self.assertTrue(session.steps())

    def test_steps_hide_models_without_agents(self) -> None:
        session = self.load()
        session.set_agents([])
        keys = [step.key for step in session.steps()]
        self.assertNotIn("models", keys)
        self.assertNotIn("roles", keys)
        self.assertIn("agents", keys)

    def test_steps_include_repo_placement_and_models_for_a_lane(self) -> None:
        session = self.load()
        session.set_agents(["opencode"])
        keys = [step.key for step in session.steps()]
        self.assertIn("placement", keys)
        self.assertIn("models", keys)
        self.assertIn("roles", keys)

    def test_choice_round_trips_draft_values(self) -> None:
        session = self.load()
        session.set_agents(["opencode"])
        session.set_skills_enabled(True)
        session.set_role_tier("reviewer", "standard")
        session.set_role_effort("reviewer", "high")
        session.set_tier_model("opencode", "fast", "provider/tiny")
        session.set_role_model("scout", "opencode", "provider/scout")
        choice = session.choice()
        self.assertEqual(choice.agents, ["opencode"])
        self.assertEqual(choice.profiles_map["reviewer"].tier, "standard")
        self.assertEqual(choice.profiles_map["reviewer"].effort, "high")
        self.assertEqual(choice.tiers_map["fast"]["opencode"], "provider/tiny")
        self.assertEqual(choice.profiles_map["scout"].models["opencode"], "provider/scout")
        self.assertFalse(choice.no_skills)

    def test_agents_keep_registry_order(self) -> None:
        session = self.load()
        session.set_agents(["claude", "opencode"])
        self.assertEqual(session.draft.agents, ["opencode", "claude"])

    def test_remembered_state_seeds_the_draft(self) -> None:
        state = setup.SetupState(
            placement="home",
            agents=["claude"],
            hooks_mode="advisory",
            agents_pointer=True,
        )
        session = setup.SetupSession.load(self.repo, self.home, "1.0", state, discover=_catalogs)
        self.assertEqual(session.draft.agents, ["claude"])
        self.assertEqual(session.draft.hooks_mode, "advisory")
        self.assertTrue(session.draft.agents_pointer)

    def test_validation_names_bad_values(self) -> None:
        session = self.load()
        session.set_agents(["opencode"])
        session.set_hooks_mode("sometimes")
        errors = session.validate()
        self.assertTrue(any("hooks mode" in error for error in errors))
        with self.assertRaises(setup.SetupSessionError):
            session.set_integration("missing", "install")

    def test_repo_placement_needs_a_checkout(self) -> None:
        bare = Path(self.tmp.name) / "bare"
        bare.mkdir()
        session = setup.SetupSession.load(bare, self.home, "1.0", discover=_catalogs)
        session.set_placement("repo")
        self.assertTrue(any("git checkout" in error for error in session.validate()))

    def test_apply_writes_through_the_shared_path(self) -> None:
        session = self.load()
        session.set_placement("home")
        session.set_agents(["opencode"])
        session.set_hooks_mode("off")
        for item in session.pending:
            session.set_integration(item.id, "defer")
        result = session.apply()
        self.assertTrue(Path(result["db"]).is_file())
        self.assertTrue((self.home / ".lazyplan" / "setup.json").is_file())
        profile = self.home / ".config" / "opencode" / "agent" / "lazyplan-implementer.md"
        self.assertTrue(profile.is_file())

    def test_invalid_draft_refuses_to_apply(self) -> None:
        session = self.load()
        session.set_agents(["opencode"])
        session.set_hooks_mode("sometimes")
        with self.assertRaises(setup.SetupSessionError):
            session.apply()

    def test_layout_root_is_none_outside_a_checkout(self) -> None:
        self.assertIsNone(session_module.layout_root(Path(self.tmp.name) / "outside"))

    def test_an_old_state_file_without_wizard_fields_loads(self) -> None:
        state_dir = self.home / ".lazyplan"
        state_dir.mkdir()
        (state_dir / "setup.json").write_text(
            json.dumps({"version": 1, "placement": "home", "agents": ["opencode"]}),
            encoding="utf-8",
        )
        session = self.load()
        self.assertEqual(session.draft.agents, ["opencode"])
        self.assertEqual(session.draft.theme, "")

    def test_second_apply_keeps_managed_files_byte_identical(self) -> None:
        session = self.load()
        session.set_placement("home")
        session.set_agents(["opencode"])
        session.set_hooks_mode("off")
        for item in session.pending:
            session.set_integration(item.id, "defer")
        session.apply()
        mapping = self.home / ".lazyplan" / "agents.json"
        profile = self.home / ".config" / "opencode" / "agent" / "lazyplan-implementer.md"
        before = (mapping.read_bytes(), profile.read_bytes())
        session.apply()
        self.assertEqual((mapping.read_bytes(), profile.read_bytes()), before)

    def test_session_apply_matches_the_terminal_choice_files(self) -> None:
        other = Path(self.tmp.name) / "other-home"
        other.mkdir()
        session = self.load()
        session.set_placement("home")
        session.set_agents(["opencode"])
        session.set_hooks_mode("off")
        for item in session.pending:
            session.set_integration(item.id, "defer")
        session.apply()
        setup.apply_choice(session.choice(), None, other, "1.0")
        self.assertEqual(
            (self.home / ".lazyplan" / "agents.json").read_bytes(),
            (other / ".lazyplan" / "agents.json").read_bytes(),
        )
        for name in ("lazyplan-implementer.md", "lazyplan-reviewer.md"):
            relative = Path(".config") / "opencode" / "agent" / name
            self.assertEqual(
                (self.home / relative).read_bytes(),
                (other / relative).read_bytes(),
            )


class SetupWriterSeamTest(unittest.TestCase):
    """The TUI is a front end: one session, one writer, one trigger."""

    TUI = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "presentation" / "tui"

    def read(self, relative: str) -> str:
        return (self.TUI / relative).read_text(encoding="utf-8")

    def test_the_wizard_never_calls_a_setup_writer_directly(self) -> None:
        for relative in ("screens/setup.py", "controllers/setup.py"):
            source = self.read(relative)
            for writer in ("apply_choice(", "install_integrations(", "install_items("):
                with self.subTest(module=relative, writer=writer):
                    self.assertNotIn(writer, source)
        self.assertIn("session.apply(", self.read("screens/setup.py"))

    def test_one_screen_construction_and_one_trigger_source(self) -> None:
        controller = self.read("controllers/setup.py")
        self.assertEqual(controller.count("SetupWizardScreen("), 1)
        self.assertEqual(controller.count("from ...setup.triggers import"), 1)
        self.assertIn("detect(", controller)
