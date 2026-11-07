"""Heal mode resolution: flags win over the environment, then safe."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from lazyplan.infrastructure import settings
from lazyplan.presentation.cli.parser import build_parser


class TestHealMode(unittest.TestCase):
    def test_default_is_safe(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LAZYPLAN_HEAL", None)
            self.assertEqual(settings.heal_mode(), settings.HEAL_SAFE)

    def test_environment_modes(self):
        for value in ("off", "safe", "strict"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"LAZYPLAN_HEAL": value}):
                self.assertEqual(settings.heal_mode(), value)

    def test_invalid_environment_falls_back_to_safe(self):
        with mock.patch.dict(os.environ, {"LAZYPLAN_HEAL": "loud"}):
            self.assertEqual(settings.heal_mode(), settings.HEAL_SAFE)

    def test_flag_overrides_environment(self):
        with mock.patch.dict(os.environ, {"LAZYPLAN_HEAL": "strict"}):
            self.assertEqual(settings.heal_mode(False), settings.HEAL_OFF)
            self.assertEqual(settings.heal_mode(True), settings.HEAL_SAFE)


class TestHealFlags(unittest.TestCase):
    def test_flags_parse_after_the_command(self):
        parser = build_parser()
        off = parser.parse_args(["reconcile", "--no-heal"])
        on = parser.parse_args(["task", "move", "--id", "1", "--to", "done", "--heal"])
        self.assertFalse(off.heal)
        self.assertTrue(on.heal)

    def test_flags_are_mutually_exclusive(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["reconcile", "--heal", "--no-heal"])
