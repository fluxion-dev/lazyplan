"""CLI agent catalog commands."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout

from lazyplan.infrastructure.agents import load_catalog
from lazyplan.presentation.cli.commands.agent import (
    _cmd_agent_add,
    _cmd_agent_list,
    _cmd_agent_remove,
)
from tests.support.home import sandbox_home


class TestAgentCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_list_and_remove(self) -> None:
        add = Namespace(
            key="claude",
            title="Claude",
            executable="claude-agent-acp",
            args=[],
            env=["CLAUDE_ENV=1"],
            default=True,
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(_cmd_agent_add(None, add, "test"), 0)
        profiles, default = load_catalog()
        self.assertEqual(default, "claude")
        self.assertEqual(profiles[-1].command, ("claude-agent-acp",))
        self.assertEqual(profiles[-1].env, {"CLAUDE_ENV": "1"})

        listing = io.StringIO()
        with redirect_stdout(listing):
            self.assertEqual(_cmd_agent_list(None, Namespace(json=True), "test"), 0)
        payload = json.loads(listing.getvalue())
        self.assertEqual([row["key"] for row in payload["agents"]], ["opencode", "claude"])

        with redirect_stdout(io.StringIO()):
            self.assertEqual(_cmd_agent_remove(None, Namespace(key="claude"), "test"), 0)
        profiles, default = load_catalog()
        self.assertEqual([profile.key for profile in profiles], ["opencode"])
        self.assertEqual(default, "opencode")

    def test_duplicate_and_last_agent_are_rejected(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(_cmd_agent_remove(None, Namespace(key="opencode"), "test"), 2)
        add = Namespace(
            key="opencode",
            title="",
            executable="opencode",
            args=["acp"],
            env=[],
            default=False,
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(_cmd_agent_add(None, add, "test"), 2)


if __name__ == "__main__":
    unittest.main()
