---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — interview for a plan's why/what/acceptance criteria, cut milestones and tasks, and keep the journal accurate while implementing. Use when the user asks to plan work, track progress, break down a feature, check status, implement or continue planned work, resume a task, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# lazyplan (`lpui`) — local plan journal

`lpui` is the repo's plan of record: plans > milestones > tasks, stored in
`.agents/lazyplan/lazyplan.db` (SQLite, committed with the repo or local — check
`.agents/lazyplan/config.json`). The human watches `lpui ui`; agents inject work
through the CLI. Never touch the TUI process — only call `lpui`.

A plan is: title + why + what + acceptance criteria. Milestones cut a plan into
slices; tasks cut a milestone into units of work. That is the whole model — no
dates, owners, labels, or estimates.

## Identity and surfaces

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode task add ...`). Reads don't need it.
`--actor`, `--porcelain`, and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`). In an active loop, pass
`--porcelain`: writes answer with one tab-separated row and overview reads stay
glyph-free. `--json` wins when both are present; use it only when you need
fields porcelain does not carry.

If your host supports MCP, use the local `lpui mcp` server (or
`lpui mcp --read-only` for reviews); otherwise use `--porcelain` on every call.
Start work with `lpui next --porcelain`: it claims the first eligible todo and
moves it doing. A task is doing exactly while you hold its claim: moving a task
to doing claims it for your `--actor`, and moving it off doing releases it.
Hooks keep your checkout's claims alive; release when you stop, and note
handoffs with `lpui note add`. MCP resources
include `lazyplan://brief`, `lazyplan://context`, `lazyplan://plan/{id}`, and
`lazyplan://draft/{id}`.

## DB scoping and setup

`--db PATH` → `$LAZYPLAN_DB` → nearest repo-owned
`.agents/lazyplan/lazyplan.db` walking up → shared `~/.lazyplan/lazyplan.db`.
On Windows the shared home is `%LOCALAPPDATA%/lazyplan/`, and the default actor
is `%USERNAME%` (`$USER` elsewhere). Plan text is read as UTF-8 or UTF-16 with a
BOM and written as UTF-8.

Setup runs on first use: it detects agents, installs their skills, seeds the
role map, and remembers the result in `~/.lazyplan/setup.json`. The default is
the shared home database and no repo files. On a terminal the first `lpui`
applies that baseline and then opens a setup wizard before normal use; **finish
later** writes nothing and asks again at the next applicable launch. `lpui
setup --placement repo` opts the current checkout into `.agents/lazyplan/` plus
repo skills, templates, an `AGENTS.md` pointer, and gitignore entries. `--db`
and `$LAZYPLAN_DB` always win, are never moved, and keep setup out of the way.
`lpui doctor` reports the resolved layout and findings without writing (exit 0
clean, 1 misplaced). Agent commands never prompt; only the wizard, `lpui setup`,
and `lpui upgrade` do. Don't override `--db` unless asked.

## Roles, models, and effort

A milestone names its lane role and a task names its own role. Roles name a
capability tier, and `agents.json` beside the database maps each tier to a model
per host; a role may also carry an `effort` of `inherit`, `low`, `medium`, or
`high`, which only hosts with a native field render. Resolution is the role's
per-host model, its all-host model, the tier target, the host default, then
inherit.

```bash
lpui --porcelain dispatch --plan P --json   # per-host tier, effort, and model
lpui setup --agent-tier qa=deep --agent-tier docs=standard
lpui setup --tier-model opencode:fast=provider/tiny
lpui setup --role-model claude:reviewer=opus --no-model-review
```

Setup seeds the map and writes one managed subagent file per role for each
selected host; the wizard edits the same map. `--yes`, `--json`, a version
upgrade, and every agent command apply the saved map without prompting. Read
`agents.json`, not source, when a model or effort looks wrong; `lpui doctor`
lists missing or drifted profiles.

## Linked repos

Plans, milestones, and tasks each link 0..n repo checkouts so one central DB can
plan work across repos. A row with no explicit links inherits: a task inherits
its milestone's effective repos, a milestone inherits its plan's. Link by
absolute checkout path plus remote URL (auto-detected from
`git remote get-url origin` when omitted):

