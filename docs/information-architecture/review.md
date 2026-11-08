# Information architecture review

Review gate for P138 milestone 451. The generated [inventory](inventory.md)
proves the current surfaces; [findings](findings.md) ranks the gaps; [spec.md](spec.md)
is the target model under review.

## Decision

Approved as written by the human on 2026-11-07. No corrections were requested,
so no spec edits were needed.

Approved items:

- Entity model: 17 entity hubs plus 8 UI namespaces.
- Journeys: Capture, Organize, Execute, Prove, Ship, Inspect, Coordinate,
  Administer, each within the three-interaction budget.
- Keymap: `q` quits everywhere; detail's add-question becomes `Q` and keeps the
  old binding for one minor release. Global keys have one meaning.
- Taxonomy: noun-first action IDs; palette IDs map through
  `registry.PALETTE_TO_ACTION`, while CLI and MCP keep their current names
  during migration.
- Navigation: back, forward, breadcrumbs, and selection restoration on every
  route; every hub is at most three interactions from the tree.
- Parity exceptions: setup, upgrade, and doctor stay CLI-only; theme, fold,
  mark, and bulk stay TUI-only.
- Deprecation: legacy aliases and removed keys work for one minor release;
  removal target is `0.37.0`.
- Hub sequencing: provenance, feed, and override hubs land in M455.

## Corrections

None.

## Gate evidence

- `python3 tools/ia_inventory.py --check` — every inventoried surface matches
  the committed snapshot.
- `PYTHONPATH=src .venv/bin/python -m unittest tests.ia.test_registry tests.ia.test_map_invariants`
  — registry and map invariants pass.
- `python3 tools/check-docs.py` — documentation allowlist and links pass.
- `./tools/check.sh` — full gate suite green before the refactor milestone.

## Sign-off

The human approved the spec on 2026-11-07. No refactor task had started before
this record, so M452 may begin.
