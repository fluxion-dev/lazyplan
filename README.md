# lazyplan (`lpui`) — v0.8.2

[![CI](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-fluxion--dev.github.io%2Flazyplan-blue)](https://fluxion-dev.github.io/lazyplan/)

Terminal issue tracker + roadmap planner for you **and** your coding agent:
projects > stories > tasks in a per-repo SQLite DB, a keyboard-first TUI
for humans, and a `--json` CLI agents can drive. Full guide with install
tabs and examples: **[fluxion-dev.github.io/lazyplan](https://fluxion-dev.github.io/lazyplan/)**.

## Install

```bash
pipx install lazyplan-tui   # recommended: provides `lpui` (+ `lazyplan` alias)
lpui --help
```

System packages (vendored deps, needs only `python3 >= 3.11`):

```bash
# Fedora / RHEL / openSUSE — grab the matching asset from Releases
sudo dnf install ./lazyplan-0.8.2-1.x86_64.rpm   # or -1.aarch64.rpm on ARM
# Debian / Ubuntu
sudo apt install ./lazyplan_0.8.2-1_amd64.deb     # or -1_arm64.deb on ARM
```

One-liner (picks rpm/deb on supported distros, else pipx, else venv):

```bash
curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | sh
# pin + choose:  sh install.sh --version X.Y.Z --method rpm|deb|pipx|venv
# user prefix:   sh install.sh --method venv --prefix ~/.local
# uninstall:     sh install.sh --uninstall
```

From source (editable install with dev extras):

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev,postgres]"
```

`pipx upgrade lazyplan-tui` for later releases. No pipx? The
`--method venv` path is the same isolated install without it.

## Quick start

```bash
cd ~/my-project
lpui init --yes             # creates .plan/lazyplan.db + .plan/config.json
lpui add-project --name "my-project"
lpui                        # TUI; every subdir of the repo shares this DB (`lpui ui` also works)
```

`lpui init` with no flags offers an agent-skills wizard instead
(`--no-skills`, `--skills-scope project|global|both|none`, `--json`
stays machine-readable and never prompts).

Run from any subdirectory — the repo root is found via `git rev-parse`
(`.git` fallback); outside a repo the global DB is used.

DB resolution (first match wins): `--db PATH` → `$LAZYPLAN_DB` →
repo `.plan/lazyplan.db` → global `~/.local/share/lazyplan/lazyplan.db`.
Commit `.plan/config.json` to share the plan with the team; the `*.db`
itself stays local (gitignored) unless you force-add it.

Shell completions: `eval "$(lpui completion --shell bash)"` (or `--shell zsh`).
System packages ship these plus `man lpui` out of the box.

Note: versions ≤0.7.0 shipped this as `lp`, renamed to avoid clashing with
the classic Unix print command.

## How it works

- You plan in `lpui` (`lpui ui` is the same): tree / gantt / feed views, nano-style bottom bar.
- Any coding agent reads (`list`, `show`, `feed --json`) and writes
  (`--actor NAME add-task …`) against the same SQLite file; the TUI
  re-reads every second and toasts new arrivals. Agents never touch the
  TUI process — judgment calls go through `propose` / `ask`, which you
  approve / answer in the UI.

| key | action |
|---|---|
| `1`/`2`/`3` | tree / gantt / feed views |
| `j`/`k`, arrows, click | navigate · `enter` edits detail in place · `left`/`right` collapse/expand |
| `n` | contextual new (task→story→project) |
| `P`/`S`/`T` | new project / story / task forms |
| `e` / `d` | edit · delete (with confirm) |
| `space` / `c` | cycle status · tick first open criterion |
| `z` / `Z` | fold one / fold all |
| `+`/`-` | gantt zoom (width 20–100) |
| `f` / `o` / `O` | status / project / owner filter |
| `s` / `ctrl+p` | search · command palette (fuzzy, rows + views) |
| `4` then `a`/`x` | proposals view · approve / reject |
| `/` | focus command bar · `?` help · `r` refresh · `q` quit |

The command bar accepts the same verbs as `lpui`
(`add-task --story 1 --title x`, `status --kind task --id 1 --to done`,
`tree`/`gantt`/`feed`, `help`). Full key list: `lpui help` (same as `?`).

## CLI reference

Full help is installed with the package:

```bash
lpui --help              # globals + examples + env/files/exit codes
lpui --version           # print the installed version and exit
lpui <command> --help    # per-command flags, e.g. lpui add-task --help
man lpui                 # full manual (also `man lazyplan`); installed to share/man/man1
lpui help                # TUI keybindings (same as `?` in the TUI)
```

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

Exit codes: `0` ok · `1` row not found · `2` usage/validation error ·
`3` TUI unavailable (Textual missing — reinstall with dependencies:
`pip install "lazyplan-tui"` / `pipx reinstall lazyplan-tui`).

## Agents

The CLI is the agent API: stdlib-only (no Textual import), `--json`
everywhere, exit codes machines can branch on. Identity comes from
`--actor NAME` (defaults to `$USER`); every write lands in `feed` with
that actor attached.

```bash
lpui --actor helper list --json                    # read the tree
lpui --actor helper show --kind task --id 3       # full context for one row
lpui --actor helper add-task --story 1 --title "Draft proposal"
lpui --actor helper propose --kind task --parent 1 --title "Refactor X"  # needs human ok
lpui --actor helper ask --question "Minimal or full scope?"              # human answers in UI
lpui feed --json --follow &                        # tail activity (polls every second)
```

Rules: never invent ids (`list` first); prefer `update`/`status` over
delete + recreate; `propose`/`ask` instead of guessing on scope or taste;
never `approve`/`reject` your own proposals or `answer` your own questions.
Repo skill with the full contract: `.agents/skills/lazyplan/SKILL.md`;
design rules contributors must follow: [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Data, backup, replicas

- One repo, one DB: `.plan/lazyplan.db` next to the code it plans
  (`.plan/config.json` marks the scope; commit the config, not the DB).
- Back up or move plans: `lpui export --format json > backup.json` /
  `lpui import --file backup.json` (ids remap on import).
- Read replica for dashboards: `lpui sync --dsn postgresql://…`
  (one-way SQLite → Postgres; needs `pip install "lazyplan-tui[postgres]"`).
- Demo data to explore the views: `lpui seed` (never in a real repo plan).

## Develop

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev,postgres]"   # ruff + mypy (+ psycopg for `lpui sync`)
./tools/check.sh                   # lint + format + types + unittest (system AND venv python)
./tools/bump.sh patch [--push]     # or minor | major; version lives in pyproject.toml
./tools/package.sh                 # local .deb/.rpm build (needs nfpm; see script header)
./tools/tmux-lazyplan.sh           # plan | agent | git panes — edit the script to swap in your tools
```

Gates: `ruff check` + `ruff format --check`, `mypy` (strict incl. untyped
defs), man page in sync (`tools/gen-man.py`), full unittest suite on both
interpreters. Single source of truth for the version is
`version = "x.y.z"` in `pyproject.toml` (`tests/test_version.py` enforces
the README header mirror; `tools/bump.sh` updates both plus site asset URLs).

## Project

- Docs site: <https://fluxion-dev.github.io/lazyplan/>
- Repository: <https://github.com/fluxion-dev/lazyplan>
- Releases (binaries, debs, rpms): <https://github.com/fluxion-dev/lazyplan/releases>
- Issues: <https://github.com/fluxion-dev/lazyplan/issues>
- Changelog: <https://github.com/fluxion-dev/lazyplan/releases> (auto-generated per tag)

This repo plans itself here: `lpui list` — P#1 “lazyplan roadmap”
plus P#2 “architecture hardening”. License: MIT — see [LICENSE](LICENSE).
