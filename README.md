# lazyplan (`lpui`) — v0.25.0

[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/fluxion-dev/lazyplan/blob/main/LICENSE)

Plan work with your coding agent, in the terminal.

lazyplan is one shared plan for you and your agent. You get a fast keyboard screen. Your agent gets a simple command line. Plans, milestones, and tasks stay in one place instead of disappearing into chat. Read-only git and PR provenance shows where each one landed.

**[See it in action →](https://fluxion-dev.github.io/lazyplan/#screens)**

## Install

```bash
pipx install lazyplan-tui
lpui --help
```

On Windows: `pipx install --backend pip lazyplan-tui`.

Prefer a system package or the one-line installer? See
[install options](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#install).

## Start

```bash
cd ~/my-plan
lpui                     # first run detects agents and creates the plan store
lpui plan add --title "my-plan" --why "reason" --what "scope"
lpui
```

Working with a team? `lpui setup --placement repo` keeps the plan in the repo.

Want demo data first? Run `lpui seed`.

## Why it feels different

- **One source of truth.** The plan you see is the plan your agent reads. No copy-pasting context between chats.
- **Made for focus.** Plans stay as one-line summaries until you open them. Detail is there when you need it.
- **Yours to keep.** Local-first by default. Export or import any time. No account, no cloud, no lock-in.

## What you get

- A plan tree with progress at a glance, plus milestones and tasks underneath.
- A preview of the reason, the next tasks, and what done means.
- A read-only detail page for careful reading, with quick keys to edit and move work.
- One place your agent can update while you keep the big picture.

## How it works

- Plans start as one-line summaries with progress. Open one to reveal milestones, then tasks.
- The right pane previews the selected row: why, what, next tasks, and acceptance progress.
- The bottom line shows the keys that work right now. `?` opens help; `c` opens the command palette.
- Your agent writes through the same command line. The screen updates as it works.

## Everyday commands

```bash
lpui list                         # plans and progress
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing  # move work forward
lpui criterion tick --id 1        # tick the next acceptance item
lpui feed                         # recent activity
```

## For your agent

The command line reads and writes the same plan, with porcelain rows, JSON, and
clear exit codes:

```bash
lpui --actor helper --porcelain next
lpui --actor helper --porcelain note add --kind task --id 3 --text "Decision"
lpui --actor helper --porcelain list --tree
lpui --actor helper list --json
```

Use `--porcelain` in an active loop: writes answer with one tab-separated row
and reads stay glyph-free. Use `--json` when you need full fidelity.

`next` claims the first eligible task with a renewable lease, so two agents do
not take the same work. Renew or release the claim, note handoffs, and block
parked work with a reason. Relate each plan criterion to a proving task; then
`lpui trace --plan 1` shows the evidence and `lpui lint --plan 1 --strict`
gates the gaps. After each commit, link it and move the task.
Hosts that support MCP can use `lpui mcp` for typed tools and resources;
`--read-only` is available for reviewers. `lpui stats --since 7.days` shows
WIP, cycle time, aging, stale work, and reopened rows, and the TUI Attention
filter surfaces the same risk categories. Review comments live on rows,
`lpui share --plan 1` produces a read-only snapshot, and `lpui sync` merges
plans by stable UID without overwriting conflicts. `task finish --require-pr
--require-checks` gates done on cached evidence, and branch collisions are
reported before work starts. In the screen, space marks rows for bulk
move/block/release with one undo, and `/` searches descriptions, notes,
comments, claims, blocked reasons, and issue refs. `lpui issue import` brings GitHub issues (live)
or Linear exports in as plans or tasks with source refs; imports are one-way
and re-import only refreshes source metadata. `lpui audit --since 7.days --strict`
turns the three accuracy metrics into a CI gate. `lpui setup` installs read-only
lifecycle hooks for detected agents; `lpui setup --no-hooks` removes them.

The first run installs the agent skill. `lpui setup --placement repo` generates the full contract in the repo.

## Your data

Plans live in one local database: shared in your home by default, or inside a repo with `lpui setup --placement repo`. Back up with `lpui export --format json`; restore with `lpui import --file`. See [data and backup](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#data-and-backup).

## Learn more

- [Screenshots and quickstart](https://fluxion-dev.github.io/lazyplan/)
- [Usage and CLI reference](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Contributing](https://github.com/fluxion-dev/lazyplan/blob/main/CONTRIBUTING.md) (main is protected; open a PR)
- [Releases](https://github.com/fluxion-dev/lazyplan/releases) · [Issues](https://github.com/fluxion-dev/lazyplan/issues)

MIT licensed. This repo plans itself: run `lpui list`.
