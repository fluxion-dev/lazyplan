# lazyplan usage

The short start lives in the [README](../README.md). This page keeps the detail:
install options, setup and layout, everyday commands, the screen, agent use, and data.

## Install

The recommended path is pipx:

```bash
pipx install lazyplan-tui
lpui
```

The first `lpui` run finishes setup (agents, skills, database) and opens the
screen. On Windows, use the pip backend:

```powershell
pipx install --backend pip lazyplan-tui
```

On Windows the shared home `~/.lazyplan/` is `%LOCALAPPDATA%\lazyplan\`
everywhere in this guide, and the default `--actor` is `%USERNAME%`.

### Linux packages

System packages include the CLI, man pages, and shell completions. Grab the
matching `.deb` or `.rpm` from [Releases](https://github.com/fluxion-dev/lazyplan/releases).

```bash
# Fedora / RHEL / openSUSE
sudo dnf install ./lazyplan-<version>-1.x86_64.rpm

# Debian / Ubuntu
sudo apt install ./lazyplan_<version>-1_amd64.deb
```

Use the `aarch64` / `arm64` asset on ARM machines.

### One-line installer

Let the installer choose the right method for your machine:

```bash
curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | sh
```

The installer ends with the next step: run `lpui` to finish setup. Pin a
version or choose a method:

```bash
sh install.sh --version X.Y.Z --method rpm|deb|pipx|venv
sh install.sh --method venv --prefix ~/.local
sh install.sh --uninstall
```

### From source

```bash
git clone https://github.com/fluxion-dev/lazyplan.git
cd lazyplan
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell, create the venv with `py -m venv .venv` and activate it
with `.venv\Scripts\Activate.ps1`.

### Upgrade

```bash
lpui upgrade
lpui upgrade --check
```

`lpui upgrade` manages pipx and venv installs. System packages upgrade through
`dnf` or `apt`. The TUI status bar and CLI stderr mention new versions; stdout
stays clean for `--json`. A successful upgrade re-runs setup with the new
binary, including under `--json`, so hooks and the AGENTS pointer refresh
without prompting.

On Windows the same command manages pipx and venv installs. If the automatic
upgrade cannot run, reinstall with `pipx install --backend pip lazyplan-tui`.
A source checkout updates with `git pull`.

## Start

```bash
cd ~/my-plan
lpui
```

The first run sets up lazyplan: it detects your coding agents, installs their
skills, creates the database, and remembers the choices in
`~/.lazyplan/setup.json`. On a terminal you get a short wizard; scripts, agents,
and `--json` get the same defaults without prompts. No separate setup step to remember.

Then create your first plan:

```bash
lpui plan add --title "my-plan" --why "reason" --what "scope"
```

`lpui` with no command opens the screen. `lpui ui` does the same.

## Setup and scope

The full first-run, rerun, switch, and uninstall walkthrough lives in
[setup](setup.md). Setup writes one layout. Re-run it any time to change
placement or agents:

```bash
lpui setup
lpui setup --placement repo --yes
lpui setup --json
```

| Choice | Database and templates | Config | Skills | `AGENTS.md` |
| --- | --- | --- | --- | --- |
| Home (default) | `~/.lazyplan/` | not written | each agent's home skill dir | not written |
| `--placement repo` | `<repo>/.agents/lazyplan/` | repo config | repo skill dirs | repo pointer |
| `--db PATH` / `$LAZYPLAN_DB` | `PATH` and its sibling `templates/` | only for a repo plan dir | none | none |

The wizard asks two questions: where plans live (home or this repo when you are
inside a git checkout) and which detected agents get the skill. Templates use
the opinionated defaults and are written without extra questions. An explicit
`--db` or `$LAZYPLAN_DB` always wins and is never moved.

### Inspect before writing

```bash
lpui doctor
lpui doctor --json
```

Read-only. Exit `0` means clean, `1` means any finding: misplaced resources,
missing hook files, a state-version mismatch, or migration drift. The report
names the resolved database, config, templates, skill paths, hook files, state,
and every finding. It resolves the same database a normal run would open,
including `--db` and `$LAZYPLAN_DB`.

