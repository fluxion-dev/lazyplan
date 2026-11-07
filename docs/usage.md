# lazyplan usage

The short start lives in the [README](../README.md). This page keeps the
detail: install, setup and scope, everyday commands, the screen, agent use,
provenance, and data.

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
matching `.deb` or `.rpm` from
[Releases](https://github.com/fluxion-dev/lazyplan/releases).

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
`dnf` or `apt`. The TUI notifies and CLI stderr mentions new versions; stdout
stays clean for `--json`. A successful upgrade re-runs setup with the new
binary. Installed skills and hooks refresh silently, while a skill or hook
surface added by the release is offered once on a terminal. Headless runs
(`--json`, `--yes`, agent calls, and the Windows helper) leave those additions
pending with no writes; `lpui doctor` names them, and the next interactive
`lpui` or `lpui setup` asks again.

On Windows the command and the TUI Update screen use a detached helper. lpui
closes first, then the helper waits for the process to exit, updates the
existing pipx venv with that venv's own `python -m pip` (or a plain venv's
pip), writes the full command and output under
`%LOCALAPPDATA%\lazyplan\logs\`, runs the post-upgrade setup review, and
relaunches the TUI. A failed install leaves the old version runnable and the
next launch shows the log path. `lpui upgrade --diagnose` prints the detected
method, owning Python, pipx and shim paths, and log directory without changing
anything. If the helper cannot start, close lpui and repair with
`pipx install --force --backend pip lazyplan-tui`. A source checkout updates
with `git pull`.

Upgrading from 0.30.1 or earlier is not supported in place: the package layout
and console scripts changed. Force a reinstall in the environment that owns
`lpui`:

```bash
# pipx
pipx install --force lazyplan-tui

# pip, including the install.sh venv
python -m pip install --force-reinstall lazyplan-tui
```

On Windows, add `--backend pip` to the pipx command. Do not use `lpui upgrade`
or a plain `pipx upgrade` for this jump. The reinstall replaces only the program
files; your database, templates, skills, hooks, and `~/.lazyplan` state stay.

### Uninstall

Remove the program with `pipx uninstall lazyplan-tui` or your package manager.
Your plans live in `~/.lazyplan/` (or `.agents/lazyplan/` in a repo); export
them before deleting that folder. `lpui setup --no-skills --no-hooks` removes
installed agent integrations, and `lpui setup --no-agents-pointer` removes the
marked `AGENTS.md` section.

## Start

```bash
cd ~/my-plan
lpui
```

The first run sets up lazyplan: it detects your coding agents, installs their
skills, creates the database, and remembers the choices in
`~/.lazyplan/setup.json`. On a terminal you get a short wizard; scripts, agents,
and `--json` get the same defaults without prompts.

Then create your first plan:

```bash
lpui plan add --title "my-plan" --why "reason" --what "scope"
```

`lpui` with no command opens the screen. `lpui ui` does the same.

## Setup and scope

Setup writes one layout. Re-run it any time to change placement or agents:

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
- A release can add a skill or hook host/event. Setup refreshes what is already
  installed, then lists only the new items with one prompt: install all, not
  now, or never. Install writes every listed file with a backup.
- Not-now is remembered until the next version change; never is remembered
  until that item's definition changes. Both choices live in
  `~/.lazyplan/setup.json`.
- `--no-skills` and `--no-hooks` are remembered across upgrades. New skills or
  hooks stay pending and doctor reports them; pass `--hooks` to opt back in.
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
lpui setup --placement repo|home      # where plans live
lpui setup --agents "opencode,claude" # or all, or none; $LAZYPLAN_AGENTS
lpui setup --skills-dir PATH          # or $LAZYPLAN_SKILLS_DIR
lpui setup --no-skills                # database only; $LAZYPLAN_NO_SKILLS
lpui setup --hooks                    # install lifecycle hooks, re-enabling after --no-hooks
lpui setup --no-hooks                 # remove lifecycle hooks and remember the opt-out
lpui setup --agents-pointer           # add the marked AGENTS.md section
lpui setup --no-agents-pointer        # remove the marked AGENTS.md section
lpui setup --yes                      # apply without prompts
lpui setup --json                     # machine-readable, no prompts
lpui --heal | --no-heal               # automatic repair on or off for this command
```