```bash
lpui --actor NAME link-repo --kind plan --id P --repo /path/to/checkout [--remote URL]
lpui --actor NAME unlink-repo --kind plan --id P --repo /path/to/checkout
lpui repos --kind task --id T [--effective]    # explicit vs inherited
lpui list --repo /path/to/checkout             # only matching rows
```

`show` and `list --json` include `repos` plus `effective_repos`;
`export --format json` carries explicit `repos` (import round-trip).

## Git proof and pull requests

Rows can carry the exact commits that shipped them, including changed files.
`link` attaches HEAD, or a SHA, from the current checkout; `--repo PATH` reads a
different linked checkout. `commits` lists direct and inherited commits, and
`--refresh` re-resolves cached metadata/files and marks missing commits
`[stale]`. Add `--files` to `show` or `commits` to list paths.

```bash
lpui --actor NAME link --kind task --id T [--sha SHA] [--repo PATH]
lpui commits --kind task --id T [--refresh] [--files]
lpui task show --id T [--files]
lpui git status --kind task --id T [--json]
lpui git scan --since 7.days [--dry-run] [--repo PATH]
```

`task start` sets a task doing and records an existing branch plus its base. It
uses the current branch unless `--branch NAME` names another existing branch.
lazyplan never creates or checks out branches and never creates worktrees; use
your VCS tool for that first. `task finish` links `base..HEAD` and moves the task
to done only when the tree is clean. lazyplan never commits, pushes, fetches, or
merges. Commit messages can also carry a `Lazyplan: T12` trailer, and a
`task/12-*` branch attributes commits in its base..HEAD range. Marking a row done
links HEAD only when the tree is clean and HEAD is not already linked to another
row; otherwise lpui warns and leaves the link for you.

GitHub support is read-only and opt-in. lpui maps each linked checkout's origin
remote to a `github.com` owner/repo and caches pull requests, checks, and reviews
locally. `list`, `show`, and opening the screen never call GitHub; only
`pr refresh` does. Auth precedence: `LAZYPLAN_GITHUB_TOKEN`, `GITHUB_TOKEN`,
`GH_TOKEN`, then `gh auth token`. Tokens never enter the database, export, feed,
or logs.

```bash
lpui --actor NAME pr auth
lpui --actor NAME pr status --kind task --id T
lpui --actor NAME pr refresh --kind task --id T
lpui --actor NAME pr list --kind task --id T
lpui --actor NAME pr link --kind task --id T --url https://github.com/org/repo/pull/7
lpui --actor NAME pr unlink --kind task --id T --number 7
```

`pr refresh` links each PR to the task that owns its commit or branch and caches
state, checks, reviews, base/head refs, and merge metadata. Requests reuse ETags
and fall back to cached data offline; stale data is marked. `pr link` is offline
and manual. lazyplan never creates branches, worktrees, commits, pushes, PRs,
reviews, comments, or merges; other tools own those actions.

## Starting a plan: interview first

Never invent a plan's definition. When the user asks to plan something,
interview them before writing anything. A solid definition covers:

- Vision: why this exists (one or two sentences) — the problem and the value.
- Scope: explicit in-scope and out-of-scope lists, in plain language. Push
  until both lists are concrete — vague scope is rejected, not recorded.
- Deliverables: tangible outputs and their order.
- Commit strategy: the ordered slices of small commits that will land the work,
  and the check that keeps each commit green. A plan that cannot name its slices
  is not ready to cut.
- Constraints: technical or operational limits, plus assumptions.
- Success metrics: measurable outcomes that mean it worked.
- Acceptance criteria: how we know it is done.
- Quality: ask whether QA testing, refactoring, and documentation cleanup steps
  should be included, and ask what testing is relevant to the changes being
  made. All three are included by default — only an explicit user opt-out
  excludes them.

Fold vision into `--why`; scope, deliverables, commit strategy, constraints, and
metrics into `--what`; acceptance criteria become plan-level checklist items.
There are no stakeholder, owner, or estimate fields — if it does not fit why,
what, or criteria, it does not belong in the definition.

