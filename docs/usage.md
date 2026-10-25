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
`lpui --json list`.

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
| `e` / `s` / `x` / `a` / `d` | edit · advance status · tick next criterion · add criterion · delete |
| `n` | create by context (plan, milestone, or task) |
| `/` | filter by text |
| `f` | change status filter |
| `A` | show all plans |
| `?` | help |
| `c` | command palette |
| `q` | quit |

The palette and the CLI use the same names: Create plan, Move to doing, Tick
next criterion, Delete selection.

## Agents

Every command accepts `--json`. Writes accept `--actor NAME`; the default is
`$USER`. The activity feed shows who changed what.

```bash
lpui --actor helper list --json
lpui --actor helper plan show --id 1
lpui --actor helper task add --milestone 1 --title "Draft proposal"
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
- Start a session with `lpui brief`; update the journal after each commit, then
  run `lpui audit --since 7.days` before closing a plan. Lifecycle hooks remind
  you, but they are read-only.

`lpui setup --placement repo` writes the full contract into the repo; the
default setup installs the skill into each detected agent's own folder.

### Session brief and accuracy audit

Start a session with the brief, update after each commit, and close with the
audit:

```bash
lpui brief                        # active plan, doing task, next task, loose commits
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
| Claude Code | `~/.claude/settings.json` | SessionStart, UserPromptSubmit, PostToolUse, Stop, PreCompact |
| Gemini CLI | `~/.gemini/settings.json` | SessionStart, BeforeAgent, AfterTool, AfterAgent, PreCompress |
| Codex | `~/.codex/hooks.json` | SessionStart, UserPromptSubmit, PostToolUse, Stop, PreCompact |
| Cursor | `~/.cursor/hooks.json` | sessionStart, beforeSubmitPrompt, postToolUse, stop, preCompact |

Notes:

- OpenCode injects the brief into the first model context of a session and
  queues a commit reminder for the next context.
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

```bash
lpui seed
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
`F` cycles source filters: all, linked, has PR, stale, unlinked. Dirty state is
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
- Completion: `eval "$(lpui completion --shell bash)"` (or `zsh`).

Exit codes: `0` worked · `1` row not found or setup layout misplaced · `2` flags
or input wrong · `3` screen cannot start because Textual is missing.

Versions up to 0.7.0 shipped this tool as `lp`, renamed because that name
clashed with the classic Unix print command.
