## lazyplan (`lpui`)

Repo plan of record: plans > milestones > tasks in `.agents/lazyplan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- New plan? Interview the human first: vision, scope in and out, deliverables, constraints, metrics, acceptance criteria. Scout the codebase during the interview.
- Read: `lpui --porcelain list --tree`, `lpui --porcelain next`, `lpui --porcelain claims`, `lpui --porcelain plan show --id N`, `lpui --porcelain audit --since 7.days`, `lpui --porcelain feed --limit 20` (`--json` for full fidelity)
- Porcelain rows are `kind<TAB>id<TAB>status<TAB>title<TAB>parent<TAB>extra`; parse by tabs, not by scraping text. Set `LAZYPLAN_PORCELAIN=1` for a whole session.
- MCP: hosts that support it can call `lpui mcp` for typed tools/resources; `--read-only` hides writes.
- Coordinate: `next` claims atomically; `claim renew|release` manages the lease; `note add` hands off context; `task block --reason` parks blocked work without a fourth status.
- Collaborate: `comment add/list/resolve` for review, `share --plan P` for a read-only snapshot, and `sync --file dump.json --dry-run` for a plan-level merge (conflicts never overwrite).
- Trace: `criterion relate --id C --task T` records proof; `trace --plan P` shows evidence; `lint --plan P --strict` gates uncovered criteria and weak task descriptions.
- Write (full CRUD): `lpui plan|milestone|task add`, `... edit`, `... move`, `... delete`; `lpui criterion add|tick|untick|delete` (all with `--actor <name>`)
- During execution: mark the task doing before code; after each commit link it with `lpui --porcelain link --kind task --id T` (or `task finish`) and move the row; finish with `lpui --porcelain audit --since 7.days` and tick criteria with evidence.
- Lifecycle hooks are read-only; they remind, never move work, and never write to the database. On Windows, Claude Code runs them in Git Bash or PowerShell; both find `lpui` on `PATH`.
- Read paths are batched and query-budgeted (`tools/perf_bench.py --check`); do not add per-row queries to tree, list, export, audit, MCP, or TUI refresh.
- Milestones read As a/I want/so that with Given-When-Then criteria; tasks start with a verb and carry a DoD checklist; cut both from scouted ground only
- Scout before creating anything — no row from unscouted ground; scope lists what is in and out explicitly
- Implementation requests get an ambiguity hunt first: touch-points, edge cases, non-goals, assumptions — never accept "implement X" at face value
- Write every row for scanning: paragraphs and sections, no single-blob text, no placeholder content; starters ship empty, fill them with real words
- Templates in `.agents/lazyplan/templates/` fill/enforce/auto-add criteria at creation; missing templates mean legacy defaults; setup scaffolds them, and edits are never overwritten
- Plans include QA, refactoring, and documentation cleanup by default; ask about relevant testing in the interview, drop them only on explicit opt-out
- Done means: `lpui criterion add --kind plan`, cut milestones, cut tasks, work in creation order
- Unsure on scope or taste? Ask the human in conversation — never guess the definition
- Review gate: present the plan, edit on the spot, execute only on check-off; the plan is the truth
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lpui --help`