When the request is to build, implement, or change something, hunt the
ambiguity before writing any row: scope in and out, touch-points with real
paths, edge cases and non-goals, and assumptions stated so the human can correct
them. Vague scope is rejected, not recorded. No row is written from unscouted
ground, in any case, no exceptions.

When a question is visual (a layout, an icon, an empty state), do not describe
the alternatives only in words. Write a choices manifest with 2–12 image
options, run `lpui choose --manifest choices.json` in the background, give the
human the printed loopback URL, and read `selection.json` after the pick.
Author the images yourself; the command only displays them. Fold the chosen
option into `--why`, `--what`, or the task description — the selection file is
input to the definition, not a plan row.

## Readability and scouting

Write every plan why/what, milestone desc, and task desc for scanning: short
paragraphs separated by blank lines, sections with headers or lists where
needed. Creation rejects long single-blob text (over 300 chars with no paragraph
breaks or section markers) — split it into paragraphs and sections. Short
one-liners stay legal. Never ship bracket, example, or placeholder text as
content or criteria — starters ship empty on purpose, and the interview must
fill them with real words.

While interviewing, scout the codebase (explore agents, grep, file reads) so
each question clears up real ambiguity: what exists, what constrains the
approach, what the deliverables touch. Never cut work from an unscouted
definition. Scouting is mandatory before creating anything — plan, milestone, or
task. No row is written from unscouted ground, in any case, no exceptions.

## Record the definition

```bash
lpui --actor NAME plan add --title "API v2" --why ".." --what ".."
lpui --actor NAME --porcelain draft sketch --file sketch.md
lpui --porcelain draft list
```

`plan add` creates a definition-only sketch; `plan apply` and `draft add`
create full document drafts. Neither gets a plan id until the human promotes it
(see Plan drafts). Put acceptance criteria in the sketch's `## Done` section
with `draft revise`, then review the definition. Pass `--direct --reason TEXT`
only for bulk or fixture work the human has waived review for; the reason is
noted on the plan.

Only once the definition is agreed and every assumption is confirmed (see
Interrogate the written draft), formalize the sketch into the plan
document — milestones from the plan, then tasks from each milestone, shaped as
below plus the default QA, refactor, and documentation tasks. Every derived
milestone and task must carry the labeled resume contract (see Resume contract):
`formalize` refuses a tree that leaves it implicit, and the derived tree is not
reviewed a second time. The sketch is the review gate.

Every plan carries QA testing tasks, a refactoring task, and documentation
cleanup by default, shaped by the interview's testing answer. Ground every QA task in the acceptance criteria: each criterion is exercised by a named test task, and DoD checklists reference the criteria they satisfy. Only an explicit user opt-out ("skip QA", "no refactoring") excludes them — silence means include. Default task shapes include "Run the relevant test suites", "Refactor what the change touched", and "Clean up touched documentation".

Work top-down in creation order. Commit each task as it completes — or in a
tight series of green commits — then link it and move it through todo → doing →
done. Do not defer commits to the end of the plan.

## Interrogate the written draft

The first draft is the midpoint of the interview, not the end. Run a post-draft
interrogation before the review gate: reread the draft as a stranger and grill
the human on every block until no assumption is yours alone.

- Read the title, why, what, and each `## Done` criterion back one at a time.
  Name what each leaves open: boundaries, order, data shapes, failure modes,
  compatibility, and whether the words mean must or nice.
- State every assumption the draft makes — touched files and systems, existing
  behavior that must not change, inputs and prerequisites, migration and
  performance limits, test scope, and whether QA, refactor, and documentation
  tasks are included — and ask the human to confirm or correct each one. A nod
  without specifics is not a confirmation.
- Push the scope edges: what is explicitly out, what would make the plan fail
  even if every task lands, and which edge cases and non-goals the interview
  has not named.
- Fold each answer into a `draft revise` before formalizing. Record each
  unresolved question as an annotation with `draft annotate --kind question`,
  wait for the answer, then resolve it. Never formalize or promote while an
  assumption is still unconfirmed.

## Review gate: plan is truth

Present the draft — the sketch when there is one — for check-off before
formalizing or implementing anything. For a document draft, present the plan for check-off before implementing anything:

