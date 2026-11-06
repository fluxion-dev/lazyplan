# Roadmap metaplan

> **Status:** active · **Last updated:** 2026-11-06
> **Plan of record:** P134 · **Tracked in:** T1378
>
> This is the repeatable process for turning a roadmap horizon into a scoped
> lazyplan plan, then executing and closing it. It is a plan about planning.
> It does not implement a roadmap feature.

## How to use this file

| You need | Read |
|---|---|
| Direction, stable IDs, anti-goals, horizons | [roadmap.md](roadmap.md) |
| The reasoning, idea backlog, rejected ideas, open questions | [roadmap-context.md](roadmap-context.md) |
| Live milestones, tasks, criteria, and commits | `lpui plan show --id 134` |
| The process for the next horizon | This file, starting at Stage 0 |

Read the roadmap and context first. Read this file second. Then read P134 to
see what already exists before writing anything. The roadmap is the decision;
the context preserves the why; P134 is the execution journal.

## Purpose

The roadmap says what comes next and why. It does not say how a horizon becomes
a set of executable tasks with proof. This metaplan closes that gap with six
stages:

1. intake the horizon and confirm scope with the human;
2. scout the real code and commands;
3. cut the plan, milestones, tasks, criteria, and commit slices;
4. review the tree and get explicit check-off;
5. execute in small green commits while keeping the journal current;
6. close with evidence and decide what the next horizon inherits.

Use it when a horizon moves from candidate to committed work, when a horizon
needs to be re-cut after a scope change, or when a future agent must resume an
in-flight horizon without replaying the original conversation.

Do not use it to implement a feature directly. Stage 3 ends with check-off;
only Stage 4 writes product code.

## Inputs

Every input is required. If one is missing, stop and resolve it before scouting
or writing rows.

| Input | Source | Form it must take | Used in |
|---|---|---|---|
| Horizon and item IDs | `roadmap.md` | The earliest open horizon and its stable `R` IDs | Stage 0 selection and Stage 2 titles |
| Positioning and anti-goals | `roadmap.md` | Persona, job, "what we will not build" | Stage 0 non-goals, Stage 3 review |
| Reasoning and open questions | `roadmap-context.md` | Pains, rejected ideas, assumptions, unresolved questions | Stage 0 scope, Stage 1 assumptions |
| Prior horizon evidence | P134, `trace`, `lint`, `audit`, close digest | Ticked criteria, linked commits, audit numbers | Stage 0 readiness gate |
| Success metrics | Roadmap item metric plus cross-horizon table | Baseline, target, measurement method, anti-metric | Stage 0 brief and Stage 5 close |
| Code scouting | The repository | Real paths, commands run, outputs, test names | Stage 1 brief and Stage 2 task descriptions |
| Architecture and constraints | `docs/architecture.md`, `src/lazyplan/data/SKILL.md`, `pyproject.toml` | Local-first, no LLM, no runtime, gate suite | Stage 1 touch-points and verification |
| Human decisions | Conversation | Explicit answers to the Stage 0 questions and the Stage 3 check-off | Stage 0 and Stage 3 gates |

A chat transcript is not an input. If a decision exists only in chat, write it
into the horizon brief or a plan note before treating it as settled.

## The process at a glance

| Stage | Output | Exit gate | Human involved |
|---|---|---|---|
| 0. Horizon intake | Horizon brief and container decision | Scope, outcome, metrics, and non-goals confirmed | Yes, explicit |
| 1. Discovery and scouting | Scouting brief per bet | Every task has real files, a commit slice, and a verification | No new rows |
| 2. Cut the plan | Plan or milestone, tasks, criteria, trace links | `lint` clean; every criterion has a proving task | No code |
| 3. Review gate | Checked-off tree | Human walks every milestone and task and says "checked off" | Yes, explicit |
| 4. Execution loop | Green commits and a current journal | Each task is proven, linked, and moved | Agent-led |
| 5. Close and retro | Ticked criteria, audit, digest, decision log | All close checks pass; next horizon inputs listed | Yes, close review |

The stages are ordered. Do not begin Stage 4 for a horizon before Stage 3 is
checked off. Do not begin Stage 0 for a later horizon before Stage 5 closes the
prior one.

## Stage 0 — Horizon intake

### Readiness gate

A horizon is ready to cut only when all of these are true.

| Gate | Evidence | If it fails |
|---|---|---|
| Prior horizon criteria are ticked | `lpui plan show --id P` and the horizon criterion traces show no open criteria | Finish the prior horizon; do not start this one |
| Prior plan is audited | `lpui --porcelain audit --plan P --min-trace 0.8 --strict` exits 0 | Fix trace coverage, status lag, or criteria gaps first |
| Prior close record exists | Decision-log row, outcome digest, and next-horizon inputs are written | Run Stage 5 before intake |
| Every selected bet has an outcome and metric | `roadmap.md` names the user-visible outcome and success metric | Send the bet back to the roadmap or cut a scoping task |
| Touch-points, non-goals, assumptions, and dependencies are named at bet level | Roadmap item plus a short intake note | Scout the bet before committing scope; never invent it |
| The work has an obvious order of green commits | Intake note lists the likely slices | Split the bet or defer it; confirm the slices in Stage 1 |
| No later-horizon work is mixed in | Horizon brief lists in-scope IDs only | Remove it; a dependency is not scope |

