# lazyplan (`lpui`) — v0.15.0

[![CI](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/lazyplan/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fluxion-dev/lazyplan)](https://github.com/fluxion-dev/lazyplan/releases)
[![PyPI](https://img.shields.io/pypi/v/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![Python](https://img.shields.io/pypi/pyversions/lazyplan-tui)](https://pypi.org/project/lazyplan-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-fluxion--dev.github.io%2Flazyplan-blue)](https://fluxion-dev.github.io/lazyplan/)

You plan work here, and your coding agent plans here too.

Everything lives in one small database next to your code. You get a keyboard-driven screen for yourself. Your agent gets a `--json` command line that reads the same data. Each plan has a title, a priority, a reason why it exists, a description of what to build, and a checklist that says when it is done. That is all there is to it.

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
sudo dnf install ./lazyplan-0.15.0-1.x86_64.rpm   # or -1.aarch64.rpm on ARM
# Debian / Ubuntu
sudo apt install ./lazyplan_0.15.0-1_amd64.deb     # or -1_arm64.deb on ARM
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

When a new version comes out, run `pipx upgrade lazyplan-tui`. If you do not have pipx, the `--method venv` path gives you the same isolated install without it.

## Quick start

Run these three commands. You will have a live plan you can open:

```bash
cd ~/my-plan
lpui init --yes             # zero-touch: local skills + DB, no repo writes
lpui add-plan --title "my-plan" --why "reason" --what "scope" --priority p1
lpui                        # TUI (`lpui ui` also works)
```

The first time you run `lpui init` with no flags, it asks which agents to install for, then writes the skill into each selected agent's own local skills folder (plus a sibling `lazyplan.db` per skill dir) without touching your repo. Pass `--team` to opt a repo into shared storage instead: `lpui init --team` writes `.agents/lazyplan/`, repo skills, the `AGENTS.md` pointer, and templates, and offers `.gitignore` entries. You can skip skills with `--no-skills`, pick agents non-interactively with `--agents "opencode,claude"` (or `all`), force one folder with `--skills-dir PATH` (or `$LAZYPLAN_SKILLS_DIR`), or pass `--json` for machine-readable output that never asks you questions.

You can run `lpui` from any folder. By default it stays out of your repo: it uses the first existing agent-local skill DB, else the global database. Only team-initialized repos resolve into the repo.

Where does it look for the database? The first match wins: `--db PATH`, then `$LAZYPLAN_DB`, then the repo's team-initialized `.agents/lazyplan/lazyplan.db`, then the first existing agent-local skill DB, then the global `~/.local/share/lazyplan/lazyplan.db`. For teams, commit `.agents/lazyplan/config.json` to share the plan. The `*.db` file itself stays local (it is gitignored) unless you force-add it.

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

- You start a plan tree with a bar of shortcuts at the bottom, like nano. Starting out? Your agent asks you first what you want to build, why it matters, and how you will know it is done. Then it writes that down as the plan.
- Once you agree on the plan, your agent breaks it into milestones, then breaks each milestone into small prioritized tasks. It always works on `p0` first.
- Rows that came from a git commit show a short commit chip. Press `enter` on a row to see its commits in a read-only panel.
- You and your agent share one SQLite file. The screen refreshes every second and tells you when something new arrives. Your agent never touches the screen itself. Big decisions about wording and scope stay a conversation with you.

| key | what it does |
|---|---|
| `j`/`k`, arrows, click | move around and select · `enter`/double-click edits in place · `left`/`right` fold and unfold |
| `n` | new item (task→milestone→plan, depending on where you are) |
| `P`/`M`/`T` | new plan / milestone / task |
| `e` / `d` | edit · delete (it asks you to confirm) |
| `space` / `c` | move to next status · tick off the first open checklist item |
| `z` / `Z` | fold one group / fold everything |
| `f` / `o` | filter by status / filter by plan |

Agents use the `lpui` command line. The screen is keyboard-only with no place to type commands. For the full key list, run `lpui help` (or press `?` inside the app).

## CLI reference

The package installs full help text. Start here:

```bash
lpui --help              # globals + examples + env/files/exit codes
lpui --version           # print the installed version and exit
lpui <command> --help    # per-command flags, e.g. lpui add-task --help
man lpui                 # full manual (also `man lazyplan`); installed to share/man/man1
lpui help                # screen key bindings (same as `?` in the app)
```

Flags work before or after the command (`lpui list --json` means the same as `lpui --json list`). On commands that change data, `--actor NAME` records who did it so you can see it in `feed`.

```bash
lpui seed
lpui list [--status todo|doing|done|all] [--archived] [--plan ID] [--priority p0] [--all] [--limit N]  # default: 5 most recent
lpui show --kind plan|milestone|task --id N   # full context: why/what + criteria + commits + children
lpui add-plan --title "API v2" --why ".." --what ".." --priority p1
lpui add-criteria --kind plan --id 1 --text "works offline"
lpui check --id 1 / lpui uncheck --id 1        # tick acceptance items (advisory)
lpui add-milestone --plan 1 --title "Auth refresh" [--desc .. --priority p0]
lpui add-task --milestone 1 --title "Rotate tokens" [--desc ctx --priority p1]
lpui link --kind task --id 1 [--sha HASH]      # attach HEAD (git repos only; disabled otherwise)
lpui commits --kind task --id 1                # list linked commits (empty outside git)
lpui unlink --kind task --id 1 --sha HASH      # detach a commit
lpui link-repo --kind plan --id 1 --repo ~/checkouts/api [--remote URL]
lpui unlink-repo --kind plan --id 1 --repo ~/checkouts/api
lpui repos --kind task --id 1 [--effective]    # explicit links, or inherited
lpui list [--repo ~/checkouts/api]             # filter by effective repo
lpui export [--format json|markdown] | lpui import --file dump.json
lpui update --kind task --id 1 [--title --desc --priority p0|none]
lpui update --kind plan --id 1 [--title --what --why --priority p0|none]
lpui status --kind task --id 1 --to doing    # closing with open criteria warns, never blocks
lpui delete --kind task --id 1
lpui feed [--limit 20]            # recent human/agent activity
lpui watch [--limit 20]           # tail (agents: lpui feed --json --follow &)
lpui --actor helper add-task --milestone 3 --title "Draft proposal"
```

Exit codes: `0` means it worked · `1` means the row was not found · `2` means the flags or input were wrong · `3` means the screen cannot start because Textual is missing. If that happens, reinstall with dependencies: `pip install "lazyplan-tui"` or `pipx reinstall lazyplan-tui`.

## Agents

Your agent talks to the same database through the command line. It only needs the standard library (it never imports the screen code). Every command accepts `--json`. Exit codes tell scripts what happened. Each write carries an `--actor NAME` label (it defaults to `$USER`) so you can see in `feed` who did what.

```bash
lpui --actor helper list --json                    # read the tree
lpui --actor helper show --kind plan --id 1    # full context: why/what + criteria
lpui --actor helper add-task --milestone 1 --title "Draft proposal" --priority p1
lpui feed --json --follow &                         # tail activity (polls every second)
```

How your agent is expected to work: it asks you about the plan first (why it exists, what it covers, how you will know it is done, how urgent it is — it never makes that up). On implementation requests it hunts ambiguity first: in/out scope, touch-points, edge cases, non-goals, assumptions. Then it breaks the work into milestones and prioritized tasks. It looks up ids with `list` instead of guessing them. It prefers `update` and `status` over deleting and re-creating. It works on `p0` first. Every row is written for scanning — paragraphs and sections, never a single blob or placeholder text. The full contract lives in the repo skill file `.agents/skills/lazyplan/SKILL.md`. If you contribute code, follow the design rules in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Data, backup, replicas

- Zero-touch by default: `lpui init` keeps skills plus a sibling `lazyplan.db` in each agent-local skill dir and writes nothing to your repo. For teams, `lpui init --team` creates `.agents/lazyplan/lazyplan.db` next to the code it plans. The `.agents/lazyplan/config.json` file marks which folder it belongs to. Commit the config file so your team shares the plan. The database itself stays on your machine.
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

Before you push, `./tools/check.sh` must pass: `ruff check` plus `ruff format --check`, `mypy` in strict mode (every function needs types, no `type: ignore` without a TODO link), the man page matching the code (`tools/gen-man.py`), and the full test suite on both interpreters. The version lives in one place only: `version = "x.y.z"` in `pyproject.toml` (`tests/test_version.py` checks that the README header matches; `tools/bump.sh` updates both, plus the download links on the site).

## Project

- Docs site: <https://fluxion-dev.github.io/lazyplan/>
- Repository: <https://github.com/fluxion-dev/lazyplan>
- Releases (binaries, debs, rpms): <https://github.com/fluxion-dev/lazyplan/releases>
- Issues: <https://github.com/fluxion-dev/lazyplan/issues>
- Changelog: <https://github.com/fluxion-dev/lazyplan/releases> (written automatically for each release)

This repo plans itself right here: run `lpui list`. License: MIT — see [LICENSE](LICENSE).