### Upgrades and migration

Setup runs again after a version change and reviews layout drift once per
finding; it does not ask on every command.

- An untracked or ignored repo database is offered once: move it to
  `~/.lazyplan/lazyplan.db`, keep it here, or never ask for that path.
- A database tracked by git is never offered a move; doctor reports it.
- Keep/never is remembered in `~/.lazyplan/setup.json`; a changed state can
  re-arm the prompt.
- Every setup write keeps one tree-preserving backup per run under
  `~/.lazyplan/backups/<timestamp>/`. Unchanged files are never rewritten and
  never backed up.
- If both databases contain plans, setup refuses to merge and prints
  export/import guidance instead.
- Only `lpui`, `lpui setup`, and `lpui upgrade` prompt. Agent calls set up
  silently and never wait for input.

### Where the database resolves

The first match wins:

1. `--db PATH`
2. `$LAZYPLAN_DB`
3. the nearest enclosing `.agents/lazyplan/lazyplan.db`
4. `~/.lazyplan/lazyplan.db` (`%LOCALAPPDATA%/lazyplan` on Windows)

Commit `.agents/lazyplan/config.json` to share a team plan. The `*.db` file stays
local (gitignored) unless you force-add it.

### Setup flags and environment

```bash
lpui setup --agents "opencode,claude"  # or all, or none; $LAZYPLAN_AGENTS
lpui setup --skills-dir PATH           # or $LAZYPLAN_SKILLS_DIR
lpui setup --no-skills                 # database only; $LAZYPLAN_NO_SKILLS
lpui setup --hooks                     # install lifecycle hooks (default)
lpui setup --no-hooks                  # remove installed lifecycle hooks
lpui setup --agents-pointer            # add the marked AGENTS.md section
lpui setup --no-agents-pointer         # remove the marked AGENTS.md section
lpui setup --yes                       # apply without prompts
lpui setup --json                      # machine-readable, no prompts
```

Precedence is explicit flag, then environment, then remembered state, then
detection. The wizard uses the same defaults, so `lpui setup --placement repo`
or `--no-skills` changes what the questions propose.

`LAZYPLAN_NO_SETUP=1` skips first-run setup and upgrade review. `NO_COLOR`,
`LAZYPLAN_NO_COLOR`, `CLICOLOR=0`, and `TERM=dumb` keep the wizard plain.
`LAZYPLAN_NO_SPINNER=1` freezes the doing spinner in the TUI.
`--placement repo` outside a git checkout falls back to home.

## Everyday commands

```bash
lpui list                         # plans and progress
lpui list --tree                  # full plan/milestone/task tree
lpui list --status doing          # filter by status
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing
lpui criterion tick --id 1
lpui feed                         # recent activity
```

Flags work before or after the command: `lpui list --json` is the same as
`lpui --json list`. `--porcelain` switches journal commands to stable
tab-separated rows; `--json` wins when both are present.

## The screen

Plans start collapsed. Press `right` or `z` to reveal milestones; tasks stay
folded until you open their milestone. Completed plans are dimmed and sorted last.

A doing row animates through `◐ ◓ ◑ ◒` while work is in progress. The CLI,
export, preview, and detail views keep the static `◐`; set
`LAZYPLAN_NO_SPINNER=1` to freeze the tree.

| key | action |
|---|---|
| `j`/`k`, arrows, click | move and select |
| `left`/`right`, click arrow | collapse/expand, or walk to parent / first child |
| `enter` | open the read-only detail page |
| `space` | mark or unmark the selected row for bulk actions |
| `e` / `s` / `x` / `a` / `d` | edit · advance status · tick next criterion · add criterion · delete |
| `n` | create by context (plan, milestone, or task) |
| `/` | filter by text |
| `f` | change status filter |
| `F` | change source filter: all, linked, PR, stale, unlinked, claims, blocked, attention |
| `g` | open the source trail for the selected row |
| `A` | show all plans |
| `?` | help |
| `c` | command palette |
| `q` | quit |