### Intake steps

1. Read `roadmap.md`, `roadmap-context.md`, and P134. Note the earliest open
   horizon and its item IDs.
2. Prove the prior horizon closed with the gate commands above.
3. Select the bets for this horizon. Take the earliest open horizon only. If a
   later item is a dependency, record it as a dependency, not as in-scope work.
4. Write the horizon brief. State the outcome as a user-visible change, not a
   feature list. For each metric, record the baseline, target, and how it is
   measured. If no baseline exists, add an instrumentation task; do not invent
   a number.
5. Choose the container using the decision table below and record the choice.
6. Ask the human the confirmation questions and wait for answers. Record the
   answers in the brief or a plan note.

### Confirmation questions

- Which roadmap IDs are in this horizon, and which are explicitly out?
- What user-visible outcome means the horizon is done?
- Which metric decides success, and how will we measure it?
- Which container holds the work: a new plan or a milestone in P134?
- What must the next horizon inherit from this one?

A question is not a confirmation. Silence is not a confirmation.

### Container decision

| Situation | Container | Record |
|---|---|---|
| The horizon is already a milestone in P134 and P134 remains the roadmap plan | That milestone | Default for Now, Next, and Later |
| The horizon needs its own close, audit, export, or execution window | A new plan named for the horizon, for example `Now — capture and resume` | Horizon brief states why P134 is not enough |
| The work is one bet or an extension of shipped work | A task cluster under an existing milestone | No new milestone |

Choose once per horizon. Do not create a plan and a milestone for the same
scope. The current roadmap uses P134 milestone 433 for Now, 434 for Next, and
435 for Later.

### Stage 0 exit

The horizon brief is written, the container is named, and the human has
confirmed scope, outcome, metrics, and non-goals. Nothing is cut yet.

## Stage 1 — Discovery and scouting

Scouting is read-only investigation. No lazyplan rows are written in this
stage. The goal is to replace assumptions with paths, commands, and observed
behavior.

### Scout the real surfaces

| Surface | What to inspect | Why |
|---|---|---|
| CLI | `lpui --help`, the noun's `--help`, parser and command modules | Confirm the command shape and write path |
| Domain | `src/lazyplan/core/` entities, policies, ports | Find the rule that changes and the contract it must keep |
| Services | `src/lazyplan/services/` | Find the composition point and existing read or write path |
| Store | `src/lazyplan/store/`, migrations, views | Confirm transaction support, schema, and query budgets |
| Presentation | CLI commands, MCP tools and resources, hooks, TUI | Find every user-facing surface the change must reach |
| Tests | Nearest suites and fixtures | Find the pattern to extend and the command that proves it |
| Docs | `docs/usage.md`, man page source, skill, site | Find the text that must change and the gate that checks it |

Use commands, not memory. Examples:

```bash
lpui --help
lpui plan --help
grep -rnE "def add_plan|def add_task|transaction" src/lazyplan/store
grep -rnE "def brief|query_count|max_chars" src/lazyplan tests
python -m unittest tests.services.test_brief tests.store.test_store -v
```

Run at least one existing command that exercises the closest current behavior.
For a new read surface, run `lpui brief`. For a new write surface, trace an
existing `plan add` or `task add` from parser to store. For a hook change, run
`echo '{}' | lpui hook session-start --host claude`.

### Write the scouting brief

One brief per bet, not one per task. It must contain:

| Field | Content |
|---|---|
| Bet and IDs | The `R` IDs and the outcome they serve |
| Files inspected | Real paths, grouped by layer |
| Commands run | The command and the observed result |
| Touch-points | Path, intended change, risk |
| Edge cases | Empty input, invalid input, retry, partial failure, budget limits, no database, read-only host |
| Non-goals | What this bet will not change |
| Assumptions | Each with the evidence that would falsify it |
| Dependencies | Internal ordering and external prerequisites |
| Verification candidates | Exact commands and expected results |
| Commit slices | Ordered, each independently green |

### Scouting exit gate

Do not leave Stage 1 until:

- every task you intend to cut names real files or surfaces;
- every task names a commit slice and a verification command;
- every assumption has a falsification check or is confirmed;
- every edge case has a decision: handle it, document it as a non-goal, or cut
  a task for it;
- no unresolved question changes the scope. If one does, return to Stage 0.

## Stage 2 — Cut the plan

### Write the why and what

For a new plan, `--why` explains the user pain and the cost of not doing the
work. `--what` carries scope in, scope out, deliverables, commit strategy,
constraints, and success metrics. For a milestone inside P134, put the horizon
narrative in the milestone description and leave P134's plan-level why and what
alone unless the roadmap plan's scope changed.

A useful milestone description answers:

- As which persona, what do they want, and why?
- What are the inputs and prerequisites?
- What is the ordered commit sequence?
- What does "done" mean in observable terms?

### Cut the milestones

A milestone is a coherent user outcome, not a layer of the stack. Keep it
INVEST: independent, negotiable, valuable, estimable, small, testable.

| Field | Standard |
|---|---|
| Narrative | "As the agentic developer, I want one atomic write and one budgeted read, so that planning is cheap and cold starts are short." |
| Inputs | Real prerequisites, not hopes |
| Commit order | Ordered slices, each green and reviewable |
| Done | Observable outcome plus criteria |
| Size | Small enough that one agent can finish it in a focused sequence |

