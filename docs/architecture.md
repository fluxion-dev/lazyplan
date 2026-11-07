# Architecture

lazyplan is organised as one pure core, one services layer, and one
presentation layer. Infrastructure and the SQLite store sit below services as
adapters. Every feature appears in each layer as the same slice name.

## Layers

Dependencies point one way:

```text
core -> infrastructure -> store -> services -> presentation -> entry point
```

- `core` is pure. It holds entities, policies, and ports. It imports only the
  standard library and `lazyplan.core`; it never imports `sqlite3`, `os`,
  `pathlib`, or another lazyplan layer.
- `infrastructure` holds external adapters: text files, templates, git, forge,
  GitHub, skills, hooks, setup files, and update staging. It may use core.
- `store` is the SQLite adapter. It implements the core ports structurally and
  may use core and infrastructure.
- `services` holds use cases. It types against core ports, never against the
  concrete `Store`, and may use core and infrastructure.
- `presentation` holds every surface: the TUI, CLI, MCP server, setup flow, and
  shared rendering. It may use core and services.
- `__main__.py` is the only entry point and may import any package.

The gate lives in `tests/architecture/test_architecture.py`. A new top-level
module needs a layer entry, and `tests/architecture/test_module_budget.py`
keeps hand-written modules under 600 lines.

## Slices

| Slice | Owns |
| --- | --- |
| planning | plans, milestones, tasks, criteria, plan questions, sessions, external references, status rollup, tree reads |
| coordination | claims, next, leases, touch-points, blocked work |
| collaboration | notes, comments, mentions |
| provenance | commits, repos, branches, forge and GitHub, source trail, trace, criterion evidence, task start and finish gates |
| insights | metrics, stats, audit, brief, lint, attention, plan readiness, review packet, ship note |
| transfer | export, import, sync, share, issue intake, seed |
| environment | setup layout, hooks, skills, upgrade, update staging |

Each slice has a policy module and a port in `core`, a use-case module in
`services`, and its surfaces in `presentation`. The TUI shows several slices in
one shell; the slice name still owns the widget, controller, and read service.

## Ports

Ports are `typing.Protocol` definitions in `core/ports/`. They name what a
use case needs, not how SQLite implements it. `Store` satisfies each port
structurally, so there are no runtime adapter classes and no duplicate method
bodies.

A service function takes the narrow port it needs:

```python
def create_task(plans: PlanningPort, milestone_id: int, title: str) -> Task:
    ...
```

The composition root passes a `Store`:

```python
store = Store(db_path)
services.planning.create_task(store, milestone_id, title)
```

## Composition roots

Only a composition root constructs `Store`:

- `presentation/cli/main.py`
- `presentation/tui/app.py`
- `presentation/mcp/server.py`
- `presentation/setup/wizard.py`

Every other presentation module receives the service result it needs, or calls
a read service. `tests/architecture/store_import_baseline.json` records the
remaining direct Store imports while a slice migrates; the list only shrinks
and must be empty before release.

## Shims

During the refactor, old module paths re-export the new canonical modules so
the suite stays green while slices move. Shims are temporary:

- a shim re-exports names; it contains no behavior;
- the slice that moves a module updates its direct callers;
- the final milestone deletes every shim and old root.

No new code may import a shim path.

## Adding a slice

1. Add the policy and port under `core`.
2. Add the use case under `services` and type it against the port.
3. Add the surface under `presentation`, using the service.
4. Add the layer entries and tests, and shrink the Store-import allowlist.
5. Cover the new behavior with a targeted suite before closing the task.
