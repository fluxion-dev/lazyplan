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
- a clean-install smoke that builds a wheel, installs it into a throwaway
  venv, and checks both console scripts (`tools/check-install.sh`)
- the unittest suite on both system Python and the venv Python
- the performance budget check (`tools/perf_bench.py --check`; see
  `docs/performance.md`)

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

This is the target tree for P103. Entries marked `planned` do not exist yet;
the milestone that creates them removes the marker.

```text
src/lazyplan/
  kinds.py models.py messages.py textfile.py
  porcelain.py docs_meta.py              leaf helpers and data types
  repo.py vcs.py forge.py github.py      infrastructure adapters
  templates.py
  migrate.py                             schema migrations
  store/                                 SQLite persistence (planned)
    base.py plans.py claims.py annotations.py links.py views.py
  services/                              use-case orchestration (planned)
    plans.py claims.py tasks.py vcs.py forge.py tree.py transfer.py
  audit.py brief.py hooks.py issues.py   domain reports and hooks
  seed.py share.py source.py stats.py trace.py lint.py
  cli/                                   agent and human ingress (planned)
    main.py emit.py rows.py
    parser/                              argparse by noun (planned)
    commands/                            handlers by noun (planned)
  setup/                                 first-run flow (planned)
    state.py findings.py apply.py moves.py wizard.py ui.py layout.py
  tui/                                   Textual app (planned)
    app.py tree.py preview.py git_state.py filters.py rows.py updates.py
    screens/                             forms, detail, help, palette, source
  mcp/                                   MCP server, tools, resources (planned)
  palette.py                             shared command metadata (planned rename)
  design.py render.py skills.py
  data/                                  packaged skill and AGENTS text (planned)
tests/
  support/                               shared home and pilot helpers (planned)
  store/ services/ cli/ setup/ tui/      domain suites (planned)
  vcs/ skills/ site/ fixtures/
docs/                                    usage, release, and design notes
site/                                    marketing site (Vite)
tools/                                   gates, benchmarks, and release scripts
```

Keep the CLI and the TUI on the same data model. The plan is the design: write
the row before the code, and keep the row current when the code changes.

## Architecture

Dependencies point one way:

```text
leaf -> infrastructure -> store -> domain -> services -> presentation -> entry point
```

- `models`, `kinds`, `textfile`, `messages`, `porcelain`, and the palette
  metadata are leaves. They import no store, service, or UI code.
- `repo`, `vcs`, `forge`, `github`, and `templates` are infrastructure. They
  may use leaves.
- `store` owns SQLite and may use leaves, infrastructure, and `migrate`.
- Domain modules (`audit`, `brief`, `hooks`, `issues`, `share`, `source`,
  `stats`, `trace`, `lint`) may use the layers below them.
- `services` may use domain, store, infrastructure, and leaves.
- `cli`, `tui`, `setup`, `mcp`, `design`, `render`, and `skills` are
  presentation. They may use everything below them.
- `__main__` is the only entry point and may import any package.

A new top-level module needs a layer entry in `tests/test_architecture.py`.
`tests/test_module_budget.py` enforces the 600-line budget and records temporary
exceptions in `tests/architecture_baseline.json`. Shrink an exception in the
commit that splits the file, and delete it once the file is under budget.

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

## Download stats

The landing page shows PyPI downloads from a same-origin snapshot:

```bash
python3 tools/fetch-downloads.py
```

It reads pypistats `overall`, sums the `without_mirrors` series, and writes
`site/public/downloads.json` atomically. A network or validation failure writes
`{"available": false}` and exits 0, so a deploy is never blocked; the page hides
the strip in that case or when the snapshot is older than seven days. The JSON
is gitignored, and the Pages workflow refreshes it before every build on a
daily schedule.

## Style

- Plain words in user-facing text. Name the outcome, not the implementation.
- Keep functions small enough for `xenon` C; extract helpers instead of nesting.
- No dead code. `vulture` fails on it outside the allowlist.
- Every public behavior gets a test, especially setup layout and CLI parsing.
- Read and write text through `lazyplan.textfile`; a test fails on any call that
  falls back to the platform encoding.
- Tests that touch a home directory call `sandbox_home` from `tests/support/home.py`.
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