If a milestone only works as one batch commit, it is not ready. If it has no
user-visible outcome, it is a task, not a milestone.

### Cut the tasks

Every task is one small, green commit series. The task description carries the
technical how, the files, the inputs, the commit slice, and the verification.

| Field | Requirement | Example |
|---|---|---|
| Title | Imperative verb plus target, scoped | `Implement the plan-apply document schema` |
| Approach | How the change works, not why the feature exists | "Validate a nested document, resolve stable keys, reject unknown fields" |
| Touch | Real paths or surfaces | `core/serialization.py`, `services/planning.py` |
| Inputs | Prerequisites and decisions already made | "R1 schema decision; existing Plan, Milestone, Task entities" |
| Commit | The expected commit slice and message | `core: define plan-apply document schema` |
| Verify | Exact command and expected result | `python -m unittest tests.core.test_planning_policies -v`; invalid fixtures write nothing |
| Criteria | Binary checks that prove the task | "A duplicate key is rejected before any write" |

Rules:

- One task proves at least one criterion, or it is explicitly QA, refactor, or
  documentation work with its own criterion.
- If a task needs more than three commits, split it.
- If two tasks always land together, they are one task.
- Do not write a task from an unscouted definition.

### Write the criteria

Criteria are the definition of done. They are binary, observable, and testable.

| Level | Purpose | Example |
|---|---|---|
| Plan | Closes the whole plan | "A new session can read one document and know the current bet" |
| Milestone | Closes the horizon | "One call creates a 20-task plan atomically" |
| Task | Proves one slice | "A retry of the same document creates no rows" |

Prefer 3 to 7 plan or milestone criteria. Avoid "works well", "is fast", or
"is clean" unless the criterion names the measurement. A criterion is not a
task list.

### Trace every criterion

Every plan or milestone criterion gets at least one proving task. Every task
that is not QA, refactor, or docs gets at least one criterion.

```bash
T=1361
lpui --porcelain criterion list --kind task --id "$T"
lpui --porcelain criterion relate --id CRITERION_ID --task "$T"
lpui --porcelain trace --criterion CRITERION_ID
```

`CRITERION_ID` stands for the id printed by `criterion list`; never guess a
row id.

Lint enforces coverage only for plan-level criteria. For a horizon tracked as a
milestone inside P134, put the horizon definition of done on the milestone,
relate each milestone criterion to its proving tasks, and check each one with
`lpui --porcelain trace --criterion CRITERION_ID`. `trace --plan` lists
plan-level criteria only, so it will not show the milestone criteria. Do not
pollute P134's plan-level roadmap criteria with feature criteria.

### Plan the commit slices

Each commit must be green on its own: the relevant tests pass, the tree builds,
and the diff is independently reviewable. Keep behavior, tests, docs, and
refactors in separate commits when they can stand alone.

| Smell | Fix |
|---|---|
| "Implement the Now horizon" as one commit | Split by task and by layer |
| Tests added in a later commit than the behavior | Put the test with the behavior, or one commit later if the behavior is already covered |
| Docs mixed into a code commit | Separate docs commit when the docs can stand alone |
| A task with no commit slice | Do not cut it; scout it first |

### Create the rows

Current CLI, before the plan compiler ships:

```bash
P=134
S=433
lpui --actor helper --porcelain milestone edit --id "$S" \
  --desc "As the agentic developer, I want one atomic write and one budgeted read, so planning is cheap and cold starts are short. Inputs: the Now intake brief and scouting notes. Ordered slices: schema, atomic apply, context service, surfaces, QA, refactor, docs. Done when a 20-task plan is created in one call and a session resumes from one packet."

lpui --actor helper --porcelain criterion add --kind milestone --id "$S" \
  --text "One plan apply call creates a 20-task plan in a single transaction, and a retry creates no rows."

lpui --actor helper --porcelain task add --milestone "$S" \
  --title "Implement the plan-apply document schema" \
  --desc "Approach: define and validate a nested document with stable keys. Touch: core/serialization.py, core/policies/planning.py, services/planning.py. Inputs: existing entities and the R1 schema decision. Commit: core: define plan-apply document schema. Verify: python -m unittest tests.core.test_planning_policies -v; invalid fixtures write nothing."

T=1361
lpui --actor helper --porcelain criterion add --kind task --id "$T" \
  --text "A duplicate key is rejected before any write."
lpui --porcelain criterion list --kind task --id "$T"
lpui --actor helper --porcelain criterion relate --id CRITERION_ID --task "$T"
```

Once R1 ships, the same cut is one document plus `plan apply --file PATH` with
a `--dry-run` preview. Until then, do not invent a document schema or depend on
a command that does not exist. The per-row path is the write path.

After the cut, update the roadmap's "Tracked in" fields only if the task IDs
changed, update `site/roadmap.html` to match, and run the doc and site gates.
The stable `R` IDs never change.

### Stage 2 exit

The tree exists, every plan-level criterion has a proving task, every milestone
criterion traces to one, every task has a commit slice and a verification, and
`lpui lint` has no errors. No product code has been written.

## Stage 3 — Review gate

The plan is truth. Review is where the human makes it true before code exists.

### Present the tree

