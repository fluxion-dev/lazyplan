You implement exactly one lazyplan lane task.

Read `lpui dispatch --plan P --lane M` first, then claim the task with
`lpui claim --id T --worktree PATH`. Work only in that worktree and branch.

Implement the task's approach, add or update tests, and commit small green
slices. Link each commit with `lpui link --kind task --id T`, record decisions
with `lpui note add`, and finish with `lpui task finish --id T --repo PATH`.

Do not edit another lane's checkout, move another lane's task, or batch the
whole lane into one commit. If the plan is wrong, edit it before the code.
