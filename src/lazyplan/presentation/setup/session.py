"""One setup session shared by the TUI wizard and the terminal fallback.

The session builds a draft from remembered setup, discovered host catalogs, and
the remembered model map without writing. Screens edit the draft through small
mutators, validate it, and call :meth:`SetupSession.apply`, which runs the same
``apply_choice`` and integration writer the CLI uses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, TextIO

from lazyplan.core.policies.agents import HOSTS, TIERS
from lazyplan.core.policies.hooks import MODES
from lazyplan.infrastructure import host_models, profiles, skills
from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.infrastructure.integrations import IntegrationItem

from . import layout, models
from .apply import apply_choice, install_integrations
from .constants import HOME, REPO
from .findings import default_choice
from .integrations import inspect, install_items, remember_decisions
from .layout import SetupChoice
from .state import SetupState, load_state
from .steps import Step, visible_steps
from .triggers import clear_pending

INTEGRATION_DECISIONS = ("install", "defer", "never")
Discover = Callable[[Iterable[str], Path, Path | None], dict[str, HostCatalog]]


class SetupSessionError(ValueError):
    """The draft is incomplete or names a value setup cannot write."""


@dataclass
class SetupDraft:
    """Editable setup values before any file is written."""

    placement: str = HOME
    agents: list[str] = field(default_factory=list)
    skills_enabled: bool = True
    skills_dir: str = ""
    hooks_mode: str = "strict"
    agents_pointer: bool = False
    profiles_map: dict[str, profiles.Profile] = field(default_factory=dict)
    tiers_map: dict[str, dict[str, str]] = field(default_factory=dict)
    integrations: dict[str, str] = field(default_factory=dict)
    theme: str = ""


@dataclass
class SetupSession:
    """One wizard run: the draft, its context, and the shared apply path."""

    cwd: Path
    home: Path
    version: str
    root: Path | None
    state: SetupState
    draft: SetupDraft
    catalogs: dict[str, HostCatalog] = field(default_factory=dict)
    pending: tuple[IntegrationItem, ...] = ()
    discover: Discover | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(
        cls,
        cwd: Path,
        home: Path | None = None,
        version: str = "",
        state: SetupState | None = None,
        discover: Discover | None = None,
    ) -> SetupSession:
        """Build a session from remembered setup and local discovery."""
        home = home or Path.home()
        state = state or load_state(home)
        root = layout_root(cwd)
        base = default_choice(cwd, home, state)
        agents = _order_hosts(base.agents or _detected_agents(home))
        seed = replace(base, agents=agents)
        plan = skills.plan_choice(seed, root, home)
        resolved = layout.resolve_choice(seed, root, plan, home)
        profile_map, tiers = models.initial_maps(resolved.db, home, root, agents, discover)
        draft = SetupDraft(
            placement=base.placement,
            agents=agents,
            skills_enabled=not base.no_skills,
            skills_dir=base.skills_dir or "",
            hooks_mode=state.effective_mode(),
            agents_pointer=state.agents_pointer,
            profiles_map=profile_map,
            tiers_map=tiers,
            theme=state.theme,
        )
        finder = discover or host_models.discover_all
        session = cls(
            cwd=cwd,
            home=home,
            version=version,
            root=root,
            state=state,
            draft=draft,
            catalogs=finder(agents, home, root),
            discover=discover,
        )
        session.refresh_pending()
        return session

    @property
    def db_path(self) -> Path:
        """The database the current draft would use, without writing."""
        choice = self.choice()
        plan = skills.plan_choice(choice, self.root, self.home)
        return layout.resolve_choice(choice, self.root, plan, self.home).db

    @property
    def host_labels(self) -> dict[str, str]:
        """Display label for every selected host that has a catalog."""
        return {host: catalog.label for host, catalog in self.catalogs.items()}

    def steps(self) -> tuple[Step, ...]:
        """The steps this context needs, in order."""
        return visible_steps(
            has_repo=self.root is not None,
            has_agents=bool(self.draft.agents) and self.draft.skills_enabled,
            has_pending=bool(self.pending),
        )

    def choice(self) -> SetupChoice:
        """The draft as the argument-independent setup choice."""
        return SetupChoice(
            placement=self.draft.placement,
            agents=list(self.draft.agents),
            skills_dir=self.draft.skills_dir or None,
            no_skills=not self.draft.skills_enabled,
            profiles_map=dict(self.draft.profiles_map),
            tiers_map={tier: dict(values) for tier, values in self.draft.tiers_map.items()},
            model_review=False,
        )

    def set_placement(self, placement: str) -> None:
        """Switch placement and reload the map that placement owns."""
        self.draft.placement = placement
        self.reload_models()
        self.refresh_pending()

    def set_agents(self, keys: list[str] | tuple[str, ...]) -> None:
        """Replace the selected hosts and rebuild their default model map."""
        wanted = set(keys)
        self.draft.agents = [host for host in HOSTS if host in wanted]
        self.reload_models()
        self.refresh_pending()

    def set_skills_enabled(self, enabled: bool) -> None:
        """Turn managed skills and profiles on or off."""
        self.draft.skills_enabled = enabled
        self.refresh_pending()

    def set_hooks_mode(self, mode: str) -> None:
        """Choose strict, advisory, or off."""
        self.draft.hooks_mode = mode
        self.refresh_pending()

    def reload_models(self) -> None:
        """Re-read catalogs and defaults for the current placement and hosts."""
        finder = self.discover or host_models.discover_all
        self.catalogs = finder(self.draft.agents, self.home, self.root)
        loaded, tiers = models.initial_maps(
            self.db_path,
            self.home,
            self.root,
            self.draft.agents,
            self.discover,
        )
        self.draft.profiles_map = loaded
        self.draft.tiers_map = tiers

    def refresh_pending(self) -> None:
        """Recompute pending integrations and keep their decisions."""
        probe = replace(
            self.state,
            skills_enabled=self.draft.skills_enabled,
            hooks_enabled=self.draft.hooks_mode != "off",
        )
        self.pending = inspect(self.choice(), probe, self.root, self.home, self.version).pending
        known = {item.id for item in self.pending}
        self.draft.integrations = {
            item_id: decision
            for item_id, decision in self.draft.integrations.items()
            if item_id in known
        }
        for item in self.pending:
            self.draft.integrations.setdefault(item.id, "install")

    def set_integration(self, item_id: str, decision: str) -> None:
        """Record install, defer, or never for one pending item."""
        if decision not in INTEGRATION_DECISIONS:
            raise SetupSessionError(
                f"integration decision must be {'|'.join(INTEGRATION_DECISIONS)}"
            )
        if item_id not in {item.id for item in self.pending}:
            raise SetupSessionError(f"unknown integration {item_id!r}")
        self.draft.integrations[item_id] = decision

    def set_role_tier(self, role: str, tier: str) -> None:
        """Point one role at a capability tier."""
        if tier not in TIERS:
            raise SetupSessionError(f"tier must be {'|'.join(TIERS)}")
        profile = self.draft.profiles_map.get(role)
        if profile is None:
            raise SetupSessionError(f"unknown role {role!r}")
        self.draft.profiles_map[role] = replace(profile, tier=tier)

    def set_role_effort(self, role: str, effort: str) -> None:
        """Set one role's effort level; an empty value means inherit."""
        profile = self.draft.profiles_map.get(role)
        if profile is None:
            raise SetupSessionError(f"unknown role {role!r}")
        self.draft.profiles_map[role] = replace(profile, effort=effort.strip())

    def set_tier_model(self, host: str, tier: str, model: str) -> None:
        """Set or clear one host's model for a tier."""
        self._check_target(host, tier)
        self.draft.tiers_map.setdefault(tier, {})[host] = model.strip()

    def set_role_model(self, role: str, host: str, model: str) -> None:
        """Set or clear one role's per-host override."""
        profile = self.draft.profiles_map.get(role)
        if profile is None:
            raise SetupSessionError(f"unknown role {role!r}")
        if host not in self.draft.agents:
            raise SetupSessionError(f"host must be one of {', '.join(self.draft.agents)}")
        models = dict(profile.models)
        if model.strip():
            models[host] = model.strip()
        else:
            models.pop(host, None)
        self.draft.profiles_map[role] = replace(profile, models=models)

    def _check_target(self, host: str, tier: str) -> None:
        if host not in self.draft.agents:
            raise SetupSessionError(f"host must be one of {', '.join(self.draft.agents)}")
        if tier not in TIERS:
            raise SetupSessionError(f"tier must be {'|'.join(TIERS)}")

    def validate(self) -> list[str]:
        """Human-readable problems that block apply."""
        errors: list[str] = []
        if self.draft.placement not in (HOME, REPO):
            errors.append(f"placement must be {HOME} or {REPO}")
        if self.draft.placement == REPO and self.root is None:
            errors.append("repo placement needs a git checkout")
        if self.draft.hooks_mode not in MODES:
            errors.append(f"hooks mode must be {'|'.join(MODES)}")
        unknown = [host for host in self.draft.agents if host not in HOSTS]
        if unknown:
            errors.append(f"unknown agents: {', '.join(unknown)}")
        for role, profile in self.draft.profiles_map.items():
            if profile.tier not in TIERS:
                errors.append(f"{role} tier must be {'|'.join(TIERS)}")
        for item_id, decision in self.draft.integrations.items():
            if decision not in INTEGRATION_DECISIONS:
                errors.append(f"{item_id} decision must be {'|'.join(INTEGRATION_DECISIONS)}")
        return errors

    def apply(self, write: TextIO | None = None) -> dict[str, Any]:
        """Write the draft through the shared setup apply path."""
        errors = self.validate()
        if errors:
            raise SetupSessionError("; ".join(errors))
        choice = self.choice()
        result = apply_choice(choice, self.root, self.home, self.version, write)
        install_integrations(
            result,
            self.home,
            self.root,
            self.draft.hooks_mode,
            self.draft.agents_pointer,
        )
        chosen, deferred, never = self._integration_groups()
        if chosen:
            result["integrations"] = install_items(
                chosen,
                choice,
                load_state(self.home),
                self.root,
                self.home,
                self.version,
            ).to_dict()
        state = load_state(self.home)
        if deferred:
            remember_decisions(deferred, state, "deferred", self.version, self.home)
        if never:
            remember_decisions(never, state, "never", self.version, self.home)
        state = load_state(self.home)
        if self.draft.theme:
            state.theme = self.draft.theme
        clear_pending(state, self.version, self.home)
        return result

    def _integration_groups(
        self,
    ) -> tuple[
        tuple[IntegrationItem, ...],
        tuple[IntegrationItem, ...],
        tuple[IntegrationItem, ...],
    ]:
        groups: dict[str, list[IntegrationItem]] = {"install": [], "defer": [], "never": []}
        for item in self.pending:
            decision = self.draft.integrations.get(item.id, "install")
            groups[decision].append(item)
        return (
            tuple(groups["install"]),
            tuple(groups["defer"]),
            tuple(groups["never"]),
        )


def layout_root(cwd: Path) -> Path | None:
    """The git checkout setup may write into, if any."""
    from lazyplan.infrastructure.repo import find_repo_root

    return find_repo_root(cwd)


def _detected_agents(home: Path) -> list[str]:
    return [host.key for host in skills.detect_agents(home) if host.detected]


def _order_hosts(keys: list[str]) -> list[str]:
    wanted = set(keys)
    return [host for host in HOSTS if host in wanted]