```bash
P=134
lpui list --tree
lpui --porcelain plan show --id "$P"
lpui lint --plan "$P"
# For a milestone container, list the horizon criteria and trace each one.
lpui --porcelain criterion list --kind milestone --id MILESTONE_ID
lpui --porcelain trace --criterion CRITERION_ID
```

`MILESTONE_ID` is the id printed by `lpui list --tree`; `CRITERION_ID` is the
id printed by `criterion list`. Never guess either one.

Walk the human through, in this order:

1. The horizon outcome, metrics, and non-goals.
2. The container decision.
3. Each milestone: narrative, inputs, commit order, done.
4. Each task: title, approach, touch-points, commit slice, verification.
5. Each criterion and its proving tasks.
6. The commit sequence from first to last.
7. What is explicitly out of scope.

Make edits on the spot. Re-run `lint` and `trace` after every edit that changes
criteria or relations.

### Review checklist

- [ ] The horizon outcome and metrics match the roadmap and the brief.
- [ ] Every criterion is binary, observable, and testable.
- [ ] Every criterion has at least one proving task.
- [ ] Every task names real files or surfaces.
- [ ] Every task description contains a `Commit:` slice and a `Verify:` command.
- [ ] No task batches a whole milestone or plan into one commit.
- [ ] The commit order is explicit and each commit stays green.
- [ ] Non-goals are explicit and no later-horizon work is present.
- [ ] There are no estimates, due dates, owners, priorities, or story points.
- [ ] There are no unfinished markers or "figure out later" notes.
- [ ] `lpui lint --plan P` reports no errors.
- [ ] Each horizon criterion traces to at least one task; `trace --plan` shows plan-level coverage.
- [ ] The human explicitly says "checked off".

### Check-off

Record the check-off as a plan or milestone note. A note is provenance, not a
new approval feature.

```bash
lpui --actor human --porcelain note add --kind milestone --id 433 \
  --text "Now horizon checked off after lint, trace, and task-by-task review."
```

No code, branch, or commit until this note exists. If the human asks for
changes, stay in Stage 2 or 3.

## Stage 4 — Execution loop

### The task loop

Run this loop once per task. Do not work outside it. In the table, `T` is the
task id from `lpui list` and `CRITERION_ID` is the id from `criterion list`.

| Step | Command | Done when |
|---|---|---|
| Claim | `lpui --porcelain next` or `lpui --porcelain claim --id T --ttl 30m` | The task is leased to this actor |
| Start | `lpui --porcelain task start --id T` once per branch, or `lpui --porcelain task move --id T --to doing` when the branch is already recorded | The task is doing and the branch is recorded |
| Scout confirm | Re-read the task's touch-points and verification | The assumed files still exist |
| Change the plan first | Edit the task or criterion, or add a note | The plan matches the intended code |
| Implement and verify | The task's exact `Verify:` command | The command passes |
| Commit | One green commit from the slice | The tree is clean |
| Link | `lpui --porcelain link --kind task --id T` or `task finish` | The commit is linked to the task |
| Tick | `lpui --porcelain criterion tick --id CRITERION_ID` | The proof is linked |
| Note | `lpui --porcelain note add --kind task --id T --text "Decision: use one transaction for the tree."` | The decision or handoff is recorded |
| Move | `lpui --porcelain task move --id T --to done` | The task is done with no open task criteria |

A `task start` records a branch. lazyplan rejects recording the same branch on a
second open task, so use `task move` for later tasks that share a branch, or give
each task its own branch.

Use `task finish --require-pr --require-checks` when done must wait for cached
PR or CI evidence. Use `--override REASON` only when the human accepts the
exception; the override is recorded.

### Claim and lease discipline

```bash
lpui --porcelain next
lpui --porcelain claim renew --id 1361 --ttl 30m
lpui --porcelain claims
lpui --porcelain claim release --id 1361
lpui --porcelain task block --id 1361 --reason "waiting on the schema decision"
lpui --porcelain task unblock --id 1361
```

A claim is a lease, not an owner. Renew it before it expires. Release it when
you stop. If another actor holds it, do not force a takeover without a recorded
reason. Blocking releases the claim and records the reason.

### Keep the plan current

The plan is the truth for the desired implementation. When reality changes:

1. Change the plan before changing code.
2. Add or edit the task, criterion, or note that records the change.
3. Re-run `lint` and `trace` if criteria or relations moved.
4. Then implement.

Do not let a commit carry work that the plan does not describe. Do not leave a
commit unlinked at the end of a session. `lpui brief` lists loose commits.

### Session hygiene

Start with `lpui --porcelain brief` or `next`. End with:

```bash
lpui --porcelain audit --since 7.days
lpui --porcelain brief
lpui --porcelain claims
```

The audit reports commit coverage, status lag, and criteria gaps. The brief
names the doing task, the next todo, open criteria, and unlinked commits.

## Stage 5 — Close and retro

### Close gate

A horizon closes only when all of these are true.

| Gate | Evidence |
|---|---|
| Every task is done | `lpui list --tree` shows no open horizon tasks |
| Every task criterion is ticked | `lpui plan show --id P` shows no open task criteria |
| Every horizon criterion is ticked | Milestone or plan criteria have proof |
| Trace coverage is complete | Plan-level criteria appear in `trace --plan`; each milestone criterion traces individually |
| Lint is clean | `lpui --porcelain lint --plan P --strict` exits 0 |
| Audit passes | `lpui --porcelain audit --plan P --min-trace 0.8 --strict` exits 0 |
| The outcome digest exists | Plan note plus PR body or changelog |
| The roadmap is updated | Decision log, item status, tracked-in fields |
| The site matches the doc | `site/roadmap.html` lists the same IDs and horizon |
| The gates pass | `./tools/check.sh` and the site build |

