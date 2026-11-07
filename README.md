# lazyplan (`lpui`) — v0.34.0

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

On Windows, use the pip backend:

```powershell
pipx install --backend pip lazyplan-tui
lpui --version
```

The shared home is `%LOCALAPPDATA%\lazyplan\` and the default `--actor` is
`%USERNAME%`. Plan text is read as UTF-8 or UTF-16 and written as UTF-8, so
PowerShell 5 exports round-trip.

Upgrading from 0.30.1 or earlier? The 0.30.2 refactor changed the package layout
and entry points, so reinstall with force: `pipx install --force lazyplan-tui`
(or `python -m pip install --force-reinstall lazyplan-tui`). See the
[upgrade notes](docs/usage.md#upgrade).

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

## New in 0.35

- **The screen is a control room.** It opens on what needs you: attention
  rows, open questions, drift, stale claims, and the last handoff. A two-line
  strip shows health and needs; an agents pane shows who is working.
- **Manual override mode.** The screen is read-only by default. Press `O` to
  arm deliberate writes and keep a visible banner; every change is recorded,
  and risky writes ask for a reason. See them with `lpui feed --overrides`.
- **Trust actions in the palette.** Approve a plan and read its diff, prove a
  criterion, manage questions and references, claim, block, and finish a task
  without dropping to the CLI.
- **Observe and Override.** The palette and help are split by intent so reads
  and writes do not blur together.

## New in 0.34

- **Trust layer.** Approve plan revisions and see exactly what drifted,
  record criterion evidence, keep open questions, and print one deterministic
  review packet. `plan diff`, `criterion prove`, `question`, `plan ready`, and
  `review` close the loop.
- **Sessions and handoff.** `session start` tags every write, `session end`
  records the summary and the next action, and `context`/`brief` show the
  previous handoff to a cold agent.
- **Parallel-safe claims.** Tasks carry touch-points. `next` skips work that
  overlaps an active claim in the same checkout, a manual claim needs
  `--force`, and `task finish` warns when commits touch another open task.
- **External references.** Link a plan to an epic, issue, or doc read-only;
  lazyplan never fetches or writes back to the tracker.
- **Ship note.** `lpui ship --plan 1` turns a plan into a deterministic
  Markdown summary for a PR body or changelog.
- **A sharper screen.** Themes, the GIT pane, live timeline scoping, the
  Markdown export picker, and Windows updates that close cleanly.

## What you get

- A needs-me landing view with attention reasons, open questions, drift, claims, and active sessions.
- A two-line control strip and an agents pane, with manual override mode and an audited feed.
- A plan tree with progress at a glance, plus milestones and tasks underneath.
- One atomic JSON write for a whole plan tree, with feature, bugfix, and refactor recipes.
- A budgeted context packet that resumes a session from the active slice and its proof.
- Session records with a summary and handoff, tagged onto every write.
- Touch-point-aware claims that keep parallel agents from editing the same files.
- Approval snapshots, plan diff, criterion evidence, open questions, and review.
- Read-only external references and a deterministic ship note for PRs and changelogs.
- A balanced tree and preview that reflow at every terminal width.
- A Markdown export picker that starts in Downloads and never overwrites by accident.
- A sticky preview of the reason, the next tasks, and what done means.
- A GIT pane with the checkout, commit, and pull-request context for the row.
- A read-only detail page for careful reading, with quick keys to edit and move work.
- Claim, blocked, gate, and attention state on the rows that need it.
- One place your agent can update while you keep the big picture.

## Built to scale

The benchmark fixture holds 88 plans, 275 milestones, and 789 tasks. Query
counts are deterministic and gated on Linux and macOS per change, with the
same suite running on Windows nightly:

| Path | Before | After |
|---|---:|---:|
| Tree load | 909 queries / 120 ms | 12 / 48 ms |
| `list --json` | 7,853 / 560 ms | 18 / 62 ms |
| `export --format json` | 18,612 / 1,222 ms | 26 / 27 ms |
| TUI refresh | 5,148 / 557 ms | 139 / 112 ms |

Linux timings from the final sweep. See [performance](docs/performance.md) for
the method, budgets, and per-platform ceilings.

## How it works

- Plans start as one-line summaries with progress. Open one to reveal milestones, then tasks.
- The side column takes an equal half of the screen and previews the selected row: why, what, next tasks, and acceptance progress, with a GIT card for the linked checkout and commits.
- The timeline card at the bottom shows the selected row and its immediate children, with the scoped plan in its border.
- The bottom line shows the keys that work right now. `?` opens help; `c` opens the command palette; `t` cycles themes.
- Your agent writes through the same command line. The screen updates as it works.

## Everyday commands

```bash
lpui list                         # plans and progress
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing  # move work forward
lpui criterion tick --id 1        # tick the next acceptance item
lpui session start --plan 1       # tag this working stretch
lpui session end --summary "Shipped the store" --handoff "next: T2"
lpui ref link --plan 1 --url https://github.com/org/repo/issues/7
lpui ship --plan 1                # PR body or changelog entry
lpui feed                         # recent activity
```

## For your agent

The command line reads and writes the same plan, with porcelain rows, JSON, and
clear exit codes:

```bash
lpui --actor helper --porcelain next
lpui --actor helper --porcelain context --max-chars 4000
lpui plan recipe feature > plan.json
lpui --actor helper --porcelain plan apply --file plan.json
lpui --actor helper --porcelain note add --kind task --id 3 --text "Decision"
lpui --actor helper --porcelain list --tree
lpui --actor helper list --json
```

Use `--porcelain` in an active loop: writes answer with one tab-separated row
and reads stay glyph-free. Use `--json` when you need full fidelity.

- **Create once.** `plan apply` writes a whole tree in one transaction from a
  JSON document; stable keys make a retry a no-op, and recipes supply the
  feature, bugfix, or refactor skeleton.
- **Resume.** `lpui context --max-chars 4000` returns the active plan, next
  work, open criteria, decisions, commits, comments, and claims in one read.
- **Coordinate.** `next` claims the first eligible task with a renewable
  lease, so two agents do not take the same work. Renew or release the claim,
  note handoffs, and block parked work with a reason.
- **Stay out of each other's files.** `task add --touch PATH` or `touch add`
  declares what a task will edit. `next` skips overlapping claims in the same
  checkout, and `task finish` warns before an overlap reaches the merge.
- **Resume a stretch.** `session start --plan 1` tags every write; `session end
  --summary ... --handoff ...` leaves the next agent the reason and next step.
- **Prove.** Relate each plan criterion to a proving task; `lpui trace --plan 1`
  shows the evidence, `criterion prove` records the command and exit code, and
  `lpui lint --plan 1 --strict` gates the gaps.
- **Review and ship.** `plan approve`, `plan diff`, and `question` capture the
  scope and the ambiguity; `review --plan 1` prints the full packet and
  `ship --plan 1` prints the outcome note for a PR or changelog.
- **Link, do not mirror.** `ref link --plan 1 --url ...` stores a read-only
  pointer to an epic or issue. lazyplan never fetches or writes back.
- **Collaborate.** Comments and mentions live on plans, milestones, and tasks.
  `lpui share --plan 1` produces a read-only HTML or JSON snapshot; `lpui sync`
  merges plans by stable UID without overwriting conflicts.
- **Gate completion.** `task finish --require-pr --require-checks` reads cached
  PR and CI evidence before done; `--override REASON` records an exception.
  A branch already recorded on another open task is rejected.
- **Import work.** `lpui issue import` brings GitHub issues (live) or Linear
  exports in as plans or tasks with source refs. Imports are one-way and
  re-import only refreshes source metadata.
- **Use MCP.** Hosts that support the Model Context Protocol can call
  `lpui mcp` for typed tools and resources; `--read-only` is available for
  reviewers.
- **Watch flow.** `lpui stats --since 7.days` shows WIP, cycle time, aging,
  stale work, and reopened rows. The TUI Attention filter surfaces the same
  risks, and `/` searches titles, descriptions, notes, comments, claims,
  blocked reasons, and issue refs.

In the screen, `space` marks rows for bulk move/block/release with one undo.
After each commit, link it and move the task. `lpui audit --since 7.days
--strict` turns the three accuracy metrics into a CI gate. `lpui setup`
installs read-only lifecycle hooks for detected agents; `lpui setup --no-hooks`
removes them.

The first run installs the agent skill. `lpui setup --placement repo` generates
the full contract in the repo. See the [usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
for every command and limit.

## Your data

Plans live in one local database: shared in your home by default, or inside a repo with `lpui setup --placement repo`. Back up with `lpui export --format json`; restore with `lpui import --file`. See [data and backup](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#data-and-backup).

## Learn more

- [Screenshots and quickstart](https://fluxion-dev.github.io/lazyplan/)
- [Product roadmap](docs/product/roadmap.md)
- [Usage and CLI reference](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Performance and benchmarks](https://github.com/fluxion-dev/lazyplan/blob/main/docs/performance.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Changelog](https://github.com/fluxion-dev/lazyplan/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/fluxion-dev/lazyplan/blob/main/CONTRIBUTING.md) (main is protected; open a PR)
- [Releases](https://github.com/fluxion-dev/lazyplan/releases) · [Issues](https://github.com/fluxion-dev/lazyplan/issues)

MIT licensed. This repo plans itself: run `lpui list`.