```bash
lpui --porcelain list --tree --status all
lpui --porcelain draft show --id D
```

Walk the human through every block, make last edits on the spot, and start
only on explicit check-off. Then formalize and promote, relate every plan
criterion to at least one proving task
(`lpui criterion relate --id C --task T`), and run `lpui lint --plan P` before
implementation. Ensure the formal document names its commit strategy and that
every task desc carries the resume contract, including its expected commit
slice and verification; reject a plan that batches a whole milestone or plan
into one commit. During execution,
the plan stays the truth: fold new findings into the plan before changing code,
never around it.

## Plan documents and recipes

When the whole tree is already known, write it in one document; promotion
creates it atomically:

```bash
lpui --porcelain plan recipe feature > plan.json   # feature | bugfix | refactor
lpui --porcelain plan apply --file plan.json --dry-run
lpui --actor NAME --porcelain plan apply --file plan.json
```

The document is JSON with a `plan` object and a `milestones` list; tasks nest
under milestones. Every plan, milestone, and task carries a stable `key`.
Retrying the same document is a no-op, and a failed apply rolls the whole tree
back. Recipes are skeletons with QA, refactoring, and documentation tasks; fill
the words, add criteria, then apply.

## Plan drafts

Every new plan starts as a draft that stays out of the queue until the human
promotes it. There are two forms:

- A **sketch** is the default. `plan add`, the TUI `n` form, and `draft sketch`
  store a definition-only Markdown page with a title, why, what, and acceptance
  criteria. It has no milestones or tasks.
- A **document** is the full tree. `plan apply` and `draft add` store the same
  JSON document that promotion creates.

A sketch is plain Markdown:

```markdown
# Title

## Why

...

## What

...

## Done

- Acceptance criterion
```

`# Title`, `## Why`, and `## What` are required; aliases such as `## Goal`,
`## Scope`, and `## Acceptance criteria` are accepted, and unknown sections stay
in the what.

```bash
lpui --actor NAME --porcelain draft sketch --file sketch.md
lpui --porcelain draft list [--status review|revising|promoted|all]
lpui --porcelain draft show --id D
lpui --porcelain draft annotations --id D [--status open|addressed|dismissed|all]
lpui --actor NAME --porcelain draft annotate --id D --block KEY --kind comment|question|change --text TEXT [--quote Q]
lpui --porcelain draft wait --id D [--timeout SECONDS]
lpui --actor NAME --porcelain draft respond --id A --response TEXT
lpui --actor NAME --porcelain draft resolve --id A [--response TEXT]
lpui --actor NAME --porcelain draft revise --id D --file sketch.md --base-revision N --note TEXT
lpui --actor NAME --porcelain draft ready --id D
lpui --actor NAME --porcelain draft formalize --id D --file plan.json --base-revision N --note TEXT
lpui --actor NAME --porcelain draft promote --id D
lpui --actor NAME --porcelain draft add --file plan.json
```

- Right after creating a draft, and after every `draft revise`, run
  `lpui --porcelain draft wait --id D` in the background. Saving an annotation
  moves the draft to revising and ends the wait at once with the open
  annotations (exit 0): answer each with `respond` or `resolve`, revise, run
  `ready` once none are open, and re-arm. Exit 3 means promoted, so stop; exit 4
  is `--timeout`, so re-arm. Open annotations end the wait immediately, so
  nothing saved between two waits is missed.
- Interrogate the written draft before the review gate: read every block back,
  name each assumption and scope edge, and fold the answers into a revision.
  Track unresolved ones as `question` annotations and wait; formalize and
  promote only when none remain.
- Review the sketch, not the derived tree. After the human approves the
  definition, `draft formalize` supplies the milestones and tasks as the JSON
  document. lpui refuses a document whose title, why, what, or plan criteria
  differ from the sketch, and refuses a milestone or task that leaves the
  resume contract implicit; any definition change goes through another sketch
  revision.
- `draft revise` reads Markdown for a sketch and JSON for a document. It must
  name the current base revision.
- `promote` refuses an unformalized sketch, open annotations, invalid
  documents, and a taken plan key; it creates the tree atomically.