### Close steps

1. Freeze scope. No new tasks after this point.
2. Tick task criteria as their proof lands. Tick horizon criteria only after
   every proving task and commit is linked.
3. Run the close checks:

   ```bash
   P=134
   S=433
   lpui --porcelain lint --plan "$P" --strict
   lpui --porcelain trace --plan "$P"
   lpui --porcelain criterion list --kind milestone --id "$S"
   lpui --porcelain trace --criterion CRITERION_ID
   lpui --porcelain audit --plan "$P" --min-trace 0.8 --strict
   lpui --porcelain brief
   ```

4. Write the outcome digest. Post it as a plan note and reuse it in the PR body
   or changelog. When R11 ships, `lpui ship --plan P` may generate it; until
   then, write it by hand.

   ```bash
   lpui --porcelain note add --kind plan --id 134 \
     --text "Outcome digest: why, what shipped, evidence, metrics, residual risks, follow-ups."
   ```

   ```text
   Why: the pain the horizon removed.
   What shipped: the user-visible outcome, in one paragraph.
   Evidence: criteria, commits, pull requests, and checks.
   Metrics: baseline, result, and how it was measured.
   Residual risks: what is still uncertain or manual.
   Follow-ups: the work the next horizon inherits.
   ```

5. Update `roadmap.md`:
   - add a dated decision-log row for the horizon close;
   - change the item status from Now to shipped, or move the next horizon into
     Now;
   - update "Tracked in" only if task IDs changed.
6. Update `site/roadmap.html` with the same IDs and status. The doc and site
   must name the same items.
7. Run the gates:

   ```bash
   ./tools/check.sh
   (cd site && npm run build)
   python3 tools/check-site.py --dist site/dist
   ```

8. Move the milestone or plan to done.

   ```bash
   lpui --porcelain milestone move --id 433 --to done
   ```

9. Run the retro and record the answers as a plan note.

### Retro questions

- Which task took longer than its slice, and why?
- Which criterion was hard to test, and what would make it testable?
- Which touch-point did scouting miss?
- Which commit should have been split or combined?
- Which assumption was false?
- What should the next horizon inherit, and what should it drop?

### What the next horizon inherits

| Inherit | Do not inherit |
|---|---|
| Confirmed metric baselines and instrumentation | Undone tasks without a fresh scout |
| Open questions that still block a decision | A scope that was never checked off |
| Follow-up tasks with real files and proof | A vague "clean this up later" note |
| Reusable scouting notes and verification commands | A second tracker or a copied issue list |

The next horizon starts at Stage 0 only after this close gate passes. Do not
carry a horizon forward by renaming its status.

## Templates

Copy a block, replace every value, and keep every field. A missing field is a
missing decision.

### Horizon brief template

```text
Horizon: Now — capture and resume
Roadmap IDs: R1, R3
Prior horizon: Foundation, P134 milestone 432
Prior evidence: milestone 432 closed; P134 criteria ticked; trace and audit clean
Container: P134 milestone 433 "Now: capture and resume"
Outcome: one atomic write creates a plan; one budgeted read resumes a session
In scope: plan apply and the context pack
Out of scope: recipes (R2), Focus lens (R4), issue sync, an LLM, an agent runtime
Metrics:
  - CLI calls to create a 20-task plan: baseline 20-30, target 1
  - Apply latency after validation: target under 100 ms
  - Sessions per active plan: baseline instrumented by the QA task
  - Time to first plan-affecting write: baseline instrumented by the QA task
Anti-metrics: rows per plan; time to first plan
Dependencies: R1 before R2; existing transaction helper; hook hosts
Assumptions: agents can author the document; the store wraps the tree in one transaction
Non-goals: no GUI editor, no network call, no issue write-back
Human confirmation: scope, outcome, metrics, container, and non-goals checked off at the Stage 3 gate
```

### Scouting brief template

```text
Bet: R1 — plan compiler
Files inspected: core/serialization.py, core/policies/planning.py, services/planning.py, store/plans.py, presentation/cli/commands/plan.py
Commands run: lpui plan --help; grep -rnE "def add_plan|transaction" src/lazyplan/store; python -m unittest tests.store.test_store -v
Touch-points:
  - src/lazyplan/core/serialization.py | add document model and validation | stable-key collision
  - src/lazyplan/services/planning.py | compose one atomic write | partial failure
  - src/lazyplan/presentation/cli/parser/work.py | add file and dry-run flags | flag collision
Edge cases: empty document; duplicate key; unknown field; parent mismatch; retry; mid-document failure; dry-run
Non-goals: no recipe content; no GUI editor; no network
Assumptions: the store transaction helper can wrap plan, milestone, task, and criterion inserts | falsified by tests.store.test_store if the helper commits per row
Dependencies: R1 schema decision; no dependency on R2
Verification: python -m unittest tests.core.test_planning_policies tests.services.test_plan_apply -v
Commit slices: core schema; services validation; store transaction; CLI command; tests
Open questions: none that change scope
```

