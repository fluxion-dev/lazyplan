"""SQLite schema for a fresh lazyplan database."""

from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    goal TEXT NOT NULL DEFAULT '',
    uid TEXT NOT NULL DEFAULT '',
    archived_at REAL NOT NULL DEFAULT 0,
    worktree_required INTEGER NOT NULL DEFAULT 0,
    dispatch_mode TEXT NOT NULL DEFAULT 'serial',
    max_agents INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entity_keys (
    kind TEXT NOT NULL CHECK (kind IN ('plan', 'milestone', 'task')),
    key TEXT NOT NULL,
    row_id INTEGER NOT NULL,
    PRIMARY KEY (kind, key),
    UNIQUE (kind, row_id)
);
CREATE INDEX IF NOT EXISTS idx_entity_keys_row ON entity_keys(kind, row_id);
CREATE TABLE IF NOT EXISTS plan_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    approved_at REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    reason TEXT NOT NULL DEFAULT '',
    digest TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    change_mark INTEGER NOT NULL DEFAULT 0,
    enforced INTEGER NOT NULL DEFAULT 0,
    UNIQUE (plan_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_plan_revisions_plan ON plan_revisions(plan_id, revision DESC);
CREATE TABLE IF NOT EXISTS plan_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    kind TEXT NOT NULL CHECK (kind IN ('plan', 'milestone', 'task', 'criterion')),
    obj_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    field TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_plan_changes_plan ON plan_changes(plan_id, id);
CREATE TABLE IF NOT EXISTS criterion_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criterion_id INTEGER NOT NULL REFERENCES criteria(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    command TEXT NOT NULL DEFAULT '',
    exit_code INTEGER,
    commit_sha TEXT NOT NULL DEFAULT '',
    pr_url TEXT NOT NULL DEFAULT '',
    artifact_path TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    CHECK (
        command <> '' OR commit_sha <> '' OR pr_url <> ''
        OR artifact_path <> '' OR note <> ''
    )
);
CREATE INDEX IF NOT EXISTS idx_criterion_evidence_criterion
    ON criterion_evidence(criterion_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_criterion_evidence_task
    ON criterion_evidence(task_id, id DESC);
CREATE TABLE IF NOT EXISTS plan_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    actor TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    resolved_at REAL NOT NULL DEFAULT 0,
    resolved_by TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_plan_questions_plan
    ON plan_questions(plan_id, status, id);
CREATE TABLE IF NOT EXISTS plan_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (trim(title) <> ''),
    status TEXT NOT NULL DEFAULT 'review'
        CHECK (status IN ('review', 'revising', 'promoted')),
    document TEXT NOT NULL CHECK (trim(document) <> ''),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    actor TEXT NOT NULL DEFAULT 'human',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    promoted_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_plan_drafts_status ON plan_drafts(status, id);
CREATE TABLE IF NOT EXISTS plan_draft_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES plan_drafts(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    document TEXT NOT NULL CHECK (trim(document) <> ''),
    actor TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (draft_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_plan_draft_revisions_draft
    ON plan_draft_revisions(draft_id, revision DESC);
CREATE TABLE IF NOT EXISTS draft_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES plan_drafts(id) ON DELETE CASCADE,
    block_key TEXT NOT NULL CHECK (trim(block_key) <> ''),
    quote TEXT NOT NULL DEFAULT '',
    start_offset INTEGER NOT NULL DEFAULT 0 CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL DEFAULT 0 CHECK (end_offset >= start_offset),
    kind TEXT NOT NULL CHECK (kind IN ('comment', 'question', 'change')),
    body TEXT NOT NULL CHECK (trim(body) <> ''),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'addressed', 'dismissed')),
    author TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    response TEXT NOT NULL DEFAULT '',
    responded_by TEXT NOT NULL DEFAULT '',
    responded_at REAL NOT NULL DEFAULT 0,
    anchor_state TEXT NOT NULL DEFAULT 'ok'
        CHECK (anchor_state IN ('ok', 'moved', 'orphaned'))
);
CREATE INDEX IF NOT EXISTS idx_draft_annotations_draft
    ON draft_annotations(draft_id, status, id);
CREATE TABLE IF NOT EXISTS external_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'other',
    kind TEXT NOT NULL DEFAULT 'issue',
    external_id TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'human',
    created_at REAL NOT NULL,
    UNIQUE(plan_id, url)
);
CREATE INDEX IF NOT EXISTS idx_external_refs_plan ON external_refs(plan_id, id);
CREATE TABLE IF NOT EXISTS session_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL DEFAULT 'human',
    plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    repo_path TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    handoff TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT 'working',
    last_seen_at REAL NOT NULL DEFAULT 0,
    host TEXT NOT NULL DEFAULT '',
    host_session TEXT NOT NULL DEFAULT '',
    auto_closed INTEGER NOT NULL DEFAULT 0,
    plan_source TEXT NOT NULL DEFAULT 'auto',
    archived_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_session_history_open
    ON session_history(ended_at, actor, repo_path);
