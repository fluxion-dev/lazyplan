"""Shared setup constants."""

SETUP_VERSION = 1
STATE_NAME = "setup.json"
HOME = "home"
REPO = "repo"
HUMAN_COMMANDS = ("ui", "setup", "upgrade")
SKIP_COMMANDS = (
    "setup",
    "upgrade",
    "completion",
    "doctor",
    "audit",
    "brief",
    "context",
    "hook",
    "help",
    "plan-recipe",
)
NO_SETUP_ENV = "LAZYPLAN_NO_SETUP"
