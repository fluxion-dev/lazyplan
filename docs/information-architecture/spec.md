# Target information architecture

This spec is the review artifact for P138. The generated
[inventory](inventory.md) proves what exists today; the
[findings](findings.md) rank the gaps. This page defines the target model and
the rules that later refactor milestones implement.

## Entity model

Every record belongs to exactly one owner. The tree is
`plan → milestone → task`; criteria, evidence, questions, references, claims,
sessions, notes, comments, commits, files, and pull requests hang off those
owners through the links below.

| Entity | Owner | Hub? | Cross-links |
| --- | --- | --- | --- |
| `plan` | root | Yes | milestones, criteria, questions, references, sessions, notes, comments, repos, commits, PRs, events |
| `milestone` | plan | Yes | tasks, criteria, notes, comments, commits, PRs |
| `task` | milestone | Yes | criteria, claims, touch-points, notes, comments, commits, files, PRs |
| `criterion` | plan, milestone, or task | Yes | evidence, proving tasks |
| `evidence` | criterion | Yes | task, commit, PR, artifact |
| `question` | plan | Yes | resolution note |
| `reference` | plan | Yes | external URL |
| `claim` | task | Yes | actor, worktree, repo |
| `session` | plan | Yes | events, handoff note |
| `note` | plan, milestone, or task | Yes | actor, timestamp |
| `comment` | plan, milestone, or task | Yes | mentions, resolution |
| `commit` | task, milestone, or plan | Yes | files, PRs, repo |
| `file` | commit | Yes | diff |
| `pull_request` | task, milestone, or plan | Yes | checks, reviews, commits |
| `repo` | plan, milestone, or task | Yes | branch, commits, PRs |
| `event` | any row | Yes | actor, target, override reason |
| `override` | event | Yes | actor, target, reason |

Inline-only data: touch-points (task field list), handoff (session field), and
repo inheritance (effective repos). They appear inside their owner's hub rather
than as separate tree rows.

## Primary journeys

Each journey starts at the tree and ends in a durable result. The budget is the
number of interactions from the tree; hubs never exceed three.

| Journey | Entry | Ordered steps | Exit | Budget |
| --- | --- | --- | --- | --- |
| Capture | tree | `n` → choose kind → fill title/why/what | new plan or task | 2 |
| Organize | tree | open plan → add milestone/task → reorder by creation order | tree shows the cut | 3 |
| Execute | tree | open task → claim → move doing → note handoff | task doing with a lease | 3 |
| Prove | tree | open criterion → prove → record command/commit | criterion ticks with evidence | 3 |
| Ship | tree | open plan → review → export/ship note | Markdown packet | 3 |
| Inspect | tree | open row → provenance → commit/file/PR | read-only trail | 3 |
| Coordinate | tree | open task → claims/touch-points → claim/block | active lease or blocked row | 3 |
| Administer | tree | palette → setup/update/doctor | resolved layout | 3 |

Human and agent variants use the same steps; agents call the CLI/MCP adapter for
the same action ID instead of pressing the key.

## Canonical taxonomy

Action IDs are noun-first (`entity.verb`). The prefix is either an entity from
the table above or a UI namespace: `app`, `view`, `row`, `bulk`, `git`,
`source`, `theme`, or `palette`. Surface adapters keep their current names while
they migrate:

| Surface | Adapter |
| --- | --- |
| TUI | `presentation/shared/palette.py` command IDs map through `registry.PALETTE_TO_ACTION` |
| CLI | parser groups and legacy verbs map to the same action ID |
| MCP | tool names map to the same action ID |
| Docs/help | labels and hints render from the action label |

Disposition policy: palette IDs are `keep` when they already match the label;
`merge` when several palette IDs (move to todo/doing/done, bulk move, fold one/
all) share one action; `rename` when the label changes but the handler stays;
`deprecate` only for legacy CLI aliases and removed keys.

## Keymap

Global keys are reserved and mean the same thing everywhere: `?` help,
`c` palette, `escape` back, `q` quit, `O` manual override.

