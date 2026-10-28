"""Argument groups for system commands."""

from __future__ import annotations

import argparse


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
        action="store_true",
        default=None,
        help="install lifecycle hooks for detected agents (the default)",
    )
    setup.add_argument(
        "--no-hooks",
        dest="hooks",
        action="store_false",
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
        help="upgrade lpui itself to the latest release (pipx/venv installs)",
        parents=[common],
    )
    up.add_argument(
        "--check",
        action="store_true",
        help="only report the installed and latest versions, change nothing",
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
