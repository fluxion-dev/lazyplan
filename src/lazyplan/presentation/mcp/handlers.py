"""Handler factories for the repeated MCP tool shapes.

Each factory builds one closure per tool, so a shape is implemented once no
matter how many tools use it. The closures read the store on every call, which
keeps the no-database error where the dispatcher expects it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from lazyplan import services

from ...core.ports.app import AppPort

#: One tool handler: the arguments dict to the JSON payload.
Handler = Callable[[dict], object]

#: Where a handler reads its store, so a missing database still errors per call.
StoreOf = Callable[[], AppPort]


def kind_id_rows(
    store_of: StoreOf, read: Callable[[AppPort, str, int], Iterable[object]]
) -> Handler:
    """vars() of every row a kind/id read returns."""

    def handler(args: dict) -> object:
        return [vars(row) for row in read(store_of(), str(args["kind"]), int(args["id"]))]

    return handler


def one_arg_rows(
    store_of: StoreOf,
    read: Callable[[AppPort, int], Iterable[object]],
    key: str = "id",
) -> Handler:
    """vars() of every row a single-argument read returns."""

    def handler(args: dict) -> object:
        return [vars(row) for row in read(store_of(), int(args[key]))]

    return handler


def kind_id_action(store_of: StoreOf, actor: str, call: Callable[..., object]) -> Handler:
    """Run one service call addressed by kind and id, as this actor."""

    def handler(args: dict) -> object:
        return call(store_of(), str(args["kind"]), int(args["id"]), actor=actor)

    return handler


def question_note(store_of: StoreOf, actor: str, call: Callable[..., Any]) -> Handler:
    """Resolve or reopen one question; a missing row is a tool error."""

    def handler(args: dict) -> object:
        question = call(store_of(), int(args["id"]), note=str(args.get("note") or ""), actor=actor)
        if question is None:
            raise KeyError(f"question {args['id']} not found")
        return vars(question)

    return handler


def maintenance_days(
    port_of: Callable[[], Any],
    actor: str,
    run: Callable[..., Any],
    payload: Callable[[Any], object],
) -> Handler:
    """Run one days/apply maintenance call and render its payload view."""

    def handler(args: dict) -> object:
        result = run(
            port_of(),
            days=args.get("days") or None,
            apply=bool(args.get("apply")),
            actor=actor,
        )
        return payload(result)

    return handler


def review_packet(store_of: StoreOf, build: Callable[..., Any]) -> Handler:
    """Build one plan packet: the requested plan, else the active one."""

    def handler(args: dict) -> object:
        store = store_of()
        plan = (
            store.get_plan(int(args["plan"])) if args.get("plan") else services.active_plan(store)
        )
        if plan is None:
            return {"plan": None, "markdown": "no active plans\n", "payload": {}}
        packet = build(
            store,
            plan.id,
            max_chars=int(args.get("max_chars") or 0),
            cwd=Path.cwd(),
        )
        if packet is None:
            raise KeyError(f"plan {plan.id} not found")
        return {"plan": plan.id, "markdown": packet.markdown, "payload": packet.payload}

    return handler
