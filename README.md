# lazyplan (`lpui`) — v0.12.0

[![CI](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-fluxion--dev.github.io%2Flazyplan-blue)](https://fluxion-dev.github.io/lazyplan/)

Terminal project journal for you **and** your coding agent:
projects > stories > tasks in a per-repo SQLite DB, a keyboard-first TUI
for humans, and a `--json` CLI agents can drive. A project is a title plus
a priority, a why, a what, and acceptance criteria — nothing else. Full
guide with install tabs and examples:
**[fluxion-dev.github.io/lazyplan](https://fluxion-dev.github.io/lazyplan/)**.

## Install

```bash
pipx install lazyplan-tui   # recommended: provides `lpui` (+ `lazyplan` alias)
lpui --help
```

System packages (vendored deps, needs only `python3 >= 3.11`):

```bash
# Fedora / RHEL / openSUSE — grab the matching asset from Releases
sudo dnf install ./lazyplan-0.12.0-1.x86_64.rpm   # or -1.aarch64.rpm on ARM
# Debian / Ubuntu
sudo apt install ./lazyplan_0.12.0-1_amd64.deb     # or -1_arm64.deb on ARM
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
python -m pip install -e ".[dev]"
```

`pipx upgrade lazyplan-tui` for later releases. No pipx? The
`--method venv` path is the same isolated install without it.

## Quick start

```bash
cd ~/my-project
lpui init --yes             # creates .lazyplan/lazyplan.db + .lazyplan/config.json
lpui add-project --title "my-project" --why "reason" --what "scope" --priority p1
lpui                        # TUI; every subdir of the repo shares this DB (`lpui ui` also works)
```

`lpui init` with no flags offers an agent-skills wizard instead
(`--no-skills`, `--skills-scope project|global|both|none`, `--json`
stays machine-readable and never prompts). On a TTY it also offers to
move a legacy `.plan/` dir and to gitignore the dirs it created.

Run from any subdirectory — the repo root is found via `git rev-parse`
(`.git` fallback); outside a repo the global DB is used.

DB resolution (first match wins): `--db PATH` → `$LAZYPLAN_DB` →
repo `.lazyplan/lazyplan.db` → global `~/.local/share/lazyplan/lazyplan.db`.
Commit `.lazyplan/config.json` to share the plan with the team; the `*.db`
itself stays local (gitignored) unless you force-add it.

Shell completions: `eval "$(lpui completion --shell bash)"` (or `--shell zsh`).
System packages ship these plus `man lpui` out of the box.

Note: versions ≤0.7.0 shipped this as `lp`, renamed to avoid clashing with
the classic Unix print command.

## How it works

- You plan in `lpui` (`lpui ui` is the same): a project tree with a
  nano-style bottom bar. New project? The agent interviews you first —
  why, what, acceptance criteria, priority — then records the definition.
- Once the definition is agreed, stories cut the project into slices and
  prioritized tasks cut each story into units of work. Work p0 first.
- Rows with linked git commits show short-SHA chips; `enter` on a row lists
  its commits in the detail dialog read-only.
- Any coding agent reads (`list`, `show`, `feed --json`) and writes
  (`--actor NAME add-task …`) against the same SQLite file; the TUI
  re-reads every second and toasts new arrivals. Agents never touch the
  TUI process — scope and taste stay a human conversation.

| key | action |
|---|---|
| `j`/`k`, arrows, click | navigate + select · `enter`/double-click edits detail in place · `left`/`right` collapse/expand |
| `n` | contextual new (task→story→project) |
| `P`/`S`/`T` | new project / story / task forms |
| `e` / `d` | edit · delete (with confirm) |
| `space` / `c` | cycle status · tick first open criterion |
| `z` / `Z` | fold one / fold all |
| `f` / `o` | status / project filter |

Agents use the `lpui` CLI; the TUI is keyboard-only with no command entry.
Full key list: `lpui help` (same as `?`).

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
lpui list [--status todo|doing|done|all] [--archived] [--project ID] [--priority p0]  # default: all
lpui show --kind project|story|task --id N   # full context: why/what + criteria + commits + children
lpui add-project --title "API v2" --why ".." --what ".." --priority p1
lpui add-criteria --kind project --id 1 --text "works offline"
lpui check --id 1 / lpui uncheck --id 1        # tick acceptance items (advisory)
lpui add-story --project 1 --title "Auth refresh" [--desc .. --priority p0]
lpui add-task --story 1 --title "Rotate tokens" [--desc ctx --priority p1]
lpui link --kind task --id 1 [--sha HASH]      # attach HEAD (git repos only; disabled otherwise)
lpui commits --kind task --id 1                # list linked commits (empty outside git)
lpui unlink --kind task --id 1 --sha HASH      # detach a commit
lpui export [--format json|markdown] | lpui import --file dump.json
lpui update --kind task --id 1 [--title --desc --priority p0|none]
lpui update --kind project --id 1 [--title --what --why --priority p0|none]
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
lpui --actor helper show --kind project --id 1    # full context: why/what + criteria
lpui --actor helper add-task --story 1 --title "Draft proposal" --priority p1
lpui feed --json --follow &                        # tail activity (polls every second)
```

Rules: interview the human before creating a project (why, what,
acceptance criteria, priority — never invent the definition); cut stories
then prioritized tasks once the definition is agreed; never invent ids
(`list` first); prefer `update`/`status` over delete + recreate; work p0
first. Repo skill with the full contract:
`.agents/skills/lazyplan/SKILL.md`; design rules contributors must follow:
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Data, backup, replicas

- One repo, one DB: `.lazyplan/lazyplan.db` next to the code it plans
  (`.lazyplan/config.json` marks the scope; commit the config, not the DB).
- Back up or move plans: `lpui export --format json > backup.json` /
  `lpui import --file backup.json` (ids remap on import).
- Demo data to explore the tree: `lpui seed` (never in a real repo plan).

## Develop

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"   # ruff + mypy
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

This repo plans itself here: `lpui list`. License: MIT — see [LICENSE](LICENSE).
