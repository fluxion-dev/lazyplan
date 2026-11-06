# Product roadmap

> **Status:** active · **Last updated:** 2026-11-06 · **Plan of record:** P134 in lazyplan
>
> This page is the product direction. The detailed reasoning is in
> [roadmap-context.md](roadmap-context.md), and the repeatable process for
> turning a horizon into an implementation plan is in
> [roadmap-metaplan.md](roadmap-metaplan.md). The live work is tracked in
> lazyplan plan P134.

## Positioning

lazyplan is the working memory and audit trail for agentic development. It
keeps one plan that the human and the agent can both read, with the evidence
that shows what shipped.

The issue tracker is for committed work. lazyplan is for the thinking before
commitment: the why, the slice, the decision, and the proof.

## Persona and job

**Primary persona: the agentic developer.** They run one or more coding agents,
work in focused bursts, review output instead of babysitting keystrokes, and
refuse to turn speculative plans into tickets.

**Job to be done:** When I hand work to an agent, I need to preserve intent and
context across sessions and prove what shipped, without maintaining a second
tracker.

**Anti-persona:** a program manager who wants sprints, estimates, assignees, and
a portfolio dashboard. Those needs belong in an issue tracker, not here.

## What we will not build

- Two-way Jira, Linear, or GitHub Issues sync.
- Plans mirrored as issues.
- Sprints, story points, assignees, labels, priorities, or date planning.
- A built-in LLM or a cloud account.
- An agent runtime that creates branches, worktrees, commits, or merges.
- Real-time multiplayer editing.

Each of these would make lazyplan more like the tracker the persona is escaping.

## Product principles

1. **The plan is the truth.** Change the plan before changing course, not after.
2. **Local-first, no account.** The database is yours; export it any time.
3. **The agent brings the intelligence.** lazyplan supplies structure,
   constraints, and evidence; it does not call a model.
4. **Proof over claims.** A tick is a claim; a commit, a check, or an evidence
   row is proof.
5. **Cheap to capture, cheap to resume.** If planning costs more than the work,
   the product has failed.
6. **One loop, not more surfaces.** Capture, execute, prove, resume.
7. **Read-only integrations.** Pull context in, publish outcomes out, and never
   mirror the plan into a tracker.

## Current capability scorecard

| Capability | State | Read |
|---|---|---|
| Intent capture | Adequate | The interview skill and templates are strong, but creation is one-row-at-a-time. No atomic or bulk path, so agents burn context and can leave partial plans. |
| Work breakdown | Strong | Plan, milestone, task, and criteria hierarchy with rollup and creation-order sequencing. Deliberately free of dates, owners, and estimates. |
| Execution coordination | Adequate | Claims, leases, `next`, blocked work, and takeover. Coordination is task-level only, with no file or worktree collision awareness. |
| Provenance | Strong | Commits, branches, pull requests, source trail with diffs, and criterion-to-commit trace. GitHub-only and read-only by design. |
| Verification | Adequate | Finish gates, lint, and audit. Evidence is descriptive; there is no structured proof ledger. |
| Resume and continuity | Adequate | `brief` plus session-start and pre-compact hooks. No session memory, decision log, or plan diff. |
| Human review | Adequate | Strong read surfaces, source trail, comments, and share. No review packet and no drift view. |
| Collaboration | Adequate | Comments, mentions, static share, and plan-granularity sync. Fine for solo; thin for a human with several agents. |
| Integrations | Strong | MCP, porcelain, five hook hosts, and one-way issue import. Deliberate no write-back. |
| UX, performance, trust | Strong | Fast TUI, palette, filters, timeline, local-first storage, and benchmarked query budgets. |

The gaps cluster at the two ends of the loop: getting a plan in cheaply, and
coming back to one cold.

## The loop

```text
intent -> execution -> proof -> resume
```

Five leaks keep the loop from closing:

1. **Capture is expensive.** A 20-task plan costs 20 to 30 writes and can fail
   halfway through.
2. **Approved plans drift.** The skill says the plan is truth, but nothing
   surfaces a post-approval change.
3. **Done is claimed, not proven.** Criteria can be ticked on trust.
4. **Parallel agents collide.** Claims prevent duplicate task pickup, not
   duplicate file edits.
5. **A cold session has no memory.** `brief` gives state, not history or
   reasoning.

## Horizons

The horizons are ordered. A later horizon starts only after the prior horizon's
criteria are ticked and the plan is audited. Items use stable IDs so the docs,
site, lazyplan, and commits refer to the same thing.

### Now — Capture and resume

**Goal:** make a plan cheap to create and a session cheap to resume. This is
the first implementation bet and the only horizon currently cut into detailed
tasks.

