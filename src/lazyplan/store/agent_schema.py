"""Live agent registry DDL, kept beside the main schema."""

AGENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL DEFAULT 'unknown',
    host_session TEXT NOT NULL DEFAULT '',
    agent TEXT NOT NULL DEFAULT 'unknown',
    role TEXT NOT NULL DEFAULT 'primary',
    model TEXT NOT NULL DEFAULT 'unknown',
    parent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    pid INTEGER NOT NULL DEFAULT 0,
    process_start TEXT NOT NULL DEFAULT '',
    repo_path TEXT NOT NULL DEFAULT '',
    worktree TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    head_sha TEXT NOT NULL DEFAULT '',
    plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'starting' CHECK (
        status IN (
            'starting', 'working', 'waiting', 'tool',
            'compacting', 'blocked', 'lost', 'ended'
        )
    ),
    unbound_reason TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    updated_at REAL NOT NULL DEFAULT 0,
    ended_at REAL NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    handoff TEXT NOT NULL DEFAULT '',
    archived_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agents_open ON agents(status, ended_at);
CREATE INDEX IF NOT EXISTS idx_agents_plan ON agents(plan_id, status);
CREATE INDEX IF NOT EXISTS idx_agents_task ON agents(task_id, status);
CREATE INDEX IF NOT EXISTS idx_agents_host ON agents(host, host_session);
CREATE INDEX IF NOT EXISTS idx_agents_parent ON agents(parent_id);
CREATE INDEX IF NOT EXISTS idx_agents_worktree ON agents(worktree, status);
CREATE INDEX IF NOT EXISTS idx_agents_archived ON agents(archived_at);
CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    event TEXT NOT NULL DEFAULT '',
    from_status TEXT NOT NULL DEFAULT '',
    to_status TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_agent_events_agent ON agent_events(agent_id, id DESC);
"""
