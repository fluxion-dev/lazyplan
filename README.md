# lazyplan (`lpui`) — v0.35.0

[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/fluxion-dev/lazyplan/blob/main/LICENSE)

Plan work with your coding agent, in the terminal.

lazyplan is one shared plan for you and your agent. You get a fast keyboard
screen; the agent gets a plain command line. Plans, milestones, and tasks live
in one local database instead of disappearing into chat, and read-only git and
pull-request provenance shows where each one landed.

**[Screenshots and quickstart →](https://fluxion-dev.github.io/lazyplan/)**

## Install

```bash
pipx install lazyplan-tui
lpui --help
```

On Windows, use the pip backend:

```powershell
pipx install --backend pip lazyplan-tui
lpui --version
```

Upgrading from 0.30.1 or earlier? Reinstall with force, because the package
layout changed: `pipx install --force lazyplan-tui` (or
`python -m pip install --force-reinstall lazyplan-tui`). See the
[upgrade notes](docs/usage.md#upgrade).

For system packages, the one-line installer, or installs from source, see
[install options](docs/usage.md#install).

## First run

```bash
cd ~/my-plan
lpui                     # detects agents and creates the plan store
lpui plan add --title "my-plan" --why "reason" --what "scope"
lpui
```

Keep the plan in the repo with `lpui setup --placement repo`, or try the demo
data with `lpui seed`.

## Why it differs

- **One source of truth.** The plan you see is the plan your agent reads. No
  copy-pasting context between chats.
- **Made for focus.** Plans stay as one-line summaries until you open them.
  Detail is there when you need it.
- **Yours to keep.** Local-first by default. Export or import any time. No
  account, no cloud, no lock-in.

## The screen

The screen is a control room: it opens on what needs you, with attention rows,
open questions, drift, stale claims, and the last handoff. It is read-only by
default; press `O` for Manual override mode when you want deliberate writes.
The palette splits reads and writes as Observe and Override.

## Everyday commands

```bash
lpui list                         # plans and progress
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing  # move work forward
lpui criterion tick --id 1        # tick the next acceptance item
lpui feed                         # recent activity
```

## For your agent

The first run installs the agent skill. Agents read and write the same plan
through the CLI, using `--porcelain` for terse rows and `--json` for full
fidelity:

```bash
lpui --actor helper --porcelain next
lpui --actor helper --porcelain context --max-chars 4000
lpui plan recipe feature > plan.json
lpui --actor helper --porcelain plan apply --file plan.json
```

See the [agent contract](docs/usage.md#agents) for claims, sessions, evidence,
and MCP. For your data, back up with `lpui export --format json` and restore
with `lpui import --file`; see [data and backup](docs/usage.md#data-and-backup).

## Learn more

- [Usage and CLI reference](docs/usage.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) (main is protected; open a PR)
- [Screenshots](https://fluxion-dev.github.io/lazyplan/)
- [Releases](https://github.com/fluxion-dev/lazyplan/releases) ·
  [Issues](https://github.com/fluxion-dev/lazyplan/issues)

MIT licensed. This repo plans itself: run `lpui list`.