The palette and the CLI use the same names: Create plan, Move to doing, Tick
next criterion, Delete selection. The palette also has Bulk move to doing/done,
Bulk block tasks, Bulk release claims, Clear marks, and Undo bulk change. Bulk
status and block confirm first; undo restores the exact prior status/blocked
state once. Bulk delete and archive stay single-row.

`/` searches titles, descriptions, why/what, notes, comments, claim actors,
blocked reasons, and issue refs. Marks are session-only and survive refreshes.

## Performance

lazyplan reads in bulk. The tree, lists, export, audit, MCP, and the TUI
refresh each load their rows in a bounded number of queries instead of one per
row. On the 88-plan, 789-task fixture the tree falls from 909 queries to 12,
`list --json` from 7,853 to 18, export from 18,612 to 26, and TUI refresh from
5,148 to 139.

`tools/perf_bench.py --check` is part of the gate suite and runs on Linux,
macOS, and Windows. The method, before and after table, and query budgets live
in [performance](performance.md).

CLI reads use a cached update notice, so list, show, next, hooks, MCP, and
porcelain calls make no network request.

## Agents

Every command accepts `--json`. Journal commands also accept `--porcelain` for
the active loop. Writes accept `--actor NAME`; the default is `$USER`
(`%USERNAME%` on Windows). The
activity feed shows who changed what.

```bash
lpui --actor helper --porcelain task add --milestone 1 --title "Draft proposal"
lpui --actor helper --porcelain list --tree
lpui --actor helper plan show --id 1
lpui feed --json --follow
```

Your agent is expected to work from the plan, not invent it:

- Ask the human for the plan's why, scope, and acceptance criteria first.
- Hunt ambiguity before implementing: touch-points, edge cases, non-goals,
  assumptions.
- Look up ids with `list`; never guess them.
- Prefer `edit` and `move` over deleting and re-creating.
- Work in creation order.
- Plan the commit sequence before coding: every task lands as one or more
  small, green commits, never one batch for the whole plan or milestone.
- Name each task's expected commit slice and verification in its desc, and
  commit after each task completes rather than deferring work to the end.
- Link commits after the fact with `lpui link` or `task finish`; no commit
  trailer is required. These rules apply to new plans; existing plans are
  not rewritten.
- Write rows for scanning: short paragraphs and sections, no placeholder text.
- If the host supports MCP, prefer `lpui mcp`; otherwise use `--porcelain`.
- Check flow health with `lpui stats --since 7.days`; the human screen uses the Attention filter.
- Leave review comments with `comment add` and share a read-only plan with `share`; sync is plan-granularity.
- Use `task finish --require-pr --require-checks` when done must wait for evidence; overrides are recorded.
- Import provider issues with `issue import`; re-import refreshes source metadata only and never writes back.
- Relate every plan criterion to a proving task and run `lpui --porcelain
  lint --plan P` before check-off.
- Start a session with `lpui --porcelain next` to claim work, or
  `lpui --porcelain brief` for the whole picture. Renew the lease while you
  work, note handoffs, and release it when you stop. Update the journal after
  each commit, then run `lpui --porcelain audit --since 7.days` before closing
  a plan. Lifecycle hooks remind you, but they are read-only.

`lpui setup --placement repo` writes the full contract into the repo; the
default setup installs the skill into each detected agent's own folder.

### Porcelain output

`--porcelain` (or `LAZYPLAN_PORCELAIN=1` for a whole session) switches journal
commands to stable tab-separated rows. Writes answer with one line; overview
and `show` reads keep their facts without glyphs, indentation, repos, commits,
or PR decoration. `--json` wins when both flags are present.

Every row has the same six columns, in this order, with no header:

| column | meaning |
| --- | --- |
| `kind` | record type: `plan`, `milestone`, `task`, `criterion`, `commit`, `repo`, `pr`, or a read record |
| `id` | row id, SHA, path, PR number, or key |
| `status` | lifecycle status, link state, or read-specific state |
| `title` | human name, subject, path, or value |
| `parent` | `-` or `kind:id` of the owning row |
| `extra` | task progress `done/total` for plans and milestones, otherwise `-` or a documented detail |

