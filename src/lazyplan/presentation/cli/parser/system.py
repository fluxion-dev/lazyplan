"""Argument groups for system commands."""

from __future__ import annotations

import argparse

from lazyplan.core.policies.agents import HOSTS, TIERS
from lazyplan.core.policies.lanes import AGENT_ROLES


def _role_tier(value: str) -> tuple[str, str]:
    """Parse ROLE=TIER for --agent-tier."""
    role, sep, tier = value.partition("=")
    if not sep or not role or not tier:
        raise argparse.ArgumentTypeError("expected ROLE=TIER")
    if role not in AGENT_ROLES:
        raise argparse.ArgumentTypeError(f"role must be {'|'.join(AGENT_ROLES)}")
    if tier not in TIERS:
        raise argparse.ArgumentTypeError(f"tier must be {'|'.join(TIERS)}")
    return role, tier


def _host_key(value: str, roles: bool) -> tuple[str, str, str]:
    """Parse HOST:TIER=MODEL or HOST:ROLE=MODEL."""
    key, sep, model = value.partition("=")
    host, colon, name = key.partition(":")
    if not sep or not colon or not host or not name or not model:
        label = "ROLE" if roles else "TIER"
        raise argparse.ArgumentTypeError(f"expected HOST:{label}=MODEL")
    if host not in HOSTS:
        raise argparse.ArgumentTypeError(f"host must be {'|'.join(HOSTS)}")
    allowed = AGENT_ROLES if roles else TIERS
    if name not in allowed:
        label = "role" if roles else "tier"
        raise argparse.ArgumentTypeError(f"{label} must be {'|'.join(allowed)}")
    return host, name, model


def _tier_model(value: str) -> tuple[str, str, str]:
    return _host_key(value, roles=False)


def _role_model(value: str) -> tuple[str, str, str]:
    return _host_key(value, roles=True)


def add_setup(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    setup = sub.add_parser(
        "setup",
        help="re-run setup: where plans live, which agents get the skill, and layout review",
        parents=[common],
    )
    setup.add_argument(
        "--placement",
        choices=["home", "repo"],
        default="",
        help="store plans in your home or in this repo (repo needs a git checkout)",
    )
    setup.add_argument(
        "--agents",
        default="",
        metavar="LIST",
        help="which agents to install for (space/comma list, 'all', or 'none')",
    )
    setup.add_argument(
        "--agent-tier",
        action="append",
        type=_role_tier,
        default=[],
        metavar="ROLE=TIER",
        help="set one role's tier (fast, standard, deep); repeatable",
    )
    setup.add_argument(
        "--tier-model",
        action="append",
        type=_tier_model,
        default=[],
        metavar="HOST:TIER=MODEL",
        help="set one host's model for a tier; repeatable",
    )
    setup.add_argument(
        "--role-model",
        action="append",
        type=_role_model,
        default=[],
        metavar="HOST:ROLE=MODEL",
        help="override one host model for a role; repeatable",
    )
    setup.add_argument(
        "--no-model-review",
        dest="model_review",
        action="store_false",
        default=True,
        help="keep the current model map without asking",
    )
    setup.add_argument(
        "--skills-dir",
        default=None,
        metavar="PATH",
        help="put the skill in this folder instead of the detected ones",
    )
    setup.add_argument(
        "--no-skills",
        action="store_true",
        help="skip installing agent helper files",
    )
    setup.add_argument(
        "--hooks",
        dest="hooks",
        nargs="?",
        const="strict",
        default=None,
        choices=["strict", "advisory", "off"],
        metavar="MODE",
        help="install lifecycle hooks in strict (default), advisory, or off mode",
    )
    setup.add_argument(
        "--no-hooks",
        dest="hooks",
        action="store_const",
        const="off",
        help="remove installed lifecycle hooks and leave agent configs alone",
    )
    setup.add_argument(
        "--agents-pointer",
        dest="agents_pointer",
        action="store_true",
        default=None,
        help="add a marked lazyplan section to this repo's AGENTS.md",
    )
    setup.add_argument(
        "--no-agents-pointer",
        dest="agents_pointer",
        action="store_false",
        help="remove the marked lazyplan section from AGENTS.md",
    )
    setup.add_argument(
        "--yes",
        action="store_true",
        help="apply the current choices without asking",
    )
    setup.add_argument(
        "--post-upgrade",
        action="store_true",
        help=argparse.SUPPRESS,
    )


def add_seed(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "seed", help="add demo data: one plan with milestones and tasks", parents=[common]
    )


def add_info(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "info",
        help="show which database file is in use, the repo root, and how many plans, milestones, and tasks you have",
        parents=[common],
    )


def add_doctor(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "doctor",
        help="read-only report of the resolved setup layout and findings",
        parents=[common],
    )


def add_completion(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    c = sub.add_parser("completion", help="print tab-completions for your shell", parents=[common])
    c.add_argument(
        "--shell", choices=["bash", "zsh"], required=True, help="which shell you use (required)"
    )


def add_upgrade(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    up = sub.add_parser(
        "upgrade",
        help="upgrade lpui itself to the latest release (pipx/uv/venv installs)",
        parents=[common],
    )
    up.add_argument(
        "--check",
        action="store_true",
        help="only report the installed and latest versions, change nothing",
    )
    up.add_argument(
        "--diagnose",
        action="store_true",
        help="print install and update paths, change nothing",
    )


def add_notes(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    notes = sub.add_parser(
        "notes",
        help="print the release notes bundled with this version (works offline)",
        parents=[common],
    )
    scope = notes.add_mutually_exclusive_group()
    scope.add_argument(
        "--all",
        action="store_true",
        help="show every bundled release, newest first",
    )
    scope.add_argument(
        "--since",
        default="",
        metavar="VERSION",
        help="show releases newer than VERSION through the installed one",
    )


def add_choose(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    choose = sub.add_parser(
        "choose",
        help="serve a local page of image choices and record the pick",
        parents=[common],
    )
    choose.add_argument(
        "--manifest",
        required=True,
        metavar="PATH",
        help="choices JSON file with 2-12 image options",
    )
    choose.add_argument(
        "--out",
        default="",
        metavar="PATH",
        help="selection file (default: selection.json beside the manifest)",
    )
    choose.add_argument(
        "--port",
        type=int,
        default=0,
        metavar="PORT",
        help="loopback port (0 picks a free one)",
    )
    choose.add_argument(
        "--open",
        action="store_true",
        help="open the page in the browser",
    )
    choose.add_argument(
        "--force",
        action="store_true",
        help="replace an existing selection file",
    )


def add_help(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "help", help="show the screen's key bindings (same as ? in the app)", parents=[common]
    )


def add_ui(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "ui",
        help="open the keyboard-driven screen (this runs when you give no command)",
        parents=[common],
    )
