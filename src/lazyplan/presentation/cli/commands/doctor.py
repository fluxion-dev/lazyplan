"""Doctor CLI command."""

from __future__ import annotations

import argparse
from pathlib import Path

from lazyplan.core.policies.lanes import AGENT_ROLES
from lazyplan.infrastructure import agent_install, host_models, profiles
from lazyplan.infrastructure.repo import find_repo_root
from lazyplan.presentation import setup
from lazyplan.services import hooks as hook_service
from lazyplan.services.worktrees import stale_reason, verify_worktree

from ....core.entities import PlanWorktree, Status
from ....core.ports.app import AppPort
from ...setup import health as setup_health
from ...setup import layout as setup_layout
from ..emit import _emit
from ..parser import package_version
from ..store import optional_store


def _worktree_row_findings(row: PlanWorktree) -> list[dict]:
    """Drift findings for one registered worktree."""
    base = {
        "kind": "worktree",
        "plan_id": row.plan_id,
        "milestone_id": row.milestone_id,
        "repo_path": row.repo_path,
        "worktree_path": row.worktree_path,
    }
    stale = stale_reason(row)
    if stale:
        state = "missing-path" if "does not exist" in stale else "unlisted"
        lane = f"lane M{row.milestone_id} " if row.milestone_id else ""
        return [{**base, "state": state, "detail": f"{lane}{stale}"}]
    check = verify_worktree(row.repo_path, row.worktree_path, row.branch)
    if not check.ok:
        lane = f"lane M{row.milestone_id} " if row.milestone_id else ""
        return [{**base, "state": "drift", "detail": f"{lane}{check.reason}"}]
    return []


def _worktree_findings(store: AppPort | None) -> list[dict]:
    """Every registry gap a doing or registered plan shows."""
    if store is None:
        return []
    findings: list[dict] = []
    for plan in store.list_plans(archived="show"):
        rows = store.list_plan_worktrees(plan.id)
        if plan.worktree_required and plan.status == Status.DOING and not rows:
            findings.append(
                {
                    "kind": "worktree",
                    "plan_id": plan.id,
                    "milestone_id": None,
                    "repo_path": "",
                    "worktree_path": "",
                    "state": "unregistered",
                    "detail": f"plan #{plan.id} is doing without a registered worktree",
                }
            )
        elif (
            plan.worktree_required
            and plan.status == Status.DOING
            and plan.dispatch_mode == "parallel"
        ):
            lanes = {row.milestone_id for row in rows}
            for milestone in store.list_milestones(plan.id):
                if milestone.id in lanes:
                    continue
                findings.append(
                    {
                        "kind": "worktree",
                        "plan_id": plan.id,
                        "milestone_id": milestone.id,
                        "repo_path": "",
                        "worktree_path": "",
                        "state": "unregistered-lane",
                        "detail": f"lane M{milestone.id} has no registered worktree",
                    }
                )
        for row in rows:
            findings.extend(_worktree_row_findings(row))
    return findings


def _profile_report(
    choice: setup.SetupChoice,
    state: setup.SetupState,
    root: Path | None,
    home: Path,
    db_path: Path,
) -> dict:
    """Missing, drifted, and unmarked profiles for the remembered setup."""
    profile_agents = (
        [] if choice.explicit_db or not state.profile_files else list(choice.agents or state.agents)
    )
    scope = "project" if state.placement == "repo" and root is not None else "global"
    loaded, _saved = profiles.load_all(db_path)
    tiers = host_models.effective_tiers(db_path, home, root, profile_agents)
    state_on_disk = agent_install.inspect_profiles(scope, root, home, profile_agents, db_path)
    models: dict[str, dict[str, str]] = {}
    for host in profile_agents:
        models[host] = {}
        for role in AGENT_ROLES:
            profile = loaded.get(role)
            if profile is None:
                continue
            try:
                resolved = profiles.resolve(profile, host, tiers=tiers)
            except profiles.ProfileError:
                continue
            models[host][role] = resolved["model"]
    return {
        "scope": scope,
        "agents": profile_agents,
        "files": [str(path) for path in state_on_disk.files],
        "missing": [str(path) for path in state_on_disk.missing],
        "drifted": [str(path) for path in state_on_disk.drifted],
        "unmanaged": [str(path) for path in state_on_disk.unmanaged],
        "models": models,
    }


