# Agent instructions

<!-- lazyplan:start -->
## lazyplan (`lpui`)

Repo plan of record: projects > stories > tasks in `.plan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- New project? Interview the human first: why, what, acceptance criteria, priority.
- Read: `lpui list`, `lpui show --kind project --id N`, `lpui feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lpui add-project`, `lpui add-story`, `lpui add-task`, `lpui update`, `lpui status`, `lpui delete` (all with `--actor <name>`)
- Done means: `lpui add-criteria --kind project`, cut stories, cut prioritized tasks, work p0 first
- Unsure on scope or taste? Ask the human in conversation — never guess the definition
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lpui --help`
<!-- lazyplan:end -->