Tabs and newlines inside text become spaces, so one record always stays on one
line. Fields are never truncated.

```bash
lpui --actor helper --porcelain plan add --title "API v2" --why ".." --what ".."
lpui --actor helper --porcelain criterion add --kind plan --id 1 --text "Works offline"
lpui --actor helper --porcelain milestone add --plan 1 --title "Feature Y" --desc ".."
lpui --actor helper --porcelain task add --milestone 1 --title "Do X" --desc ".."
lpui --actor helper --porcelain task move --id 2 --to doing
lpui --porcelain next
lpui --porcelain claims
lpui --porcelain note add --kind task --id 2 --text "Decision or handoff"
lpui --porcelain task block --id 2 --reason "waiting"
lpui --porcelain criterion relate --id 1 --task 2
lpui --porcelain trace --plan 1
lpui --porcelain lint --plan 1
lpui --porcelain list --tree
lpui --porcelain plan show --id 1
```

```text
plan	1	doing	API v2	-	0/1
milestone	1	doing	Feature Y	plan:1	0/1
task	2	doing	Do X	milestone:1	-
```

`show` keeps why, what, desc, criteria, and children; it omits linked repos,
commits, and pull requests. Use `--json` when you need those full records.
The record families for brief, audit, feed, info, commits, repos, git status,
git scan, and PR reads are documented in `src/lazyplan/porcelain.py`.

### Claims, notes, and blocked work

An active agent can claim work atomically instead of racing for the same task:

```bash
lpui --porcelain next                        # claim the first eligible todo
lpui --porcelain claim --id 3 --ttl 30m      # claim a specific task
lpui --porcelain claim renew --id 3 --ttl 1.hours
lpui --porcelain claim release --id 3
lpui --porcelain claims                      # aliases: who
lpui --porcelain note add --kind task --id 3 --text "Decision or handoff"
lpui --porcelain note list --kind task --id 3
lpui --porcelain task block --id 3 --reason "waiting on design"
lpui --porcelain task unblock --id 3
```

A claim is a lease, not an owner. It carries the actor, start, expiry, and an
optional note; the default TTL is 30 minutes. Expired leases are reclaimable,
`claim renew` extends the holder's lease, and `claim --force` or
`claim release --force` takes over with a recorded reason. `next` skips
blocked, claimed, and done tasks. Blocking releases the claim and records the
reason as a note; it does not add a fourth status, so the task returns to the
todo pool and `next` still skips it until it is unblocked.

Notes are append-only on plans, milestones, and tasks. `show` and `brief`
include them; `task block` adds one automatically. Claims and notes travel in
export/import.

### Traceability and lint

Relate each plan criterion to the tasks that prove it, then inspect the evidence:

```bash
lpui --porcelain criterion relate --id 4 --task 12
lpui --porcelain criterion unrelate --id 4 --task 12
lpui --porcelain trace --plan 1
lpui --porcelain trace --criterion 4
lpui --porcelain lint --plan 1
lpui --porcelain lint --plan 1 --strict
lpui audit --plan 1 --min-trace 0.8 --strict
```

`trace` walks criterion → proving tasks → effective commits → pull requests. A
criterion with no proving task is reported as missing, not omitted. Relations
are many-to-many and survive export/import.

`lint` is read-only and advisory by default. It flags:

- plan criteria with no proving task;
- task descriptions with no commit-slice token;
- task descriptions with no verification token;
- `TODO`, `TBD`, or `FIXME` placeholder text;
- done rows that still have open criteria.

`--strict` exits 2 when any finding exists. `audit` always reports trace
coverage and unproven criteria; `--min-trace` is opt-in and defaults to 0
(disabled), so existing strict runs keep their current thresholds.

### MCP server

Hosts that speak the Model Context Protocol can use a typed local server
instead of shelling out:

```bash
lpui --actor helper mcp
lpui --actor helper mcp --read-only
```