CREATE INDEX IF NOT EXISTS idx_session_history_plan
    ON session_history(plan_id, ended_at);
CREATE INDEX IF NOT EXISTS idx_session_history_repo
    ON session_history(ended_at, repo_path, started_at);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    lane_group INTEGER NOT NULL DEFAULT 1,
    agent_role TEXT NOT NULL DEFAULT 'implementer'
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id INTEGER NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    description TEXT NOT NULL DEFAULT '',
    blocked INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'implementer'
);
CREATE TABLE IF NOT EXISTS task_claims (
    task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    actor TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    renewed_at REAL NOT NULL DEFAULT 0,
    worktree TEXT NOT NULL DEFAULT '',
    repo_path TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_task_claims_expires ON task_claims(expires_at);
CREATE TABLE IF NOT EXISTS task_touchpoints (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    PRIMARY KEY (task_id, pattern)
);
CREATE INDEX IF NOT EXISTS idx_task_touchpoints_task ON task_touchpoints(task_id);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> '')
);
CREATE INDEX IF NOT EXISTS idx_notes_parent ON notes(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    ts REAL NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS issue_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    number TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    row_kind TEXT NOT NULL CHECK (row_kind IN ('plan', 'milestone', 'task')),
    row_id INTEGER NOT NULL,
    updated_at REAL NOT NULL DEFAULT 0,
    UNIQUE(provider, external_id)
);
CREATE INDEX IF NOT EXISTS idx_issue_links_row ON issue_links(row_kind, row_id);
CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_criteria_parent ON criteria(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS criterion_links (
    criterion_id INTEGER NOT NULL REFERENCES criteria(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (criterion_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_criterion_links_task ON criterion_links(task_id);
CREATE TABLE IF NOT EXISTS vcs_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    sha TEXT NOT NULL CHECK (length(sha) = 40),
    subject TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    timestamp INTEGER NOT NULL DEFAULT 0,
    repo_root TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL DEFAULT '[]',
    stale INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL DEFAULT 0,
    UNIQUE(parent_kind, parent_id, sha)
);
CREATE INDEX IF NOT EXISTS idx_vcs_links_parent ON vcs_links(parent_kind, parent_id);
CREATE INDEX IF NOT EXISTS idx_vcs_links_sha ON vcs_links(sha);
CREATE TABLE IF NOT EXISTS forge_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'github',
    kind TEXT NOT NULL DEFAULT 'pull',
    number INTEGER NOT NULL CHECK (number > 0),
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    checks TEXT NOT NULL DEFAULT '',
    reviews TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    base_ref TEXT NOT NULL DEFAULT '',
    head_ref TEXT NOT NULL DEFAULT '',
    merged_at TEXT NOT NULL DEFAULT '',
    merge_commit_sha TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL DEFAULT 0,
    stale INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '',
    UNIQUE(parent_kind, parent_id, provider, kind, number)
);
CREATE INDEX IF NOT EXISTS idx_forge_links_parent ON forge_links(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS forge_cache (
    key TEXT PRIMARY KEY,
    etag TEXT NOT NULL DEFAULT '',
    fetched_at INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS entity_repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    repo_path TEXT NOT NULL,
    repo_remote TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    base_sha TEXT NOT NULL DEFAULT '',
    UNIQUE(parent_kind, parent_id, repo_path, repo_remote)
);
CREATE INDEX IF NOT EXISTS idx_entity_repos_parent ON entity_repos(parent_kind, parent_id);
CREATE INDEX IF NOT EXISTS idx_entity_repos_branch ON entity_repos(branch, repo_path, repo_remote);
CREATE TABLE IF NOT EXISTS plan_worktrees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    milestone_id INTEGER REFERENCES milestones(id) ON DELETE CASCADE,
    repo_path TEXT NOT NULL,
    repo_remote TEXT NOT NULL DEFAULT '',
    worktree_path TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    registered_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_worktrees_plan ON plan_worktrees(plan_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    kind TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    session_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_milestones_plan ON milestones(plan_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
CREATE INDEX IF NOT EXISTS idx_events_action ON events(action, id);
"""
