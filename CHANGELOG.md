# Changelog

Notable user-facing changes to lazyplan (`lpui`). Releases before 0.26.0 are
documented on the [GitHub releases page](https://github.com/fluxion-dev/lazyplan/releases).

## Unreleased

### New

- The plan tree no longer renders its non-selectable `plans` root row; plans
  are the top-level rows.
- The plans panel takes 35% of the shell width, leaving 65% for the preview.
- The PLANS and PREVIEW border headings are left-aligned.
- The bottom dashboard is now a wall-clock Gantt card spanning the full width
  and 45% of the shell height (14-row minimum), with no `METRICS` border title.
  Projects, milestones, and focused tasks each get one compact swimlane.
- Traces cover only `doing` intervals. Todo, paused, and done gaps render no
  line, but the lane and its legend label remain; resumed work shows separate
  segments with start and finish dots.
- Open work shows a `now` marker. The time axis adapts its tick count and
  date/time format to the span, and no-plan or no-milestone states render
  centered copy inside the chart.
- The legend is horizontal at the top, uses `═` for projects, `─` for
  milestones, and `·` for tasks, truncates titles with an ellipsis, and folds
  overflow into `+N more`.
- Selecting a milestone or task adds the focused milestone's task lanes and
  marks the selected task. Large lane sets scroll vertically at one row each.
- The Gantt refreshes within the one-second database poll and advances open
  lanes and the now marker every 15 seconds. The Daily activity, Task status,
  and Project progress cards are removed.
- An empty plans panel shows a centered `nothing planned... yet` message
  instead of a blank tree.

### Under the hood

- `metrics.snapshot(store, plan_id=..., scope_kind=..., scope_id=...)` derives
  doing intervals from status events, adds focused task lanes, and keeps the
  existing read-only aggregate fields.
- `MetricsController` owns the 120 ms selection debounce, the 15-second now
  tick, and refresh after a tree rebuild.
- `tui/metrics/timeline_layout.py` holds the pure axis, lane, legend, glyph,
  and segment helpers so `TimelineCard` stays a thin Plotext renderer.

### Documentation

- Updated the metrics dashboard sections in `docs/usage.md` and
  `docs/design-system.md`.

## v0.29.0 — 2026-10-31

Live update checks in an open TUI. The status bar keeps the update chip current,
and a release published while the app is open appears within minutes instead of
waiting for the next launch.

### New

- The TUI re-reads the shared update cache every 60 seconds.
- The network check runs at most once every 5 minutes through a shared gate in
  the lazyplan home, so several open instances still make one request.
- A failed check records a 15-minute backoff and keeps using the cached version
  instead of retrying every minute.
- The status chip updates when a newer version appears and clears when the
  installed version catches up. Each version toasts once; a newer version
  toasts again.

### Under the hood

- Added `poll_interval`, `network_interval`, `claim_refresh`, `defer_refresh`,
  and `refresh_update` to `upgrade`.
- `LAZYPLAN_UPDATE_INTERVAL` and `LAZYPLAN_UPDATE_NETWORK_INTERVAL` override the
  cadence; values are clamped, and invalid values fall back to the defaults.
  `LAZYPLAN_NO_UPDATE_CHECK` still disables both checks.
- The update timer stops on unmount, and one guarded worker prevents overlapping
  checks. The CLI notice stays cache-only.
- Tests cover defaults, overrides, clamping, gate contention, backoff, chip
  clearing, and toast semantics.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.28.1 — 2026-10-31

Refuses downgrades in every update path. The staged-update flow and `lpui
upgrade` reject a target older than or equal to the installed version before
any download or installer runs.

### Fixed

- `stage_update` refuses a non-newer target before fetching a wheel.
- `apply_update` and apply-on-launch refuse an older or equal staged version
  without running pipx or pip. A planted older stage is cleared.
- `run_upgrade`, `upgrade_pipx`, and `upgrade_venv` refuse a downgrade before
  building a command.
- The Update screen hides Download when the latest release is not newer, and a
  stale cached notice no longer opens it.
- Tests cover staging, apply, both runners, the screen, and the cached notice.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. Downgrades are intentionally unsupported;
there is no rollback flag.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.28.0 — 2026-10-31

Staged updates in the TUI. When a newer release exists, the status bar shows
`update vX.Y.Z` and `U` opens an Update screen. Download verifies the PyPI wheel
and caches it; the next TUI launch applies it and re-execs into the new version.

### New

- The update notice now names the latest version, and `U` or the **Update lpui**
  palette command opens a dedicated Update screen.
- The screen shows installed and latest versions plus the install method, with
  **Download** and **Later** for pipx and venv installs.
- Download fetches the exact PyPI wheel, verifies its SHA256, and keeps one
  staged slot under the shared home.
- The next TUI launch installs the cached wheel and re-execs before the
  interface opens. Agent and `--json` calls never download or apply.
- rpm, deb, and source installs keep their package-manager or `git pull`
  guidance. A failed download leaves no stage; a failed apply keeps the old
  version runnable and reports one retryable notice.

### Under the hood

- Added `update_stage` with atomic claim, digest re-verification, and pipx/venv
  installers.
- Added headless TUI and cache tests, registered the module with the
  architecture layer guard, and extended the vulture allowlist for Textual
  dispatch.
- Documented the flow, cache paths, recovery, and screen in the usage guide and
  design system.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.27.2 — 2026-10-31

Removes the redundant source marker from every row. Git integration, commit and
PR links, the source trail, and the database schema are unchanged.

### Changed

- Plan, milestone, task, and source-trail rows no longer end in a marker glyph.
  Commit and PR chips, the preview, and the detail page still show provenance.
- Plain CLI row output drops the same suffix; scripts that parsed it should
  read the chips or `lpui show --files` instead.

### Under the hood

- Deleted the unused marker helpers and branch icon entries, plus the
  row-builder plumbing that only fed them.
- Updated TUI, CLI, and docs tests to assert the remaining chips.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged, and every
existing commit, pull request, and repo link is preserved.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.27.1 — 2026-10-28

Maintenance release for the layered package restructure. CLI commands, TUI
behavior, and the SQLite schema are unchanged; this release is about making the
codebase easier to review, package, and verify.

### Under the hood

- Split the 2,369-line store into focused persistence mixins: plans, tasks,
  claims, annotations, links, repos, views, and shared declarations.
- Split services into plans, claims, tasks, VCS, forge, tree, and transfer
  modules behind the unchanged `lazyplan.services` API.
- Split the CLI into `cli/`, noun-grouped `cli/commands/`, and role-grouped
  `cli/parser/`; renamed the palette registry and published the payload
  serializer.
- Split first-run setup into stage modules and the Textual app into feature
  mixins with a `tui/screens/` package. `design.py` remains the styling source
  of truth.
- Moved the bundled skill and AGENTS text into packaged `lazyplan/data/` and
  split the MCP server into protocol, tool, and resource modules.
- Grouped tests by domain, removed every test `sys.path` edit, and added
  shared `tests/support/` helpers.
- Added architecture guards for import cycles, layer inversions, and a
  600-line module budget.
- Fixed the PEP 639 license metadata, required `setuptools>=77`, pinned
  `textual>=8.2.8,<9`, and added a clean-install smoke gate to `tools/check.sh`.
- Fixed a platform-encoding regression in the download snapshot tests.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged. Back up
first with `lpui export --format json` if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Contributor layout](https://github.com/fluxion-dev/lazyplan/blob/main/CONTRIBUTING.md#project-layout)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## v0.27.0 — 2026-10-27

Windows parity and a performance sweep through the read paths. The coordination,
review, and provenance features from 0.26 are unchanged.

### Windows support

- Install with `pipx install --backend pip lazyplan-tui`; the shared home is
  `%LOCALAPPDATA%\lazyplan` and the default actor is `%USERNAME%`.
- Standard input, output, error, and plan files use UTF-8. Reads accept UTF-8 or
  UTF-16 with a BOM, and writes preserve existing CRLF line endings.
- Claude Code hooks match both `Bash` and `PowerShell` and drop the unsupported
  `PreCompact` event; `SessionStart` re-injects the brief after compaction.
- `lpui upgrade` manages pipx and venv installs on Windows.
- CI runs the full gate suite on Linux, macOS, and Windows.

### Performance

- `tools/perf_bench.py` builds an 88-plan, 789-task fixture and gates exact query
  counts plus generous wall ceilings from `tools/check.sh` on all three platforms.
- On the fixture, tree load falls from 909 queries to 12, `list --json` from
  7,853 to 18, export from 18,612 to 26, audit from 4,740 to 202, and TUI refresh
  from 5,148 to 139.
- Reads batch through bulk maps; the TUI refreshes from one tree snapshot, moves
  git and diff work to workers, and stops rebuilding on view-only changes.
- Read indexes and a schema-version fast path make repeat opens cheaper.
- Update notices are cache-only, so list, show, next, hooks, MCP, and porcelain
  calls make no network request.

### Documentation and site

- README, usage, setup, performance, the bundled agent skill, and the man page
  cover Windows paths, encoding, hooks, upgrades, and the benchmark.
- The homepage has a 0.27 band, a Windows section, a performance section with the
  fixture results, and a PowerShell quickstart. The top navigation collapses into
  Product, Capabilities, and Learn menus, with a mobile panel.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. An existing database picks up the new read
indexes and schema version the first time the CLI opens it. Back up first with
`lpui export --format json` if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Performance and benchmarks](https://github.com/fluxion-dev/lazyplan/blob/main/docs/performance.md)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## v0.26.0 — 2026-10-26

This release turns the plan into a coordination surface: agents claim work
safely, proof stays attached to the row, reviewers can comment, and done can
wait for real evidence.

### Agent coordination

- `lpui next` atomically claims the first eligible todo with a renewable lease.
- `claim take`, `claim renew`, `claim release`, and `claim --force` manage
  specific tasks; expired leases are reclaimable.
- Notes are append-only on plans, milestones, and tasks and appear in `show`,
  `brief`, porcelain, and the TUI preview.
- `task block --reason` and `task unblock` park work without adding a fourth
  status; blocking records the reason and releases the claim.
- The TUI shows active and expired claims, blocked badges, and a `marked` count.

### Flow health

- `lpui stats --since 30.days [--by NAME] [--stale-after 1.days]` reports WIP,
  median cycle time, throughput, aging, stale todos, reopened rows, active
  claims, and blocked tasks.
- Stats support `--json` and six-column porcelain output and never call the
  network.
- The TUI **Attention** source filter surfaces expired claims, blocked tasks,
  aging doing work, done rows with open criteria, and red PR checks.

### Traceability and lint

- `criterion relate` and `criterion unrelate` link acceptance items to proving
  tasks; relations survive export/import.
- `lpui trace --plan|--criterion` walks criterion → task → commit → PR.
- `lpui lint --plan --strict` flags uncovered criteria, missing commit-slice or
  verification tokens, placeholder text, and done rows with open criteria.

### MCP server

- `lpui mcp` serves Model Context Protocol over stdio with no extra dependency.
- Read tools cover the brief, plans, rows, claims, audit, trace, lint, and info;
  write tools cover the journal, criteria, claims, notes, blocked work, and
  commit links.
- Resources expose `lazyplan://brief` and `lazyplan://plan/{id}`.
- `--read-only` hides and rejects writes and never creates a missing database.

### Collaboration

- Comments support add/list/resolve/unresolve and `@mention` filtering on plans,
  milestones, and tasks; unresolved comments appear in the detail pane.
- `lpui share --plan P` writes escaped HTML or safe JSON snapshots with no
  tokens, auth state, raw payloads, or cache records.
- Plans carry stable UIDs, generated for existing databases.
- `lpui sync --file dump.json [--dry-run]` adds unknown plans, skips identical
  plans, and reports conflicts without deleting or overwriting local work.
- Sync is plan-granularity; row-level merge is intentionally out of scope.

### Completion gates

- `task finish --require-pr` needs at least one linked pull request.
- `task finish --require-checks` needs every linked PR's cached checks to be
  `pass`, `neutral`, or `skipped`.
- Gates read cached state only; run `pr refresh` to update it. A failure exits 2
  and leaves the task doing with no commits linked.
- `--override REASON` records the actor, reason, and gate state, then completes.
- `task start` rejects a branch already recorded on another open task in the
  same checkout or remote and names the owner.

### Issue imports

- `lpui issue import --provider github --repo OWNER/REPO` imports live issues
  and skips pull requests.
- `lpui issue import --provider linear --file export.json` imports a Linear JSON
  export.
- `--as plan|task`, `--milestone`, and `--dry-run` control placement and writes.
- Re-import dedupes by provider + external id and refreshes cached source
  metadata only; imports are one-way with no writeback and no raw payloads.

### Search and bulk edit

- `/` searches titles, descriptions, why/what, notes, comments, claim actors,
  blocked reasons, and issue refs.
- `space` marks rows; marks survive refresh and are session-only.
- Palette bulk actions move marked tasks to doing/done, block with a reason,
  release claims, clear marks, and undo the last status/block change once.
- Bulk delete and archive remain single-row because undo cannot safely recreate
  subtrees.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. Existing databases gain plan UIDs and the new
tables when the CLI opens them. Back up first with `lpui export --format json`
if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## Earlier releases

See [GitHub releases](https://github.com/fluxion-dev/lazyplan/releases) for
v0.25.0 and earlier.