The server uses stdio and JSON-RPC 2.0 with no extra dependency. stdout carries
protocol frames only; diagnostics go to stderr. Write calls are attributed to
the server `--actor`; `--read-only` hides write tools, rejects direct writes,
and never creates a missing database.

Read tools: `brief`, `list_plans`, `show_row`, `claims`, `audit`, `trace`,
`lint`, `info`. Write tools: create/edit/move, criteria, claims, notes,
block/unblock, and commit linking. Resources: `lazyplan://brief` and
`lazyplan://plan/{id}`.

Claude Code, user-wide:

```bash
claude mcp add --scope user --transport stdio lazyplan -- lpui mcp
```

Or commit a project `.mcp.json`:

```json
{
  "mcpServers": {
    "lazyplan": {
      "command": "lpui",
      "args": ["mcp"]
    }
  }
}
```

OpenCode-style local server:

```json
{
  "mcp": {
    "lazyplan": {
      "type": "local",
      "command": ["lpui", "mcp"]
    }
  }
}
```

Use `--read-only` for a reviewer or dashboard host. Use `--porcelain` when the
host does not support MCP; both surfaces read the same database.

### Flow health

`lpui stats` reads existing events and current rows; it never writes or calls
the network:

```bash
lpui stats --since 30.days
lpui stats --since 7.days --by alice
lpui stats --since 30.days --stale-after 3.days
lpui --porcelain stats --since 30.days
```

It reports WIP, median cycle time from first doing to done, throughput in the
window, median and maximum aging for doing tasks, stale todos, reopened rows,
active claims, and blocked tasks. `--by` filters completed/reopened activity
and claims; WIP, aging, stale, and blocked counts are current state. Missing
timestamps are omitted, not invented.

The screen adds an **Attention** source filter to the existing cycle
(`F`): expired claims, blocked tasks, doing work older than the stale
threshold, done rows with open criteria, and red PR checks. It combines with
the status filter, and the status line shows the current attention count.

### Comments, sharing, and sync

Review comments live on plans, milestones, and tasks:

```bash
lpui --porcelain comment add --kind task --id 3 --text "Please cover @alice's case"
lpui --porcelain comment list --kind task --id 3 [--mentions alice]
lpui --porcelain comment resolve --comment 7
lpui --porcelain comment unresolve --comment 7
```

`show`, `brief`, porcelain, and the TUI detail include comments; unresolved
comments are called out. Deleting a parent removes its comments.

Share a read-only snapshot when someone does not have the database:

```bash
lpui share --plan 1
lpui share --plan 1 --format json --out /tmp/plan.json
```

HTML escapes every field; JSON omits tokens, auth state, cache payloads, and
raw forge API records. Sharing never writes the database.

Plans carry stable UIDs. Merge a dump from another machine with:

```bash
lpui sync --file backup.json --dry-run
lpui sync --file backup.json
```

Sync is plan-granularity: unknown UIDs are added, identical plans are skipped,
and a changed plan with the same UID is a conflict. Sync never deletes or
overwrites local plans, and dry-run reports the same adds/skips/conflicts
without writing. Row-level merge is intentionally out of scope.

### Completion gates

`task finish` can require cached evidence before it moves a task done:

```bash
lpui --porcelain task finish --id 3 --require-pr
lpui --porcelain task finish --id 3 --require-checks
lpui --porcelain task finish --id 3 --require-checks --override "known flaky runner"
```

`--require-pr` needs at least one linked pull request. `--require-checks`
needs every linked PR's cached checks to be `pass`, `neutral`, or `skipped`.
Gates read the cache only; run `lpui pr refresh` to update it. A failure exits
2 and leaves the task doing with no commits linked. `--override REASON`
records the actor, reason, and gate state as a note and completes normally.

`show`, `brief`, and porcelain include a gate summary (`state`, PR count, and
checks) for tasks that have linked PRs. Starting a task records an existing
branch; a second open task on the same checkout or remote branch is rejected
and names the owner. lazyplan never creates branches or worktrees.

### Issue imports

Bring provider issues into the journal as plans or tasks:

