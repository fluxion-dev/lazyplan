# P138 acceptance record

Final validation for plan 138. Evidence is reproducible from the tree; every
command below was run from the repository root.

## Criteria

| Criterion | Evidence |
| --- | --- |
| 3859 inventory covers every surface | `python3 tools/ia_inventory.py --check` |
| 3860 IA spec approved before refactor | [review.md](review.md) |
| 3861 one registry with conflict tests | `tests/ia/test_registry.py`, `tests/ia/test_surface_parity.py` |
| 3862 every child entity has a hub | `tests/tui/test_trust_hubs.py`, `tests/tui/test_coordination_hubs.py`, `tests/tui/test_provenance_hubs.py` |
| 3863 three-step reachability | [reachability.md](reachability.md), `tests/ia/test_reachability.py` |
| 3864 one taxonomy and keymap | `tests/ia/test_docs_keys.py`, `tests/ia/test_registry.py` |
| 3865 CLI and MCP path or exception | `tests/ia/test_surface_parity.py` |
| 3866 legacy paths keep working | `tests/cli/test_legacy_deprecation.py` |
| 3867 docs, man, site, and skills agree | `tools/check-docs.py`, `tools/check-site.py`, `tools/gen-man.py --check` |
| 3868 all gates green | `./tools/check.sh` |

## Validation result

- `./tools/check.sh` — **ALL GATES GREEN** on system and venv Python.
- Unittest: 1798 tests, venv `OK (skipped=1)`; system Python
  `OK (skipped=352)`.
- `python3 tools/ia_inventory.py --check` — every surface matches.
- `python3 tools/ia_reachability.py --check` — every action is at depth 3 or
  less.
- `lpui --porcelain lint --plan 138` — clean, exit 0.
- `lpui --porcelain trace --plan 138` — 21 proving relations, trace coverage
  1.0, zero trace gaps.
- `lpui --porcelain audit --plan 138` — exit 0, zero criteria gaps, zero trace
  gaps. Historical commit coverage is 33% and evidence coverage 71% because
  commits and criteria from before this plan were never linked; the strict
  coverage threshold is an opt-in CI choice, not a P138 gate.

Snapshots were updated intentionally for the new palette/hub hints and were
reviewed in `tests/snapshots/__snapshots__/`.

## Known approved exceptions

Setup, upgrade, doctor, export files, theme, fold, mark, and bulk remain on one
surface by design. `presentation/shared/registry_surfaces.py` lists each
exception with a reason, and `tests/ia/test_surface_parity.py` rejects an
untracked gap.

## Deprecations

Legacy CLI aliases and the moved detail keys (`q` detail, `Q` detail) remain
for one minor release. Removal target: `0.37.0`.
