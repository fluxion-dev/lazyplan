"""SQLite persistence. Stdlib only. Shared by TUI and `lp` CLI (agent ingress)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .models import (
    PRIORITIES,
    PRIORITY_RANK,
    Criterion,
    Link,
    Milestone,
    Project,
    Risk,
    RiskStatus,
    Status,
    Task,
    UserStory,
    format_id_list,
    normalize_labels,
    parse_id_list,
)
from .repo import ensure_plan_dir, resolve_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    goal TEXT NOT NULL DEFAULT '',
    success_metrics TEXT NOT NULL DEFAULT '',
    scope_in TEXT NOT NULL DEFAULT '',
    scope_out TEXT NOT NULL DEFAULT '',
    assumptions TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '',
    blocked_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    estimate TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '',
    blocked_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('story', 'task')),
    parent_id INTEGER NOT NULL,
    url TEXT NOT NULL CHECK (trim(url) <> ''),
    label TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_links_parent ON links(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('story', 'task')),
    parent_id INTEGER NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_criteria_parent ON criteria(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (trim(title) <> ''),
    likelihood TEXT NOT NULL DEFAULT 'med',
    impact TEXT NOT NULL DEFAULT 'med',
    mitigation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS idx_risks_project ON risks(project_id);
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (trim(title) <> ''),
    date TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('story', 'task')),
    parent_id INTEGER NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT 'human',
    status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
    result_id INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL DEFAULT 'human',
    question TEXT NOT NULL CHECK (trim(question) <> ''),
    answer TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered')),
    ts REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    kind TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_stories_project ON stories(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_story ON tasks(story_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
"""

# Idempotent migrations for DBs created by older versions.
_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "projects": ("goal", "success_metrics", "scope_in", "scope_out", "assumptions"),
    "stories": ("owner", "priority", "labels", "estimate", "blocked_by"),
    "tasks": ("start_date", "end_date", "description", "owner", "priority", "labels", "blocked_by"),
}


def default_db_path() -> Path:
    """Resolved default DB: $LAZYPLAN_DB > enclosing repo `.plan/` > global."""
    return resolve_db_path()