```bash
lpui issue import --provider github --repo owner/repo
lpui issue import --provider github --repo owner/repo --as task --milestone 1
lpui issue import --provider linear --file linear-export.json
lpui issue import --provider linear --file linear-export.json --dry-run
```

GitHub uses the same token precedence as PR refresh
(`LAZYPLAN_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, then `gh auth token`).
Linear reads a JSON export file. GitHub pull requests mixed into an issues
response are skipped.

Imports are one-way and cached: the row carries provider, number, URL, and
state; re-importing the same provider + external id refreshes only that cached
metadata and never overwrites the row's title or description. `--dry-run`
reports creates and updates without writing. `show`, `trace`, and porcelain
list the source refs, and export/import preserves them.

Only `issue import --repo` calls a provider; all reads stay offline. lazyplan
never writes back to GitHub or Linear, stores raw provider payloads, or
stores tokens.

### Session brief and accuracy audit

Start a session with the brief, update after each commit, and close with the
audit:

```bash
lpui --porcelain brief            # active plan, doing task, next task, loose commits
lpui brief --json                 # same facts for a hook or script
lpui audit --plan 12              # see the three accuracy metrics for one plan
lpui audit --since 7.days         # recent window across active plans
lpui audit --since 7.days --strict  # exit 2 when a threshold is breached
```

The brief is read-only and never creates a database. It names the doing task,
the next todo, open criteria, and commits that landed without a task link.

The audit reports three numbers:

- **Coverage** — linked implementation commits over non-merge commits in the
  window.
- **Status lag** — median commits and minutes between a linked commit and the
  first `doing` or `done` move on its task.
- **Criteria gaps** — open acceptance items on rows closed inside the window.

Strict defaults are 80% coverage, one commit of median lag, and zero gaps.
Override them with `--min-coverage`, `--max-lag`, and `--max-gaps`; legacy
databases usually need a gap tolerance before they can gate CI.

### Lifecycle hooks

`lpui setup` installs read-only hooks for every detected agent host. They
never write to the database, never move a task, and always exit 0, so a broken
hook cannot block an agent. Remove them with `lpui setup --no-hooks`; every
touched config file is backed up under `~/.lazyplan/backups/<timestamp>/`.

| Host | Config | Events |
|---|---|---|
| OpenCode | `~/.config/opencode/plugins/lazyplan.js` | session context, post-tool |
| Claude Code | `~/.claude/settings.json` | SessionStart, UserPromptSubmit, PostToolUse (Bash and PowerShell), Stop |
| Gemini CLI | `~/.gemini/settings.json` | SessionStart, BeforeAgent, AfterTool, AfterAgent, PreCompress |
| Codex | `~/.codex/hooks.json` | SessionStart, UserPromptSubmit, PostToolUse, Stop, PreCompact |
| Cursor | `~/.cursor/hooks.json` | sessionStart, beforeSubmitPrompt, postToolUse, stop, preCompact |

Notes:

- OpenCode injects the brief into the first model context of a session and
  queues a commit reminder for the next context.
- Claude Code accepts no added context on PreCompact, so lazyplan skips it
  there; SessionStart fires again after compaction and re-injects the brief.
- On Windows, Claude Code runs hook commands in Git Bash, or in PowerShell
  when Git Bash is missing. Both find `lpui` on `PATH`.
- Codex asks you to review new hooks once with `/hooks` before it runs them.
- Cursor can also import Claude Code hooks; with both enabled, the same
  reminder may appear twice.
- Set `LAZYPLAN_NO_HOOKS=1` to silence every host without uninstalling.

If a hook does not fire, run it by hand with a payload on stdin, for example:

```bash
echo '{}' | lpui hook session-start --host claude
```

Then check the host's own hook log or trust screen.

## Reference

Journal commands accept `--porcelain` for the rows shown above; the examples
below omit it for readability except where the mode is the point.

```bash
lpui seed
lpui --porcelain list --tree          # stable rows for the active loop
lpui --porcelain plan show --id 1
lpui list [--tree] [--status todo|doing|done|all] [--archived] [--plan ID] [--all] [--limit N]
lpui plan list
lpui plan show --id 1
lpui plan add --title "API v2" --why ".." --what ".."
lpui plan edit --id 1 [--title --what --why]
lpui plan move --id 1 --to doing
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
lpui criterion tick --id 4
lpui criterion untick --id 4
lpui criterion delete --id 4
lpui criterion relate --id 4 --task 3
lpui criterion unrelate --id 4 --task 3
lpui --porcelain trace --plan 1
lpui --porcelain lint --plan 1 [--strict]
lpui audit --plan 1 [--min-trace 0.8]
lpui mcp
lpui mcp --read-only
lpui stats --since 30.days [--by NAME] [--stale-after 1.days]
lpui comment add --kind task --id 1 --text "..." [--mentions NAME]
lpui comment resolve --comment 1
lpui share --plan 1 [--format html|json] [--out PATH]
lpui sync --file dump.json [--dry-run]
lpui task finish --id 3 [--require-pr] [--require-checks] [--override REASON]
lpui issue import --provider github --repo owner/repo [--as plan|task] [--dry-run]
lpui issue import --provider linear --file export.json [--as plan|task] [--dry-run]
lpui link --kind task --id 1 [--sha HASH] [--repo PATH]
lpui commits --kind task --id 1 [--refresh] [--files]
lpui show --kind task --id 1 [--files]
lpui unlink --kind task --id 1 --sha HASH
lpui git status --kind task --id 1 [--json]
lpui git scan --since 7.days [--dry-run] [--repo PATH]
lpui task start --id 3 [--branch NAME]
lpui task finish --id 3 [--repo PATH]
lpui pr auth
lpui pr status --kind task --id 3
lpui pr refresh --kind task --id 3
lpui pr list --kind task --id 3
lpui pr show --kind task --id 3 --number 7
lpui pr link --kind task --id 3 --url URL
lpui pr unlink --kind task --id 3 --number 7
lpui link-repo --kind plan --id 1 --repo ~/checkouts/api [--remote URL]
lpui unlink-repo --kind plan --id 1 --repo ~/checkouts/api
lpui repos --kind task --id 1 [--effective]
lpui list --repo ~/checkouts/api
lpui export [--format json|markdown]
lpui import --file dump.json
lpui upgrade [--check]
lpui feed [--limit 20]
lpui watch [--limit 20]
```

Run `lpui <command> --help` for per-command flags. `man lpui` contains the full
manual. Legacy flat verbs (`add-plan`, `add-task`, `update`, `status`, `delete`,
`check`, `uncheck`, …) remain as aliases.

## Git proof

Rows can carry the exact commits that shipped them, including the files each
commit changed. `link` attaches HEAD, or a SHA, from the current checkout. Pass
`--repo PATH` to read a different linked checkout without changing directory.
`commits` lists direct and inherited commits; `--refresh` re-resolves their
cached metadata and changed files and marks commits that no longer resolve as
`[stale]`. Add `--files` to `show` or `commits` to list changed paths.

`task start` sets a task doing and records an existing branch plus its base. It
uses the current branch unless `--branch NAME` names another existing branch.
lazyplan never creates or checks out branches and never creates worktrees; use
your git tool for that first. `task finish` links `base..HEAD` and moves the
task to done only when the tree is clean. lazyplan never commits, pushes,
fetches, or merges. A commit can also be attributed with a `Lazyplan: T12`
trailer or a `task/12-*` branch name:

```bash
lpui git scan --since 7.days --dry-run
lpui git scan --since 7.days
```

`git status` reports branch, dirty state, and ahead/behind for each effective
repo. `show` includes inherited commits, a stale marker, and a web URL when the
repo has an origin remote.

Marking a row done links HEAD only when the tree is clean and HEAD is not
already linked to another row. A task with a started branch must be on that
branch and the commit must be on the task branch history. Otherwise lpui prints
one warning and leaves the link for you; the status move is not blocked.

## Source trail (TUI)

Select a plan, milestone, or task and press `g` (or run **Open source trail**
from the palette) to browse where it landed. The screen groups each checkout
into repository → commits → changed files, with linked pull requests alongside.
Plans and milestones aggregate descendant work, so a plan-level trail shows
which tasks produced each commit.

Highlighting a commit or file reads its unified diff with a read-only
`git show` and renders it in the preview: file and hunk headers, old/new line
numbers, and green additions / red removals. Selecting another row scrolls the
preview back to the top. The diff is read live from the checkout, kept in a
small in-memory cache, and never written to the database, export, or feed.

Previews are bounded: at most 20 files and 300 lines are shown, followed by a
`+N more lines` or `+N more files` notice. Press `o` for the full commit in the
browser. Binary files, root commits, merge commits, empty diffs, missing
commits, and non-git checkouts each render an explicit message instead of an
empty or broken pane.

Keys:

- `j`/`k` or arrows move; `left`/`right` collapse/expand or walk to the
  parent/first child. Clicking a row arrow toggles it.
- `o` opens the selected commit, PR, or file in the browser.
- `y` copies the selected SHA, file path, or URL.
- `/` filters repos, commits, files, and PRs; `enter` applies, `esc` closes.
- `r` rebuilds from cached data and clears the diff cache; `esc` returns.

The detail page shows a compact source summary and hints at `g`. The main tree
shows compact commit/PR chips and a single-cell `⎇` marker on rows that have
commits, pull requests, or repo links. Rows without provenance stay unchanged.
`F` cycles source filters: all, linked, has PR, stale, unlinked, claims,
blocked, attention. Dirty state is
shown per selected checkout; it is not a whole-tree filter because it requires
live git reads.

Opening the Source screen makes no network call. Browser launch is explicit.

## GitHub pull requests

GitHub support is read-only and opt-in. lpui reads the origin remote of each
linked checkout, recognizes `github.com` owner/repo identities, and caches pull
request state, checks, and reviews in the local database. `list`, `show`, and
opening the screen never call GitHub; only `pr refresh` does.

Auth precedence is:

1. `LAZYPLAN_GITHUB_TOKEN`
2. `GITHUB_TOKEN`
3. `GH_TOKEN`
4. `gh auth token`

Tokens are never written to the database, export, feed, or logs. `pr auth`
reports the active source; `pr status` reports repo identity, auth source, and
cache state per linked checkout.

```bash
lpui pr auth
lpui pr status --kind task --id 3
lpui pr refresh --kind task --id 3
lpui pr list --kind task --id 3
lpui pr show --kind task --id 3 --number 7
lpui pr link --kind task --id 3 --url https://github.com/org/repo/pull/7
lpui pr unlink --kind task --id 3 --number 7
```

`pr refresh` links each PR to the task that owns its commit or branch, and
caches state, checks, reviews, base/head refs, and merge metadata. Requests
reuse ETags and fall back to cached data offline; stale data is marked.
`pr link` is offline and manual. `show` and the detail screen roll PRs up from
tasks to milestones and plans, and task rows show a PR chip. Scope is
github.com only. lazyplan never creates branches, worktrees, commits, pushes,
PRs, reviews, comments, or merges; other tools own those actions.

## Data and backup

- Default: one `~/.lazyplan/lazyplan.db` shared by every agent and folder.
- Team: `.agents/lazyplan/lazyplan.db` inside the repo; commit `config.json`,
  not the database.
- Export: `lpui export --format json > backup.json`.
- Import: `lpui import --file backup.json` (ids change on import).
- Demo data: `lpui seed`. Never run it in a repo with a real plan.
- Files: plan text is read as UTF-8 or UTF-16 (PowerShell 5 writes a BOM) and
  written as UTF-8. Existing CRLF line endings are preserved on write.
- Completion: `eval "$(lpui completion --shell bash)"` (or `zsh`).

Exit codes: `0` worked · `1` row not found or setup layout misplaced · `2` flags
or input wrong · `3` screen cannot start because Textual is missing.

Versions up to 0.7.0 shipped this tool as `lp`, renamed because that name
clashed with the classic Unix print command.
