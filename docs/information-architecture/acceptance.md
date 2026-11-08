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

## Validation commands

```bash
python3 tools/ia_inventory.py --check
python3 tools/ia_reachability.py --check
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/ia -t .
./tools/check.sh
lpui --porcelain lint --plan 138
lpui --porcelain audit --plan 138 --min-evidence 0.8
lpui --porcelain trace --plan 138
```

## Known approved exceptions

Setup, upgrade, doctor, export files, theme, fold, mark, and bulk remain on one
surface by design. `presentation/shared/registry_surfaces.py` lists each
exception with a reason, and `tests/ia/test_surface_parity.py` rejects an
untracked gap.

## Deprecations

Legacy CLI aliases and the moved detail keys (`q` detail, `Q` detail) remain
for one minor release. Removal target: `0.37.0`.