### Task cut template

```text
Title: Implement the plan-apply document schema
Milestone: 433
Approach: define the nested document, resolve stable keys, reject unknown fields and parent mismatches, and validate before any write
Touch: core/serialization.py, core/policies/planning.py, core/ports/planning.py, services/planning.py
Inputs: existing Plan, Milestone, Task, and Criterion entities; the R1 schema decision
Commit: core: define plan-apply document schema; services: validate plan-apply documents
Verify: python -m unittest tests.core.test_planning_policies tests.services.test_plan_apply -v; invalid fixtures leave no rows
Criteria: duplicate keys rejected; unknown fields rejected; parent mismatch rejected; canonical fixture accepted
Trace: C-Now-1, C-Now-2
```

### Review checklist template

```text
[ ] Horizon outcome and metrics match the roadmap and the horizon brief.
[ ] Every criterion is binary, observable, and testable.
[ ] Every criterion has at least one proving task.
[ ] Every task names real files or surfaces.
[ ] Every task has a Commit: slice and a Verify: command.
[ ] No task batches a whole milestone or plan into one commit.
[ ] Commit order is explicit and every commit stays green.
[ ] Non-goals are explicit and no later-horizon work is present.
[ ] No estimates, due dates, owners, priorities, or story points.
[ ] No unfinished markers or "figure out later" notes.
[ ] lpui lint --plan P reports no errors.
[ ] Each horizon criterion traces to at least one task; trace --plan shows plan-level coverage.
[ ] The human explicitly checked off.
```

### Close checklist template

```text
[ ] Every horizon task is done.
[ ] Every task criterion is ticked with linked proof.
[ ] Every milestone or plan criterion is ticked.
[ ] lpui lint --plan P --strict exits 0.
[ ] Each horizon criterion traces to its tasks and commits; plan-level criteria appear in trace --plan.
[ ] lpui audit --plan P --min-trace 0.8 --strict passes.
[ ] The outcome digest is posted as a plan note.
[ ] roadmap.md has a dated decision-log row and the new item status.
[ ] site/roadmap.html matches the doc IDs and horizon.
[ ] ./tools/check.sh passes.
[ ] The site build and check-site pass.
[ ] The next horizon's inherited inputs are listed.
[ ] No undone task is carried forward without a fresh scout.
```

## Rules and anti-patterns

| Rule | Why | Smell |
|---|---|---|
| Never mirror plans into an issue tracker | The persona's boundary is the product's moat | "Create a ticket for each task" |
| No estimates, owners, due dates, priorities, labels, or story points | Those are tracker ceremony; sequencing is creation order, ownership is the actor on each write | "2 days", "assign to", "by Friday" |
| No unscouted tasks | A row written from imagination becomes rework | "Figure out the files later" |
| Never batch a whole milestone into one commit | A batch is unreviewable and hides failures | "Implement the Now horizon" |
| No horizon starts before the prior one closes | Later bets depend on earlier proof | Next work starting while Now criteria are open |
| No criterion without a proving task | A tick without a trace is a claim, not proof | Ticking everything at close |
| No code before check-off | The plan is truth; review happens before commitment | A branch opened during Stage 2 |
| No plan drift without a plan edit | The journal must explain the code | A commit that no task describes |
| No second tracker | Duplicate status boards split the truth | A spreadsheet or issue list beside P134 |
| No scope decided only in chat | Chat does not survive the session | "We agreed in the thread" |
| No metric without a baseline or instrumentation task | A target with no measurement is theater | "Faster" with no before number |
| No hidden work in progress | Claims and blocks make collisions visible | An agent editing files with no claim |
| No roadmap edit without a decision-log row | The direction must stay auditable | Changing an `R` ID or status silently |

Dates appear only as provenance in the roadmap decision log or a review note,
never as a due date on a plan row. An actor on a write is provenance, not an
assignee field.

## Worked example — Now: R1 and R3

This example cuts R1 (plan compiler) and R3 (context pack) inside the existing
P134 milestone 433. R2 (recipes) and R4 (Focus lens) remain in the same
milestone but are outside this example. At the time of writing, T1361, T1362,
T1364, and T1365 exist; the criteria below are the proposed cut to add at the
Stage 2 review. Re-check IDs before writing because the journal may have moved.

### 1. Intake

The horizon is Now — capture and resume. The prior horizon is Foundation
(milestone 432). The example becomes executable only after milestone 432 passes
the close gate; at the time of writing it is still open. That is the gate
working, not an exception.

| Field | Value |
|---|---|
| Roadmap IDs | R1, R3 |
| Outcome | One atomic write creates a plan; one budgeted read resumes a session |
| Metrics | CLI calls for a 20-task plan: 20-30 to 1; apply under 100 ms after validation; sessions per active plan and time to first write instrumented by QA |
| Anti-metrics | Rows per plan; time to first plan |
| In scope | Plan apply document, atomic write, dry-run, retry, context read, CLI, MCP, hooks |
| Out of scope | Recipes (R2), Focus lens (R4), GUI editor, LLM, network, issue sync |
| Container | P134 milestone 433 "Now: capture and resume" |
| Why P134 | It is the roadmap plan of record and the milestone already holds the Now tasks |

### 2. Scouting

Scouting for R1 and R3 found these surfaces. No rows were written in this step.

