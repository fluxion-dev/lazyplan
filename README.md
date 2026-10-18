# lazyplan (`lpui`) — v0.8.0

[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Terminal stream-of-consciousness console for issue tracking + roadmap planning,
built to run in tmux next to `opencode` and `lazygit`. Design rules live in
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md), enforced by `src/lazyplan/design.py`.

## Install

```bash
pipx install lazyplan-tui   # isolated global `lpui` (+ `lazyplan` alias)
# or from a checkout: pipx install .
# or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
lpui --help
# optional: shell completions
eval "$(lpui completion --shell bash)"   # or --shell zsh
```
Renamed from `lp` to `lpui` (`lazyplan` works too): plain `lp` collided with
the classic Unix print command `/usr/bin/lp`, which shadows pipx's
`~/.local/bin` on default Fedora `PATH` order. Use `command lp` or the full
path if you ever need the printer.

DB resolution (first match wins): `--db PATH` → `$LAZYPLAN_DB` →
enclosing git repo's `.plan/lazyplan.db` → global
`~/.local/share/lazyplan/lazyplan.db`.

## Repo-scoped workflow

Each git repo gets its own plan, stored with the code:

```bash
cd ~/my-project
lpui init        # creates .plan/lazyplan.db + .plan/config.json, then offers
               # the agent-skills wizard (universal `.agents/skills/lazyplan/`
               # + `## lazyplan` pointer in AGENTS.md). Flags: --no-skills,
               # --yes, --skills-scope project|global|both|none; --json stays
               # machine-readable and never prompts.
lpui info        # resolved db path, repo root, counts, .plan files
lpui add-project --name "my-project" --start 2026-10-18 --end 2026-12-31
lpui ui          # statusbar shows [my-project]; agents in any subdir share it
```

Run `lpui` from any subdirectory — it walks up to the repo root (via
`git rev-parse` with a `.git` fallback). Outside a repo it uses the global DB.
Commit `.plan/` to share the plan with the team, or ignore `*.db` to keep it
local — your call.

## Release (semver)

Version lives in one place: `version` in `pyproject.toml`. The README header
mirrors it; `tests/test_version.py` fails the gates on drift.

```bash
./tools/bump.sh patch [--push]   # or minor | major; --dry-run to preview
```

`bump.sh` validates semver, updates `pyproject.toml` + README, commits, and
tags `vX.Y.Z` (refuses a dirty tree or an existing tag). Pushing the tag
(`--push`, or Actions → bump → patch/minor/major) triggers the release
workflow: tag-vs-pyproject check, sdist/wheel build, GitHub Release with
auto-generated notes. CI (`ci.yml`) runs `./tools/check.sh` on every push/PR.

## tmux workflow

```bash
./tools/tmux-lazyplan.sh        # plan | opencode | lazygit
```

## Dev / gates

```bash
pip install -e ".[dev,postgres]"   # ruff + mypy (+ psycopg for `lpui sync`)
./tools/check.sh                   # ruff check + format --check + mypy (strict)
                                   # + unittest on system python AND venv python
```

Standards live in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) (§Python standards,
pyguide-based).

Agents never touch the TUI process — they call `lpui --actor NAME ...` against
the same SQLite file (proposals/questions for anything needing human eyes);
the TUI polls a fingerprint (mtime + counts + max ids + last event) every
second and toasts + activity-lines new arrivals. `lpui sync` snapshots the db
to Postgres for SQL-side readers (see `src/lazyplan/postgres_sync.py`).

## TUI (`lpui ui`)

Single panel, nano-style bottom bar (activity line, statusbar, command bar,
key footer). Mouse click/expand works.

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

## CLI (agent ingress)

Flags work before or after the subcommand (`lpui list --json` == `lpui --json list`).

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
lpui sync --dsn postgresql://issues:issues@localhost:5433/issues   # one-way replica
lpui update --kind task --id 1 [--title --desc --owner --estimate --priority p0|none --labels a,b --blocked-by 1,2]
lpui status --kind task --id 1 --to doing    # closing with open criteria warns, never blocks
lpui delete --kind task --id 1
lpui feed [--limit 20]            # recent human/agent activity
lpui watch [--limit 20]           # tail (agents: lpui feed --json --follow &)
lpui --actor agent-1 add-task --story 3 --title "Draft proposal"
```

## Roadmap (dogfooded)

The repo DB holds **2 projects** (17 stories, 60 tasks, all done): P#1
“lazyplan roadmap” (11 stories, 37 tasks — MVP, planning power, distribution,
ownership, acceptance criteria, risks, goals/scope, materials, agent ingress,
postgres sync, TUI polish) and P#2 “lazyplan architecture hardening”
(6 stories, 23 tasks — toolchain, types, style, architecture, test hygiene,
docs). All feature work goes here — `lpui list`,
`lpui gantt --tasks`, `lpui show --kind story --id N`, `lpui ui`.
