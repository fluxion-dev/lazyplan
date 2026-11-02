"""Pure environment rules: versions, intervals, and wheel trust."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.environment import (
    NO_UPDATE_ENV,
    UPDATE_NETWORK_ENV,
    UPDATE_POLL_ENV,
    is_newer,
    network_interval,
    parse_version,
    poll_interval,
    update_check_enabled,
    valid_filename,
    valid_sha,
    valid_url,
    version_text,
)


class TestVersions(unittest.TestCase):
    def test_parse_and_render(self) -> None:
        self.assertEqual(parse_version("v0.30.2"), (0, 30, 2))
        self.assertEqual(version_text((0, 30, 2)), "0.30.2")

    def test_invalid_version(self) -> None:
        with self.assertRaises(ValueError):
            parse_version("newest")

    def test_newer(self) -> None:
        self.assertTrue(is_newer((0, 31, 0), (0, 30, 2)))
        self.assertFalse(is_newer((0, 30, 2), (0, 30, 2)))


class TestIntervals(unittest.TestCase):
    def test_defaults_and_override(self) -> None:
        self.assertEqual(poll_interval({}), 60.0)
        self.assertEqual(poll_interval({UPDATE_POLL_ENV: "60"}), 60.0)
        self.assertEqual(network_interval({UPDATE_NETWORK_ENV: "3600"}), 3600.0)

    def test_invalid_and_clamped(self) -> None:
        self.assertEqual(poll_interval({UPDATE_POLL_ENV: "nope"}), 60.0)
        self.assertEqual(poll_interval({UPDATE_POLL_ENV: "1"}), 5.0)

    def test_disable_flag(self) -> None:
        self.assertFalse(update_check_enabled({NO_UPDATE_ENV: "1"}))
        self.assertTrue(update_check_enabled({}))


class TestWheelTrust(unittest.TestCase):
    def test_sha(self) -> None:
        self.assertTrue(valid_sha("a" * 64))
        self.assertFalse(valid_sha("A" * 64))

    def test_filename(self) -> None:
        self.assertTrue(valid_filename("lazyplan_tui-0.30.2-py3-none-any.whl"))
        self.assertFalse(valid_filename("../evil.whl"))

    def test_url(self) -> None:
        self.assertTrue(valid_url("https://files.pythonhosted.org/x.whl", "files.pythonhosted.org"))
        self.assertFalse(valid_url("http://files.pythonhosted.org/x.whl", "files.pythonhosted.org"))


if __name__ == "__main__":
    unittest.main()
