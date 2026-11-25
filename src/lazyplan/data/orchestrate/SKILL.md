---
name: lazyplan-orchestrate
description: Run a checked-off lazyplan plan as parallel agent lanes. Use when a plan declares parallel dispatch or lanes, when dispatching worktrees to subagents, when handing work between implementer, QA, refactor, docs, integrator, and reviewer roles, or when closing a plan after lane integration.
---

# Orchestrate a lazyplan

The plan is the template. You do not invent lanes, tasks, or commit slices
while implementing; you dispatch the plan the human checked off.

## Before dispatch

1. Run `lpui --porcelain plan show --id P` and `lpui --porcelain lint --plan P`.
   Stop on open questions, uncovered criteria, or drift without a reason.
2. Run `lpui --porcelain dispatch --plan P --json`. Read the waves, lane
   states, capacity, worktree actions, and one prompt per dispatchable task.
3. If the plan is `serial`, dispatch the first incomplete milestone only. If it
   is `parallel`, fill up to `capacity.available` lanes, never beyond
   `max_agents`.
4. Run every printed `git worktree add` command, then every printed
   `lpui plan worktree add` command. `dispatch` never creates a worktree.

## Dispatch a worker

For each dispatchable item, start one worker in its lane worktree, on its
branch, with its role profile and the printed prompt. Each lane reports its
role, tier, effort, and per-host model in `dispatch --json`; start the worker
with the host's matching managed profile instead of picking a model by hand.
The worker must:

- read the full task desc with `lpui task show --id T`; it is the resume
  contract (approach, touch-points, inputs, commit slice, verification,
  guardrails), not a title to infer from;
- claim exactly the named task with the printed `lpui claim` command;
- keep one task doing in the lane;
- commit small green slices, link each with `lpui link --kind task --id T`,
  note decisions, and finish with `lpui task finish --id T --repo PATH`;
- stop when the lane has no todo task left, and leave a note rather than
  inventing work.

Do not run two workers in one lane. Do not start a later wave until every lane
in the current wave is done or blocked with a recorded reason.

## Handoffs

A lane agent stops after its task. The next agent in the same lane claims the
next task, reads the lane note, and continues. QA, refactor, and docs tasks run
in that order unless the plan says otherwise. A review task is read-only and
reports findings; it does not edit.

## Integrate and close

1. When every non-integrator lane in the final wave is done, dispatch the
   integrator lane. It merges sibling branches in wave order and runs the full
   suite after every merge.
2. Run `lpui --porcelain audit --plan P --since 7.days`,
   `lpui --porcelain trace --plan P`, and `lpui --porcelain lint --plan P
   --strict`. Record evidence for every plan criterion.
3. Mark the plan done only when the tree is clean, every criterion is proven,
   and `plan ready` passes. Print the worktree removal commands instead of
   removing them yourself.
4. Report the ship note with `lpui ship --plan P`; do not merge or push unless
   the human asks.

## Human gates

Ask the human for the plan's why, scope, criteria, and check-off; never decide
them. Ask before merging to a protected branch, deleting a worktree, or
overriding a lane collision. Everything else in a checked-off plan is yours.

## Guardrails

- lazyplan never creates, merges, or removes worktrees, commits, pushes, or
  spawns agents. You run those commands.
- The plan is the truth: fold findings into it with `task edit`, `milestone
  edit`, or `note add` before changing course.
- One lane, one doing task, one worktree, one branch.
- Keep the journal current after every commit; a handoff is a note.
