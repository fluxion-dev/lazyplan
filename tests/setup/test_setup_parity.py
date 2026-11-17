"""Parity: the terminal choice and the wizard write the same setup.

Each case builds one non-default choice, applies it through the CLI's
``apply_choice`` pipeline, snapshots every file setup owns, then resets the
sandbox and applies the same choice through ``SetupSession.apply`` (and once
through the real wizard screen). The snapshots must match byte for byte, and
the remembered decisions must agree.

The sandbox is reset instead of duplicated so absolute paths stay identical;
a second home would otherwise differ in every file that names the database.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from lazyplan.presentation.setup import integrations as integrations_module
from tests.support.home import sandbox_home
from tests.support.sqlite_state import quiesce

try:
    from textual.widgets import Button

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

VERSION = "1.0"

#: Files whose bytes depend on the clock, the sqlite page layout, or the app's
#: update gate rather than the setup choice.
VOLATILE = frozenset(
    {
        "setup.json",
        "lazyplan.db",
        "lazyplan.db-wal",
        "lazyplan.db-shm",
        "lazyplan.db-journal",
        "update.json",
        "update-gate.json",
    }
)

#: setup.json records verbs; the wizard draft records the action it took.
_DECISION_WORDS = {"installed": "install", "deferred": "defer", "never": "never"}

#: State fields that describe a choice rather than a path or a timestamp.
DECISION_FIELDS = (
    "placement",
    "agents",
    "skills_enabled",
    "hooks_mode",
    "hooks_enabled",
    "agents_pointer",
    "theme",
)


def _catalogs(
    hosts: Iterable[str],
    _home: Path,
    _root: Path | None,
) -> dict[str, HostCatalog]:
    """Offline catalogs with real tier defaults; no host binary runs."""
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=("tiny-model", "large-model"),
            tier_defaults={
                "fast": "tiny-model",
                "standard": "tiny-model",
                "deep": "large-model",
            },
        )
        for host in hosts
    }


def _decisions(pending: Iterable[Any]) -> dict[str, str]:
    """Install the first item, defer the second, never ask for the rest."""
    ids = sorted(item.id for item in pending)
    picks = {item_id: "install" for item_id in ids[:1]}
    picks.update({item_id: "defer" for item_id in ids[1:2]})
    picks.update({item_id: "never" for item_id in ids[2:]})
    return picks


class SetupParityCase(unittest.IsolatedAsyncioTestCase):
    """One non-default choice, applied twice in the same sandbox."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.repo = self.base / "repo"
        self.reset()
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def reset(self) -> None:
        """Put the sandbox back to its just-created shape."""
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)
        self.home.mkdir(parents=True)
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()

    def session(self, placement: str) -> setup.SetupSession:
        session = setup.SetupSession.load(
            self.repo,
            self.home,
            VERSION,
            discover=_catalogs,
        )
        session.set_placement(placement)
        session.set_agents(["claude"])
        session.set_hooks_mode("advisory")
        session.draft.agents_pointer = True
        session.set_role_tier("reviewer", "deep")
        session.set_role_effort("scout", "low")
        session.set_role_effort("reviewer", "high")
        session.set_tier_model("claude", "fast", "tiny-model")
        session.set_tier_model("claude", "deep", "large-model")
        for item_id, decision in _decisions(session.pending).items():
            session.set_integration(item_id, decision)
        return session

    def snapshot(self) -> dict[str, bytes]:
        """Every file setup owns, keyed by its sandbox-relative path."""
        quiesce(self.base)
        roots = (self.home, self.repo)
        files: dict[str, bytes] = {}
        for root in roots:
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                if path.name in VOLATILE or "backups" in relative.parts:
                    continue
                key = f"{root.name}/{relative.as_posix()}"
                data = path.read_bytes()
                if path.name == "config.json":
                    payload = json.loads(data)
                    payload["created"] = ""
                    data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
                files[key] = data
        return files

    def decisions(self) -> dict[str, Any]:
        """The remembered choices, without paths or timestamps."""
        state = setup.load_state(self.home)
        picked = {field: getattr(state, field) for field in DECISION_FIELDS}
        picked["integrations"] = {
            item_id: _DECISION_WORDS.get(str(value.get("decision", "")), "unknown")
            for item_id, value in sorted(state.integration_choices.items())
        }
        return picked

    def terminal_apply(self, placement: str) -> tuple[dict[str, Any], dict[str, str]]:
        """The CLI's non-interactive pipeline for the same choice."""
        session = self.session(placement)
        choice = session.choice()
        picks = _decisions(session.pending)
        result = setup.apply_choice(choice, session.root, self.home, VERSION)
        setup.install_integrations(
            result,
            self.home,
            session.root,
            session.draft.hooks_mode,
            session.draft.agents_pointer,
        )
        state = setup.load_state(self.home)
        groups: dict[str, list[Any]] = {"install": [], "defer": [], "never": []}
        for item in session.pending:
            groups[picks.get(item.id, "install")].append(item)
        if groups["install"]:
            result["integrations"] = integrations_module.install_items(
                tuple(groups["install"]),
                choice,
                state,
                session.root,
                self.home,
                VERSION,
            ).to_dict()
        integrations_module.remember_decisions(
            tuple(groups["defer"]),
            setup.load_state(self.home),
            "deferred",
            VERSION,
            self.home,
        )
        integrations_module.remember_decisions(
            tuple(groups["never"]),
            setup.load_state(self.home),
            "never",
            VERSION,
            self.home,
        )
        return result, picks

    def wizard_apply(self, placement: str) -> dict[str, Any]:
        """The TUI session path for the same choice."""
        session = self.session(placement)
        return session.apply()

    def assert_same_setup(self, placement: str) -> None:
        _result, picks = self.terminal_apply(placement)
        terminal_files = self.snapshot()
        terminal_decisions = self.decisions()

        self.reset()
        self.wizard_apply(placement)
        self.assert_matches(
            terminal_files,
            terminal_decisions,
            self.snapshot(),
            self.decisions(),
            placement,
            picks,
        )

    def assert_matches(
        self,
        terminal_files: dict[str, bytes],
        terminal_decisions: dict[str, Any],
        wizard_files: dict[str, bytes],
        wizard_decisions: dict[str, Any],
        placement: str,
        picks: dict[str, str],
    ) -> None:
        """Both paths wrote the same bytes and remembered the same decisions."""
        self.assertEqual(sorted(wizard_files), sorted(terminal_files))
        for name in sorted(terminal_files):
            with self.subTest(file=name):
                self.assertEqual(wizard_files[name], terminal_files[name])
        self.assertEqual(wizard_decisions, terminal_decisions)

        # The parity assertion is only meaningful when both sides wrote the
        # artifacts the criterion names.
        root = "repo" if placement == "repo" else "home"
        self.assertTrue(any(name.endswith("/agents.json") for name in wizard_files))
        self.assertIn("home/.claude/settings.json", wizard_files)
        self.assertIn(f"{root}/.claude/skills/lazyplan/SKILL.md", wizard_files)
        self.assertIn(f"{root}/.claude/agents/lazyplan-scout.md", wizard_files)
        self.assertEqual(wizard_decisions["agents"], ["claude"])
        self.assertEqual(wizard_decisions["hooks_mode"], "advisory")
        if placement == "home":
            self.assertTrue(wizard_decisions["agents_pointer"])
        else:
            # Repo placement always writes the pointer as part of the plan,
            # so only the home-placement toggle is remembered as a choice.
            self.assertFalse(wizard_decisions["agents_pointer"])
        self.assertIn("repo/AGENTS.md", wizard_files)
        self.assertEqual(wizard_decisions["integrations"], picks)
        self.assertEqual(set(picks.values()), {"install", "defer", "never"})

        mapping_name = next(name for name in wizard_files if name.endswith("/agents.json"))
        mapping = json.loads(wizard_files[mapping_name])
        self.assertEqual(mapping["profiles"]["scout"]["tier"], "fast")
        self.assertEqual(mapping["profiles"]["scout"]["effort"], "low")
        self.assertEqual(mapping["profiles"]["reviewer"]["tier"], "deep")
        self.assertEqual(mapping["profiles"]["reviewer"]["effort"], "high")
        self.assertEqual(mapping["tiers"]["fast"]["claude"], "tiny-model")
        self.assertEqual(mapping["tiers"]["deep"]["claude"], "large-model")

    def test_snapshot_ignores_a_transient_sqlite_journal(self) -> None:
        transient = self.home / ".lazyplan" / "lazyplan.db-journal"
        transient.parent.mkdir(parents=True)
        transient.write_text("transient", encoding="utf-8")
        self.assertNotIn("home/.lazyplan/lazyplan.db-journal", self.snapshot())
        extra = self.home / ".lazyplan" / "real.txt"
        extra.write_text("kept", encoding="utf-8")
        self.assertIn("home/.lazyplan/real.txt", self.snapshot())


