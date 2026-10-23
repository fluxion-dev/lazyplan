# lazyplan (`lpui`) — v0.20.0

[![CI](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-fluxion--dev.github.io%2Flazyplan-blue)](https://fluxion-dev.github.io/lazyplan/)

You plan work here, and your coding agent plans here too.

Everything lives in one small SQLite database — shared in your home by default, or inside a repo when you opt in with `--team`. You get a keyboard-driven screen for yourself. Your agent gets a `--json` command line that reads the same data. Each plan has a title, a reason why it exists, a description of what to build, and a checklist that says when it is done. That is all there is to it.

Want the full guide with pictures? Start here:
**[fluxion-dev.github.io/lazyplan](https://fluxion-dev.github.io/lazyplan/)**.

## Install

Pick one of the four ways below. The first one suits most people.

```bash
pipx install lazyplan-tui   # recommended: provides `lpui` (+ `lazyplan` alias)
lpui --help
```

On Windows (PowerShell), use the pip backend:

```powershell
pipx install --backend pip lazyplan-tui
```

Need a system package instead? These bundles include everything they need. You only need `python3 >= 3.11` on your machine:

```bash
# Fedora / RHEL / openSUSE — grab the matching asset from Releases
sudo dnf install ./lazyplan-0.20.0-1.x86_64.rpm   # or -1.aarch64.rpm on ARM
# Debian / Ubuntu
sudo apt install ./lazyplan_0.20.0-1_amd64.deb     # or -1_arm64.deb on ARM
```

Want the installer to choose for you? This one-liner picks the right method for your machine:

```bash
curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | sh
# pin + choose:  sh install.sh --version X.Y.Z --method rpm|deb|pipx|venv
# user prefix:   sh install.sh --method venv --prefix ~/.local
# uninstall:     sh install.sh --uninstall
```

Working on lazyplan itself? Install it straight from source:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

When a new version comes out, run `lpui upgrade` (`lpui upgrade --check` reports without changing anything). It manages pipx and venv installs; system packages upgrade through your package manager instead. You do not have to check manually: the TUI statusbar says when an update is available, and CLI commands repeat it on stderr (never on stdout, so `--json` and scripts are unaffected). If you do not have pipx, the `--method venv` path gives you the same isolated install without it.

## Quick start

Run these three commands. You will have a live plan you can open:

```bash
cd ~/my-plan
lpui init --yes             # local skills + shared DB (clean repo stays untouched)
lpui plan add --title "my-plan" --why "reason" --what "scope"
lpui                        # TUI (`lpui ui` also works)
```

The first time you run `lpui init` with no flags, it asks which agents to install for, then writes the skill into each selected agent's own local skills folder without touching a clean repo (all agents share the one database in `~/.lazyplan`). Leftovers from an earlier scoped install are reported and repaired with backups. Pass `--team` to opt a repo into shared storage instead: `lpui init --team` writes `.agents/lazyplan/`, repo skills, the `AGENTS.md` pointer, and templates, and offers `.gitignore` entries. You can skip skills with `--no-skills`, pick agents non-interactively with `--agents "opencode,claude"` (or `all`), force one folder with `--skills-dir PATH` (or `$LAZYPLAN_SKILLS_DIR`), or pass `--json` for machine-readable output that never asks you questions.

### Where init puts things

The scope you choose is the single authority for every resource:

| You run | Database | Templates | `config.json` | Skills | `AGENTS.md` |
| --- | --- | --- | --- | --- | --- |
| `lpui init` | `~/.lazyplan/lazyplan.db` | `~/.lazyplan/templates/` | not written | each agent's home skill dir | not written |
| `lpui init --team` (or `--skills-scope project`) | `<repo>/.agents/lazyplan/lazyplan.db` | `<repo>/.agents/lazyplan/templates/` | `<repo>/.agents/lazyplan/config.json` (commit it) | repo skill dirs | repo pointer |
| `lpui init --skills-scope both` | repo database | repo templates | repo config | repo and home skill dirs | repo pointer |
| `lpui init --no-skills` | same storage as the other flags | same | same | none | none |
| `--db PATH` / `$LAZYPLAN_DB` | `PATH` | beside `PATH` | repo config only when `PATH` is a repo plan dir | per scope flags | per scope flags |

`--team --no-skills` still selects repo storage. An explicit `--db` or `$LAZYPLAN_DB` always wins and is never moved.

Inspect the expected versus actual layout without writing anything:

```bash
lpui init --check          # same flags as init, no changes
lpui doctor                # the same report without init flags
lpui init --check --json   # machine-readable, stable JSON
```

Exit code `0` means clean, `1` means misplaced resources, `2` means bad flags. `doctor --team` checks the repo-owned layout.

Global init repairs leftovers from an earlier scoped install. A repo database moves to the home path when the home database is empty; repo config, templates, generated skills, the marked `AGENTS.md` block, and lazyplan `.gitignore` entries are cleaned up or moved home. Every touched file is backed up under `~/.lazyplan/backups/<timestamp>/`, and the report lists each backup. If both databases already contain plans, init stops, backs up the repo database, and prints an export/import next step — it never merges or deletes plans. Team init never moves home data.

You can run `lpui` from any folder. By default every agent and every folder shares one database in your home folder (`~/.lazyplan`, or `%LOCALAPPDATA%/lazyplan` on Windows). Only team-initialized repos resolve into the repo.

Where does it look for the database? The first match wins: `--db PATH`, then `$LAZYPLAN_DB`, then the nearest team-initialized `.agents/lazyplan/lazyplan.db` walking up from where you run it, then the shared `~/.lazyplan/lazyplan.db` (`%LOCALAPPDATA%/lazyplan` on Windows). For teams, commit `.agents/lazyplan/config.json` to share the plan. The `*.db` file itself stays local (it is gitignored) unless you force-add it.

Planning across checkouts? Link repos to any row (0..n, path plus remote URL). Tasks inherit their milestone's repos, milestones inherit their plan's:

```bash
lpui link-repo --kind plan --id 1 --repo ~/checkouts/api
lpui repos --kind task --id 2 --effective
lpui list --repo ~/checkouts/api
```

Need tab completion? Run `eval "$(lpui completion --shell bash)"` (or `--shell zsh`). System packages include completions plus the `man lpui` page out of the box.

Note: versions up to 0.7.0 shipped this tool as `lp`, renamed because that name clashed with the classic Unix print command.

## How it works

You plan in `lpui` (`lpui ui` opens the same screen). Here is what you will see:

See screenshots of the screen beside a coding agent at <https://fluxion-dev.github.io/lazyplan/#screens>.

- Plans start as one-line summaries with progress, for example `◐ P2 API v2 3/8`. Press `right` or `z` to reveal milestones, then tasks. Nothing is dumped on you at once.
- The right pane previews the selected row: why/what, the next few open tasks, acceptance progress, commits, and repos. At narrow widths the preview steps aside and `enter` opens the full detail page.
- `enter` opens the detail page in a read-only view. Press `e` to edit, `s` to advance status, `x` to tick a criterion, `a` to add one, `n` to add the next level, and `d` to delete (the confirmation says what else will go). `escape` goes back.
- The bottom line shows human counts (`3 plans · 12 open · 1 doing`) and the keys that work right now. The palette lists plain outcomes and disables commands that cannot run for the current selection.
- You and your agent share one SQLite file. The screen refreshes every second and tells you when something new arrives. Your agent never touches the screen itself. Big decisions about wording and scope stay a conversation with you.

| key | what it does |
|---|---|
| `j`/`k`, arrows, click | move and select · `left`/`right` fold and unfold · `enter` open detail |
| `e` / `s` / `x` / `a` / `d` | edit · advance status · tick next criterion · add criterion · delete |
| `n` | create by context (plan, milestone, or task); the form names its target |
| `/` | filter by text · `f` change status filter · `A` show all plans · `r` refresh |
| `?` | help · `c` command palette · `q` quit |

The palette and the CLI use the same names: Create plan, Move to doing, Tick next criterion, Delete selection. Old CLI verbs still work as aliases, and typing one in the palette finds the canonical command.

Plans start collapsed. Press `right` (or `z`) on a plan to show its milestones; tasks stay folded until you open their milestone. Completed plans are dimmed and sorted last.

## CLI reference

The package installs full help text. Start here:

```bash
lpui --help              # globals + examples + env/files/exit codes
lpui --version           # print the installed version and exit
lpui <command> --help    # per-command flags, e.g. lpui task add --help
man lpui                 # full manual (also `man lazyplan`); installed to share/man/man1
lpui help                # screen key bindings (same as the in-app help screen)
```

Flags work before or after the command (`lpui list --json` means the same as `lpui --json list`). On commands that change data, `--actor NAME` records who did it so you can see it in `feed`.

```bash
lpui seed
lpui list [--tree] [--status todo|doing|done|all] [--archived] [--plan ID] [--all] [--limit N]
lpui plan list                              # summaries; 5 most recent by default
lpui plan list --tree                       # full plan/milestone/task tree
lpui plan show --id 1                       # why/what + criteria + commits + children
lpui plan add --title "API v2" --why ".." --what ".."
lpui plan edit --id 1 [--title --what --why]
lpui plan move --id 1 --to doing            # closing with open criteria warns, never blocks
lpui plan delete --id 1
lpui milestone add --plan 1 --title "Auth refresh" [--desc ..]
lpui milestone edit --id 2 [--title --desc]
lpui milestone show --id 2
lpui milestone move --id 2 --to done
lpui milestone delete --id 2
lpui task add --milestone 1 --title "Rotate tokens" [--desc ctx]
lpui task edit --id 3 [--title --desc]
lpui task show --id 3
lpui task move --id 3 --to done
lpui task delete --id 3
lpui criterion add --kind plan --id 1 --text "works offline"
lpui criterion list --kind plan --id 1
lpui criterion tick --id 4 / lpui criterion untick --id 4
lpui criterion delete --id 4
lpui link --kind task --id 1 [--sha HASH]      # attach HEAD (git repos only; disabled otherwise)
lpui commits --kind task --id 1                # list linked commits (empty outside git)
lpui unlink --kind task --id 1 --sha HASH      # detach a commit
lpui link-repo --kind plan --id 1 --repo ~/checkouts/api [--remote URL]
lpui unlink-repo --kind plan --id 1 --repo ~/checkouts/api
lpui repos --kind task --id 1 [--effective]    # explicit links, or inherited
lpui list [--repo ~/checkouts/api]             # filter by effective repo
lpui export [--format json|markdown] | lpui import --file dump.json
lpui upgrade [--check]                   # self-update pipx/venv installs (system pkgs: use dnf/apt)
lpui feed [--limit 20]            # recent human/agent activity
lpui watch [--limit 20]           # tail (agents: lpui feed --json --follow &)
lpui --actor helper task add --milestone 3 --title "Draft proposal"
```

Legacy flat verbs (`add-plan`, `add-task`, `update`, `status`, `delete`, `check`, `uncheck`, …) still work and remain in `lpui --help` as aliases.

Exit codes: `0` means it worked · `1` means the row was not found · `2` means the flags or input were wrong · `3` means the screen cannot start because Textual is missing. If that happens, reinstall with dependencies: `pip install "lazyplan-tui"` or `pipx reinstall lazyplan-tui`.

## Agents

Your agent talks to the same database through the command line. It only needs the standard library (it never imports the screen code). Every command accepts `--json`. Exit codes tell scripts what happened. Each write carries an `--actor NAME` label (it defaults to `$USER`) so you can see in `feed` who did what.

```bash
lpui --actor helper list --json                    # read the tree
lpui --actor helper plan show --id 1           # full context: why/what + criteria
lpui --actor helper task add --milestone 1 --title "Draft proposal"
lpui feed --json --follow &                         # tail activity (polls every second)
```

How your agent is expected to work: it asks you about the plan first (why it exists, what it covers, how you will know it is done — it never makes that up). On implementation requests it hunts ambiguity first: in/out scope, touch-points, edge cases, non-goals, assumptions. Then it breaks the work into milestones and tasks. It looks up ids with `list` instead of guessing them. It prefers `update` and `status` over deleting and re-creating. It works in creation order. Every row is written for scanning — paragraphs and sections, never a single blob or placeholder text. The full agent contract is generated per clone by `lpui init --team`. If you contribute code, follow the design rules in `src/lazyplan/design.py`.

## Data, backup, replicas

- Shared home by default: `lpui init` installs skills and keeps one `~/.lazyplan/lazyplan.db` for every agent. On a clean repo it creates no repo files; if an earlier scoped install left DB, config, template, skill, `AGENTS.md`, or `.gitignore` artifacts behind, global init repairs them with backups. For teams, `lpui init --team` creates `.agents/lazyplan/lazyplan.db` next to the code it plans. The `.agents/lazyplan/config.json` file marks which folder it belongs to. Commit the config file so your team shares the plan. The database itself stays on your machine.
- Need a backup, or moving to a new machine? Run `lpui export --format json > backup.json` to save, and `lpui import --file backup.json` to load it back (ids change on import, and that is fine). Exports include linked repos.
- Want to click around first? Run `lpui seed` for demo data. Never run it in a repo with a real plan.

## Develop

You need `python3` to hack on lazyplan. The normal flow looks like this:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"   # ruff + mypy
./tools/check.sh                   # lint + format + types + unittest (system AND venv python)
./tools/bump.sh patch [--push]     # or minor | major; version lives in pyproject.toml
./tools/package.sh                 # local .deb/.rpm build (needs nfpm; see script header)
./tools/tmux-lazyplan.sh           # plan | agent | git panes — edit the script to swap in your tools
```

Release steps and rollback commands live in `docs/releasing.md`.

Before you push, `./tools/check.sh` must pass: `ruff check` plus `ruff format --check`, `mypy` in strict mode (every function needs types, no `type: ignore` without a TODO link), the man page matching the code (`tools/gen-man.py`), and the full test suite on both interpreters. The version lives in one place only: `version = "x.y.z"` in `pyproject.toml` (`tests/test_version.py` checks that the README header matches; `tools/bump.sh` updates both, plus the download links on the site).

## Project

- Docs site: <https://fluxion-dev.github.io/lazyplan/>
- Repository: <https://github.com/fluxion-dev/lazyplan>
- Releases (binaries, debs, rpms): <https://github.com/fluxion-dev/lazyplan/releases>
- Issues: <https://github.com/fluxion-dev/lazyplan/issues>
- Changelog: <https://github.com/fluxion-dev/lazyplan/releases> (written automatically for each release)

This repo plans itself right here: run `lpui list`. License: MIT — see [LICENSE](LICENSE).
