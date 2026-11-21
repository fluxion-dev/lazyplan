# lazyplan (`lpui`) — v0.51.1

[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/fluxion-dev/lazyplan/blob/main/LICENSE)

Plan work with your coding agent, in the terminal.

lazyplan is one shared plan for you and your agent. You get a fast keyboard
screen; the agent gets a plain command line. Plans, milestones, and tasks live
in one local database instead of disappearing into chat, and read-only git and
pull-request provenance shows where each one landed. A plan can start as a
draft, take anchored review notes, and only then join the queue.

**[Screenshots and quickstart →](https://fluxion-dev.github.io/lazyplan/)**

## Install

```bash
uv tool install lazyplan-tui
# or
pipx install lazyplan-tui

lpui --help
```

Both installs are isolated and self-update with `lpui upgrade`. If `lpui` is
not on PATH, run `uv tool update-shell` after a uv install or `pipx ensurepath`
after a pipx install, then open a new terminal.

On Windows, use the pip backend for pipx:

```powershell
pipx install --backend pip lazyplan-tui
lpui --version
```

`uvx --from lazyplan-tui lpui` runs the latest release without installing it.
The PyPI project is `lazyplan-tui`; the commands are `lpui` and `lazyplan`.

Upgrading from 0.30.1 or earlier? Reinstall with force, because the package
layout changed: `uv tool install --force lazyplan-tui`,
`pipx install --force lazyplan-tui`, or
`python -m pip install --force-reinstall lazyplan-tui`. See the
[upgrade notes](docs/usage.md#upgrade).

For system packages, the one-line installer, or installs from source, see
[install options](docs/usage.md#install).

## First run

```bash
cd ~/my-plan
lpui                     # applies setup, then opens the setup wizard
lpui plan add --title "my-plan" --why "reason" --what "scope"
lpui
```

The first `lpui` applies a baseline setup, then opens a wizard before normal
use. **Finish later** writes nothing, and `S` reopens the wizard from any
screen; a run without a terminal, or with `--json` or `--yes`, applies the same
defaults without asking. See [setup and scope](docs/usage.md#setup-and-scope)
for the steps.

Keep the plan in the repo with `lpui setup --placement repo`, or try the demo
data with `lpui seed`.

## Why it differs

- **One source of truth.** The plan you see is the plan your agent reads. No
  copy-pasting context between chats.
- **Reviewed, not rubber-stamped.** A plan starts as a short sketch — why, what,
  and acceptance criteria. The human leaves anchored comments, questions, and
  change requests; the agent revises against them, then derives the milestones
  and tasks without changing the reviewed definition. Promotion is refused
  while feedback is open or a sketch is unformalized.
- **Made for focus.** Plans stay as one-line summaries until you open them,
  branches stay open or closed exactly as you left them, large branches load on
  demand, and the timeline waits for `T`. Three themes and five icon palettes
  keep the screen yours.
- **Proof where you need it.** Criteria, evidence, questions, references,
  claims, agents, comments, commits, and pull requests are selectable hubs,
  not a wall of text.
- **Yours to keep.** Local-first by default. Export or import any time. No
  account, no cloud, no lock-in.

## Everyday commands

```bash
lpui list                         # plans and progress
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing  # move work forward
lpui criterion edit --id 1 --done # mark an acceptance item done
lpui feed                         # recent activity
```

The bottom bar pins the running version, with an arrow beside it when a newer
release is cached; click the badge or press `U` to update. Ordinary notices
collect in a session log (`L`) instead of stacking as toasts; only the startup
and update notices interrupt.

## For your agent

The first run installs the agent skills. Agents read and write the same plan
through the CLI, using `--porcelain` for terse rows and `--json` for full
fidelity:

```bash
lpui --actor helper --porcelain next
lpui --actor helper --porcelain context --max-chars 4000
lpui --actor helper --porcelain draft sketch --file sketch.md
lpui --actor helper --porcelain draft wait --id 1
lpui --actor helper --porcelain draft formalize --id 1 --file plan.json --base-revision 2
lpui --actor helper --porcelain draft promote --id 1
```

New plans start as definition-only sketches outside the queue. The human
annotates the sketch in the review screen, each saved annotation wakes the agent
running `draft wait`, and `draft formalize` supplies the milestones and tasks
without rewriting the reviewed title, why, what, or criteria. Promoting the
formalized draft creates the plan tree atomically once every annotation is
answered.

Parallel plans are lanes: a milestone gets a wave, a role, and its own
registered worktree, and roles name a capability tier and an effort level.
[Agent profiles](docs/usage.md#agent-profiles) and [lanes and
waves](docs/usage.md#lanes-and-waves) cover the model map and the worktree
commands; `lpui dispatch --plan P` prints the waves, worktrees, and one worker
prompt per ready task.

See the [agent contract](docs/usage.md#agents) for claims, agents, evidence,
and MCP. For your data, back up with `lpui export --format json` and restore
with `lpui import --file`; see [data and backup](docs/usage.md#data-and-backup).

## Learn more

- [Usage and CLI reference](docs/usage.md)
- [Information architecture](docs/information-architecture/spec.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) (main is protected; open a PR)
- [Screenshots](https://fluxion-dev.github.io/lazyplan/)
- [Releases](https://github.com/fluxion-dev/lazyplan/releases) ·
  [Issues](https://github.com/fluxion-dev/lazyplan/issues)

MIT licensed. This repo plans itself: run `lpui list`.
