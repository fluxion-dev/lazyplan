# Contributing to lazyplan

Thanks for helping. lazyplan is a small Python project with a terminal UI, a
CLI, and an agent skill, all backed by one SQLite database.

## Set up

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
py -m venv .venv; .venv\Scripts\Activate.ps1
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

On Windows, run it from Git Bash. CI runs the same gates on Linux, macOS, and
Windows; the required `gates` check passes only when all three pass.

The gate suite runs:

- `ruff check` and `ruff format --check`
- `mypy` in strict mode
- `vulture` for dead code and `xenon` for complexity
- the man page sync check (`tools/gen-man.py --check`)
- the unittest suite on both system Python and the venv Python

Fix failures rather than editing the scripts around them. If you add a new
module, add tests and type annotations with it.

## Landing changes

`main` is protected by the committed ruleset in
`.github/rulesets/main.json`. Every change lands through a pull request:

```bash
git switch -c my-change
# edit, then commit in small green slices
git push -u origin my-change
gh pr create --base main --fill
```

Wait for the `gates` check from `.github/workflows/ci.yml`, then merge with
merge, squash, or rebase. A pull request does not need an approving review,
but it cannot merge without `gates`.

Only repository admins bypass the ruleset, for emergencies and for the first
apply. Release automation does not: the `bump` workflow opens a release pull
request, and `tag-release` creates the version tag after that PR merges.

Write deploy keys bypass rulesets the same way an admin does. A temporary
write deploy key fast-forwarded `main` during the first apply. Do not add
write deploy keys to this repo; use a pull request, or a read-only deploy key
for automation that only fetches.

Manage the live ruleset with the committed payload:

```bash
tools/protect-main.sh --status   # what is applied now
tools/protect-main.sh --dry-run  # print the payload, write nothing
tools/protect-main.sh            # create or update; a second run is a no-op
```

Do not edit the ruleset in the GitHub settings page. Change the payload, run
the script, and commit the result.

## Project layout

```text
src/lazyplan/cli.py        command dispatch and setup entry
src/lazyplan/cli_parser.py argparse surface
src/lazyplan/setup.py     first-run setup state, findings, and moves
src/lazyplan/setup_ui.py  setup wizard rendering and plain fallback
src/lazyplan/setup_layout.py resolved setup resources and repairs
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

## Screenshots

Site screenshots come from the real TUI, never hand-drawn. `tools/capture-screens.py`
builds a throwaway git repo and plan database with fixed commit dates and a
fictional `acme/web` remote, opens the source trail at 130x35, and writes the
PNG and WebP into `site/public/screens/`.

```bash
.venv/bin/python tools/capture-screens.py
.venv/bin/python tools/capture-screens.py --out /tmp/shots --keep-svg /tmp/trail.svg
```

Requires `git`, ImageMagick 7 with WebP and librsvg, and textual installed in
the venv. The fixture is deterministic: two runs produce byte-identical files,
so a diff of the committed images shows exactly what changed. Add new content
by extending `COMMITS` and `PRS` in the tool, then commit both formats and
delete the intermediate SVG.

## Style

- Plain words in user-facing text. Name the outcome, not the implementation.
- Keep functions small enough for `xenon` C; extract helpers instead of nesting.
- No dead code. `vulture` fails on it outside the allowlist.
- Every public behavior gets a test, especially setup layout and CLI parsing.
- Read and write text through `lazyplan.textfile`; a test fails on any call that
  falls back to the platform encoding.
- Tests that touch a home directory call `sandbox_home` from `tests/home_sandbox.py`.
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
