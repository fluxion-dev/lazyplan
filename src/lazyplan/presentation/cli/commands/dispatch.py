"""Dispatch CLI: read-only lanes, waves, capacity, and worker prompts."""

from __future__ import annotations

import argparse
import sys

from lazyplan.services import dispatch

from ....core.ports.insights import InsightsPort
from ...shared import porcelain
from ...shared.design import msg_error
from ..emit import _emit


def _cmd_dispatch(store: InsightsPort, args: argparse.Namespace, actor: str) -> int:
    """Print the dispatch manifest for one plan."""
    del actor
    try:
        manifest = dispatch.build(
            store,
            args.plan,
            lane_id=args.lane,
            max_chars=args.max_chars,
        )
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        return _emit(args, manifest)
    if porcelain.enabled(args):
        for lane in manifest["lanes"]:
            print(
                porcelain.row(
                    "lane",
                    lane["milestone_id"],
                    lane["state"],
                    lane["title"],
                    f"plan:{manifest['plan']['id']}",
                    f"w{lane['group']}:{lane['agent_role']}",
                )
            )
        return 0
    print(_render(manifest))
    return 0


def _render(manifest: dict) -> str:
    """Human-readable dispatch manifest."""
    plan = manifest["plan"]
    capacity = manifest["capacity"]
    lines = [
        f"P{plan['id']} {plan['title']} · {plan['dispatch_mode']} · max {plan['max_agents']}",
        f"now      wave {manifest['wave']} · capacity"
        f" {capacity['active']}/{capacity['max']} active, {capacity['available']} available",
    ]
    if manifest["blocked"]:
        lines.append("blocked  " + "; ".join(manifest["blocked"]))
    lines.append("lanes:")
    for lane in manifest["lanes"]:
        lines.append(
            f"  M{lane['milestone_id']} {lane['title']} [{lane['state']}]"
            f" w{lane['group']} {lane['agent_role']}"
        )
        todo = lane.get("next")
        if todo:
            lines.append(f"    T{todo['id']} {todo['title']} ({todo['role']})")
        for worktree in lane["worktrees"]:
            state = "registered" if worktree["registered"] else "register"
            lines.append(f"    {state}: {worktree['worktree_path']} [{worktree['branch']}]")
        for reason in lane["blocked"]:
            lines.append(f"    blocked: {reason}")
    if manifest["dispatchable"]:
        lines.append("dispatchable:")
        for item in manifest["dispatchable"]:
            lines.append(
                f"  M{item['lane_id']} T{item['task_id']} {item['title']} ({item['role']})"
            )
            if item["claim_command"]:
                lines.append(f"    {item['claim_command']}")
    if manifest["actions"]:
        lines.append("actions:")
        for action in manifest["actions"]:
            lines.append(f"  {action}")
    return "\n".join(lines)
