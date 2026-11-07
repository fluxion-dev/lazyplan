# Roadmap context

> This file preserves the November 6, 2026 ideation. The roadmap is the
> decision; this is the reasoning. Keep it when the roadmap changes so the
> "why" survives the next session.

## Origin

The session started with a product-direction question: evaluate lazyplan's
current feature set and brainstorm improvements for the primary persona. The
persona statement that framed everything:

> A developer who uses agentic flows in their development, but does not want to
> junk up their issue tracking system with plans disguised as issues.

That is not a feature request. It is a positioning constraint. lazyplan should
be the place where plans live before they are committed, not another surface
that copies speculative work into Jira, Linear, or GitHub Issues.

## Persona and job

**The agentic developer** runs one or more coding agents, works in focused
bursts, reviews output rather than supervising keystrokes, and treats plans as
working memory.

**Job to be done:** preserve intent and context across sessions and prove what
shipped, without maintaining a second tracker.

**Anti-persona:** the program manager who wants sprints, estimates, assignees,
and a portfolio dashboard. Those needs belong in the tracker.

## What we evaluated

The review covered the CLI surface, TUI, MCP server, lifecycle hooks, the
packaged skill and AGENTS contract, the SQLite store and services layers, the
site, and the release and site gates.

### Capability scorecard

| Capability | State | Evidence and gap |
|---|---|---|
| Intent capture | Adequate | The interview skill and templates are strong. Creation is one-row-at-a-time; a 20-task plan takes 20+ writes and can leave a partial tree after a failure. |
| Work breakdown | Strong | Plan, milestone, task, and criteria hierarchy, status rollup, creation-order sequencing. No dates, owners, or estimates by design. |
| Execution coordination | Adequate | Atomic `next`, renewable claims, blocked work, force takeover. No file-level or worktree-level collision awareness. |
| Provenance | Strong | Commit and branch links, GitHub PR cache, source trail with diffs, criterion-to-commit trace. Read-only and GitHub-only. |
| Verification | Adequate | `task finish --require-pr/--require-checks`, lint, and audit. Evidence is descriptive; no evidence ledger. |
| Resume and continuity | Adequate | `brief` plus session-start and pre-compact hooks. No session object, decision log, or plan diff. |
| Human review | Adequate | Fast TUI, sticky preview, git pane, source trail, comments, static share. No review packet or drift view. |
| Collaboration | Adequate | Comments, mentions, HTML/JSON share, plan-granularity sync. Fine for solo; thin for several agents and a reviewer. |
| Integrations | Strong | MCP, porcelain, five hook hosts, one-way issue import. Deliberate no write-back. |
| UX, performance, trust | Strong | Keyboard-first TUI, palette, filters, timeline, local-first storage, benchmarked query budgets. |
| Scale | Strong | The 88-plan benchmark keeps tree, list, export, and TUI refresh on bounded query paths. |

### The five pains

1. **"Creating the plan costs more than the plan."** An agent making 20 to 30
   create calls is slow, token-expensive, and fragile on retry.
2. **"I approved a plan; by the end it was different and I cannot see how."**
   The skill says the plan is truth, but nothing enforces or surfaces drift.
3. **"Done is claimed, not proven."** PR and CI gates help, but criteria can
   still be ticked on trust.
4. **"Two agents stepped on each other."** Claims prevent duplicate task pickup,
   not duplicate file edits or worktree collisions.
5. **"A new session does not know what the last one decided."** `brief` gives
   state, not history or reasoning.

## Full idea backlog

Effort is a rough sizing: S, M, or L. Status is the roadmap decision, not the
original brainstorm.

| ID | Idea | Pain removed | Effort | Status |
|---|---|---|---|---|
| R1 | Plan compiler: `plan apply` for a nested document, one transaction, stable keys, dry-run | 30 calls to 1; no partial plans | M | Now |
| R2 | Plan recipes: feature, bugfix, and refactor skeletons on top of apply | Re-deriving the same shape | S | Now |
| R3 | Context pack: budgeted active plan, doing task, next, decisions, commits, claims | Cold-start cost | S/M | Now |
| R4 | Focus lens: doing, claims, blocked, attention, next | No cockpit for a human supervising agents | M | Now |
| R5 | Approval snapshot and plan diff with reasons and a TUI badge | Silent scope drift | L | Next candidate |
| R6 | Evidence ledger on criteria, with a finish gate and proof panel | "Trust me" completion | M | Next candidate |
| R7 | Review packet for a human or reviewer agent | Ad hoc handoff | S/M | Next candidate |
| R8 | Open questions and a plan-ready gate | Ambiguity buried in chat | S | Next candidate |
| R9 | Session records and handoff notes | No memory of the last session | M/L | Later candidate |
| R10 | Parallel-safe claims with touch-points and worktree recording | Two agents editing the same files | L | Later candidate |
| R11 | Outcome digest for a PR body or changelog | Closing work still needs a hand-written summary | S | Later candidate |
| R12 | Read-only external reference links | Losing the tracker connection without mirroring | S | Later candidate |