Precedence is explicit flag, then environment, then remembered state, then
detection. The wizard uses the same defaults, so `lpui setup --placement repo`
or `--no-skills` changes what the questions propose.

`LAZYPLAN_NO_SETUP=1` skips first-run setup and upgrade review. `NO_COLOR`,
`LAZYPLAN_NO_COLOR`, `CLICOLOR=0`, and `TERM=dumb` keep the wizard plain.
`LAZYPLAN_NO_SPINNER=1` freezes the doing spinner in the TUI.
`LAZYPLAN_THEME` selects a TUI palette: `dark` or `mocha` (the default),
`void` for an OLED-black variant, and `light` or `latte` for the light theme.
Unset or any other value uses mocha. Press `t` in the TUI to cycle the three
palettes without restarting.
`--placement repo` outside a git checkout falls back to home.

| Variable | Meaning |
| --- | --- |
| `LAZYPLAN_DB` | Which database file to use (same as `--db`). |
| `LAZYPLAN_PORCELAIN` | Terse tab-separated rows for active agents; `--json` still wins. |
| `LAZYPLAN_NO_SETUP` | Skip first-run setup and upgrade review. |
| `LAZYPLAN_AGENTS` | Default agent list for setup; an explicit flag wins. |
| `LAZYPLAN_SKILLS_DIR` | Default skill directory for setup; an explicit flag wins. |
| `LAZYPLAN_NO_SKILLS` | Install no agent skill. |
| `LAZYPLAN_NO_HOOKS` | Silence installed hooks at runtime; does not remove them. |
| `LAZYPLAN_NO_SPINNER` | Freeze the doing spinner in the TUI. |
| `LAZYPLAN_THEME` | TUI palette: mocha, void, or latte (aliases dark, oled, light). |
| `LAZYPLAN_NO_COLOR` | Disable setup wizard color. |
| `NO_COLOR`, `CLICOLOR=0`, `TERM=dumb` | Plain setup output. |
| `USER`, `USERNAME` | Used for `--actor` when you do not give one (`USERNAME` on Windows). |

`doctor` and `upgrade` accept the global `--json`, `--porcelain`, `--version`,
and `--actor`; `upgrade` adds `--check` and `--diagnose`.

### Setup files

| Path | Meaning |
| --- | --- |
| `~/.lazyplan/lazyplan.db` | Your plans, shared by every agent and folder (default home). |
| `%LOCALAPPDATA%/lazyplan/` | The shared home on Windows, in place of `~/.lazyplan/`. |
| `.agents/lazyplan/lazyplan.db` | The repo database (only with `lpui setup --placement repo`; keep it local). |
| `.agents/lazyplan/config.json` | Repo marker; commit it with the plan. |
| `.agents/lazyplan/templates/{plan,milestone,task}.md` | Repo creation templates; commit them to share defaults. |
| `~/.lazyplan/templates/{plan,milestone,task}.md` | Home creation templates. |
| `~/.lazyplan/setup.json` | Remembered setup choices and migration decisions. |
| `~/.lazyplan/backups/<timestamp>/` | Tree-preserving backups of every touched file. |
| `~/.agents/skills/lazyplan/SKILL.md` | Universal agent skill; per-tool skill directories are written too. |
| `~/.config/opencode/plugins/lazyplan.js`, `~/.claude/settings.json`, `~/.gemini/settings.json`, `~/.codex/hooks.json`, `~/.cursor/hooks.json` | Managed read-only hook surfaces. |
| `AGENTS.md` | Optional marked lazyplan section in a repo. |