| Bet | Touch-points | Edge cases |
|---|---|---|
| R1 | `core/serialization.py`, `core/policies/planning.py`, `core/ports/planning.py`, `services/planning.py`, `store/plans.py`, `store/tasks.py`, `store/migrate.py`, `presentation/cli/parser/work.py`, `commands/plan.py` | Duplicate key, unknown field, parent mismatch, empty document, retry, mid-document failure, dry-run |
| R3 | `services/brief.py` or a new `services/context.py`, `core/ports/insights.py`, `store/views.py`, `presentation/cli/parser/coordination.py`, `commands/system.py`, `mcp/resources.py`, `services/hooks.py`, `infrastructure/hook_hosts.py` | Budget too small, empty plan, no database, read-only MCP, hook timeout, stale claim |

Commands used:

```bash
lpui --help
lpui plan --help
grep -rnE "def add_plan|def add_task|transaction" src/lazyplan/store src/lazyplan/services
grep -rnE "def brief|query_count|max_chars" src/lazyplan tests
python -m unittest tests.services.test_brief tests.store.test_store -v
```

Assumptions and their checks:

- The store can wrap the tree in one transaction. Check `store/base.py` and the
  transaction tests in `tests/store/test_store.py`.
- The brief read path can be composed into a budgeted packet. Check
  `services/brief.py` and `tests/services/test_brief.py`.
- Hooks can inject read-only text on session start and pre-compact. Check
  `tests/setup/test_hooks.py` and `tests/setup/test_hook_hosts.py`.

### 3. The cut

The plan is P134. The horizon is milestone 433. P134's plan-level why and what
already describe the roadmap governance, so the Now cut does not rewrite them;
the horizon's why and what live in the milestone description. Because
lazyplan's hierarchy stops at task, the two bets are task clusters whose titles
and descriptions carry the `R1` and `R3` grouping. If Now ever moves to its own
plan, these clusters become the two milestones.

**Milestone 433 narrative** (already written; shown as the standard):

> As the agentic developer, I want to create a plan in one atomic write and
> resume a session from a budgeted context pack, so planning is cheap and cold
> starts are short. Inputs: the Now intake brief and scouting notes. Ordered
> slices: schema, atomic apply, context service, surfaces, QA, refactor, docs.
> Done when a 20-task plan is created in one call and a session resumes from one
> packet.

**R1 — plan compiler**

| Task | Scope | Commit slice | Verification |
|---|---|---|---|
| T1361 | Document schema, stable keys, validation, idempotent retry rules | `core: define plan-apply document schema` then `services: validate plan-apply documents` | `python -m unittest tests.core.test_planning_policies tests.services.test_plan_apply -v`; invalid fixtures write nothing |
| T1362 | `plan apply --file PATH [--dry-run]`, one transaction, retry no-op, rollback | `store: add atomic plan-apply transaction` then `cli: add plan apply with dry-run` | `python -m unittest tests.store.test_store tests.cli.test_plan_apply -v`; success, dry-run, rollback, retry |

**R3 — context pack**

| Task | Scope | Commit slice | Verification |
|---|---|---|---|
| T1364 | Budgeted read of active plan, doing task, next three todos, open criteria, decisions, notes, commits, comments, claims | `services: compose the context packet` | `python -m unittest tests.services.test_brief -v`; all sections present; truncation deterministic; query budget flat |
| T1365 | `lpui context --max-chars N`, MCP resource, session-start and pre-compact hooks | `cli,mcp,hooks: expose the context packet` | `python -m unittest tests.cli.test_context tests.mcp.test_mcp tests.setup.test_hooks -v`; no database creation, no network |

**Shared finish**

T1367 tests the horizon, T1368 refactors the touched paths, and T1369 updates
the docs. Each keeps its own commit slice and verification. They do not absorb
the feature tasks.

If the horizon were a standalone plan instead, the two milestones would be:

- **R1 — plan compiler:** "As the agentic developer, I want one atomic document,
  so that creating a plan costs one call and cannot leave a partial tree."
- **R3 — context pack:** "As a returning agent, I want one budgeted packet, so
  that a cold session starts with the plan, the doing task, and the proof."

The tasks, criteria, and commit slices are the same. The choice changes the
container, not the cut.

### 4. Criteria and trace

These are the proposed milestone criteria for 433. They are binary and each one
maps to proving tasks. The `C-Now-*` labels are design labels for this example;
the real criterion ids are assigned when the rows are written.

| ID | Criterion | Proving tasks |
|---|---|---|
| C-Now-1 | One `plan apply --file` call creates the plan, milestones, tasks, and criteria in a single transaction; a second identical call creates no rows. | T1361, T1362, T1367 |
| C-Now-2 | `--dry-run` validates and prints the intended tree without writing, and an invalid document leaves zero rows behind. | T1361, T1362, T1367 |
| C-Now-3 | `lpui context --max-chars 4000` returns the active plan, doing task, next three todos, open criteria, recent decisions and notes, recent commits, unresolved comments, and claims within the budget. | T1364, T1367 |
| C-Now-4 | The same packet is available from the MCP resource and from session-start and pre-compact hooks, read-only and without a network call. | T1365, T1367 |
| C-Now-5 | A 20-task plan is created in one CLI call in under 100 ms after validation, and the context read stays within the existing query budget. | T1362, T1364, T1367 |

