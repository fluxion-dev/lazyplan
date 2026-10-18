# Agent instructions

<!-- lazyplan:start -->
## lazyplan (`lpui`)

Repo plan of record: projects > stories > tasks in `.plan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- Read: `lpui list`, `lpui show --kind story --id N`, `lpui feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lpui add-project`, `lpui add-story`, `lpui add-task`, `lpui update`, `lpui status`, `lpui delete` (all with `--actor <name>`)
- Extras: `lpui add-criteria`, `lpui add-link`, `lpui add-risk`, `lpui add-milestone` (flags in the skill)
- Unsure? `lpui propose` / `lpui ask` for human approval
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lpui --help`
<!-- lazyplan:end -->
