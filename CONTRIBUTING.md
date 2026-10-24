# Contributing to lazyplan

Thanks for helping. lazyplan is a small Python project with a terminal UI, a
CLI, and an agent skill, all backed by one SQLite database.

## Set up

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the app from the working tree:

```bash
lpui
```

## Before you push

```bash
./tools/check.sh
```

The gate suite runs:

- `ruff check` and `ruff format --check`
- `mypy` in strict mode
- `vulture` for dead code and `xenon` for complexity
- the man page sync check (`tools/gen-man.py --check`)
- the unittest suite on both system Python and the venv Python

Fix failures rather than editing the scripts around them. If you add a new
module, add tests and type annotations with it.

## Project layout

```text
src/lazyplan/cli.py        command dispatch and init flow
src/lazyplan/cli_parser.py argparse surface
src/lazyplan/init_layout.py resolved init resources and repairs
src/lazyplan/store.py      SQLite persistence
src/lazyplan/tui.py        Textual app
src/lazyplan/tree_nav.py   shared tree gestures (j/k, left/right, click)
src/lazyplan/screens.py    detail and form screens
src/lazyplan/design.py     one source of truth for TUI styling
src/lazyplan/skills.py     agent skill text and install
tests/                     unittest suite (stdlib + venv)
docs/                      usage, release, and design notes
site/                      marketing site (Vite)
```

Keep the CLI and the TUI on the same data model. The plan is the design: write
the row before the code, and keep the row current when the code changes.

## Style

- Plain words in user-facing text. Name the outcome, not the implementation.
- Keep functions small enough for `xenon` C; extract helpers instead of nesting.
- No dead code. `vulture` fails on it outside the allowlist.
- Every public behavior gets a test, especially init layout and CLI parsing.
- Do not add a second source of truth for the version. `pyproject.toml` wins;
  `tools/bump.sh` mirrors it into the README, site, and man page.

## Docs

- [Usage and CLI reference](usage.md)
- [Release steps](releasing.md)
- [TUI design system](design-system.md)

The README is the short landing page. Put detail in `docs/usage.md`, not back
into the README.

## Release

Release notes, tags, and rollback steps live in [docs/releasing.md](releasing.md).
Do not tag a red commit.