- A sketch reserves no plan key and carries no lane settings; the formal
  document supplies both. Use `plan add --direct` when lane settings must be
  queued immediately.
- Annotations anchor to one block and an optional exact quote. A revision that
  cannot find a quote marks the annotation `moved` or `orphaned`; answer or ask,
  never delete feedback silently.
- MCP tools: `draft_list`, `draft_show`, `draft_sketch`, `draft_add`,
  `draft_formalize`, `draft_revise`, `draft_annotate`, `draft_respond`,
  `draft_resolve`, `draft_promote`; the resource is `lazyplan://draft/{id}`.

## Trust and coordination

Approvals, evidence, questions, readiness, and review close the loop after the
plan is cut. Parallel agents use claims, agents, touch-points, references, and
a ship note.

```bash
lpui --actor NAME plan approve --id P [--reason TEXT] [--enforce]
lpui --porcelain plan revisions --id P
lpui --porcelain plan diff --id P [--check]
lpui --actor NAME criterion prove --id C --command "pytest" --exit-code 0 \
  --commit SHA [--task T]
lpui --actor NAME criterion edit --id C --done
lpui --porcelain criterion evidence --id C
lpui --actor NAME task finish --id T --require-evidence
lpui --actor NAME question add --plan P --text "Which host?"
lpui --porcelain question list --plan P [--status open|resolved|all]
lpui --actor NAME question resolve --id Q [--note TEXT]
lpui --porcelain plan ready --id P
lpui review --plan P [--max-chars N] [--json]
lpui --porcelain audit --plan P [--min-evidence 0.8] --strict
```

Approval is advisory by default. `plan diff --check` is the opt-in CI gate;
`plan approve --enforce` also gates `plan move --to done` until drift is approved
or overridden. Scope edits accept `--reason`; status, completion, claims, commits, and
PRs never create drift.

Evidence is record-only: lazyplan never runs the command, fetches the PR, or
reads the artifact. The latest row decides whether a criterion is proven.
`criterion prove` records evidence without changing completion; set completion
separately with `criterion edit --id C --done` (or `--open`). `task finish
--require-evidence` checks every task criterion, with `--override REASON` as
the recorded escape.

Questions are plan-level and all open questions block `plan ready`. Readiness
also requires clean lint and a proving task for every plan criterion. `review`
is the deterministic Markdown handoff; it calls no model and no network.

```bash
lpui feed --session S
lpui --actor NAME touch add --task T --path PATH
lpui --porcelain claims
lpui --actor NAME claim --id T [--worktree PATH] [--repo PATH] [--force]
lpui --actor NAME task finish --id T
lpui --actor NAME link --kind task --id T
lpui --actor NAME ref link --plan P --url URL [--type epic|issue|doc|other]
lpui ref list|unlink --plan P
lpui ship --plan P [--json] [--max-chars N]
```

Claims are the only record of who works on what; the agents panel lists them
live. Moving a task another actor holds to doing is refused; `claim --force`
takes it over. A released or expired claim puts a doing task back to todo.
Hooks renew the claims held in their checkout and release them at session
end. `lpui hook --check` probes the transport without writing.
`context`/`brief` carry the plan's notes, so a handoff is a note.
Touch-points make `next` skip work that overlaps an active claim in the same
checkout; a manual claim needs `--force` and finish only warns. References are
read-only links to external work: no fetch, no write-back. `ship` prints the
deterministic outcome note; `review` remains the full packet.

## Plan worktrees

New plans are isolation-required. Print the setup command, create the worktree
with git, then register it. lazyplan never creates, removes, or checks out a
worktree itself.

```bash
lpui plan worktree --print --id P
git -C REPO worktree add -b plan/P-SLUG SIBLING
lpui --actor NAME plan worktree add --id P --repo REPO
lpui plan worktree list --id P [--stale]
lpui --actor NAME plan worktree remove --id P --repo REPO
```

`plan move --to doing`, `next --plan P`, and `claim --id T` refuse the shared
checkout. `--force --reason` records the
override. A done move refuses a dirty worktree and prints removal commands;
`doctor` and `--stale` report drift without deleting. Plans created before the
flag stay grandfathered.