class HomePlacementParityTest(SetupParityCase):
    def test_the_wizard_and_the_terminal_choice_agree(self) -> None:
        self.assert_same_setup("home")


class RepoPlacementParityTest(SetupParityCase):
    def test_the_wizard_and_the_terminal_choice_agree(self) -> None:
        self.assert_same_setup("repo")


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class WizardScreenParityTest(SetupParityCase):
    async def test_the_real_screen_matches_the_terminal_choice(self) -> None:
        _result, picks = self.terminal_apply("home")
        terminal_files = self.snapshot()
        terminal_decisions = self.decisions()

        self.reset()
        session = self.session("home")
        app = create_app(str(self.base / "screen.db"))
        async with app.run_test(size=(120, 40)) as pilot:
            screen = SetupWizardScreen(session, start="review")
            app.push_screen(screen, lambda _result: None)
            for _ in range(40):
                if app.screen is screen:
                    break
                await pilot.pause(0.05)
            self.assertIs(app.screen, screen)
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()
            screen.query_one("#setup-next", Button).press()
            for _ in range(40):
                if Path(session.db_path).is_file():
                    break
                await pilot.app.workers.wait_for_complete()
                await pilot.pause(0.05)
            self.assertTrue(Path(session.db_path).is_file())
            await pilot.press("l")
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()

        self.assert_matches(
            terminal_files,
            terminal_decisions,
            self.snapshot(),
            self.decisions(),
            "home",
            picks,
        )