#### R1 — Plan compiler

**Status:** Now

**Outcome:** an agent can create a plan, its milestones, its tasks, and its
criteria in one atomic write, with a dry-run preview and idempotent retries.

**Why:** the interview is valuable; the 30 calls are not. A single document
also eliminates partial plans and makes structural recipes possible.

**Shape:** `lpui plan apply --file plan.yaml [--dry-run]` accepts a nested
document with stable keys. One transaction creates the tree; one bad row rolls
everything back. Retrying the same document is a no-op.

**Success metric:** time and CLI calls to create a 20-task plan, before and
after. Target: one call, under 100 ms after validation.

**Tracked in:** T1361, T1362.

#### R2 — Plan recipes

**Status:** Now

**Outcome:** feature, bugfix, and refactor recipes pre-cut the shape of a plan
without pre-filling the content. QA, documentation, and refactor tasks are
present by default.

**Why:** every plan re-derives the same skeleton. Recipes keep the interview
focused on the actual problem, not the ceremony.

**Shape:** recipes are structural templates consumed by `plan apply`. They
supply milestone and task skeletons plus criteria prompts, and they leave the
words empty for the interview.

**Success metric:** percentage of new plans that start from a recipe; time to
first review gate.

**Tracked in:** T1363.

#### R3 — Context pack

**Status:** Now

**Outcome:** a new session reads one budgeted packet instead of reconstructing
the plan from the tree.

**Why:** resume is the retention moment. If a cold session starts smart, the
plan earns its keep every day.

**Shape:** a read-only composition of the active plan, doing task, next three
todos, open criteria, recent decisions and notes, recent commits, unresolved
comments, and claims. Exposed as `lpui context --max-chars N`, an MCP resource,
and session-start and pre-compact hook context.

**Success metric:** sessions per active plan; time from session start to the
first plan-affecting write.

**Tracked in:** T1364, T1365.

#### R4 — Focus lens

**Status:** Now

**Outcome:** the human sees what is in flight without scanning the whole tree.

**Why:** with several agents, the question is not "what exists?" but "what is
moving, what is stuck, and what needs me now?"

**Shape:** a TUI view or filter preset for doing tasks, active claims, blocked
work, attention rows, and next candidates. Existing tree, filter, and mark
behavior stays intact.

**Success metric:** time to find blocked or aging work; use of the lens in
weekly sessions.

**Tracked in:** T1366.

### Next — Trust layer

**Goal:** make delegation safe as agents take on more. These bets are candidates
until Now ships; each has a scoping task now and detailed implementation tasks
at horizon start.

#### R5 — Approval snapshots and plan diff

**Status:** Next candidate

**Outcome:** a human approves a plan revision, and later sees exactly what
changed: added tasks, changed scope, removed criteria, and why.

**Why:** the gap between "I approved this" and "this is what ran" is where trust
is lost. A diff makes drift visible without blocking the agent.

**Shape:** a revision snapshot on approval, `plan diff`, a reason on
scope-changing edits, and a TUI drift badge. Enforcement is opt-in.

**Success metric:** post-approval change rate; time to re-approval; drift caught
per plan.

**Tracked in:** T1370.

#### R6 — Evidence ledger

**Status:** Next candidate

**Outcome:** a criterion can carry proof, not just a tick.

**Why:** "done" should be auditable. Recording evidence also gives reviewers
something concrete to inspect without reading the whole transcript.

**Shape:** record the command, exit code, commit or PR, artifact path, and actor
against a criterion. lazyplan records; the agent or CI runs the command. A
finish gate can require evidence, and the TUI shows a proof panel.

**Success metric:** percentage of closed criteria with evidence; strict audit
pass rate.

**Tracked in:** T1371.

#### R7 — Review packet

**Status:** Next candidate

**Outcome:** a human or reviewer agent receives one Markdown packet with the
plan, the post-approval diff, criteria coverage, commits and PRs, lint and audit
findings, and open questions.

**Why:** handoff is currently assembled by hand from several commands.

**Shape:** `lpui review --plan P` or `brief --review` emits a Markdown packet
that can become a PR body or a review comment.

**Success metric:** time from "agent says done" to a human review decision.

**Tracked in:** T1372.

#### R8 — Open questions and plan-ready gate

**Status:** Next candidate

**Outcome:** ambiguity is recorded before it becomes rework, and a plan cannot
claim readiness while material questions are open.

**Why:** the interview already hunts ambiguity; the product should keep the
result instead of losing it in chat.

**Shape:** first-class open questions per plan, plus a `plan ready` gate that
combines lint, criterion coverage, and unresolved questions.

**Success metric:** rework rate; percentage of plans that pass readiness on the
first review.