## Orchestration and dispatch

A milestone is a lane. A plan declares `dispatch_mode` and `max_agents`;
milestones declare `lane_group` (wave) and `agent_role`; tasks declare `role`.
Waves run in group order, lanes in one wave run in parallel up to the cap, and
tasks run serially inside a lane. A parallel plan needs an integrator lane in a
later wave.

`lpui dispatch --plan P` is read-only: it returns waves, lane state, capacity,
the exact worktree commands, and a bounded prompt per dispatchable task. Run
the printed git commands, register each lane with `plan worktree add
--milestone S`, then start one worker per ready task with its role profile. A
high-reasoning orchestrator plans and reviews; cheap workers implement.

One lane holds one doing task. `next --lane S` limits selection; a second claim
is refused unless forced with a reason. Session start names the lane, wave,
role, and worktree; session end records a handoff note and releases that
checkout's claims. `lpui lint --plan P` rejects parallel plans without a lane
cap, an integrator, QA coverage, or disjoint same-wave touch-points.

The `lazyplan-orchestrate` skill carries the full loop: dispatch, worktrees,
role handoffs, integration, and closeout.

## During execution

Update the journal as you go, not at the end:

```bash
lpui --porcelain next                          # claim the first eligible task
lpui --porcelain context --max-chars 4000      # active slice, next work, proof
lpui --porcelain brief                         # active plan + next update
lpui --porcelain claim renew --id T --ttl 30m  # lease heartbeat while working
lpui --porcelain note add --kind task --id T --text "Decision or handoff"
lpui --porcelain task block --id T --reason "waiting"  # release the lease and park it
lpui --porcelain task move --id T --to done            # when the slice is complete
lpui --porcelain audit --since 7.days                  # coverage, lag, criteria gaps
```

Porcelain rows are `kind<TAB>id<TAB>status<TAB>title<TAB>parent<TAB>extra`.
Parse them by splitting on tabs; never scrape the human text. Set
`LAZYPLAN_PORCELAIN=1` for a whole agent session instead of passing the flag on
every call. Reach for `--json` only when you need full-fidelity fields.

- Never batch a whole plan or milestone into one commit; link each green commit.
- Tick task and plan criteria as they are proven, before closing the row.
- Lifecycle hooks may block a commit with no doing task, block one stop with
  unlinked commits, inject the active plan on every prompt, and end the agent
  at session end. They also record each host session's exact state; they
  never move a task or link a commit. `LAZYPLAN_HOOKS=advisory` downgrades
  blocks to reminders without reinstalling.
- `lpui claims` / `lpui who` shows active leases. `claim release --force` and
  `claim --force` record a takeover; blocked work is skipped by `next`.
- `lpui trace --plan P` walks each criterion to its proving task, commits, and
  PRs. `lpui lint --plan P --strict` rejects uncovered criteria, incomplete
  milestone or task resume contracts, placeholders, and done rows with open
  criteria.
- `lpui stats --since 7.days` reports WIP, cycle time, throughput, aging, stale
  work, reopened rows, claims, and blocked tasks. The screen splits plans into
  plan queue and plan review panels; attention data stays in the preview strip.
- Finish with `task finish --require-pr --require-checks` when the task must
  prove PR/CI evidence; `--override REASON` records an exception. A branch
  already recorded on another open task is rejected.
- Import issues once with `issue import` (GitHub live or Linear export);
  re-import refreshes source metadata only and never writes back.
- Human screen: `?` help, `c` palette, `[` / `]` history, and `q` quit work on
  every screen. Every status, block, claim, and delete action is single-row.
  The plan tree paints plans first and loads milestones and tasks on expand;
  a text filter reveals matching collapsed branches.
- Trust hubs are selectable: criteria (`t` from detail), evidence (`enter` on
  a criterion), questions, and references from the palette. Criteria add, edit
  (including done), relate, and delete; questions add, resolve, and reopen;
  references link, open, and unlink.
- Coordination hubs are selectable too: claims and touch-points (`k` from
  detail), and comments and notes (`m`). Claim and touch-point authoring works
  from the screen; import, sync, and setup stay CLI-only.
