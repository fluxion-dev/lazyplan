# lazyplan (`lpui`) — v0.8.0

[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Terminal issue tracker + roadmap planner for you and your coding agent:
projects > stories > tasks in a per-repo SQLite DB, a keyboard-first TUI
for humans, and a `--json` CLI agents can drive. Rules live in
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Quick start

```bash
pipx install lazyplan-tui   # provides `lpui` (+ `lazyplan` alias)
lpui --help
cd ~/my-project
lpui init --yes             # creates .plan/lazyplan.db + .plan/config.json
lpui add-project --name "my-project"
lpui ui                     # TUI; every subdir of the repo shares this DB
```

`lpui init` with no flags offers an agent-skills wizard instead
(`--no-skills`, `--skills-scope project|global|both|none`, `--json`
stays machine-readable and never prompts).

Run from any subdirectory — the repo root is found via `git rev-parse`
(`.git` fallback); outside a repo the global DB is used. Commit `.plan/`
to share the plan with the team, or ignore `*.db` to keep it local.

DB resolution (first match wins): `--db PATH` → `$LAZYPLAN_DB` →
repo `.plan/lazyplan.db` → global `~/.local/share/lazyplan/lazyplan.db`.

Shell completions: `eval "$(lpui completion --shell bash)"` (or `--shell zsh`).

Note: versions ≤0.7.0 shipped this as `lp`, renamed to avoid clashing with
the classic Unix print command.

## How it works

- You plan in `lpui ui`: tree / gantt / feed views, nano-style bottom bar.
- Any coding agent reads (`list`, `show`, `feed --json`) and writes
  (`--actor NAME add-task …`) against the same SQLite file; the TUI
  re-reads every second and toasts new arrivals. Agents never touch the
  TUI process — judgment calls go through `propose` / `ask`, which you
  approve / answer in the UI.

| key | action |
|---|---|
| `1`/`2`/`3` | tree / gantt / feed views |
| `j`/`k`, arrows, click | navigate · `enter` edit detail in place |
| `n` | contextual new (task→story→project) |
| `P`/`S`/`T` | new project / story / task forms |
| `e` / `d` | edit · delete (with confirm) |
| `space` / `c` | cycle status · tick first open criterion |
| `+`/`-` | gantt zoom (width 20–100) |
| `f` / `o` / `O` | status / project / owner filter |
| `s` / `ctrl+p` | search · command palette (fuzzy, rows + views) |
| `4` then `a`/`x` | proposals view · approve / reject |
| `/` | focus command bar · `?` help · `r` refresh · `q` quit |

The command bar accepts the same verbs as `lpui`
(`add-task --story 1 --title x`, `status --kind task --id 1 --to done`,
`tree`/`gantt`/`feed`, `help`).

## CLI reference

Flags work before or after the subcommand (`lpui list --json` == `lpui --json list`).
`--actor NAME` on writes surfaces who did what in `feed`.

```bash
lpui seed
lpui list [--status todo|doing|done] [--project ID] [--owner NAME] [--priority p0]
lpui gantt [--tasks] [--width 40] [--status ..] [--project ID] [--owner NAME] [--priority p0]
# * = critical path, ! = blocked, ◆ = milestone
lpui show --kind project|story|task --id N   # full context: narrative + links + children
lpui add-project --name "API v2" [--goal .. --metrics .. --scope-in .. --scope-out .. --assumptions ..]
lpui add-story --project 1 --title "Auth refresh" [--owner a1 --priority p0 --labels x,y --estimate 2w --blocked-by 3]
lpui add-task --story 1 --title "Rotate tokens" [--desc ctx --owner a1 --priority p1 --estimate 2d --blocked-by 4]
lpui add-link --kind story --id 1 --url URL [--label spec]
lpui add-criteria --kind task --id 1 --text "works offline"
lpui check --id 1 / lpui uncheck --id 1        # tick acceptance items (advisory)
lpui add-risk --project 1 --title "slip" [--likelihood high --impact high --mitigation buf]
lpui add-milestone --project 1 --title "Beta" --date 2026-11-15
lpui propose --kind task --parent 1 --title "Refactor X" [--priority p1 --owner a1]
lpui proposals [--status pending] | lpui approve --id 1 / lpui reject --id 1
lpui ask --question "Which scope?" | lpui questions | lpui answer --id 1 --text "Minimal"
lpui export [--format json|markdown] | lpui import --file dump.json
lpui sync --dsn postgresql://user:pass@host:port/db   # one-way SQLite -> Postgres replica
lpui update --kind task --id 1 [--title --desc --owner --estimate --priority p0|none --labels a,b --blocked-by 1,2]
lpui status --kind task --id 1 --to doing    # closing with open criteria warns, never blocks
lpui delete --kind task --id 1
lpui feed [--limit 20]            # recent human/agent activity
lpui watch [--limit 20]           # tail (agents: lpui feed --json --follow &)
lpui --actor helper add-task --story 3 --title "Draft proposal"
```

## Develop

```bash
pip install -e ".[dev,postgres]"   # ruff + mypy (+ psycopg for `lpui sync`)
./tools/check.sh                   # lint + format + types + unittest (system AND venv python)
./tools/bump.sh patch [--push]     # or minor | major; version lives in pyproject.toml
./tools/tmux-lazyplan.sh           # plan | agent | git panes — edit the script to swap in your tools
```

## Roadmap (dogfooded)

This repo plans itself here: `lpui list` — P#1 “lazyplan roadmap”
(11 stories, 37 tasks) and P#2 “lazyplan architecture hardening”
(6 stories, 23 tasks), all done.
