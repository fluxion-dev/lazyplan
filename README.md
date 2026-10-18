# lazyplan (`lp`) — v0.7.0

Terminal stream-of-consciousness console for issue tracking + roadmap planning,
built to run in tmux next to `opencode` and `lazygit`. Design rules live in
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md), enforced by `src/lazyplan/design.py`.

## Install

```bash
pipx install ~/personal-repos/lazyplan   # isolated global `lp`
# or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
lp --help
# optional: shell completions
eval "$(lp completion --shell bash)"   # or --shell zsh
```
Note: this shadows the classic Unix print command `/usr/bin/lp`.
Use `command lp` or the full path if you ever need the printer.

DB resolution (first match wins): `--db PATH` → `$LAZYPLAN_DB` →
enclosing git repo's `.plan/lazyplan.db` → global
`~/.local/share/lazyplan/lazyplan.db`.

## Repo-scoped workflow

Each git repo gets its own plan, stored with the code:

```bash
cd ~/my-project
lp init        # creates .plan/lazyplan.db + .plan/config.json, then offers
               # the agent-skills wizard (universal `.agents/skills/lazyplan/`
               # + `## lazyplan` pointer in AGENTS.md). Flags: --no-skills,
               # --yes, --skills-scope project|global|both|none; --json stays
               # machine-readable and never prompts.
lp info        # resolved db path, repo root, counts, .plan files
lp add-project --name "my-project" --start 2026-10-18 --end 2026-12-31
lp ui          # statusbar shows [my-project]; agents in any subdir share it
```

Run `lp` from any subdirectory — it walks up to the repo root (via
`git rev-parse` with a `.git` fallback). Outside a repo it uses the global DB.
Commit `.plan/` to share the plan with the team, or ignore `*.db` to keep it
local — your call.

## tmux workflow

```bash
./tools/tmux-lazyplan.sh        # plan | opencode | lazygit
```

## Dev / gates

```bash
pip install -e ".[dev,postgres]"   # ruff + mypy (+ psycopg for `lp sync`)
./tools/check.sh                   # ruff check + format --check + mypy (strict)
                                   # + unittest on system python AND venv python
```

Standards live in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) (§Python standards,
pyguide-based).

Agents never touch the TUI process — they call `lp --actor NAME ...` against
the same SQLite file (proposals/questions for anything needing human eyes);
the TUI polls a fingerprint (mtime + counts + max ids + last event) every
second and toasts + activity-lines new arrivals. `lp sync` snapshots the db
to Postgres for SQL-side readers (see `src/lazyplan/postgres_sync.py`).

## TUI (`lp ui`)

Single panel, nano-style bottom bar (activity line, statusbar, command bar,
key footer). Mouse click/expand works.

| key | action |
|---|---|
| `1`/`2`/`3` | tree / gantt / feed views |
| `j`/`k`, arrows, click | navigate · `enter` edit detail in place |
| `n` | contextual new (task→story→project) |
| `P`/`S`/`T` | new project / story / task forms |
| `e` / `d` | edit · delete (with confirm) |
| `space` / `c` | cycle status · tick first open criterion |
| `+`/`-` | gantt zoom (width 20–100) |
| `f` / `o` / `O` | status / project / owner filter |
| `s` / `ctrl+p` | search · command palette (fuzzy, rows + views) |
| `4` then `a`/`x` | proposals view · approve / reject |
| `/` | focus command bar · `?` help · `r` refresh · `q` quit |

The command bar accepts the same verbs as `lp`
(`add-task --story 1 --title x`, `status --kind task --id 1 --to done`,
`tree`/`gantt`/`feed`, `help`).

## CLI (agent ingress)

Flags work before or after the subcommand (`lp list --json` == `lp --json list`).

```bash
lp seed
lp list [--status todo|doing|done] [--project ID] [--owner NAME] [--priority p0]
lp gantt [--tasks] [--width 40] [--status ..] [--project ID] [--owner NAME] [--priority p0]
# * = critical path, ! = blocked, ◆ = milestone
lp show --kind project|story|task --id N   # full context: narrative + links + children
lp add-project --name "API v2" [--goal .. --metrics .. --scope-in .. --scope-out .. --assumptions ..]
lp add-story --project 1 --title "Auth refresh" [--owner a1 --priority p0 --labels x,y --estimate 2w --blocked-by 3]
lp add-task --story 1 --title "Rotate tokens" [--desc ctx --owner a1 --priority p1 --estimate 2d --blocked-by 4]
lp add-link --kind story --id 1 --url URL [--label spec]
lp add-criteria --kind task --id 1 --text "works offline"
lp check --id 1 / lp uncheck --id 1        # tick acceptance items (advisory)
lp add-risk --project 1 --title "slip" [--likelihood high --impact high --mitigation buf]
lp add-milestone --project 1 --title "Beta" --date 2026-11-15
lp propose --kind task --parent 1 --title "Refactor X" [--priority p1 --owner a1]
lp proposals [--status pending] | lp approve --id 1 / lp reject --id 1
lp ask --question "Which scope?" | lp questions | lp answer --id 1 --text "Minimal"
lp export [--format json|markdown] | lp import --file dump.json
lp sync --dsn postgresql://issues:issues@localhost:5433/issues   # one-way replica
lp update --kind task --id 1 [--title --desc --owner --estimate --priority p0|none --labels a,b --blocked-by 1,2]
lp status --kind task --id 1 --to doing    # closing with open criteria warns, never blocks
lp delete --kind task --id 1
lp feed [--limit 20]            # recent human/agent activity
lp watch [--limit 20]           # tail (agents: lp feed --json --follow &)
lp --actor agent-1 add-task --story 3 --title "Draft proposal"
```

## Roadmap (dogfooded)

The default DB holds project **P#1 “lazyplan roadmap”** (11 stories, 37 tasks).
Done: S#1 MVP, S#4 planning power, S#6 distribution, S#7 ownership,
S#8 acceptance criteria, S#9 risk register, S#10 goals/scope, S#11 materials.
Doing: S#2 TUI polish (palette/search/editable-detail left). Open: S#3 agent
ingress, S#5 postgres sync. All feature work goes here — `lp list`,
`lp gantt --tasks`, `lp show --kind story --id N`, `lp ui`.