## Everyday commands

```bash
lpui list                         # plans and progress
lpui list --tree                  # full plan/milestone/task tree
lpui plan show --id 1             # why, what, criteria, milestones
lpui task move --id 1 --to doing
lpui criterion tick --id 1
lpui context --max-chars 4000     # active plan, next work, and proof
lpui feed                         # recent activity
```

Flags work before or after the command: `lpui list --json` is the same as
`lpui --json list`. `--porcelain` switches journal commands to stable
tab-separated rows; `--json` wins when both are present.

## The screen

Plans start collapsed. Press `right` or `z` to reveal milestones; tasks stay
folded until you open their milestone. Completed plans are dimmed and sorted
last. A doing row animates a small spinner; set `LAZYPLAN_NO_SPINNER=1` to
freeze it.

The main screen pairs the plan tree with a preview column: a two-line control
strip, the selected row's reason, scope, next tasks, acceptance progress, a
`git` card for linked checkouts and pull requests, and an `agents` card for
active sessions and the last handoff. The bottom timeline card follows the
selected row and its immediate children.

On launch the tree opens on the **needs me** lens: attention tasks plus plans
with drift, open questions, stale claims, or blocked work. `F` cycles the
source lenses and returns to all plans.

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
| `F` | change source filter: needs me, all, linked, PR, stale, unlinked, claims, blocked, attention, focus |
| `g` | open the source trail for the selected row |
| `A` | show all plans |
| `?` | help |
| `c` | command palette |
| `t` | cycle theme: mocha, void, latte |
| `O` | toggle manual override mode (writes are blocked while off) |
| `q` | quit |

The palette and the CLI use the same names: Create plan, Move to doing, Tick
next criterion, Delete selection. The palette also has Bulk move to doing/done,
Bulk block tasks, Bulk release claims, Clear marks, and Undo bulk change. Bulk
status and block confirm first; undo restores the exact prior status/blocked
state once. Bulk delete and archive stay single-row.

`/` searches titles, descriptions, why/what, notes, comments, claim actors,
blocked reasons, and issue refs. Marks are session-only and survive refreshes.

### Manual override mode

The screen is read-only by default. Press `O` (or run **Toggle manual
override** from the palette) to enable writes; the red banner and the `OVERRIDE`
nav subtitle stay visible while it is on. Press `O` again to return to
read-only.

Every write from the screen is deliberate and recorded. The event names the
target, the action, and, for a risky write, the reason you typed. Deleting a
row and taking over a claim ask for a reason first; cancelling leaves the row
or claim untouched. See only those rows with:

```bash
lpui feed --overrides
```

The normal `lpui feed` still shows every event. Agents and the CLI continue to
write directly; override mode only gates the screen.

The palette carries the work that does not need a dedicated key. **Approve
plan scope**, **Show plan diff**, **Prove criterion**, **Add / Resolve / Reopen
plan question**, **Link / Unlink external reference**, **Claim task**, **Block
task**, **Unblock task**, and **Finish task** all run from the same palette.
Run **Export plan as Markdown** to open a destination picker; the CLI
equivalent is `lpui export --format markdown --plan ID --file PATH`
(add `--force` to replace an existing file).

Select a plan, milestone, or task and press `g` to browse the source trail:
checkout → commits → changed files, with linked pull requests alongside. The
preview shows a read-only diff; large diffs stop at 20 files / 300 lines.
`o` opens the selected commit, PR, or file, `y` copies it, and `/` filters.

## Agents

Every command accepts `--json`. Journal commands also accept `--porcelain` for
the active loop. Writes accept `--actor NAME`; the default is `$USER`
(`%USERNAME%` on Windows). The activity feed shows who changed what.

```bash
lpui --actor helper --porcelain task add --milestone 1 --title "Draft proposal"
lpui --actor helper --porcelain list --tree
lpui --actor helper plan show --id 1
lpui feed --json --follow
lpui feed --overrides              # only manual changes made from the screen
```

