"""Legacy CLI verbs kept as aliases for canonical noun-first work."""

from __future__ import annotations

#: The parser is the source of truth; this table drives the parity tests and
#: keeps the aliases honest.
LEGACY_COMMANDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("plan", "add"): ("add-plan",),
    ("milestone", "add"): ("add-milestone",),
    ("task", "add"): ("add-task",),
    ("criterion", "add"): ("add-criteria",),
    ("plan", "edit"): ("update",),
    ("milestone", "edit"): ("update",),
    ("task", "edit"): ("update",),
    ("plan", "move"): ("status",),
    ("milestone", "move"): ("status",),
    ("task", "move"): ("status",),
    ("criterion", "tick"): ("check",),
    ("criterion", "untick"): ("uncheck",),
    ("plan", "delete"): ("delete",),
    ("milestone", "delete"): ("delete",),
    ("task", "delete"): ("delete",),
    ("criterion", "delete"): ("delete-criteria",),
    ("plan", "show"): ("show",),
    ("milestone", "show"): ("show",),
    ("task", "show"): ("show",),
    ("", "list"): ("list",),
    ("", "export"): ("export",),
    ("", "help"): ("help",),
}