def _ser(d: dict) -> dict:
    """JSON/agent-safe: Status -> value, datetimes stay ISO via default=str."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    return d


def _actor(explicit: str = "") -> str:
    """Normalize an actor name, defaulting to $USER or human."""
    if explicit.strip():
        return explicit.strip()[:64]
    return (os.environ.get("USER", "") or "human")[:64]


class Store:
    """SQLite persistence shared by the TUI and the lp CLI."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_db_path(path)
        ensure_plan_dir(self.path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            for table, cols in _MIGRATIONS.items():
                existing = {
                    r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for col in cols:
                    if col not in existing:
                        conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
                        )

    def _connect(self) -> sqlite3.Connection:
        """Open a row-factory connection with foreign keys on."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -- events (M3 agent feed) ----------------------------------------
    def log(self, actor: str, kind: str, action: str, detail: str = "") -> None:
        """Append an event row."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?,?,?,?,?)",
                (time.time(), _actor(actor), kind, action, detail[:500]),
            )

    def feed(self, limit: int = 20) -> list[dict]:
        """Recent events, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (max(limit, 1),)
            ).fetchall()
        return [dict(r) for r in rows]

    def fingerprint(self) -> tuple:
        """Conflict-safe poll key: mtime + row counts + max ids + last event."""
        try:
            mtime = os.path.getmtime(str(self.path))
        except OSError:
            mtime = 0.0
        c = self.counts()
        with self._connect() as conn:
            mp = conn.execute("SELECT COALESCE(MAX(id),0) m FROM projects").fetchone()["m"]
            ms = conn.execute("SELECT COALESCE(MAX(id),0) m FROM stories").fetchone()["m"]
            mt = conn.execute("SELECT COALESCE(MAX(id),0) m FROM tasks").fetchone()["m"]
            me = conn.execute("SELECT COALESCE(MAX(id),0) m FROM events").fetchone()["m"]
            mpr = conn.execute("SELECT COALESCE(MAX(id),0) m FROM proposals").fetchone()["m"]
            mq = conn.execute("SELECT COALESCE(MAX(id),0) m FROM questions").fetchone()["m"]
        return (mtime, c["projects"], c["stories"], c["tasks"], mp, ms, mt, me, mpr, mq)

    # -- projects ------------------------------------------------------
    def add_project(
        self,
        name: str,
        description: str = "",
        start_date: str = "",
        end_date: str = "",
        goal: str = "",
        success_metrics: str = "",
        scope_in: str = "",
        scope_out: str = "",
        assumptions: str = "",
        actor: str = "human",
    ) -> Project:
        """Insert a project and log the event."""
        p = Project(
            id=0,
            name=name.strip(),
            description=description,
            start_date=start_date,
            end_date=end_date,
            goal=goal,
            success_metrics=success_metrics,
            scope_in=scope_in,
            scope_out=scope_out,
            assumptions=assumptions,
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, description, start_date, end_date, status,"
                " goal, success_metrics, scope_in, scope_out, assumptions)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    p.name,
                    p.description,
                    p.start_date,
                    p.end_date,
                    p.status.value,
                    p.goal,
                    p.success_metrics,
                    p.scope_in,
                    p.scope_out,
                    p.assumptions,
                ),
            )
            p.id = cur.lastrowid or 0
        self.log(actor, "project", "add", f"P#{p.id} {p.name}")
        return p

    def _row_to_project(self, r: sqlite3.Row) -> Project:
        """Row to Project."""
        return Project(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            start_date=r["start_date"],
            end_date=r["end_date"],
            status=Status(r["status"]),
            goal=r["goal"] or "",
            success_metrics=r["success_metrics"] or "",
            scope_in=r["scope_in"] or "",
            scope_out=r["scope_out"] or "",
            assumptions=r["assumptions"] or "",
        )

    def _check_blocked(self, kind: str, obj_id: int | None, blocked: list[int]) -> None:
        """Existence + self + cycle guard for blocked_by. None obj_id = new row (no cycle possible)."""
        table = {"story": "stories", "task": "tasks"}[kind]
        with self._connect() as conn:
            rows = conn.execute(f"SELECT id, blocked_by FROM {table}").fetchall()
        graph = {r["id"]: parse_id_list(r["blocked_by"] or "") for r in rows}
        for b in blocked:
            if obj_id is not None and b == obj_id:
                raise ValueError(f"{kind} #{obj_id} cannot block itself")
            if b not in graph:
                raise KeyError(f"{kind} #{b} not found")
        if obj_id is None:
            return
        graph[obj_id] = list(blocked)
        seen: set[int] = set()
        stack = list(blocked)
        while stack:
            cur = stack.pop()
            if cur == obj_id:
                raise ValueError("blocked-by cycle detected")
            if cur not in seen:
                seen.add(cur)
                stack.extend(graph.get(cur, []))

    def is_blocked(self, kind: str, obj_id: int) -> bool:
        """True when any blocker is not done (used for gantt markers)."""
        obj = self.get_story(obj_id) if kind == "story" else self.get_task(obj_id)
        if obj is None or not obj.blocked_by:
            return False
        for b in obj.blocked_by:
            other = self.get_story(b) if kind == "story" else self.get_task(b)
            if other is None or other.status != Status.DONE:
                return True
        return False

    def get_project(self, pid: int) -> Project | None:
        """Fetch a project by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return self._row_to_project(r) if r is not None else None

    def list_projects(self) -> list[Project]:
        """All projects, id order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [self._row_to_project(r) for r in rows]

    def update_project(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        goal: str | None = None,
        success_metrics: str | None = None,
        scope_in: str | None = None,
        scope_out: str | None = None,
        assumptions: str | None = None,
        actor: str = "human",
    ) -> Project | None:
        """Patch project fields and log."""
        p = self.get_project(pid)
        if p is None:
            return None
        if name is not None:
            if not name.strip():
                raise ValueError("project name must not be empty")
            p.name = name.strip()
        if description is not None:
            p.description = description
        if start_date is not None:
            p.start_date = start_date
        if end_date is not None:
            p.end_date = end_date
        for attr, val in (
            ("goal", goal),
            ("success_metrics", success_metrics),
            ("scope_in", scope_in),
            ("scope_out", scope_out),
            ("assumptions", assumptions),
        ):
            if val is not None:
                setattr(p, attr, val)
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name=?, description=?, start_date=?, end_date=?,"
                " goal=?, success_metrics=?, scope_in=?, scope_out=?, assumptions=?"
                " WHERE id=?",
                (
                    p.name,
                    p.description,
                    p.start_date,
                    p.end_date,
                    p.goal,
                    p.success_metrics,
                    p.scope_in,
                    p.scope_out,
                    p.assumptions,
                    pid,
                ),
            )
        self.log(actor, "project", "edit", f"P#{pid} {p.name}")
        return p

    # -- stories -------------------------------------------------------
    def add_story(
        self,
        project_id: int,
        title: str,
        description: str = "",
        start_date: str = "",
        end_date: str = "",
        owner: str = "",
        priority: str = "",
        labels: str = "",
        estimate: str = "",
        blocked_by: str = "",
        actor: str = "human",
    ) -> UserStory:
        """Insert a story and log the event."""
        s = UserStory(
            id=0,
            project_id=project_id,
            title=title.strip(),
            description=description,
            start_date=start_date,
            end_date=end_date,
            owner=owner,
            priority=priority,
            labels=normalize_labels(labels.split(",")),
            estimate=estimate,
            blocked_by=parse_id_list(blocked_by),
        )
        self._check_blocked("story", None, s.blocked_by)
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise KeyError(f"project #{project_id} not found")
            cur = conn.execute(
                "INSERT INTO stories (project_id, title, description, status, start_date, end_date,"
                " owner, priority, labels, estimate, blocked_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    s.project_id,
                    s.title,
                    s.description,
                    s.status.value,
                    s.start_date,
                    s.end_date,
                    s.owner,
                    s.priority,
                    ",".join(s.labels),
                    s.estimate,
                    format_id_list(s.blocked_by),
                ),
            )
            s.id = cur.lastrowid or 0
        self.log(actor, "story", "add", f"S#{s.id} {s.title}")
        return s

    def _row_to_story(self, r: sqlite3.Row) -> UserStory:
        """Row to UserStory."""
        return UserStory(
            id=r["id"],
            project_id=r["project_id"],
            title=r["title"],
            description=r["description"],
            status=Status(r["status"]),
            start_date=r["start_date"],
            end_date=r["end_date"],
            owner=r["owner"] or "",
            priority=r["priority"] or "",
            labels=normalize_labels((r["labels"] or "").split(",")),
            estimate=r["estimate"] or "",
            blocked_by=parse_id_list(r["blocked_by"] or ""),
        )

    def get_story(self, sid: int) -> UserStory | None:
        """Fetch a story by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM stories WHERE id=?", (sid,)).fetchone()
        return self._row_to_story(r) if r is not None else None

    def list_stories(self, project_id: int) -> list[UserStory]:
        """Stories of a project, priority then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM stories WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
        out = [self._row_to_story(r) for r in rows]
        out.sort(key=lambda s: (PRIORITY_RANK.get(s.priority, 99), s.id))
        return out

    def update_story(
        self,
        sid: int,
        title: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        labels: str | None = None,
        estimate: str | None = None,
        blocked_by: str | None = None,
        actor: str = "human",
    ) -> UserStory | None:
        """Patch story fields and log."""
        s = self.get_story(sid)
        if s is None:
            return None
        if title is not None:
            if not title.strip():
                raise ValueError("story title must not be empty")
            s.title = title.strip()
        if description is not None:
            s.description = description
        if start_date is not None:
            s.start_date = start_date
        if end_date is not None:
            s.end_date = end_date
        if owner is not None:
            s.owner = owner
        if priority is not None:
            if priority not in ("", *PRIORITIES):
                raise ValueError(f"priority must be one of p0..p3, got {priority!r}")
            s.priority = priority
        if labels is not None:
            s.labels = normalize_labels(labels.split(","))
        if estimate is not None:
            s.estimate = estimate
        if blocked_by is not None:
            parsed = parse_id_list(blocked_by)
            self._check_blocked("story", sid, parsed)
            s.blocked_by = parsed
        with self._connect() as conn:
            conn.execute(
                "UPDATE stories SET title=?, description=?, start_date=?, end_date=?, owner=?,"
                " priority=?, labels=?, estimate=?, blocked_by=? WHERE id=?",
                (
                    s.title,
                    s.description,
                    s.start_date,
                    s.end_date,
                    s.owner,
                    s.priority,
                    ",".join(s.labels),
                    s.estimate,
                    format_id_list(s.blocked_by),
                    sid,
                ),
            )
        self.log(actor, "story", "edit", f"S#{sid} {s.title}")
        return s

    # -- tasks ---------------------------------------------------------
    def add_task(
        self,
        story_id: int,
        title: str,
        estimate: str = "",
        start_date: str = "",
        end_date: str = "",
        description: str = "",
        owner: str = "",
        priority: str = "",
        labels: str = "",
        blocked_by: str = "",
        actor: str = "human",
    ) -> Task:
        """Insert a task and log the event."""
        t = Task(
            id=0,
            story_id=story_id,
            title=title.strip(),
            estimate=estimate,
            start_date=start_date,
            end_date=end_date,
            description=description,
            owner=owner,
            priority=priority,
            labels=normalize_labels(labels.split(",")),
            blocked_by=parse_id_list(blocked_by),
        )
        self._check_blocked("task", None, t.blocked_by)
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)).fetchone() is None:
                raise KeyError(f"story #{story_id} not found")
            cur = conn.execute(
                "INSERT INTO tasks (story_id, title, status, estimate, start_date, end_date,"
                " description, owner, priority, labels, blocked_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    t.story_id,
                    t.title,
                    t.status.value,
                    t.estimate,
                    t.start_date,
                    t.end_date,
                    t.description,
                    t.owner,
                    t.priority,
                    ",".join(t.labels),
                    format_id_list(t.blocked_by),
                ),
            )
            t.id = cur.lastrowid or 0
        self.log(actor, "task", "add", f"T#{t.id} {t.title}")
        return t

    def _row_to_task(self, r: sqlite3.Row) -> Task:
        """Row to Task."""
        return Task(
            id=r["id"],
            story_id=r["story_id"],
            title=r["title"],
            status=Status(r["status"]),
            estimate=r["estimate"] or "",
            start_date=r["start_date"] or "",
            end_date=r["end_date"] or "",
            description=r["description"] or "",
            owner=r["owner"] or "",
            priority=r["priority"] or "",
            labels=normalize_labels((r["labels"] or "").split(",")),
            blocked_by=parse_id_list(r["blocked_by"] or ""),
        )

    def get_task(self, tid: int) -> Task | None:
        """Fetch a task by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return self._row_to_task(r) if r is not None else None

    def list_tasks(self, story_id: int) -> list[Task]:
        """Tasks of a story, priority then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE story_id=? ORDER BY id", (story_id,)
            ).fetchall()
        out = [self._row_to_task(r) for r in rows]
        out.sort(key=lambda t: (PRIORITY_RANK.get(t.priority, 99), t.id))
        return out

    def update_task(
        self,
        tid: int,
        title: str | None = None,
        estimate: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        labels: str | None = None,
        blocked_by: str | None = None,
        actor: str = "human",
    ) -> Task | None:
        """Patch task fields and log."""
        t = self.get_task(tid)
        if t is None:
            return None
        if title is not None:
            if not title.strip():
                raise ValueError("task title must not be empty")
            t.title = title.strip()
        if estimate is not None:
            t.estimate = estimate
        if start_date is not None:
            t.start_date = start_date
        if end_date is not None:
            t.end_date = end_date
        if description is not None:
            t.description = description
        if owner is not None:
            t.owner = owner
        if priority is not None:
            if priority not in ("", *PRIORITIES):
                raise ValueError(f"priority must be one of p0..p3, got {priority!r}")
            t.priority = priority
        if labels is not None:
            t.labels = normalize_labels(labels.split(","))
        if blocked_by is not None:
            parsed = parse_id_list(blocked_by)
            self._check_blocked("task", tid, parsed)
            t.blocked_by = parsed
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET title=?, estimate=?, start_date=?, end_date=?,"
                " description=?, owner=?, priority=?, labels=?, blocked_by=? WHERE id=?",
                (
                    t.title,
                    t.estimate,
                    t.start_date,
                    t.end_date,
                    t.description,
                    t.owner,
                    t.priority,
                    ",".join(t.labels),
                    format_id_list(t.blocked_by),
                    tid,
                ),
            )
        self.log(actor, "task", "edit", f"T#{tid} {t.title}")
        return t

    def delete(self, kind: str, obj_id: int, actor: str = "human") -> bool:
        """Delete a row and its subtree (links, criteria); FK cascades the rest."""
        table = {"project": "projects", "story": "stories", "task": "tasks"}.get(kind)
        if table is None:
            raise ValueError("kind must be project|story|task")
        with self._connect() as conn:
            if kind == "project":
                sids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM stories WHERE project_id=?", (obj_id,)
                    ).fetchall()
                ]
                for sid in sids:
                    self._delete_story_links(conn, sid)
            elif kind == "story":
                self._delete_story_links(conn, obj_id)
            else:
                conn.execute(
                    "DELETE FROM links WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
            cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (obj_id,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, kind, "delete", f"{kind} #{obj_id}")
        return ok

    @staticmethod
    def _delete_story_links(conn: sqlite3.Connection, story_id: int) -> None:
        """Remove links and criteria under a story and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute("SELECT id FROM tasks WHERE story_id=?", (story_id,)).fetchall()
        ]
        conn.execute("DELETE FROM links WHERE parent_kind='story' AND parent_id=?", (story_id,))
        conn.execute("DELETE FROM criteria WHERE parent_kind='story' AND parent_id=?", (story_id,))
        for tid in tids:
            conn.execute("DELETE FROM links WHERE parent_kind='task' AND parent_id=?", (tid,))
            conn.execute("DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (tid,))

    # -- links (S#11 supporting materials) ------------------------------
    def add_link(
        self, parent_kind: str, parent_id: int, url: str, label: str = "", actor: str = "human"
    ) -> Link:
        """Attach a supporting link and log."""
        link = Link(
            id=0, parent_kind=parent_kind, parent_id=parent_id, url=url.strip(), label=label
        )
        exists = self.get_story(parent_id) if parent_kind == "story" else self.get_task(parent_id)
        if exists is None:
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO links (parent_kind, parent_id, url, label) VALUES (?,?,?,?)",
                (link.parent_kind, link.parent_id, link.url, link.label),
            )
            link.id = cur.lastrowid or 0
        self.log(actor, "link", "add", f"{parent_kind} #{parent_id}: {link.url}")
        return link

    def list_links(self, parent_kind: str, parent_id: int) -> list[Link]:
        """Links on a story or task."""
        if parent_kind not in ("story", "task"):
            raise ValueError("parent_kind must be story|task")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM links WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [
            Link(
                id=r["id"],
                parent_kind=r["parent_kind"],
                parent_id=r["parent_id"],
                url=r["url"],
                label=r["label"],
            )
            for r in rows
        ]

    def delete_link(self, link_id: int, actor: str = "human") -> bool:
        """Remove a link and log."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM links WHERE id=?", (link_id,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "link", "delete", f"link #{link_id}")
        return ok

    # -- criteria (S#8 acceptance checklists, advisory only) ---------------
    def add_criteria(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Criterion:
        """Add an acceptance checklist item and log."""
        c = Criterion(id=0, parent_kind=parent_kind, parent_id=parent_id, text=text.strip())
        exists = self.get_story(parent_id) if parent_kind == "story" else self.get_task(parent_id)
        if exists is None:
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO criteria (parent_kind, parent_id, text, done) VALUES (?,?,?,0)",
                (c.parent_kind, c.parent_id, c.text),
            )
            c.id = cur.lastrowid or 0
        self.log(actor, "criteria", "add", f"{parent_kind} #{parent_id}: {c.text[:80]}")
        return c

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]:
        """Checklist items of a story or task."""
        if parent_kind not in ("story", "task"):
            raise ValueError("parent_kind must be story|task")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criteria WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [
            Criterion(
                id=r["id"],
                parent_kind=r["parent_kind"],
                parent_id=r["parent_id"],
                text=r["text"],
                done=bool(r["done"]),
            )
            for r in rows
        ]

    def set_criteria(self, cid: int, done: bool, actor: str = "human") -> Criterion | None:
        """Tick or untick a checklist item and log."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM criteria WHERE id=?", (cid,)).fetchone()
            if r is None:
                return None
            conn.execute("UPDATE criteria SET done=? WHERE id=?", (1 if done else 0, cid))
        self.log(actor, "criteria", "check" if done else "uncheck", f"criteria #{cid}")
        return Criterion(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            text=r["text"],
            done=done,
        )

    def delete_criteria(self, cid: int, actor: str = "human") -> bool:
        """Remove a checklist item and log."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM criteria WHERE id=?", (cid,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "criteria", "delete", f"criteria #{cid}")
        return ok

    def criteria_progress(self, parent_kind: str, parent_id: int) -> tuple[int, int]:
        """Return (done, total) for a parent."""
        items = self.list_criteria(parent_kind, parent_id)
        return sum(1 for c in items if c.done), len(items)

    def open_criteria(self, kind: str, obj_id: int) -> list[Criterion]:
        """Not-done checklist items."""
        return [c for c in self.list_criteria(kind, obj_id) if not c.done]

    # -- risks (S#9 project-level risk register) ---------------------------
    def add_risk(
        self,
        project_id: int,
        title: str,
        likelihood: str = "med",
        impact: str = "med",
        mitigation: str = "",
        actor: str = "human",
    ) -> Risk:
        """Register a project risk and log."""
        r = Risk(
            id=0,
            project_id=project_id,
            title=title.strip(),
            likelihood=likelihood,
            impact=impact,
            mitigation=mitigation,
        )
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise KeyError(f"project #{project_id} not found")
            cur = conn.execute(
                "INSERT INTO risks (project_id, title, likelihood, impact, mitigation, status)"
                " VALUES (?,?,?,?,?,?)",
                (r.project_id, r.title, r.likelihood, r.impact, r.mitigation, r.status.value),
            )
            r.id = cur.lastrowid or 0
        self.log(actor, "risk", "add", f"P#{project_id} risk: {r.title[:80]}")
        return r

    def list_risks(self, project_id: int) -> list[Risk]:
        """Risks sorted likelihood x impact, then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM risks WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
        out = [
            Risk(
                id=r["id"],
                project_id=r["project_id"],
                title=r["title"],
                likelihood=r["likelihood"],
                impact=r["impact"],
                mitigation=r["mitigation"],
                status=RiskStatus(r["status"]),
            )
            for r in rows
        ]
        rank = {"high": 0, "med": 1, "low": 2}
        out.sort(key=lambda x: (rank.get(x.likelihood, 9), rank.get(x.impact, 9), x.id))
        return out

    def set_risk(
        self,
        rid: int,
        status: RiskStatus | None = None,
        mitigation: str | None = None,
        actor: str = "human",
    ) -> Risk | None:
        """Move a risk or set mitigation, then log."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM risks WHERE id=?", (rid,)).fetchone()
            if r is None:
                return None
            risk = Risk(
                id=r["id"],
                project_id=r["project_id"],
                title=r["title"],
                likelihood=r["likelihood"],
                impact=r["impact"],
                mitigation=r["mitigation"],
                status=RiskStatus(r["status"]),
            )
            if status is not None:
                risk.status = status
            if mitigation is not None:
                risk.mitigation = mitigation
            conn.execute(
                "UPDATE risks SET status=?, mitigation=? WHERE id=?",
                (risk.status.value, risk.mitigation, rid),
            )
        self.log(actor, "risk", "edit", f"risk #{rid} -> {risk.status.value}")
        return risk

    # -- milestones (S#4 timeline markers) ----------------------------------
    def add_milestone(
        self, project_id: int, title: str, date: str = "", actor: str = "human"
    ) -> Milestone:
        """Add a timeline marker and log."""
        m = Milestone(id=0, project_id=project_id, title=title.strip(), date=date)
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise KeyError(f"project #{project_id} not found")
            cur = conn.execute(
                "INSERT INTO milestones (project_id, title, date) VALUES (?,?,?)",
                (m.project_id, m.title, m.date),
            )
            m.id = cur.lastrowid or 0
        self.log(actor, "milestone", "add", f"P#{project_id} {m.date}: {m.title[:80]}")
        return m

    def list_milestones(self, project_id: int) -> list[Milestone]:
        """Milestones by date, then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM milestones WHERE project_id=? ORDER BY date, id", (project_id,)
            ).fetchall()
        return [
            Milestone(id=r["id"], project_id=r["project_id"], title=r["title"], date=r["date"])
            for r in rows
        ]

    def delete_milestone(self, mid: int, actor: str = "human") -> bool:
        """Remove a milestone and log."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM milestones WHERE id=?", (mid,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "milestone", "delete", f"milestone #{mid}")
        return ok

    # -- proposals (S#3 agent submit, human approves) -----------------------
    def propose(self, kind: str, parent_id: int, fields: dict, actor: str = "human") -> dict:
        """Queue an agent proposal after validating the parent."""
        if kind not in ("story", "task"):
            raise ValueError("kind must be story|task")
        exists = self.get_project(parent_id) if kind == "story" else self.get_story(parent_id)
        if exists is None:
            raise KeyError(f"parent {kind} #{parent_id} not found")
        title = str(fields.get("title", "")).strip()
        if not title:
            raise ValueError("proposal needs a title")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO proposals (kind, parent_id, payload, actor, status, ts)"
                " VALUES (?,?,?,?, 'pending', ?)",
                (kind, parent_id, json.dumps(fields), _actor(actor), time.time()),
            )
            pid = cur.lastrowid or 0
        self.log(actor, "proposal", "submit", f"proposal #{pid}: {kind} '{title}'")
        return {"id": pid, "kind": kind, "parent_id": parent_id, "status": "pending"}

    def list_proposals(self, status: str | None = None) -> list[dict]:
        """Proposals, optionally filtered by status."""
        with self._connect() as conn:
            if status is None:
                rows = conn.execute("SELECT * FROM proposals ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM proposals WHERE status=? ORDER BY id", (status,)
                ).fetchall()
        return [dict(r) for r in rows]

    def decide_proposal(self, pid: int, approve: bool, actor: str = "human") -> dict | None:
        """Approve (applies the change) or reject a proposal."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if r is None:
                return None
            if r["status"] != "pending":
                raise ValueError(f"proposal #{pid} already {r['status']}")
            fields = json.loads(r["payload"] or "{}")
            result_id = 0
            if approve:
                if r["kind"] == "story":
                    new_obj: UserStory | Task = self.add_story(
                        r["parent_id"],
                        fields.get("title", ""),
                        fields.get("description", ""),
                        fields.get("start_date", ""),
                        fields.get("end_date", ""),
                        owner=fields.get("owner", ""),
                        priority=fields.get("priority", ""),
                        labels=fields.get("labels", ""),
                        estimate=fields.get("estimate", ""),
                        blocked_by=fields.get("blocked_by", ""),
                        actor=actor,
                    )
                else:
                    new_obj = self.add_task(
                        r["parent_id"],
                        fields.get("title", ""),
                        fields.get("estimate", ""),
                        fields.get("start_date", ""),
                        fields.get("end_date", ""),
                        description=fields.get("description", ""),
                        owner=fields.get("owner", ""),
                        priority=fields.get("priority", ""),
                        labels=fields.get("labels", ""),
                        blocked_by=fields.get("blocked_by", ""),
                        actor=actor,
                    )
                result_id = new_obj.id
            conn.execute(
                "UPDATE proposals SET status=?, result_id=? WHERE id=?",
                ("applied" if approve else "rejected", result_id, pid),
            )
        self.log(
            actor,
            "proposal",
            "approved" if approve else "rejected",
            f"proposal #{pid}" + (f" -> {r['kind']} #{result_id}" if approve else ""),
        )
        return {"id": pid, "status": "applied" if approve else "rejected", "result_id": result_id}

    # -- questions (S#3 agent asks, human answers) ---------------------------
    def ask(self, actor: str, question: str) -> dict:
        """Record a question from an agent."""
        if not question.strip():
            raise ValueError("question must not be empty")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO questions (actor, question, status, ts) VALUES (?,?,'open',?)",
                (_actor(actor), question.strip(), time.time()),
            )
            qid = cur.lastrowid or 0
        self.log(actor, "question", "ask", f"Q#{qid}: {question.strip()[:80]}")
        return {"id": qid, "status": "open"}

    def list_questions(self, open_only: bool = True) -> list[dict]:
        """Questions, open only unless asked otherwise."""
        with self._connect() as conn:
            if open_only:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE status='open' ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM questions ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def answer_question(self, qid: int, answer: str, actor: str = "human") -> dict | None:
        """Answer a question and mark it answered."""
        if not answer.strip():
            raise ValueError("answer must not be empty")
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
            if r is None:
                return None
            conn.execute(
                "UPDATE questions SET answer=?, status='answered' WHERE id=?", (answer.strip(), qid)
            )
        self.log(actor, "question", "answer", f"Q#{qid}: {answer.strip()[:80]}")
        return {"id": qid, "status": "answered"}

    # -- export / import (S#5 portability) -----------------------------------
    def export_all(self) -> dict:
        """Full dump: projects with stories/tasks/links/criteria/risks/milestones."""
        projects = []
        for p in self.list_projects():
            stories = []
            for s in self.list_stories(p.id):
                tasks = []
                for t in self.list_tasks(s.id):
                    tasks.append(
                        {
                            "task": _ser(vars(t)),
                            "links": [vars(li) for li in self.list_links("task", t.id)],
                            "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                        }
                    )
                stories.append(
                    {
                        "story": _ser(vars(s)),
                        "links": [vars(li) for li in self.list_links("story", s.id)],
                        "criteria": [vars(c) for c in self.list_criteria("story", s.id)],
                        "tasks": tasks,
                    }
                )
            projects.append(
                {
                    "project": _ser(vars(p)),
                    "stories": stories,
                    "risks": [self._risk_to_dict(r) for r in self.list_risks(p.id)],
                    "milestones": [vars(m) for m in self.list_milestones(p.id)],
                }
            )
        return {"lazyplan": 1, "projects": projects}

    @staticmethod
    def _risk_to_dict(r: Risk) -> dict:
        """Risk with a JSON-safe status value."""
        d = vars(r)
        d["status"] = r.status.value
        return d

    def import_all(self, data: dict, actor: str = "human") -> dict[str, int]:
        """Load an export_all() dump, remapping ids. Preserves statuses,
        criteria ticks, and blocked_by chains. Returns counts."""
        if not isinstance(data, dict) or data.get("lazyplan") != 1:
            raise ValueError("not a lazyplan export (missing lazyplan: 1)")
        counts = {
            "projects": 0,
            "stories": 0,
            "tasks": 0,
            "links": 0,
            "criteria": 0,
            "risks": 0,
            "milestones": 0,
        }
        story_map: dict[int, int] = {}
        task_map: dict[int, int] = {}

        def _apply_status(kind: str, obj_id: int, status: str) -> None:
            if status and status != Status.TODO.value:
                self.set_status(kind, obj_id, Status(status), actor=actor)

        for entry in data.get("projects", []):
            p = entry["project"]
            np = self.add_project(
                p.get("name", "imported"),
                p.get("description", ""),
                p.get("start_date", ""),
                p.get("end_date", ""),
                goal=p.get("goal", ""),
                success_metrics=p.get("success_metrics", ""),
                scope_in=p.get("scope_in", ""),
                scope_out=p.get("scope_out", ""),
                assumptions=p.get("assumptions", ""),
                actor=actor,
            )
            _apply_status("project", np.id, p.get("status", ""))
            counts["projects"] += 1
            for risk in entry.get("risks", []):
                nr = self.add_risk(
                    np.id,
                    risk.get("title", ""),
                    risk.get("likelihood", "med"),
                    risk.get("impact", "med"),
                    risk.get("mitigation", ""),
                    actor=actor,
                )
                if risk.get("status", "open") != "open":
                    self.set_risk(nr.id, status=RiskStatus(risk["status"]), actor=actor)
                counts["risks"] += 1
            for ms in entry.get("milestones", []):
                self.add_milestone(np.id, ms.get("title", ""), ms.get("date", ""), actor=actor)
                counts["milestones"] += 1
            for sentry in entry.get("stories", []):
                sp = sentry["story"]
                ns = self.add_story(
                    np.id,
                    sp.get("title", ""),
                    sp.get("description", ""),
                    sp.get("start_date", ""),
                    sp.get("end_date", ""),
                    owner=sp.get("owner", ""),
                    priority=sp.get("priority", ""),
                    labels=",".join(sp.get("labels", [])),
                    estimate=sp.get("estimate", ""),
                    actor=actor,
                )
                story_map[int(sp.get("id", -1))] = ns.id
                _apply_status("story", ns.id, sp.get("status", ""))
                counts["stories"] += 1
                for li in sentry.get("links", []):
                    self.add_link("story", ns.id, li["url"], li.get("label", ""), actor=actor)
                    counts["links"] += 1
                for c in sentry.get("criteria", []):
                    nc = self.add_criteria("story", ns.id, c.get("text", ""), actor=actor)
                    if c.get("done"):
                        self.set_criteria(nc.id, True, actor=actor)
                    counts["criteria"] += 1
                for tentry in sentry.get("tasks", []):
                    tp = tentry["task"]
                    nt = self.add_task(
                        ns.id,
                        tp.get("title", ""),
                        tp.get("estimate", ""),
                        tp.get("start_date", ""),
                        tp.get("end_date", ""),
                        description=tp.get("description", ""),
                        owner=tp.get("owner", ""),
                        priority=tp.get("priority", ""),
                        labels=",".join(tp.get("labels", [])),
                        actor=actor,
                    )
                    task_map[int(tp.get("id", -1))] = nt.id
                    _apply_status("task", nt.id, tp.get("status", ""))
                    counts["tasks"] += 1
                    for li in tentry.get("links", []):
                        self.add_link("task", nt.id, li["url"], li.get("label", ""), actor=actor)
                        counts["links"] += 1
                    for c in tentry.get("criteria", []):
                        nc = self.add_criteria("task", nt.id, c.get("text", ""), actor=actor)
                        if c.get("done"):
                            self.set_criteria(nc.id, True, actor=actor)
                        counts["criteria"] += 1
        # second pass: re-link blocked_by chains through the id maps
        for entry in data.get("projects", []):
            for sentry in entry.get("stories", []):
                sp = sentry["story"]
                if sp.get("blocked_by") and sp.get("id") in story_map:
                    remapped = [story_map[b] for b in sp["blocked_by"] if b in story_map]
                    if remapped:
                        self.update_story(
                            story_map[sp["id"]],
                            blocked_by=",".join(str(i) for i in remapped),
                            actor=actor,
                        )
                for tentry in sentry.get("tasks", []):
                    tp = tentry["task"]
                    if tp.get("blocked_by") and tp.get("id") in task_map:
                        remapped_t = [task_map[b] for b in tp["blocked_by"] if b in task_map]
                        if remapped_t:
                            self.update_task(
                                task_map[tp["id"]],
                                blocked_by=",".join(str(i) for i in remapped_t),
                                actor=actor,
                            )
        return counts

    def critical_path(self, project_id: int) -> list[int]:
        """Story ids on the longest blocked_by chain (by date span, min 1d).

        Edge b -> s means s is blocked by b (b precedes s). Guards against
        unexpected cycles by treating re-entry as a chain end.
        """
        from datetime import date as _date

        def _dur(s: UserStory) -> int:
            try:
                if s.start_date and s.end_date:
                    lo = _date.fromisoformat(s.start_date)
                    hi = _date.fromisoformat(s.end_date)
                    return max(1, (hi - lo).days + 1)
            except ValueError:
                pass
            return 1

        stories = self.list_stories(project_id)
        in_project = {s.id for s in stories}
        dur = {s.id: _dur(s) for s in stories}
        preds = {s.id: [b for b in s.blocked_by if b in in_project] for s in stories}
        memo: dict[int, tuple[int, list[int]]] = {}

        def longest(n: int, trail: frozenset) -> tuple[int, list[int]]:
            if n in memo:
                return memo[n]
            best = (dur.get(n, 1), [n])
            for p in preds.get(n, []):
                if p in trail:
                    continue
                plen, pchain = longest(p, trail | {n})
                cand = (plen + dur.get(n, 1), pchain + [n])
                if cand[0] > best[0]:
                    best = cand
            memo[n] = best
            return best

        best_path: list[int] = []
        best_len = 0
        for s in stories:
            total, chain = longest(s.id, frozenset())
            if total > best_len:
                best_len, best_path = total, chain
        return best_path if len(best_path) > 1 else []

    def distinct_owners(self) -> list[str]:
        """Sorted non-empty owners across stories and tasks."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT owner FROM stories WHERE owner <> ''"
                " UNION SELECT DISTINCT owner FROM tasks WHERE owner <> ''"
                " ORDER BY 1"
            ).fetchall()
        return [r["owner"] for r in rows]

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lp show`: fields + links + children."""
        if kind == "project":
            p = self.get_project(obj_id)
            if p is None:
                return None
            return {
                "project": _ser(vars(p)),
                "critical": self.critical_path(p.id),
                "risks": [self._risk_to_dict(r) for r in self.list_risks(p.id)],
                "milestones": [vars(m) for m in self.list_milestones(p.id)],
                "stories": [
                    {
                        "story": _ser(vars(s)),
                        "links": [vars(li) for li in self.list_links("story", s.id)],
                        "tasks": [_ser(vars(t)) for t in self.list_tasks(s.id)],
                    }
                    for s in self.list_stories(p.id)
                ],
            }
        if kind == "story":
            s = self.get_story(obj_id)
            if s is None:
                return None
            return {
                "story": _ser(vars(s)),
                "links": [vars(li) for li in self.list_links("story", s.id)],
                "criteria": [vars(c) for c in self.list_criteria("story", s.id)],
                "tasks": [
                    {
                        "task": _ser(vars(t)),
                        "links": [vars(li) for li in self.list_links("task", t.id)],
                        "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                    }
                    for t in self.list_tasks(s.id)
                ],
            }
        if kind == "task":
            t = self.get_task(obj_id)
            if t is None:
                return None
            return {
                "task": _ser(vars(t)),
                "links": [vars(li) for li in self.list_links("task", t.id)],
                "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
            }
        raise ValueError("kind must be project|story|task")

    # -- status --------------------------------------------------------
    def set_status(self, kind: str, obj_id: int, status: Status, actor: str = "human") -> bool:
        """Move a row and log the transition."""
        table = {"project": "projects", "story": "stories", "task": "tasks"}.get(kind)
        if table is None:
            raise ValueError("kind must be project|story|task")
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status.value, obj_id))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        return ok

    def cycle_status(self, kind: str, obj_id: int, actor: str = "human") -> Status | None:
        """Advance todo to doing to done to todo."""
        order = [Status.TODO, Status.DOING, Status.DONE]
        cur = self._current_status(kind, obj_id)
        if cur is None:
            return None
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.set_status(kind, obj_id, nxt, actor=actor)
        return nxt

    def _current_status(self, kind: str, obj_id: int) -> Status | None:
        """Current status value or None."""
        table = {"project": "projects", "story": "stories", "task": "tasks"}.get(kind)
        if table is None:
            raise ValueError("kind must be project|story|task")
        with self._connect() as conn:
            r = conn.execute(f"SELECT status FROM {table} WHERE id=?", (obj_id,)).fetchone()
        return Status(r["status"]) if r else None

    # -- tree for TUI --------------------------------------------------
    def tree(
        self,
        status: Status | None = None,
        project_id: int | None = None,
        owner: str | None = None,
        priority: str | None = None,
    ) -> list[tuple[Project, list[tuple[UserStory, list[Task]]]]]:
        """Nested projects, stories, and tasks with filters."""
        out = []
        for p in self.list_projects():
            if project_id is not None and p.id != project_id:
                continue
            stories = []
            for s in self.list_stories(p.id):
                tasks = self.list_tasks(s.id)
                if owner is not None:
                    tasks = [t for t in tasks if t.owner == owner]
                    if s.owner != owner and not tasks:
                        continue
                if priority is not None:
                    tasks = [t for t in tasks if t.priority == priority]
                    if s.priority != priority and not tasks:
                        continue
                if status is not None:
                    tasks = [t for t in tasks if t.status == status]
                    if s.status != status and not tasks:
                        continue
                stories.append((s, tasks))
            if status is not None and p.status != status and not stories:
                continue
            if owner is not None and not stories:
                continue
            if priority is not None and not stories:
                continue
            out.append((p, stories))
        return out

    def counts(self) -> dict[str, int]:
        """Project, story, and task totals."""
        with self._connect() as conn:
            np = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
            ns = conn.execute("SELECT COUNT(*) c FROM stories").fetchone()["c"]
            nt = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
            nd = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"]
        return {"projects": np, "stories": ns, "tasks": nt, "tasks_done": nd}