**Tracked in:** T1372.

### Later — Parallel agents and handoff

**Goal:** keep lazyplan the source of truth when more than one agent works at
once. These bets are candidates until Next ships.

#### R9 — Session records

**Status:** Later candidate

**Outcome:** a session has a start, an end, a summary, and handoff notes, and
the feed can be read per session.

**Why:** `brief` gives state, not history. A session record preserves why the
last agent made the choices it did.

**Shape:** `session start` and `session end --summary`, events tagged by
session, and `session show` for a compact read.

**Success metric:** resume quality; time to reconstruct the last session's
decisions.

**Tracked in:** T1374.

#### R10 — Parallel-safe claims

**Status:** Later candidate

**Outcome:** two agents do not claim work that will edit the same files.

**Why:** task-level leases are not enough when agents work in parallel
worktrees. Collisions are expensive and invisible until merge time.

**Shape:** structured touch-points on tasks, overlap checks against active
claims, worktree recorded on claim, and a finish warning when linked commits
overlap another open task.

**Success metric:** claim takeovers per 100 tasks; file-overlap warnings per
week.

**Tracked in:** T1375.

#### R11 — Outcome digest

**Status:** Later candidate

**Outcome:** closing a plan produces a ship note for a PR body or changelog
without writing a single issue.

**Why:** the persona still needs to communicate outcomes, but not by mirroring
the plan into a tracker.

**Shape:** `lpui ship --plan P` or `lpui digest --plan P` prints Markdown with
the why, what shipped, evidence, commits and PRs, residual risks, and
follow-ups.

**Success metric:** time to close out a plan; percentage of plans with a
published outcome.

**Tracked in:** T1376.

#### R12 — External reference links

**Status:** Later candidate

**Outcome:** a plan can point at an epic or issue without copying it.

**Why:** committed work still lives in the tracker. A read-only link preserves
the connection without making lazyplan a mirror.

**Shape:** store the URL and provider identity on a plan, show it in detail, and
never write back.

**Success metric:** plans linked to external work; zero write-back calls.

**Tracked in:** T1376.

## Cross-horizon metrics

| Metric | Type | Why it matters |
|---|---|---|
| Plans closed with evidence per active developer per week | North star | Measures completed loops, not rows created. |
| First plan and first agent write within 10 minutes | Activation | The product must prove value before the first session ends. |
| Sessions per active plan | Retention | A plan that is not resumed is not working memory. |
| Percentage of plans changed after approval | Drift | Lower is better, but zero means the plan is not learning. |
| Percentage of criteria with evidence | Quality | Moves "done" from claim to proof. |
| Claim takeovers per 100 tasks | Coordination | Measures how often agents collide. |
| CLI calls and rows per plan | Anti-metric | If these rise, planning is becoming the second job. |
| Time to first plan | Anti-metric | Ceremony is the enemy of capture. |

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-11-06 | One roadmap plan (P134) with Foundation, Now, Next, and Later milestones. | One source of truth; each horizon can close independently. |
| 2026-11-06 | A separate `/roadmap.html` page, not a landing-page section. | Protects the landing page's 750-word and 10-figure budget; gives the roadmap room to be useful. |
| 2026-11-06 | Now is cut in detail; Next and Later get candidate scoping tasks. | Avoids inventing unscouted implementation work. |
| 2026-11-06 | Stable item IDs and a doc/site drift test. | Keeps the repo and site aligned without a generator or a runtime dependency. |
| 2026-11-06 | No issue-tracker mirroring. Publish outcomes, link references. | The persona's boundary is the product's moat. |
| 2026-11-06 | A metaplan defines how horizons become implementation plans. | The roadmap should produce plans repeatably, not by reinventing the process each time. |

## How to update this roadmap

1. Change this document first. Add or rename an item ID only with a decision log
   entry.
2. Update `site/roadmap.html` with the same ID and horizon. The sync test fails
   if the two drift.
3. Update the lazyplan plan P134: add or retire the milestone or task, and keep
   the trace from criteria to proving tasks current.
4. Record the change in the decision log.
5. Run `./tools/check.sh`. For site changes, also run `npm run build` in
   `site/` and `python3 tools/check-site.py --dist site/dist`.
6. Link each commit to its lazyplan task. The roadmap is not a separate
   reporting chore.

## Horizon readiness gate

A horizon is ready to cut when:

- every bet has a named user outcome and a success metric;
- the bets name their touch-points, non-goals, assumptions, and dependencies;
- the prior horizon's criteria are ticked and its plan is audited;
- the work can be sliced into commits that each stay green.

A task is ready to cut when it names real files or surfaces, a commit slice, a
verification, and the plan criterion it proves. No row is written from unscouted
ground.