- Provenance hubs are selectable: the source trail (`g`) cross-links commits,
  files, and pull requests to their owning row, the pull request hub (`P`)
  refreshes, links, unlinks, and opens cached PRs, and the activity hub (`A`)
  filters the feed and jumps to the event target.
  Only the refresh action touches the network.
- Collaborate with `comment add/list/resolve`; use `share --plan P` for a
  read-only snapshot and `sync --file dump.json --dry-run` for a plan-level
  merge.
- `lpui audit --strict` is the opt-in CI gate; it defaults to 80% coverage, one
  commit of lag, and zero criteria gaps. Add `--min-trace 0.8` to gate coverage.

## Read first

```bash
lpui --porcelain list --tree [--status todo|doing|done|all]
lpui --porcelain next
lpui --porcelain claims
lpui --porcelain context --max-chars 4000
lpui --porcelain brief
lpui --porcelain audit --since 7.days
lpui --porcelain plan show --id N
lpui --porcelain dispatch --plan N [--lane M] [--max-chars 4000]
lpui --porcelain trace --plan N
lpui --porcelain lint --plan N
lpui --porcelain stats --since 7.days
lpui --porcelain feed --limit 20
lpui export --format json
lpui export --format markdown --plan ID [--file out.md] [--force]
lpui upgrade --check|--diagnose
lpui info
lpui reconcile
```

Use `--porcelain` for the active loop: one tab-separated row per record with no
glyphs or provenance noise. Use `--json` when you need full fidelity
(`lpui list --json`).

On Windows, `lpui upgrade` stages and hands off to a detached helper after lpui
exits, then relaunches the TUI. The full command and output are logged under
`%LOCALAPPDATA%\lazyplan\logs\`; `lpui upgrade --diagnose` prints the detected
method, owning Python, and log path. A failed apply leaves the old version
runnable and the next launch shows the log path. The screen pins the running
version in its taskbar, with an arrow to a newer cached release; `U` or the
badge opens the update screen, and `lpui upgrade --check` is the headless
equivalent.

## Templates

`.agents/lazyplan/templates/{plan,milestone,task}.md` (scaffolded by
`lpui setup --placement repo`; commit them to share) define what new rows look
like. Repo placement shares them; otherwise templates live beside the shared
home DB at `~/.lazyplan/templates/`. Each file is Markdown with YAML
frontmatter; the body is guidance and ignored:

```yaml
defaults: {why: "", what: ""}
required: [title]
criteria: []
```

Long single-blob `why`/`what`/`desc` (over 300 chars with no paragraph breaks or
section markers) fails creation — use paragraphs and sections. Field names are
per kind: plan `title/why/what`, milestone and task `title/desc`. Missing
`required` entries fail with exit 2 naming the field; missing template files mean
legacy behavior (tasks default `p1`). Setup writes the opinionated starters
silently; edit the files to change what new rows require. Existing edits are
never overwritten.

Structural recipes are separate: `plan recipe feature|bugfix|refactor` prints a
full document skeleton for `plan apply`, while these templates fill one row.

## Write and criteria

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is plan|milestone|task everywhere it appears.

```bash
lpui --actor NAME plan add --title "API v2" --why ".." --what ".."
lpui --actor NAME milestone add --plan P --title "Feature Y" [--desc ..]
lpui --actor NAME task add --milestone S --title "Do X" [--desc ctx]
lpui --actor NAME task edit --id T [--title .. --desc ..]
lpui --actor NAME plan edit --id P [--title .. --what .. --why ..]
lpui --actor NAME task move --id T --to doing|done
lpui --actor NAME task delete --id T
lpui --actor NAME criterion add --kind plan --id P --text "Works offline"
lpui criterion list --kind plan --id P
lpui criterion edit --id C --done / --open
lpui --actor NAME criterion delete --id C
lpui --actor NAME import --file dump.json
```

Deleting a plan removes its milestones and tasks — double-check ids first.
Status moves roll parents up automatically; closing the last open task completes
its milestone and plan. Closing with open acceptance criteria warns but never
blocks. Criteria live on plans, milestones, and tasks; plan-level criteria are
the definition of done — mark them done as the work lands. Parent progress is
recomputed from children; `lpui reconcile` can recompute parent statuses from children when an older journal drifts.

## Resume contract

A promoted plan is the handoff. A fresh agent, or one resuming after a dead
session, must be able to act from the row itself instead of inferring the
approach, files, prerequisites, commits, checks, or boundaries. Every milestone
and task description therefore carries labeled sections:

```text
Milestone
Outcome: the user value, in As a / I want / so that form
Scope: what is in and explicitly out for this slice
Inputs: prerequisites, existing behavior, rows, or environment
Slices: the ordered commits or tasks that land the milestone

