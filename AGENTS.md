# Agent instructions

<!-- lazyplan:start -->
## lazyplan (`lpui`)

Repo plan of record: plans > milestones > tasks in `.agents/lazyplan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- New plan? Interview the human first: vision, scope in and out, deliverables, constraints, metrics, acceptance criteria (priority only if volunteered; new tasks default p1). Scout the codebase during the interview.
- Read: `lpui list`, `lpui show --kind plan --id N`, `lpui feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lpui add-plan`, `lpui add-milestone`, `lpui add-task`, `lpui update`, `lpui status`, `lpui delete` (all with `--actor <name>`)
- Milestones read As a/I want/so that with Given-When-Then criteria; tasks start with a verb and carry a DoD checklist; cut both from scouted ground only
- Scout before creating anything — no row from unscouted ground; scope lists what is in and out explicitly
- Implementation requests get an ambiguity hunt first: touch-points, edge cases, non-goals, assumptions — never accept "implement X" at face value
- Write every row for scanning: paragraphs and sections, no single-blob text, no placeholder content; starters ship empty, fill them with real words
- Templates in `.agents/lazyplan/templates/` fill/enforce/auto-add criteria at creation; missing templates mean legacy defaults; `lpui init` walks through setup, reruns offer keep/edit/reset
- Plans include QA, refactoring, and documentation cleanup by default; ask about relevant testing in the interview, drop them only on explicit opt-out
- Done means: `lpui add-criteria --kind plan`, cut milestones, cut prioritized tasks, work p0 first
- Unsure on scope or taste? Ask the human in conversation — never guess the definition
- Review gate: present the plan, edit on the spot, execute only on check-off; the plan is the truth
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lpui --help`
<!-- lazyplan:end -->
