"""Setup wizard steps: stable ids, titles, and plain-language explanations.

The step list is UI-agnostic so the Textual screen, the terminal wizard, and
tests agree on what setup asks. Visibility depends only on the context the
session already resolved: a repo checkout, selected agents, and pending
integrations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """One setup question, with the reason it exists."""

    key: str
    title: str
    summary: str


WELCOME = Step(
    "welcome",
    "Welcome",
    "Setup decides where plans live, which agents receive lazyplan, and how they run."
    " Nothing is written until you review and apply these choices.",
)
PLACEMENT = Step(
    "placement",
    "Where plans live",
    "The home database follows you across every checkout. A repo database is shared"
    " with teammates through the checkout, while the database file stays ignored.",
)
AGENTS = Step(
    "agents",
    "Your agents",
    "Selected agents receive the lazyplan skill and managed subagent profiles, so"
    " they can read the plan and hand lane work to cheaper roles.",
)
HOOKS = Step(
    "hooks",
    "Hooks and the pointer",
    "Hooks record agent sessions, inject the active plan, and check commits and stops."
    " Strict hooks block, advisory hooks remind, and off removes them. The AGENTS.md"
    " pointer tells agents in this checkout where the shared plans live.",
)
MODELS = Step(
    "models",
    "Model targets",
    "Each host maps the fast, standard, and deep tiers to its own models. Leave a"
    " target at inherit to use the host's configured default instead.",
)
ROLES = Step(
    "roles",
    "Role tiers and effort",
    "Every role names a capability tier and an optional effort level. Scout and docs"
    " can stay cheap while review and integration use the deepest model and effort.",
)
INTEGRATIONS = Step(
    "integrations",
    "New integrations",
    "A release can add a skill or hook surface. Install what you want now, defer it to"
    " the next launch, or never ask again for this exact item.",
)
APPEARANCE = Step(
    "appearance",
    "Appearance and checks",
    "The theme is remembered for the next launch. The checks are read-only: they name"
    " missing tools and GitHub login problems with the command that fixes each one.",
)
REVIEW = Step(
    "review",
    "Review and apply",
    "Review every file this writes, refreshes, or removes. Apply uses the same setup"
    " writer as `lpui setup`, and nothing changes before you confirm.",
)

STEPS: tuple[Step, ...] = (
    WELCOME,
    PLACEMENT,
    AGENTS,
    HOOKS,
    MODELS,
    ROLES,
    INTEGRATIONS,
    APPEARANCE,
    REVIEW,
)
STEP_BY_KEY: dict[str, Step] = {step.key: step for step in STEPS}


def visible_steps(
    *,
    has_repo: bool,
    has_agents: bool,
    has_pending: bool,
) -> tuple[Step, ...]:
    """Return the steps worth showing for one setup context."""
    hidden: set[str] = set()
    if not has_repo:
        hidden.add(PLACEMENT.key)
    if not has_agents:
        hidden.update((MODELS.key, ROLES.key))
    if not has_pending:
        hidden.add(INTEGRATIONS.key)
    return tuple(step for step in STEPS if step.key not in hidden)
