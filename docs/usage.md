# lazyplan usage

The short start lives in the [README](../README.md). This page keeps the detail:
install options, init layout, everyday commands, the screen, agent use, and data.

## Install

The recommended path is pipx:

```bash
pipx install lazyplan-tui
lpui --help
```

On Windows, use the pip backend:

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

Pin a version or choose a method:

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
stays clean for `--json`.

## Start

```bash
cd ~/my-plan
lpui init --yes
lpui plan add --title "my-plan" --why "reason" --what "scope"
lpui
```

`lpui` with no command opens the screen. `lpui ui` does the same.

## Init and scope

`lpui init` chooses one layout and applies it to everything: database, config,
templates, skills, `AGENTS.md`, and `.gitignore` entries.

| You run | Database and templates | Config | Skills | `AGENTS.md` |
| --- | --- | --- | --- | --- |
| `lpui init` | `~/.lazyplan/` | not written | each agent's home skill dir | not written |
| `lpui init --team` | `<repo>/.agents/lazyplan/` | `<repo>/.agents/lazyplan/config.json` | repo skill dirs | repo pointer |
| `--skills-scope project` | `<repo>/.agents/lazyplan/` | repo config | repo skill dirs | repo pointer |
| `--skills-scope both` | `<repo>/.agents/lazyplan/` | repo config | repo and home skill dirs | repo pointer |
| `--no-skills` | same storage as the other flags | same | none | none |
| `--db PATH` / `$LAZYPLAN_DB` | `PATH` and its sibling `templates/` | only for a repo plan dir | per scope flags | per scope flags |

`--team --no-skills` still selects repo storage. An explicit `--db` or
`$LAZYPLAN_DB` always wins and is never moved.

### Inspect before writing

```bash
lpui init --check
lpui doctor
lpui init --check --json
```

Both are read-only. Exit `0` means clean, `1` means misplaced resources, `2`
means bad flags. `lpui doctor --team` checks the repo-owned layout.

### Safe repair

Global init repairs leftovers from an earlier scoped install:

- A repo database moves to the home path when the home database is empty.
- Repo config, templates, generated skills, the marked `AGENTS.md` block, and
  lazyplan `.gitignore` entries are moved home or cleaned up.
- Every touched file is backed up under `~/.lazyplan/backups/<timestamp>/`.
- If both databases contain plans, init stops, backs up the repo database, and
  prints export/import next steps. It never merges or deletes plans.

Team init never moves home data.

### Where the database resolves

The first match wins:

1. `--db PATH`
2. `$LAZYPLAN_DB`
3. the nearest enclosing `.agents/lazyplan/lazyplan.db`
4. `~/.lazyplan/lazyplan.db` (`%LOCALAPPDATA%/lazyplan` on Windows)

Commit `.agents/lazyplan/config.json` to share a team plan. The `*.db` file stays
local (gitignored) unless you force-add it.

### Agent and skill flags

```bash
lpui init --agents "opencode,claude"   # or all
lpui init --skills-dir PATH            # or $LAZYPLAN_SKILLS_DIR
lpui init --json                       # same layout, no prompts
```

`--team` or `--skills-scope project` outside a git repo fails with exit `2`.

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

`lpui init --team` writes the full contract into the repo. `lpui init` installs
the skill into your agent's own folder.

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

Exit codes: `0` worked · `1` row not found or init layout misplaced · `2` flags
or input wrong · `3` screen cannot start because Textual is missing.

Versions up to 0.7.0 shipped this tool as `lp`, renamed because that name
clashed with the classic Unix print command.