def _doctor_data(
    args: argparse.Namespace, home: Path, state: setup.SetupState, store: AppPort | None
) -> tuple[setup_layout.SetupLayout, list[Path], dict]:
    choice = setup.choice_from_args(args, Path.cwd(), home, state)
    root = find_repo_root(Path.cwd())
    layout, skill_files = setup.preview(choice, root, home)
    report = setup_layout.inventory(layout)
    report["findings"] = [
        {"kind": f.kind, "path": str(f.path), "state": f.state, "detail": f.detail}
        for f in setup.detect_findings(Path.cwd(), home, state)
    ]
    missing_hooks = [path for path in state.hook_files if not Path(path).is_file()]
    report["hooks"] = {
        "enabled": state.hooks,
        "mode": state.effective_mode(),
        "files": list(state.hook_files),
        "missing": missing_hooks,
    }
    report["profiles"] = _profile_report(choice, state, root, home, layout.db)
    report["state"] = state.to_dict()
    report["skills"] = [str(path) for path in skill_files]
    report["worktrees"] = _worktree_findings(store)
    report["hook_probe"] = hook_service.probe(store, Path.cwd())
    health = setup_health.check(choice, state, root, home, package_version())
    report["health"] = [finding.to_dict() for finding in health.findings]
    report["pending_integrations"] = [
        item.to_dict() for finding in health.open for item in finding.items
    ]
    issues = bool(report["findings"]) or bool(missing_hooks)
    issues = issues or bool(report["pending_integrations"]) or bool(report["worktrees"])
    issues = issues or bool(report["profiles"]["missing"])
    issues = issues or bool(report["profiles"]["drifted"])
    issues = issues or (state.hooks and not state.hook_files)
    issues = issues or state.version != setup.SETUP_VERSION
    report["clean"] = bool(report["clean"] and not issues)
    return layout, skill_files, report


def _print_layout(layout: setup_layout.SetupLayout, skill_files: list[Path]) -> None:
    print(f"database:  {layout.db}")
    print(f"templates: {layout.templates_dir}")
    print(f"config:    {layout.config or '-'}")
    for skill in skill_files:
        print(f"skill:     {skill}")


def _print_hooks(report: dict) -> None:
    hooks = report["hooks"]
    print(f"hooks:     {hooks['mode'] if hooks['enabled'] else 'none'}")
    for path in hooks["files"]:
        print(f"hook:      {path}")
    probe = report["hook_probe"]
    print(f"hook check:{' ok' if probe['ok'] else ' ' + str(probe['reason'])}")
    for path in hooks["missing"]:
        print(f"hook miss: {path}")


def _profile_state(path: str, profile_report: dict) -> str:
    if path in profile_report.get("missing", []):
        return "missing"
    if path in profile_report.get("drifted", []):
        return "drifted"
    if path in profile_report.get("unmanaged", []):
        return "unmanaged"
    return "ok"


def _print_profiles(report: dict) -> None:
    profile_report = report.get("profiles", {})
    for path in profile_report.get("files", []):
        print(f"profile:   {path} ({_profile_state(path, profile_report)})")


def _print_notes(report: dict) -> None:
    for item in report["misplaced"]:
        print(f"misplaced: {item}")
    for item in report["missing"]:
        print(f"missing:   {item}")
    for finding in report["findings"]:
        print(f"finding:   {finding['kind']} {finding['path']} ({finding['state']})")
    for finding in report["health"]:
        tags = ", ".join(tag for tag in (finding["severity"], finding["decision"]) if tag)
        print(f"health:    {finding['label']} ({tags}): {finding['capability']}")
        if finding["fix"]:
            print(f"  fix:     {finding['fix']}")
    for item in report["worktrees"]:
        print(f"worktree:  plan {item['plan_id']} {item['state']} ({item['detail']})")
    for note in report["notes"]:
        print(f"note:      {note}")


def _print_doctor(layout: setup_layout.SetupLayout, skill_files: list[Path], report: dict) -> None:
    _print_layout(layout, skill_files)
    _print_hooks(report)
    _print_profiles(report)
    print(f"clean:     {'yes' if report['clean'] else 'no'}")
    _print_notes(report)


def _cmd_doctor(store: object | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only setup report; opens an existing database but never writes."""
    del store, actor
    home = Path.home()
    state = setup.load_state(home)
    db = optional_store(args)
    layout, skill_files, report = _doctor_data(args, home, state, db)
    code = 0 if report["clean"] else 1
    if getattr(args, "json", False):
        _emit(args, report)
        return code
    _print_doctor(layout, skill_files, report)
    return code
