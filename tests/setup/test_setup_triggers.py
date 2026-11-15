"""The wizard trigger reports each reason and remembers completion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.presentation.setup import triggers
from lazyplan.presentation.setup.state import SetupState, load_state
from tests.support.home import sandbox_home


class TriggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fresh_state_is_due_for_a_first_run(self) -> None:
        self.assertEqual(triggers.pending_reason(SetupState(), "1.0"), triggers.FRESH)

    def test_existing_state_without_a_completed_wizard_is_due(self) -> None:
        state = SetupState(last_version="0.9")
        self.assertEqual(triggers.pending_reason(state, "1.0"), triggers.VERSION)

    def test_a_new_version_is_due(self) -> None:
        state = SetupState(last_version="0.9", wizard_completed="0.9")
        self.assertEqual(triggers.pending_reason(state, "1.0"), triggers.VERSION)

    def test_live_probes_report_integrations_before_drift(self) -> None:
        state = SetupState(last_version="1.0", wizard_completed="1.0")
        reason = triggers.pending_reason(
            state,
            "1.0",
            pending_integrations=True,
            profile_drift=True,
        )
        self.assertEqual(reason, triggers.INTEGRATIONS)
        only_drift = triggers.pending_reason(state, "1.0", profile_drift=True)
        self.assertEqual(only_drift, triggers.PROFILES)

    def test_a_remembered_marker_wins(self) -> None:
        state = SetupState(wizard_pending=triggers.INTEGRATIONS, wizard_completed="1.0")
        self.assertEqual(triggers.pending_reason(state, "1.0"), triggers.INTEGRATIONS)

    def test_unknown_markers_normalize_to_a_version_reason(self) -> None:
        state = SetupState(wizard_pending="someday", wizard_completed="1.0")
        self.assertEqual(triggers.pending_reason(state, "1.0"), triggers.VERSION)

    def test_mark_and_clear_round_trip_through_state(self) -> None:
        state = SetupState(last_version="0.9", wizard_completed="0.9")
        triggers.mark_pending(state, triggers.VERSION, "1.0", self.home)
        saved = load_state(self.home)
        self.assertEqual(saved.wizard_pending, triggers.VERSION)
        self.assertEqual(saved.wizard_version, "1.0")
        triggers.clear_pending(saved, "1.0", self.home)
        cleared = load_state(self.home)
        self.assertEqual(cleared.wizard_pending, "")
        self.assertEqual(cleared.wizard_version, "")
        self.assertEqual(cleared.wizard_completed, "1.0")

    def test_detect_requested_reason_needs_no_probe(self) -> None:
        need = triggers.detect(self.home, self.home, "1.0", requested=True)
        self.assertTrue(need.due)
        self.assertEqual(need.reason, triggers.REQUEST)

    def test_detect_uses_live_probes_for_a_completed_version(self) -> None:
        state = SetupState(last_version="1.0", wizard_completed="1.0")
        with mock.patch.object(triggers, "_pending_items", return_value=("item",)):
            need = triggers.detect(self.home, self.home, "1.0", state)
        self.assertEqual(need.reason, triggers.INTEGRATIONS)
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=True),
        ):
            need = triggers.detect(self.home, self.home, "1.0", state)
        self.assertEqual(need.reason, triggers.PROFILES)

    def test_detect_is_quiet_when_nothing_is_due(self) -> None:
        state = SetupState(last_version="1.0", wizard_completed="1.0")
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
        ):
            need = triggers.detect(self.home, self.home, "1.0", state)
        self.assertFalse(need.due)
        self.assertFalse((self.home / ".lazyplan" / "setup.json").exists())

    def test_detect_never_writes(self) -> None:
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
        ):
            triggers.detect(self.home, self.home, "1.0")
        self.assertFalse((self.home / ".lazyplan").exists())
