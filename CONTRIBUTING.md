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

The marketing site in `site/` builds with Node 22:

```bash
cd site && npm ci
```

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
- the site build and discoverability check (`site/`, `tools/check-site.py`)
- a clean-install smoke that builds, installs, and runs both console scripts
- the performance budgets
- the unittest suite on both system Python and the venv Python

On Windows, run it from Git Bash. CI runs the same gates on Linux and macOS for
every change; Windows runs the suite nightly in
`.github/workflows/ci-windows.yml`. The required `gates` check passes when
Ubuntu and macOS pass.

For a Windows-only failure, dispatch `.github/workflows/windows-focus.yml` with
the failing unittest module names.

Fix failures rather than editing the scripts around them. If you add a module,
add tests and type annotations with it.

## UX review board

`site/ux/` reviews every captured TUI, CLI, and setup screen in one place.
Regenerate the screenshots, build the site, and serve it:

```bash
.venv/bin/python tools/capture-ux-review.py
cd site && npm run build && cd ..
python tools/ux-review-server.py
```

Open <http://127.0.0.1:8765/lazyplan/ux/>. Submissions go to the ignored
`.agents/ux-review/feedback.json`; the page also exports JSON and Markdown and
generates a `plan apply` document for the UX refresh. Without the server it
keeps feedback in the browser.

## Tests

Tests mirror the package under `tests/`. Shared fixtures live in `tests/support/`;
use `sandbox_home` for anything that touches a home directory. Coverage favors
logical validation, CLI end-to-end runs, and store/service integration;
presentation logic lives in `tests/presentation/` without rendering a TUI.

Run one module directly:

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

The [information architecture spec](docs/information-architecture/spec.md)
defines the target entity model, journeys, taxonomy, keymap, and parity rules.
The [inventory](docs/information-architecture/inventory.md) lists every TUI,
CLI, MCP, setup, hook, and documentation path; its
[findings](docs/information-architecture/findings.md) rank the known gaps.
The generated [reachability report](docs/information-architecture/reachability.md)
proves the three-interaction budget.

## Add one action across every surface

The registry is the source of truth. To add a canonical action:

1. Add the `Action` row in `presentation/shared/registry_actions.py` (or
   `registry_actions_provenance.py`) with a noun-first id, label, key, context,
   route, and the surfaces it should reach.
2. Map it in `presentation/shared/registry_surfaces.py`: CLI paths in
   `CLI_ACTIONS`, MCP tools in `MCP_ACTIONS`, or an explicit
   `SurfaceException` with a reason. A gap fails
   `tests/ia/test_surface_parity.py`.
3. Wire the TUI handler in the owning mixin, add the palette command in
   `registry_commands.py`, and point its `handler` at the app action.
4. Add the CLI parser path and command handler, then the MCP tool and schema if
   the action declares `mcp`.
5. Update `docs/usage.md`, the site copy, and the packaged skill; regenerate
   the man page (`tools/gen-man.py`) and the inventory/reachability reports.
6. Run the gates: `ruff`, `mypy`, `tests.ia`, and `./tools/check.sh`.

Worked example: adding `criterion edit` meant one action row, one CLI path
(`criterion edit`), one MCP tool (`criterion_edit`), a hub key (`e`), a store
method (`update_criterion`), a usage example, and a parity test row. The same
checklist applies to a throwaway action in a test: add the row, extend both
maps, and `registry.uncovered()` must stay empty.
