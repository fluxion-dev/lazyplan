# Performance

`tools/perf_bench.py` is the performance source of truth. It builds a throwaway
SQLite journal with fixed row counts, then measures the read paths that dominate
normal use. It never touches the real home database and never opens a network
connection.

## Fixture

Every run creates exactly:

| Table | Rows |
|---|---:|
| plans | 88 |
| milestones | 275 |
| tasks | 789 |
| criteria | 2,095 |
| events | 10,703 |
| vcs_links | 708 |
| entity_repos | 132 |

The fixture marks 48 plans archived, 4 tasks doing, 3 tasks blocked, and leaves
6 task criteria open. A tiny one-commit git repo is added for status/show
measurements.

## Run it

```bash
# Full report
python3 tools/perf_bench.py

# Small fixture for local iteration
python3 tools/perf_bench.py --quick

# The CI gate (exact query ceilings + generous wall ceilings)
python3 tools/perf_bench.py --check
```

`--check` runs once from `tools/check.sh` after the unit suites. It is also
safe to run by hand. `--json` prints the full report.

## Pre-change baseline

Captured from `a0d31f5` (the benchmark and budget commit, before any
optimization). The Windows baseline came from the same production code with
only the fixture path-normalization test fix applied.

| Metric | Queries | Linux | macOS | Windows |
|---|---:|---:|---:|---:|
| `services.tree` | 909 | 120 ms | 163 ms | 270 ms |
| `services.tree_limit5` | 909 | 120 ms | 158 ms | 272 ms |
| `attention_ids` | 2,304 | 162 ms | 249 ms | 507 ms |
| `list_text` | 1,828 | 240 ms | 367 ms | 541 ms |
| `list_json` | 7,853 | 560 ms | 854 ms | 1,642 ms |
| `show_plan` | 139 | 2 ms | 2 ms | 5 ms |
| `export_all` | 18,612 | 1,222 ms | 1,909 ms | 3,627 ms |
| `audit_report` | 4,740 | 357 ms | 511 ms | 1,091 ms |
| `git_status` | — | 5 ms | 44 ms | 80 ms |
| `git_show` | — | 5 ms | 52 ms | 80 ms |
| `tui_refresh` | 5,148 | 557 ms | 778 ms | 1,303 ms |

## Budgets

Query counts are exact and deterministic. Wall ceilings are deliberately
generous because hosted runners and Windows process spawns are noisy; they
catch sleeps, network waits, and whole-database scans rather than small
variance.

Budgets live in `BUDGETS` in `tools/perf_bench.py`. Query budgets are the hard
gate. Tighten them when a milestone removes a query class; never loosen a
query budget to hide a new per-row read. Update a wall ceiling only when a
platform baseline shows a real, explainable shift.

## Out of scope

The website build, packaging, and release scripts are not measured here. They
have their own build checks.
