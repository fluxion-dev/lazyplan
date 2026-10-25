# Setup walkthrough

This page explains exactly what lazyplan writes, when it writes it, and what
each setup command does. Read it before you run setup on a machine you care
about.

## First run

```bash
cd ~/my-plan
lpui
```

On a terminal you get three questions: where plans live, which agents get the
skill, and whether to install the reviewed resources. Scripts, agents, and
`lpui --json` get the defaults without prompts.

The first run writes:

| Item | Home placement (default) | Repo placement |
| --- | --- | --- |
| Database | `~/.lazyplan/lazyplan.db` | `<repo>/.agents/lazyplan/lazyplan.db` |
| Templates | `~/.lazyplan/templates/*.md` | `<repo>/.agents/lazyplan/templates/*.md` |
| Config | not written | `<repo>/.agents/lazyplan/config.json` |
| Skill | `~/.agents/skills/lazyplan/SKILL.md` plus per-agent dirs | `<repo>/.agents/skills/lazyplan/SKILL.md` plus per-agent dirs |
| Hooks | `~/.claude/settings.json`, `~/.config/opencode/plugins/lazyplan.js`, and the other host configs | same, because hooks live in your home |
| `AGENTS.md` | not written unless you pass `--agents-pointer` | a marked lazyplan section |
| State | `~/.lazyplan/setup.json` | `~/.lazyplan/setup.json` |

Bare `lpui` and `lpui setup` install the same resources for the same flags.
The completion summary lists the database, skills, plugins, and any backups.

## Rerun setup

```bash
lpui setup
lpui setup --placement repo --yes
lpui setup --agents "opencode,claude"
lpui setup --no-skills
lpui setup --no-hooks
lpui setup --agents-pointer
```

Flags win over environment variables, which win over remembered state, which
wins over detection:

1. Explicit flag (`--placement`, `--agents`, `--skills-dir`, `--no-skills`,
   `--hooks`, `--no-hooks`, `--agents-pointer`, `--no-agents-pointer`).
2. Environment (`LAZYPLAN_AGENTS`, `LAZYPLAN_SKILLS_DIR`,
   `LAZYPLAN_NO_SKILLS`).
3. `~/.lazyplan/setup.json`.
4. Agent and repository detection.

A rerun with unchanged inputs writes nothing, rewrites nothing, and creates no
backup directory. A changed file is backed up under
`~/.lazyplan/backups/<timestamp>/`, preserving the original path.

## Switch placements

```bash
lpui setup --placement repo --yes   # home -> repo
lpui setup --placement home --yes   # repo -> home
```

Repo to home removes the generated repo config, starter templates, repo skill
copies, the marked `AGENTS.md` section, and the lazyplan `.gitignore` lines.
Custom template edits are left in place. The repo database is never deleted:
move it first with the upgrade review, or keep it and doctor will report it.

Home to repo writes the repo contract and replaces the home `AGENTS.md` snippet
with the repo one. The home database stays where it is and doctor notes it.

## Upgrade

```bash
lpui upgrade
lpui upgrade --json
```

A successful upgrade re-runs setup with the new package, including under
`--json`, so hooks and the pointer pick up new content. Upgrade never prompts
in JSON mode. If the upgrade cannot run, lazyplan prints one warning and keeps
working.

## Doctor

```bash
lpui doctor
lpui doctor --json
```

Doctor is read-only. It resolves the database a real run would open, including
`--db` and `$LAZYPLAN_DB`, and reports the database, templates, config, skill
paths, hook files, state, and every finding. Exit `0` is clean; exit `1` means
at least one finding, including missing hook files and a stale state version.

## Hooks and the pointer

Hooks are read-only. They never write to the database, never move a task, and
always exit `0`. Remove them with `lpui setup --no-hooks`; every touched file
is backed up. `LAZYPLAN_NO_HOOKS=1` silences installed hooks without removing
them.

`--agents-pointer` adds a marked section to the repo `AGENTS.md` when plans
live at home. It is off by default. `--no-agents-pointer` removes only the
marked section and keeps the rest of the file.

## Uninstall leftovers

Removing the package leaves your data and agent files behind on purpose:

- `~/.lazyplan/` (database, state, templates, backups)
- `~/.agents/skills/lazyplan/` and the per-agent skill directories
- hook entries in the host configs listed above
- `AGENTS.md` markers in repos where you enabled the pointer

Remove hooks first with `lpui setup --no-hooks`, export with
`lpui export --format json`, then delete the directories you no longer want.

## Troubleshooting

**A hook does not fire.** Run it by hand and read the host's hook log:

```bash
echo '{}' | lpui hook session-start --host claude
```

**Setup says the repo database is tracked.** lazyplan never moves a tracked
database. Export one database and import it, or keep the repo placement.

**Two databases both contain plans.** Setup refuses to merge them. Export one
and import it into the other, or keep them separate.

**A path is not writable.** Setup reports the failing path and leaves the rest
alone. Fix permissions and rerun; completed files are not rewritten.