Your agent is expected to work from the plan, not invent it:

- Ask the human for the plan's why, scope, and acceptance criteria first.
- Hunt ambiguity before implementing: touch-points, edge cases, non-goals,
  assumptions.
- Look up ids with `list`; never guess them.
- Prefer `edit` and `move` over deleting and re-creating.
- Work in creation order, and plan the commit sequence before coding: every
  task lands as one or more small, green commits, never one batch for the
  whole plan or milestone.
- Name each task's expected commit slice and verification in its desc, and
  commit after each task completes rather than deferring work to the end.
- Link commits after the fact with `lpui link` or `task finish`; no commit
  trailer is required.
- Write rows for scanning: short paragraphs and sections, no placeholder text.
- If the host supports MCP, prefer `lpui mcp`; otherwise use `--porcelain`.
- Check flow health with `lpui stats --since 7.days`; the human screen uses the
  Attention filter.
- Leave review comments with `comment add` and share a read-only plan with
  `share`; sync is plan-granularity.
- Use `task finish --require-pr --require-checks` when done must wait for
  evidence; overrides are recorded.
- Import provider issues with `issue import`; re-import refreshes source
  metadata only and never writes back.
- Relate every plan criterion to a proving task and run
  `lpui --porcelain lint --plan P` before check-off.
- Create the whole tree in one JSON write with `plan apply`; start from
  `plan recipe feature|bugfix|refactor` and edit the words before applying.
- Start a session with `lpui --porcelain next` to claim work, or
  `lpui --porcelain context --max-chars 4000` for the budgeted picture.
  Renew the lease while you work, note handoffs, and release it when you stop.
  Update the journal after each commit, then run
  `lpui --porcelain audit --since 7.days` before closing a plan. Lifecycle
  hooks remind you, but they are read-only.

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

```text
plan	1	doing	API v2	-	0/1
milestone	1	doing	Feature Y	plan:1	0/1
task	2	doing	Do X	milestone:1	-
```

`show` keeps why, what, desc, criteria, and children; it omits linked repos,
commits, and pull requests. Use `--json` when you need those full records.

### Plan documents and recipes

Create a whole plan tree in one atomic write:

```bash
lpui plan apply --file plan.json
lpui plan apply --file plan.json --dry-run
lpui plan recipe feature > plan.json
```

The document is JSON with `plan` and `milestones`; each milestone carries
`tasks`. Every plan, milestone, and task needs a stable `key`. A retry with the
same key is a no-op, and a failure rolls the whole tree back. `--dry-run`
validates the document and prints the intended tree without writing.

`feature`, `bugfix`, and `refactor` recipes are packaged skeletons with QA,
refactoring, and documentation tasks. Edit the words, then apply the document.

### Context and claims

```bash
lpui --porcelain context --max-chars 4000  # active plan, next work, proof, claims
lpui --porcelain brief                     # active plan, doing task, next task, loose commits
lpui --porcelain next                      # claim the first eligible todo
lpui --porcelain claim renew --id 3 --ttl 1.hours
lpui --porcelain claim release --id 3
lpui --porcelain note add --kind task --id 3 --text "Decision or handoff"
```

`context` returns the active plan, the doing task and its claim, the next three
open tasks, open criteria, recent decisions and notes, recent commits,
unresolved comments, and active claims. The budget is deterministic:
low-priority sections drop first. The same packet is the MCP resource
`lazyplan://context` (or `lazyplan://context/2000` for a budget).

A claim is a lease, not an owner. It carries the actor, start, expiry, and an
optional note; the default TTL is 30 minutes. Expired leases are reclaimable,
`claim renew` extends the holder's lease, and `claim --force` or
`claim release --force` takes over with a recorded reason. `next` skips
blocked, claimed, and done tasks. Blocking releases the claim and records the
reason as a note; it does not add a fourth status, so the task returns to the
todo pool and `next` still skips it until it is unblocked.

