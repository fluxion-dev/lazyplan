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

Run the app from the working tree with `lpui`.

## Before you push

```bash
./tools/check.sh
```

The gate runs:

- `ruff check` and `ruff format --check`
- `mypy` in strict mode
- `vulture` for dead code and `xenon` for complexity
- the man-page sync check (`tools/gen-man.py --check`)
- the docs allowlist and link gate (`tools/check-docs.py`)
- the site discoverability check (`tools/check-site.py`)
- a clean-install smoke that builds, installs, and runs both console scripts
- the unittest suite on both system Python and the venv Python
- the visual snapshots and the performance budgets

On Windows, run it from Git Bash. CI runs the same gates on Linux and macOS for
every change; Windows runs the suite nightly in
`.github/workflows/ci-windows.yml`. The required `gates` check passes when
Ubuntu and macOS pass.

Fix failures rather than editing the scripts around them. If you add a module,
add tests and type annotations with it.

## Tests

Tests mirror the package under `tests/`. Shared fixtures live in `tests/support/`;
use `sandbox_home` for anything that touches a home directory. Run one module
directly:

```bash
PYTHONPATH=src python -m unittest tests.cli.test_version
```

Run the whole suite from the repository root, because discovery needs `tests.*`
and `tests/support`:

```bash
python -m unittest discover -s tests -t .
```

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
merge, squash, or rebase. A pull request does not need an approving review, but
it cannot merge without `gates`.

Only repository admins bypass the ruleset, for emergencies and for the first
apply. Release automation does not: the `bump` workflow opens a release pull
request, and `tag-release` creates the version tag after that PR merges.

Do not add write deploy keys to this repo; use a pull request, or a read-only
deploy key for automation that only fetches. Do not edit the ruleset in the
GitHub settings page: change `.github/rulesets/main.json`, then run
`tools/protect-main.sh` and commit the result.

## Release

Release automation lives in `.github/workflows/`: `bump.yml` opens the release
pull request, `tag-release.yml` tags after it merges, and `release.yml`
publishes. Do not tag a red commit. `pyproject.toml` is the version source;
`tools/bump.sh` mirrors it into the README, site, and man page.

## Style

- Plain words in user-facing text. Name the outcome, not the implementation.
- Keep functions small enough for `xenon` C; extract helpers instead of nesting.
- No dead code. `vulture` fails on it outside the allowlist.
- Every public behavior gets a test, especially setup layout and CLI parsing.
- Read and write text through `lazyplan.textfile`; a test fails on any call that
  falls back to the platform encoding.

## Docs

The human doc set is `README.md`, this file, and [docs/usage.md](docs/usage.md).
Put detail in the usage guide, not back into the README, and follow the policy
in [AGENTS.md](AGENTS.md).
