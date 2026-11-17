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
- the packaged Textual skill coverage check (`tools/gen_textual_skills.py --check`)
- the man-page sync check (`tools/gen-man.py --check`)
- the docs allowlist and link gate (`tools/check-docs.py`)
- the packaged changelog sync check (`tools/check-changelog.py`)
- the site build and discoverability check (`site/`, `tools/check-site.py`)
- a clean-install smoke that builds, installs, and runs both console scripts
- the performance budgets (`tools/perf_bench.py --check`: exact query ceilings on a deterministic fixture)
- the unittest suite on both system Python and the venv Python

On Windows, run it from Git Bash. CI runs the same gates on Linux and macOS for
every change; Windows runs the suite nightly in
`.github/workflows/ci-windows.yml`. The required `gates` check passes when
Ubuntu and macOS pass.

For a Windows-only failure, dispatch `.github/workflows/windows-focus.yml` with
the failing unittest module names.

Fix failures rather than editing the scripts around them. If you add a module,
add tests and type annotations with it.

## Performance

`tools/perf_bench.py --check` is the performance gate. It builds a deterministic
journal in a temp directory and holds exact query ceilings for the tree, list,
show, export, audit, fingerprint, and TUI paint/reconcile/expand paths, plus
cold CLI startup. Wall ceilings stay generous so runner variance does not fail
a pull request.

When you change a measured path:

1. Run `python tools/perf_bench.py --repeat 3` before and after, and put both
   numbers in the commit message and the plan note.
2. Lower a budget only to the measured ceiling. A new metric needs a budget
   entry in the same commit.
3. For `site/` or either capture tool, run `python tools/time_phases.py --check`
   and keep the PNG/WebP bytes identical; report the phase numbers.

Do not trade a contract, determinism, or error handling for a number.

## Screenshots and the UX review board

Two capture tools build every screenshot from deterministic fixtures — fixed
dates, synthetic actors, and a fictional `acme/web` remote — so a rerun produces
the same images and no personal data. Both need git, ImageMagick 7 with librsvg
and WebP, and Textual in the venv:

```bash
.venv/bin/python tools/capture-screens.py      # marketing gallery
.venv/bin/python tools/capture-ux-review.py    # every screen, plus scenes.json
```

The first writes `site/public/screens/`; the second writes
`site/public/ux/`, where the review page reads `scenes.json`. Build the site and
serve the board:

```bash
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

### Core suite policy

The suite proves contracts, not implementation. A test belongs in the core
suite when it covers a store row or transaction, a core policy, a service, a
CLI command, an MCP tool, setup acceptance, or a TUI screen's smoke, status, or
resize behavior. `python tools/test_inventory.py --check` holds that matrix:
every core contract names its proving test, and a missing one fails the check.

Use a contract table when cases differ only by an input variant: a host, scope,
status, alias, or backend. Add a row and a `subTest` label instead of a new test
method. Keep one smoke test per screen for mount, render, and focus, and leave
exact markup, mount order, and widget internals out of the suite.

Delete a test only when the behavior it proved is gone or moves into a named
row of a contract table. Error paths, empty states, platform branches, and
safety rules stay direct.

## Resize behavior

Every screen ships a resize matrix. `tests/presentation/test_resize_surfaces.py`
mounts a surface once and walks 40×24, 80×24, 120×40, and 160×50 through
`tests.support.resize`, asserting that regions stay inside the screen, siblings
do not overlap, and selection, cursor, and scroll stay valid.

- Read the tiers from `presentation/tui/size.py` (`classes_for`); do not
  hardcode 80, 100, 120, or 30 in a screen.
- Panels reflow instead of keeping a fixed width. Long text wraps or truncates
  on purpose, and no panel paints outside its region.
- Measure content from the current layout, not from the width a widget had when
  it was last painted.
- After a resize, keep the selected row, cursor, and page when the target still
  exists; clamp to the new maximum when it does not.
- Add a case for every new surface. A case that fails first may land as
  `expectedFailure`; remove the decorator with the fix.

## Flaky tests

A failing gate is never retried to green. A flake is a defect in the test or
the code it exercises: fix the race, the shared state, or the snapshot, and
add a regression test.

- Use `sandbox_home` or a per-test temp directory for anything that reads or
  writes home. Quiesce SQLite before snapshotting a tree.
- Wait for workers, timers, and mount state. `time.sleep` and `asyncio.sleep`
  are rejected by `tools/test_hygiene.py`.
- Run a seeded shuffle before calling a fix done:

  ```bash
  python tools/repeat-tests.py --times 3 --seed 0
  python tools/repeat-tests.py --times 2 --seed 7 --no-tui
  ```

  The runner prints the exact reproducer for the first failure. The nightly
  `flakes` workflow runs the same command on Linux, macOS, and Windows.

- A temporary quarantine lives in `tests/quarantine.json`. Every entry needs a
  test id, a linked task, a reason, and a future `expires` date; a malformed or
  expired entry fails the suite. Permanent skips are not allowed.

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

Bigger feature sets land in two pull requests. The feature branches merge into
one integration branch first, and that pull request carries the code and its
gates. Docs, screenshots, and site copy follow as a second pull request cut from
the merged `main`, so each review stays small and the marketing text is written
against what actually shipped. Both pull requests wait for `gates`; the merge to
`main` owns deployment.

Only repository admins bypass the ruleset, for emergencies and for the first
apply. Release automation does not: the `bump` workflow opens a release pull
request, and `tag-release` creates the version tag after that PR merges.

Do not add write deploy keys to this repo; use a pull request, or a read-only
deploy key for automation that only fetches. Do not edit the ruleset in the
GitHub settings page: change `.github/rulesets/main.json`, then run
`tools/protect-main.sh` and commit the result.

## Release

Release automation lives in `.github/workflows/`: `bump.yml` opens the release
pull request, `tag-release.yml` tags after it merges, `release.yml` publishes
the GitHub Release and PyPI package, and `pages.yml` deploys the site. Do not
tag a red commit. `pyproject.toml` is the version source.

Put the next notes under `## Unreleased` in `CHANGELOG.md` before bumping.
`tools/bump.sh` stamps that heading with the new version and today's date,
copies the changelog into the package, and mirrors the version into the README,
site, and man page. The changelog gate rejects an undated release heading and
an empty `## Unreleased` section.

The bump workflow waits for the gates it dispatches and publishes their result
as the required `gates` status on the release commit. If GitHub still marks the
release pull request's own `pull_request` run `action_required`, approve that run
from the Actions tab; `tag-release` and `pages` run once the pull request merges.

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
   route, the surfaces it should reach, and its CLI command paths
   (`cli_paths`) and MCP tool name (`mcp_tool`). The surface maps derive from
   the rows, so the names are typed once.
2. When a declared surface has no path, record an explicit `SurfaceException`
   with a reason in `presentation/shared/registry_surfaces.py`. A gap fails
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
checklist applies to a throwaway action in a test: add the row with its paths
and `registry.uncovered()` must stay empty.