Status is authoritative. A task that is not `doing` cannot hold a lease: moving
it to todo or done releases the lease, and `reconcile` removes expired leases
and any lease left on a non-doing task. `reconcile --check` reports that drift,
plus done rows with open criteria, without writing anything.

### Progress and rollups

Progress is status-based: done tasks over all tasks under the row. It ignores
status, limit, repo, and text filters, so one snapshot shows the same done/total
in CLI list, tree, and show, the TUI, metrics, and MCP. A done task with open
criteria still counts as done; `reconcile --check` and `stats` report those
criteria as a separate gap instead of changing the count.

Parent status rolls up from its children: all done means done, any doing means
doing, otherwise todo. `reconcile` heals parent drift and releases stale leases;
`reconcile --check` reports the same drift without writing anything.

### Sessions and touch-points

```bash
lpui --actor NAME session start --plan 1 --branch task/1-records
lpui --actor NAME session end --summary "Shipped the store" --handoff "next: T2"
lpui session show
lpui session list --open
lpui touch add --task 12 --path src/lazyplan/store/sessions.py
```

`session start` writes a pointer beside the database keyed by actor and
checkout; `LAZYPLAN_SESSION=S3` overrides it. Every write made while the
session is open is tagged with its id. Hooks stay read-only: they show the open
session or a start hint, and `context`/`brief` render the previous handoff.
Sessions are operational history and are not exported.

Tasks can declare the repo-relative paths they expect to edit. `next` skips a
todo whose touch-points overlap an active claim in the same checkout. A manual
`claim` refuses on overlap unless `--force` is passed, and `task finish` prints
a warning when linked commit files overlap another open task. Finish never
blocks on overlap; claims remain leases, not owners.

### Trust: approvals, evidence, and questions

```bash
lpui plan approve --id 1 --reason "reviewed the cut"
lpui plan revisions --id 1
lpui plan diff --id 1
lpui plan diff --id 1 --check
lpui criterion prove --id 4 --command "pytest tests/store" --exit-code 0 \
  --commit "$(git rev-parse HEAD)" --task 3
lpui criterion evidence --id 4
lpui question add --plan 1 --text "Which host ships first?"
lpui question resolve --id 1 --note "OpenCode first"
lpui plan ready --id 1
lpui review --plan 1
```

Approval records the scope a human accepted. Later edits are visible as drift,
and every scope-changing edit can carry a reason. `plan diff --check` is the
opt-in CI gate. `plan approve --enforce` also makes `plan move --to done`
refuse unapproved drift; pass `--override REASON` to record the exception.
Status moves, ticks, claims, commits, and pull requests are not scope, so they
never create drift.

A tick is a claim; evidence is the proof. `criterion prove` ticks only when the
declared exit code is absent or 0; `--no-tick` records without ticking.
Evidence is append-only, and the latest row decides the criterion's state.
lazyplan never executes the command, fetches a PR, or reads an artifact.
`task finish --require-evidence` gates on the latest passing row.

Open questions are plan-level rows. `plan ready` combines three checks: lint is
clean, every plan criterion has a proving task, and no questions are open. It
exits 0 when ready, 1 when not ready, and 2 for an unknown plan.

`review` prints one deterministic Markdown packet for a human or reviewer
agent. It is assembled from existing reads, makes no LLM or network call, and
is safe to paste into a pull request.

### Review, lint, and audit

```bash
lpui --porcelain criterion relate --id 4 --task 12
lpui --porcelain trace --plan 1
lpui --porcelain lint --plan 1 [--strict]
lpui audit --plan 1 [--min-trace 0.8] [--min-evidence 0.8]
lpui stats --since 7.days
```

`trace` walks criterion → proving tasks → effective commits → pull requests. A
criterion with no proving task is reported as missing, not omitted.