| Context | Keys |
| --- | --- |
| tree | `j`/`k` move, `left`/`right` fold, `enter` detail, `space` mark, `e` edit, `s` status, `x` tick, `a` add criterion, `d` delete, `n` create, `/` filter, `f` plan mode, `g` source, `z` fold, `r` refresh, `t` theme |
| detail | `e` edit, `s` advanced status, `x` tick, `p` prove, `d` delete, `g` source, `escape` back |
| hubs | `j`/`k` move, `enter` open, `escape` back, `?` help |
| modal | `enter` accept, `escape` cancel |

Conflict resolution: `q` is always quit. The detail page's current `q`
(add question) becomes `Q`; the old binding remains for one minor release with
a deprecation notice. `c` is always the palette; the detail page does not
rebind it. Keys that differ only by screen (for example `s` advance status in
the tree and detail) share one action ID and one meaning.

## Navigation graph

The main tree is the root. Every hub is at most three interactions away.

| Route | Path | Depth |
| --- | --- | --- |
| tree → plan detail | `enter` | 1 |
| tree → task detail | `enter` on task | 1 |
| tree → detail → trust hub | `enter` → palette trust group | 2 |
| tree → detail → provenance | `enter` → `g` | 2 |
| tree → source trail | `g` | 1 |
| tree → detail → pull requests | `enter` → `P` | 2 |
| tree → detail → activity | `enter` → `A` | 2 |
| tree → create → form | `n` → kind | 2 |
| tree → export picker | palette → export | 2 |
| tree → update | `U` | 1 |

Back and forward history, breadcrumbs, and selection restoration are required on
every route. Palette and help are available in every context.

## Surface parity

| Action group | TUI | CLI | MCP | Docs | Exception |
| --- | --- | --- | --- | --- | --- |
| plan create/edit/delete | yes | yes | yes | yes | — |
| milestone/task create/edit/delete | yes | yes | yes | yes | — |
| task move/claim/block/finish | yes | yes | yes | yes | — |
| criteria tick/prove/relate | yes | yes | yes | yes | — |
| questions/references | yes | yes | yes | yes | — |
| sessions/handoffs | yes (new hub) | yes | read-only | yes | M454 |
| comments/notes | yes | yes | yes | yes | — |
| commits/files/PRs/repos | yes | yes | read-only | yes | — |
| feed/overrides | yes | yes | read-only | yes | — |
| setup/upgrade/doctor | palette | yes | no | yes | CLI-only by design |
| theme/fold/mark/bulk | yes | no | no | no | TUI-only by design |

Exceptions marked `M45x` are resolved by that milestone. CLI-only setup and
TUI-only view actions are approved exceptions and stay in the parity matrix.
`registry_surfaces.py` records one mapping per surface plus every approved
exception with a reason; `tests/ia/test_surface_parity.py` fails on an
undocumented gap.

## Deprecation policy

Legacy CLI aliases and removed TUI keys keep working for one minor release. Each
deprecation names the replacement and emits a visible notice in `--help`,
palette, or key handling. Removal target: `0.37.0` for deprecations introduced
in `0.36.0`. The registry records `deprecated_in` and `removal` per action, and
tests reject a deprecation without a removal target.

## Registry scaffold

`presentation/shared/registry.py` is stdlib-only and owns entities, namespaces,
surfaces, actions, keys, contexts, routes, palette aliases, and deprecation
fields. `palette.py` and `help.py` stay facades during migration. Tests reject
duplicate IDs, unknown taxonomy, duplicate keys in one context, palette orphans,
routes deeper than three, and any import of Textual.

## Validation and removal plan

The [reachability report](reachability.md) is generated from the registry and
proves every action is at most three interactions from the tree. The
[newcomer walkthrough](walkthrough.md) records each journey at 80x24 and
120x40; the [acceptance record](acceptance.md) carries the final gate evidence.
The [inventory](inventory.md) is the reproducible surface snapshot.

Legacy CLI aliases and the moved detail keys keep working for one minor
release. Removal target: `0.37.0`, for deprecations introduced in `0.36.0`.
`registry.deprecations()` names each replacement, and the help screen renders
the moved-key notice; `tools/ia_inventory.py --check` and
`tests/cli/test_legacy_deprecation.py` keep the promise visible until removal.