### Supporting ideas folded into the bets

- **Atomic and idempotent writes** are part of R1, not a separate feature.
- **Structural recipes** are part of R2; they are not a second template system.
- **MCP context resource and hook injection** are part of R3.
- **Plan-ready checks** combine lint, criterion coverage, and R8 questions.
- **Outcome publishing** is R11 and is deliberately not issue sync.

### Deferred ideas

- **Team sync improvements.** Plan-granularity sync conflicts are real, but the
  primary persona is solo. Revisit when a team workflow is validated.
- **Dependency graphs.** The model deliberately has no dependency field.
  Sequencing lives in creation order. Revisit only if parallel coordination
  proves it needs a soft dependency.
- **Plan health scoring.** Useful later, but it risks becoming a dashboard
  metric rather than a planning tool.
- **Automatic session summaries.** The host agent can write a summary; lazyplan
  should not call a model.
- **Worktree and branch creation.** Other tools own VCS actions. lazyplan links
  and records, never creates.

### Rejected ideas

- **Two-way Jira, Linear, or GitHub Issues sync.** It would make lazyplan a
  mirror and violate the persona's boundary.
- **Plans as issues.** The whole point is to keep speculative plans out of the
  tracker.
- **Sprints, story points, assignees, labels, priorities, dates.** These are
  tracker ceremony, not working memory.
- **Built-in LLM calls or a cloud account.** local-first and model-agnostic are
  product constraints.
- **An agent runtime.** lazyplan should not create branches, worktrees,
  commits, pushes, PRs, or merges.
- **Real-time multiplayer editing.** High cost, low fit for the persona.

## Assumptions

- The primary user is a solo developer or a developer leading a small agent
  fleet, not a program manager.
- The coding agent is the source of intelligence; lazyplan supplies structure
  and evidence.
- A plan is valuable only if it is read again. Resume quality is the retention
  mechanism.
- The issue tracker remains the system of record for committed work.
- Local-first, no-account storage is non-negotiable for the beachhead user.
- Agents can reliably call a CLI or MCP tool; the bottleneck is ceremony and
  context, not tool access.

## Open questions

1. **Beachhead host:** OpenCode, Claude Code, or genuinely cross-host? This
   changes the investment in hooks versus MCP versus CLI.
2. **Solo or team:** is the near-term user one developer with agents, or a small
   team sharing a repo plan? Team pulls review packet and outcome digest
   forward.
3. **Approval:** advisory or enforceable? The recommendation is advisory first,
   then an opt-in hard gate.
4. **Evidence:** record-only, or should lazyplan ever execute a declared
   verification command? The recommendation is record-only; execution belongs
   to the agent or CI.
5. **Activation moment:** what should a new user feel in the first ten minutes:
   a plan created, an agent writing to it, or a plan closed with proof?

## Validation plan

- Instrument activation: first plan created and first agent write within ten
  minutes.
- Instrument resume: sessions per active plan and time to first write.
- Time a 20-task plan before and after R1.
- Count CLI calls and rows per plan as anti-metrics.
- Interview five agentic developers about where plans currently die: chat,
  tracker, or nowhere.
- Test whether a post-approval diff increases willingness to delegate.

## Session decisions

- One roadmap plan, P134, with Foundation, Now, Next, and Later milestones.
- A separate `/roadmap.html` page rather than a landing-page section.
- Now cut in detail; Next and Later kept as candidate scoping tasks.
- Stable item IDs plus a doc/site drift test.
- No issue-tracker mirroring; publish outcomes and link references.
- A metaplan for turning horizons into implementation plans.
- Next shipped 2026-11-06: approvals, evidence, questions, and review; Later moves to scoping.

## Where the context lives

| Artifact | Purpose |
|---|---|
| `docs/product/roadmap.md` | The current direction and the stable item IDs. |
| `docs/product/roadmap-context.md` | This file: the reasoning, backlog, and open questions. |
| `docs/product/roadmap-metaplan.md` | The repeatable process for horizon intake, scoping, plan cut, review, and close. |
| lazyplan P134 | The execution journal with milestones, tasks, criteria, and commit links. |
| `site/roadmap.html` | The public Now/Next/Later summary. |
| `docs/product/roadmap.md` decision log | The dated record of direction changes. |

When this file and the roadmap disagree, the roadmap is the decision; update
this file only to preserve the reasoning behind a change.
