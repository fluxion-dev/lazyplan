# Changelog

Notable user-facing changes to lazyplan (`lpui`). Releases before 0.26.0 are
documented on the [GitHub releases page](https://github.com/fluxion-dev/lazyplan/releases).

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