`lint` is read-only and advisory by default. It flags plan criteria with no
proving task, task descriptions with no commit-slice or verification token,
placeholder text, and done rows that still have open criteria. `--strict`
exits 2 when any finding exists.

`audit` reports commit coverage, status lag, and criteria gaps. Strict defaults
are 80% coverage, one commit of median lag, and zero gaps; override them with
`--min-coverage`, `--max-lag`, and `--max-gaps`.

### Git provenance

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

### Pull requests

GitHub support is read-only and opt-in. lpui reads the origin remote of each
linked checkout, recognizes `github.com` owner/repo identities, and caches pull
request state, checks, and reviews in the local database. `list`, `show`, and
opening the screen never call GitHub; only `pr refresh` does.

Auth precedence is `LAZYPLAN_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, then
`gh auth token`. Tokens are never written to the database, export, feed, or
logs. `pr auth` reports the active source; `pr status` reports repo identity,
auth source, and cache state per linked checkout.

```bash
lpui pr auth
lpui pr refresh --kind task --id 3
lpui pr list --kind task --id 3
lpui pr link --kind task --id 3 --url https://github.com/org/repo/pull/7
```

`pr refresh` links each PR to the task that owns its commit or branch, and
caches state, checks, reviews, base/head refs, and merge metadata. Requests
reuse ETags and fall back to cached data offline; stale data is marked.
`pr link` is offline and manual. `show` and the detail screen roll PRs up from
tasks to milestones and plans, and task rows show a PR chip. Scope is
github.com only. lazyplan never creates branches, worktrees, commits, pushes,
PRs, reviews, comments, or merges; other tools own those actions.

### MCP and issue imports

Hosts that speak the Model Context Protocol can use a typed local server
instead of shelling out:

```bash
lpui --actor helper mcp
lpui --actor helper mcp --read-only
```

The server uses stdio and JSON-RPC 2.0 with no extra dependency. stdout carries
protocol frames only; diagnostics go to stderr. Write calls are attributed to
the server `--actor`; `--read-only` hides write tools, rejects direct writes,
and never creates a missing database. Resources are `lazyplan://brief`,
`lazyplan://context` (append `/{max_chars}` for a budget), and
`lazyplan://plan/{id}`.

Bring provider issues into the journal as plans or tasks:

```bash
lpui issue import --provider github --repo owner/repo
lpui issue import --provider linear --file linear-export.json --dry-run
```

Imports are one-way and cached: the row carries provider, number, URL, and
state; re-importing the same provider + external id refreshes only that cached
metadata and never overwrites the row's title or description. Only
`issue import --repo` calls a provider; all reads stay offline. lazyplan never
writes back to GitHub or Linear, stores raw provider payloads, or stores
tokens.

## Data and backup

- Default: one `~/.lazyplan/lazyplan.db` shared by every agent and folder.
- Team: `.agents/lazyplan/lazyplan.db` inside the repo; commit `config.json`,
  not the database.
- Export: `lpui export --format json > backup.json`.
- Import: `lpui import --file backup.json` (ids change on import).
- Plan Markdown: `lpui export --format markdown --plan 3 --file ~/Downloads/plan-P3.md`.
  Missing parent folders are created; an existing file is refused unless you
  pass `--force`.
- Demo data: `lpui seed`. Never run it in a repo with a real plan.
- Files: plan text is read as UTF-8 or UTF-16 (PowerShell 5 writes a BOM) and
  written as UTF-8. Existing CRLF line endings are preserved on write.
- Completion: `eval "$(lpui completion --shell bash)"` (or `zsh`).

## Exit codes

`0` worked · `1` row not found or setup layout misplaced · `2` flags or input
wrong · `3` the screen cannot start because Textual is missing.

Run `lpui <command> --help` for per-command flags. `man lpui` contains the full
manual. Legacy flat verbs (`add-plan`, `add-task`, `update`, `status`, `delete`,
`check`, `uncheck`, …) remain as aliases.
