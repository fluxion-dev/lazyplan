"""Shared parser constants and version lookup."""

from __future__ import annotations

import re
from pathlib import Path

from ... import textfile

_PARSER_DESCRIPTION = (
    "lazyplan keeps your plans, milestones, and tasks in one SQLite database, "
    "shared in your home by default or inside a repo through `lpui setup` "
    "(run it as lpui, or by its long name lazyplan). The first run sets up the "
    "database and agent skills. You get a keyboard-driven screen, and your "
    "coding agent gets a command line that reads the same data."
)
_PARSER_EPILOG = """\
your database (the first match wins):
  --db PATH | $LAZYPLAN_DB | nearest team ./.agents/lazyplan/lazyplan.db walking up
  | ~/.lazyplan/lazyplan.db shared home (%LOCALAPPDATA%/lazyplan on Windows)

examples:
  lpui                                   first run sets up, then opens the screen
  lpui setup                            re-run setup: placement, agents, and drift review
  lpui doctor                           read-only report of the resolved layout and findings
  lpui                                   open the screen (same as `lpui ui`)
  lpui plan list                         show plans as summaries with progress
  lpui plan list --tree                  show the full plan/milestone/task tree
  lpui plan list --status doing
  lpui --porcelain plan list --tree      stable tab-separated rows for an active agent
  lpui --porcelain next                  claim the first eligible task
  lpui --porcelain claim --id 3 --ttl 30m
  lpui --porcelain note add --kind task --id 3 --text "Decision or handoff"
  lpui --porcelain task block --id 3 --reason "waiting on design"
  lpui --porcelain criterion relate --id 1 --task 3
  lpui --porcelain trace --plan 1        # criterion -> task -> commit/PR
  lpui --porcelain lint --plan 1         # plan-quality findings
  lpui stats --since 30.days             # WIP, cycle time, aging, stale work
  lpui comment add --kind task --id 3 --text "Review @alice"
  lpui share --plan 1                     # read-only HTML snapshot
  lpui sync --file backup.json --dry-run  # plan-level merge report
  lpui issue import --provider github --repo owner/repo
  lpui issue import --provider linear --file export.json --dry-run
  lpui mcp                               # typed MCP server on stdio
  lpui --actor helper mcp --read-only    # read-only MCP for reviews
  lpui --porcelain task add --milestone 1 --title "Do X" --desc "approach"
  lpui plan show --id 1                  show one row with its why, what, checklist, and children
  lpui --actor alice plan add --title "API v2" --why ".." --what ".."
  lpui --actor alice criterion add --kind plan --id 1 --text "Works offline"
  lpui --actor alice milestone add --plan 1 --title "Feature Y" --desc "value"
  lpui --actor alice task add --milestone 1 --title "Do X" --desc "approach"
  lpui task move --id 3 --to done
  lpui task start --id 3                record an existing branch + base
  lpui task finish --id 3               link base..HEAD, done when clean
  lpui task finish --id 3 --require-pr --require-checks
  lpui link --kind task --id 3           attach the current commit (needs a git repo)
  lpui commits --kind task --id 3        list the attached commits
  lpui git status --kind task --id 3     branch, dirty tree, and tracking per linked repo
  lpui git scan --since 7.days --dry-run link commits by Lazyplan: T3 trailers or branch name
  lpui pr auth                           show which GitHub token source is active
  lpui pr status --kind task --id 3      GitHub identity and auth for linked repos
  lpui pr refresh --kind task --id 3     resolve commits and branches to pull requests
  lpui link-repo --kind plan --id 1 --repo ~/checkouts/api
  lpui repos --kind task --id 3 --effective
  lpui list --repo ~/checkouts/api
  lpui feed --limit 20                   show recent activity by you and your agents
  lpui upgrade [--check]                 self-update pipx/venv installs (no repo needed)
  lpui export --format json > backup.json
  lpui import --file backup.json

vcs: link, unlink, git status, and git scan need a git repo. link accepts
  --repo to read a different checkout. commits reads cached links anywhere;
  --refresh re-resolves them and marks missing commits stale. Marking a row
  done links HEAD only when the tree is clean and HEAD is not already linked;
  task start records an existing branch and its base, and task finish links
  base..HEAD. lazyplan never writes to git.

repos: link-repo, unlink-repo, and repos work anywhere (no git needed).
  A task with no explicit links inherits its milestone's repos, and a
  milestone inherits its plan's. list --repo matches effective repos.

github: pr verbs read cached pull requests; only pr refresh calls GitHub.
  Auth order: LAZYPLAN_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN, then gh auth token.
  Tokens never enter the database or export. github.com only, read-only.

flags work before or after the command (`lpui list --json` means the same as
`lpui --json list`). On commands that change data, `--actor NAME` records who
did it, and you can see it in `feed`. `--porcelain` prints one tab-separated
row per record for active agents; `--json` wins when both are set.

workflow: starting a plan? Ask the human what to build, why it matters,
  and how to tell it is done. Save that as the plan. Then break it into
  milestones, and each milestone into prioritized tasks. Agents claim work
  with `next` (a lease, not an owner), renew or release it, note handoffs,
  and park blocked tasks with `task block --reason`. Relate each criterion to
  a proving task and run `lint` before check-off.

environment:
  LAZYPLAN_DB       which database file to use (same as --db)
  LAZYPLAN_PORCELAIN  print porcelain rows (1/true/yes/on)
  LAZYPLAN_NO_SETUP skip first-run setup and upgrade review
  LAZYPLAN_NO_SPINNER freeze the TUI doing spinner
  NO_COLOR          plain setup output (also CLICOLOR=0 and TERM=dumb)

files: shared home by default (`lpui setup --placement repo` opts a repo in)
  ~/.lazyplan/lazyplan.db                 your plans, every agent and folder (default)
  ~/.lazyplan/setup.json                  remembered setup choices and decisions
  ~/.lazyplan/templates/                  creation templates shared by every agent
  .agents/lazyplan/lazyplan.db            repo database when placement is repo
  .agents/lazyplan/templates/{plan,milestone,task}.md  repo creation templates

exit codes: 0 it worked · 1 id not found · 2 flags or input were wrong · 3 screen cannot start (Textual is missing).

more help:
  lpui <command> --help                  flags and examples for one command
  lpui help                              the screen's key bindings (same as `?` in the app)
  man lpui                               full manual (installed with the package)
"""


def package_version() -> str:
    """Version of the running code: pyproject next to the source tree, else installed dist metadata."""
    try:
        text = textfile.read(Path(__file__).resolve().parents[4] / "pyproject.toml")
    except OSError:
        text = ""
    m = re.search(r'^version = "(.*)"$', text, re.M) if text else None
    if m:
        return m.group(1)
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("lazyplan-tui")
    except PackageNotFoundError:
        return "unknown"