Task
Approach: the technical how, naming the code path and edge cases
Touch: at least one concrete path, module, or file
Inputs: prerequisites and what must already be true
Commit: the expected commit slice(s)
Verify: the exact command or check that proves the slice
Guardrails: invariants, non-goals, and what must not change
```

`Touch:` must name a real path. `Inputs: none` and `Guardrails: none beyond the
plan scope` are legal when true. Paragraph labels, `**Label:**`, `## Label`
headings, and common aliases (`Files:`, `Prerequisites:`, `Commit slice:`,
`Verification:`, `Invariants:`) are accepted. `draft formalize`, `plan apply`,
and `draft promote` refuse a plan with no milestone or task, and a tree with a
missing or unusable section; `lint` flags the same gaps on rows created or
edited later, so `plan ready` waits
until the brief is complete. When you start or resume a task, read
`lpui task show --id T`: the journal supplies status, claims, notes, and
commits, and the description supplies the contract.

## Milestone and task standards

Each milestone states user value in narrative form, with testable criteria:

```bash
lpui --actor NAME milestone add --plan P --title "Feature Y" --desc "As a [persona], I want [action] so that [benefit]"
lpui --actor NAME criterion add --kind milestone --id S --text "Given [context], when [action], then [outcome]"
```

Keep milestones INVEST: independent, negotiable, valuable, estimable, small,
testable. At creation, `--desc` carries every milestone resume-contract section:
Outcome, Scope, Inputs, and Slices. A milestone without them is not ready to
cut. Each task advances one small, green commit series; a milestone that only
works as one batch commit is not ready. No dependency, estimate, or owner
fields — sequencing lives in creation order, context lives in `--desc`.

Task titles start with a verb and name the target. `--desc` carries every task
resume-contract section: Approach, Touch, Inputs, Commit, Verify, and
Guardrails. Task-level checklists are the definition of done:

```bash
lpui --actor NAME task add --milestone S --title "Implement token rotation" --desc "Approach and file refs"
lpui --actor NAME task add --milestone S --title "Run the relevant test suites" --desc "Suites named in the interview"
lpui --actor NAME task add --milestone S --title "Refactor what the change touched" --desc "Leave the area cleaner"
lpui --actor NAME task add --milestone S --title "Clean up touched documentation" --desc "Docs matching the final code"
lpui --actor NAME criterion add --kind task --id T --text "Unit tests pass"
```

Each task lands as one or more small commits. Every commit is green — the
relevant checks pass and the tree builds — and independently reviewable. Keep
behavior, tests, docs, and refactors in separate commits when they can stand
alone. Never batch a whole milestone or plan into one commit. The task `--desc`
names the expected commit slice and the verification for each commit. Link
commits after the fact with `lpui link` or `task finish`; no commit trailer is
required. Cut tasks only from scouted ground: each one must name real files,
real constraints, real prerequisites. Every task `--desc` names the technical
approach, concrete touch-points, inputs/prerequisites, commit slice,
verification, and guardrails — a task missing any of them is not ready to cut.

## Human-in-the-loop

Scope, taste, and repo-wide impact belong to the human: ask in conversation and
wait for an answer before writing. Never decide a plan's why/what or its
acceptance criteria on your own — interview, record, confirm. Scout the codebase during the interview to target real files and constraints. Status moves and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent plan/milestone ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- The plan is the truth for the desired implementation: change it before
  changing course.
- Format for scanability: short headers, fenced code blocks, one concern per
  block, verdict first.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is
  keyboard-only).
