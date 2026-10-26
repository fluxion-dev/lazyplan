"""Shared documentation metadata for the man page and documentation tests.

Keep this list aligned with the environment reads in `setup.py`, `skills.py`,
`hooks.py`, and `setup_ui.py`. The man generator and the docs-truth test both
read it, so a new variable has one place to land.
"""

from __future__ import annotations

ENVIRONMENT: tuple[tuple[str, str], ...] = (
    ("LAZYPLAN_DB", "Which database file to use (same as --db)."),
    (
        "LAZYPLAN_PORCELAIN",
        "Print terse tab-separated rows for active agents; --json still wins.",
    ),
    ("LAZYPLAN_NO_SETUP", "Skip first-run setup and upgrade review when set."),
    ("LAZYPLAN_AGENTS", "Default agent list for setup; an explicit flag wins."),
    ("LAZYPLAN_SKILLS_DIR", "Default skill directory for setup; an explicit flag wins."),
    ("LAZYPLAN_NO_SKILLS", "Install no agent skill when set."),
    ("LAZYPLAN_NO_HOOKS", "Silence installed hooks at runtime; does not remove them."),
    ("LAZYPLAN_NO_SPINNER", "Freeze the doing spinner in the TUI."),
    ("LAZYPLAN_NO_COLOR", "Disable setup wizard color."),
    ("NO_COLOR, CLICOLOR=0, TERM=dumb", "Plain setup output."),
    ("USER, USERNAME", "Used for --actor when you do not give one (USERNAME on Windows)."),
)

FILES: tuple[tuple[str, str], ...] = (
    ("~/.lazyplan/lazyplan.db", "Your plans, shared by every agent and folder (default home)."),
    ("%LOCALAPPDATA%/lazyplan/", "The shared home on Windows, in place of ~/.lazyplan/."),
    (
        ".agents/lazyplan/lazyplan.db",
        "The repo database (only with lpui setup --placement repo; keep it local).",
    ),
    (".agents/lazyplan/config.json", "Repo marker; commit it with the plan."),
    (
        ".agents/lazyplan/templates/{plan,milestone,task}.md",
        "Repo creation templates; commit them to share defaults.",
    ),
    ("~/.lazyplan/templates/{plan,milestone,task}.md", "Home creation templates."),
    ("~/.lazyplan/setup.json", "Remembered setup choices and migration decisions."),
    ("~/.lazyplan/backups/<timestamp>/", "Tree-preserving backups of every touched file."),
    (
        "~/.agents/skills/lazyplan/SKILL.md",
        "Universal agent skill; per-tool skill directories are written too.",
    ),
    (
        "~/.config/opencode/plugins/lazyplan.js, ~/.claude/settings.json, ~/.gemini/settings.json, ~/.codex/hooks.json, ~/.cursor/hooks.json",
        "Managed read-only hook surfaces.",
    ),
    ("AGENTS.md", "Optional marked lazyplan section in a repo."),
)
