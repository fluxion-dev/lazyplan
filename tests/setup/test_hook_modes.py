"""Hook mode precedence: environment, explicit flag, then remembered state."""

import unittest

from lazyplan.core.policies import hooks
from lazyplan.presentation.cli.parser import build_parser


class ModeCase(unittest.TestCase):
    def test_normalize_rejects_unknown_modes(self):
        self.assertEqual(hooks.normalize_mode("strict"), "strict")
        self.assertEqual(hooks.normalize_mode("ADVISORY"), "advisory")
        self.assertEqual(hooks.normalize_mode("loud"), "strict")
        self.assertEqual(hooks.normalize_mode(None), "strict")

    def test_flag_beats_environment_and_state(self):
        environ = {hooks.MODE_ENV: "advisory"}
        self.assertEqual(hooks.resolve_mode("strict", "advisory", environ), "strict")

    def test_environment_beats_state(self):
        environ = {hooks.MODE_ENV: "advisory"}
        self.assertEqual(hooks.resolve_mode(None, "strict", environ), "advisory")

    def test_stored_mode_is_the_last_resort(self):
        self.assertEqual(hooks.resolve_mode(None, "advisory", {}), "advisory")

    def test_no_hooks_env_wins_everything(self):
        environ = {hooks.NO_HOOKS_ENV: "1", hooks.MODE_ENV: "advisory"}
        self.assertEqual(hooks.resolve_mode("strict", "strict", environ), "off")

    def test_false_flag_means_off(self):
        self.assertEqual(hooks.resolve_mode(False, "strict", {}), "off")

    def test_setup_flag_accepts_a_mode(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["setup", "--hooks"]).hooks, "strict")
        self.assertEqual(parser.parse_args(["setup", "--hooks", "advisory"]).hooks, "advisory")
        self.assertEqual(parser.parse_args(["setup", "--no-hooks"]).hooks, "off")
        self.assertIsNone(parser.parse_args(["setup"]).hooks)

    def test_hook_command_carries_a_mode(self):
        parser = build_parser()
        args = parser.parse_args(["hook", "stop", "--host", "claude", "--mode", "advisory"])
        self.assertEqual(args.mode, "advisory")


if __name__ == "__main__":
    unittest.main()