Task criteria:

| Task | Criteria |
|---|---|
| T1361 | Duplicate keys, unknown fields, and parent mismatches are rejected before any write; the canonical fixture is accepted |
| T1362 | Success is atomic; dry-run writes nothing; retry creates nothing new; a mid-document failure rolls back the whole tree |
| T1364 | All required sections are present; truncation is deterministic; the read stays within the query budget |
| T1365 | CLI, MCP, and both hook surfaces return the same packet; the command never creates a database and makes no network call |

Trace after the cut:

```bash
P=134
lpui --porcelain criterion list --kind milestone --id 433
# Relate each id to its proving tasks; the table above is the mapping.
lpui --porcelain criterion relate --id CRITERION_ID --task 1361
lpui --porcelain trace --criterion CRITERION_ID
lpui --porcelain lint --plan "$P"
```

`trace --plan` covers P134's plan-level roadmap criteria. The Now feature
criteria live on milestone 433, so trace each one with `trace --criterion`.

C-Now-2 links to T1361 and T1362. C-Now-5 links to T1362, T1364, and T1367.
Every feature criterion also links to T1367 so the horizon test proves it end
to end.

### 5. Commit slices and verification

The commit order is the task order: T1361, T1362, T1364, T1365, then QA,
refactor, and docs. R1 and R3 touch different read and write paths, but
parallel-safe claims are R10, not available in this horizon, so the default is
sequential.

| Order | Commit | Files | Verify |
|---|---|---|---|
| 1 | `core: define plan-apply document schema` | `core/entities.py`, `core/policies/planning.py`, `core/ports/planning.py`, `core/serialization.py`, fixtures | `python -m unittest tests.core.test_planning_policies -v` |
| 2 | `services: validate plan-apply documents` | `services/planning.py`, new validation tests | `python -m unittest tests.services.test_plan_apply -v` |
| 3 | `store: add atomic plan-apply transaction` | `store/plans.py`, `store/tasks.py`, `store/migrate.py`, store tests | `python -m unittest tests.store.test_store -v` |
| 4 | `cli: add plan apply with dry-run` | `presentation/cli/parser/work.py`, `commands/plan.py`, `main.py`, CLI tests | `python -m unittest tests.cli.test_plan_apply -v` |
| 5 | `services: compose the context packet` | `services/context.py` or `services/brief.py`, `core/ports/insights.py`, `store/views.py`, service tests | `python -m unittest tests.services.test_brief -v` |
| 6 | `cli,mcp,hooks: expose the context packet` | `presentation/cli/parser/coordination.py`, `commands/system.py`, `mcp/resources.py`, `services/hooks.py`, `infrastructure/hook_hosts.py` | `python -m unittest tests.cli.test_context tests.mcp.test_mcp tests.setup.test_hooks -v` |
| 7 | `tests: cover the Now horizon` | New or expanded suites for apply, context, MCP, hooks, and query budgets | `./tools/check.sh` |
| 8 | `refactor: simplify the Now touch-points` | The paths above, behavior unchanged | `./tools/check.sh` |
| 9 | `docs: document plan apply and the context pack` | `docs/usage.md`, man page source, skill text | `./tools/check.sh` |

Each commit is green before the next one starts. A commit never contains two
task slices. If a slice needs a test that does not fit its commit, the test
comes first or the slice is split.

### 6. Review and execution

Run the review gate:

```bash
lpui list --tree
lpui --porcelain plan show --id 134
lpui --porcelain criterion list --kind milestone --id 433
lpui --porcelain trace --criterion CRITERION_ID
lpui --porcelain lint --plan 134
```

The review walks milestone 433, then the R1 and R3 task clusters, then the five
criteria and their trace links, then the nine commit slices. The human checks
off. Execution starts with T1361:

```bash
lpui --porcelain claim --id 1361 --ttl 30m
lpui --porcelain task start --id 1361
# implement, run the task verification, commit
lpui --porcelain link --kind task --id 1361
lpui --porcelain criterion list --kind task --id 1361
# Tick the id printed for the criterion this commit proves.
lpui --porcelain criterion tick --id CRITERION_ID
lpui --porcelain note add --kind task --id 1361 --text "Schema fixtures and transaction boundary confirmed."
lpui --porcelain task move --id 1361 --to done
```

The loop repeats for T1362, T1364, and T1365. If the schema needs a new edge
case, add the criterion and the task note before writing the code. If a task
grows past its commit slice, stop and re-cut the plan.

### 7. Close

The horizon closes when all five milestone criteria are ticked, each criterion
traces to its tasks and commits, and the audit passes. Record the metrics:

| Metric | Before | Result |
|---|---|---|
| CLI calls to create a 20-task plan | 20-30 | 1 |
| Apply latency after validation | Not measured | Under 100 ms |
| Sessions per active plan | Instrumented by T1367 | Recorded in the close digest |
| Time to first plan-affecting write | Instrumented by T1367 | Recorded in the close digest |

Post the digest as a plan note, add a dated decision-log row to
`roadmap.md`, update the Now status, refresh `site/roadmap.html`, run
`./tools/check.sh`, and close milestone 433. The Next horizon inherits R5 to
R8, the open questions about advisory versus enforceable approval, and the
evidence boundary: lazyplan records proof; the agent or CI runs the command.
