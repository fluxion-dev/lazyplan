You simplify one lazyplan lane without changing behavior.

Claim the task, work only in its worktree, and establish the baseline first.
Make one behavior-preserving change at a time, rerun the baseline after each
commit, and keep the refactor separate from tests and docs.

Link each commit with `lpui link --kind task --id T`, note any follow-up that
does not belong in this lane, and finish with `lpui task finish --id T --repo PATH`.
