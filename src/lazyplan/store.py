"""SQLite persistence. Stdlib only. Shared by TUI and `lpui` CLI (agent ingress)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from .models import (
    CRITERION_PARENTS,
    DEFAULT_TASK_PRIORITY,
    PRIORITY_RANK,
    Criterion,
    Project,
    Status,
    Task,
    UserStory,
    check_priority,
)
from .repo import ensure_plan_dir, resolve_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    goal TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('project', 'story', 'task')),
    parent_id INTEGER NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_criteria_parent ON criteria(parent_kind, parent_id);
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
    "projects": ("goal", "priority"),
}


def default_db_path() -> Path:
    """Resolved default DB: $LAZYPLAN_DB > enclosing repo `.plan/` > global."""
    return resolve_db_path()


def _ser(d: dict) -> dict:
    """JSON/agent-safe: Status -> value."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    return d


def _actor(explicit: str = "") -> str:
    """Normalize an actor name, defaulting to $USER or human."""
    if explicit.strip():
        return explicit.strip()[:64]
    return (os.environ.get("USER", "") or "human")[:64]


def _migrate_criteria(conn: sqlite3.Connection) -> None:
    """Allow criteria on projects: rebuild pre-simplification tables whose
    CHECK constraint only permits story|task."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='criteria'"
    ).fetchone()
    if row is None or row["sql"] is None:
        return
    if "'project'" in row["sql"]:
        return
    conn.execute("ALTER TABLE criteria RENAME TO criteria_old")
    conn.execute(
        """
        CREATE TABLE criteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_kind TEXT NOT NULL CHECK (parent_kind IN ('project', 'story', 'task')),
            parent_id INTEGER NOT NULL,
            text TEXT NOT NULL CHECK (trim(text) <> ''),
            done INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO criteria (id, parent_kind, parent_id, text, done)"
        " SELECT id, parent_kind, parent_id, text, done FROM criteria_old"
    )
    conn.execute("DROP TABLE criteria_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_criteria_parent ON criteria(parent_kind, parent_id)"
    )


class Store:
    """SQLite persistence shared by the TUI and the lpui CLI."""

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
            _migrate_criteria(conn)

    def _connect(self) -> sqlite3.Connection:
        """Open a row-factory connection with foreign keys on."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -- events (agent feed) -------------------------------------------
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
        """Conflict-safe poll key: mtime + row counts + max ids."""
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
            mc = conn.execute("SELECT COALESCE(MAX(id),0) m FROM criteria").fetchone()["m"]
        return (mtime, c["projects"], c["stories"], c["tasks"], mp, ms, mt, me, mc)

    # -- projects ------------------------------------------------------
    def add_project(
        self,
        name: str,
        description: str = "",
        goal: str = "",
        priority: str = "",
        actor: str = "human",
    ) -> Project:
        """Insert a project and log the event."""
        p = Project(
            id=0,
            name=name.strip(),
            description=description,
            goal=goal,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, description, status, goal, priority)"
                " VALUES (?,?,?,?,?)",
                (p.name, p.description, p.status.value, p.goal, p.priority),
            )
            p.id = cur.lastrowid or 0
        self.log(actor, "project", "add", f"P#{p.id} {p.name}")
        return p

    @staticmethod
    def _opt(r: sqlite3.Row, keys: set[str], name: str) -> str:
        """Optional text column, tolerant of legacy tables missing it."""
        return r[name] if name in keys and r[name] else ""

    def _row_to_project(self, r: sqlite3.Row) -> Project:
        """Row to Project (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return Project(
            id=r["id"],
            name=r["name"],
            description=self._opt(r, keys, "description"),
            status=Status(r["status"]) if "status" in keys else Status.TODO,
            goal=self._opt(r, keys, "goal"),
            priority=self._opt(r, keys, "priority"),
        )

    def get_project(self, pid: int) -> Project | None:
        """Fetch a project by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return self._row_to_project(r) if r is not None else None

    def list_projects(self) -> list[Project]:
        """All projects, newest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        return [self._row_to_project(r) for r in rows]

    def update_project(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        priority: str | None = None,
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
        if goal is not None:
            p.goal = goal
        if priority is not None:
            p.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name=?, description=?, goal=?, priority=? WHERE id=?",
                (p.name, p.description, p.goal, p.priority, pid),
            )
        self.log(actor, "project", "edit", f"P#{pid} {p.name}")
        return p

    # -- stories -------------------------------------------------------
    def add_story(
        self,
        project_id: int,
        title: str,
        description: str = "",
        priority: str = "",
        actor: str = "human",
    ) -> UserStory:
        """Insert a story and log the event."""
        s = UserStory(
            id=0,
            project_id=project_id,
            title=title.strip(),
            description=description,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise KeyError(f"project #{project_id} not found")
            cur = conn.execute(
                "INSERT INTO stories (project_id, title, description, status, priority)"
                " VALUES (?,?,?,?,?)",
                (s.project_id, s.title, s.description, s.status.value, s.priority),
            )
            s.id = cur.lastrowid or 0
        self.log(actor, "story", "add", f"S#{s.id} {s.title}")
        return s

    def _row_to_story(self, r: sqlite3.Row) -> UserStory:
        """Row to UserStory (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return UserStory(
            id=r["id"],
            project_id=r["project_id"],
            title=r["title"],
            description=self._opt(r, keys, "description"),
            status=Status(r["status"]) if "status" in keys else Status.TODO,
            priority=self._opt(r, keys, "priority"),
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
        priority: str | None = None,
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
        if priority is not None:
            s.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE stories SET title=?, description=?, priority=? WHERE id=?",
                (s.title, s.description, s.priority, sid),
            )
        self.log(actor, "story", "edit", f"S#{sid} {s.title}")
        return s

    # -- tasks ---------------------------------------------------------
    def add_task(
        self,
        story_id: int,
        title: str,
        description: str = "",
        priority: str = DEFAULT_TASK_PRIORITY,
        actor: str = "human",
    ) -> Task:
        """Insert a task and log the event."""
        t = Task(
            id=0,
            story_id=story_id,
            title=title.strip(),
            description=description,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)).fetchone() is None:
                raise KeyError(f"story #{story_id} not found")
            cur = conn.execute(
                "INSERT INTO tasks (story_id, title, status, description, priority)"
                " VALUES (?,?,?,?,?)",
                (t.story_id, t.title, t.status.value, t.description, t.priority),
            )
            t.id = cur.lastrowid or 0
        self.log(actor, "task", "add", f"T#{t.id} {t.title}")
        return t

    def _row_to_task(self, r: sqlite3.Row) -> Task:
        """Row to Task (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return Task(
            id=r["id"],
            story_id=r["story_id"],
            title=r["title"],
            status=Status(r["status"]) if "status" in keys else Status.TODO,
            description=self._opt(r, keys, "description"),
            priority=self._opt(r, keys, "priority"),
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
        description: str | None = None,
        priority: str | None = None,
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
        if description is not None:
            t.description = description
        if priority is not None:
            t.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET title=?, description=?, priority=? WHERE id=?",
                (t.title, t.description, t.priority, tid),
            )
        self.log(actor, "task", "edit", f"T#{tid} {t.title}")
        return t

    def delete(self, kind: str, obj_id: int, actor: str = "human") -> bool:
        """Delete a row and its subtree (criteria purged manually; FK cascades the rest)."""
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
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='project' AND parent_id=?", (obj_id,)
                )
                for sid in sids:
                    self._delete_story_criteria(conn, sid)
            elif kind == "story":
                self._delete_story_criteria(conn, obj_id)
            else:
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
            cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (obj_id,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, kind, "delete", f"{kind} #{obj_id}")
        return ok

    @staticmethod
    def _delete_story_criteria(conn: sqlite3.Connection, story_id: int) -> None:
        """Remove criteria under a story and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute("SELECT id FROM tasks WHERE story_id=?", (story_id,)).fetchall()
        ]
        conn.execute("DELETE FROM criteria WHERE parent_kind='story' AND parent_id=?", (story_id,))
        for tid in tids:
            conn.execute("DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (tid,))

    # -- criteria (acceptance checklists, advisory only) -----------------
    def _parent_exists(self, parent_kind: str, parent_id: int) -> bool:
        """True when the criteria parent row exists."""
        if parent_kind == "project":
            return self.get_project(parent_id) is not None
        if parent_kind == "story":
            return self.get_story(parent_id) is not None
        return self.get_task(parent_id) is not None

    def add_criteria(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Criterion:
        """Add an acceptance checklist item and log."""
        c = Criterion(id=0, parent_kind=parent_kind, parent_id=parent_id, text=text.strip())
        if not self._parent_exists(parent_kind, parent_id):
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
        """Checklist items of a project, story, or task."""
        if parent_kind not in CRITERION_PARENTS:
            raise ValueError("parent_kind must be project|story|task")
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

    def get_parent(self, kind: str, obj_id: int) -> Project | UserStory | Task | None:
        """Fetch any row by kind (criteria parent lookup)."""
        if kind == "project":
            return self.get_project(obj_id)
        if kind == "story":
            return self.get_story(obj_id)
        if kind == "task":
            return self.get_task(obj_id)
        raise ValueError("kind must be project|story|task")

    # -- export / import (portability) -----------------------------------
    def export_all(self) -> dict:
        """Full dump: projects (with criteria) holding stories and tasks."""
        projects = []
        for p in self.list_projects():
            stories = []
            for s in self.list_stories(p.id):
                tasks = []
                for t in self.list_tasks(s.id):
                    tasks.append(
                        {
                            "task": _ser(vars(t)),
                            "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                        }
                    )
                stories.append(
                    {
                        "story": _ser(vars(s)),
                        "criteria": [vars(c) for c in self.list_criteria("story", s.id)],
                        "tasks": tasks,
                    }
                )
            projects.append(
                {
                    "project": _ser(vars(p)),
                    "criteria": [vars(c) for c in self.list_criteria("project", p.id)],
                    "stories": stories,
                }
            )
        return {"lazyplan": 1, "projects": projects}

    def import_all(self, data: dict, actor: str = "human") -> dict[str, int]:
        """Load an export_all() dump. Returns counts."""
        if not isinstance(data, dict) or data.get("lazyplan") != 1:
            raise ValueError("not a lazyplan export (missing lazyplan: 1)")
        counts = {"projects": 0, "stories": 0, "tasks": 0, "criteria": 0}

        def _apply_status(kind: str, obj_id: int, status: str) -> None:
            if status and status != Status.TODO.value:
                self.set_status(kind, obj_id, Status(status), actor=actor)

        def _import_criteria(kind: str, obj_id: int, items: list) -> None:
            for c in items:
                nc = self.add_criteria(kind, obj_id, c.get("text", ""), actor=actor)
                if c.get("done"):
                    self.set_criteria(nc.id, True, actor=actor)
                counts["criteria"] += 1

        for entry in data.get("projects", []):
            p = entry["project"]
            np = self.add_project(
                p.get("name", p.get("title", "imported")),
                p.get("description", ""),
                goal=p.get("goal", ""),
                priority=p.get("priority", ""),
                actor=actor,
            )
            _apply_status("project", np.id, p.get("status", ""))
            counts["projects"] += 1
            _import_criteria("project", np.id, entry.get("criteria", []))
            for sentry in entry.get("stories", []):
                sp = sentry["story"]
                ns = self.add_story(
                    np.id,
                    sp.get("title", ""),
                    sp.get("description", ""),
                    priority=sp.get("priority", ""),
                    actor=actor,
                )
                _apply_status("story", ns.id, sp.get("status", ""))
                counts["stories"] += 1
                _import_criteria("story", ns.id, sentry.get("criteria", []))
                for tentry in sentry.get("tasks", []):
                    tp = tentry["task"]
                    nt = self.add_task(
                        ns.id,
                        tp.get("title", ""),
                        description=tp.get("description", ""),
                        priority=tp.get("priority", ""),
                        actor=actor,
                    )
                    _apply_status("task", nt.id, tp.get("status", ""))
                    counts["tasks"] += 1
                    _import_criteria("task", nt.id, tentry.get("criteria", []))
            # Stories landed after the project's own status: recompute it.
            self._heal("project", np.id, actor)
        return counts

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lpui show`: fields + criteria + children."""
        if kind == "project":
            p = self.get_project(obj_id)
            if p is None:
                return None
            return {
                "project": _ser(vars(p)),
                "criteria": [vars(c) for c in self.list_criteria("project", p.id)],
                "stories": [
                    {
                        "story": _ser(vars(s)),
                        "criteria": [vars(c) for c in self.list_criteria("story", s.id)],
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
                "criteria": [vars(c) for c in self.list_criteria("story", s.id)],
                "tasks": [
                    {
                        "task": _ser(vars(t)),
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
                "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
            }
        raise ValueError("kind must be project|story|task")

    # -- archive (day-old done hides; computed from status history) -----
    ARCHIVE_AFTER_SECS = 24 * 3600

    @staticmethod
    def _last_status_change(
        conn: sqlite3.Connection, kind: str, obj_id: int
    ) -> tuple[float, str] | None:
        """Latest (ts, target) status move for one row, parsed from the event log."""
        rows = conn.execute(
            "SELECT ts, detail FROM events WHERE kind=? AND action='status' ORDER BY id DESC",
            (kind,),
        ).fetchall()
        prefix = f"{kind} #{obj_id} -> "
        for r in rows:
            detail = r["detail"].removesuffix(" (rollup)")
            if detail.startswith(prefix):
                return (r["ts"], detail[len(prefix) :])
        return None

    def is_archived(self, project: Project) -> bool:
        """Done longer than a day, with history to prove it. No proof: never hide."""
        if project.status != Status.DONE:
            return False
        with self._connect() as conn:
            last = self._last_status_change(conn, "project", project.id)
        if last is None:
            return False
        ts, target = last
        return target == Status.DONE.value and (time.time() - ts) > self.ARCHIVE_AFTER_SECS

    @staticmethod
    def _rollup_target(statuses: list[Status]) -> Status:
        """Parent state from children: all done -> done, any doing -> doing, else todo."""
        if all(s == Status.DONE for s in statuses):
            return Status.DONE
        if any(s == Status.DOING for s in statuses):
            return Status.DOING
        return Status.TODO

    def _heal(self, kind: str, obj_id: int, actor: str) -> bool:
        """Recompute one story/project from its children. Returns changed."""
        if kind == "story":
            obj: Project | UserStory | None = self.get_story(obj_id)
            kids = [t.status for t in self.list_tasks(obj_id)] if obj is not None else []
            table = "stories"
        elif kind == "project":
            obj = self.get_project(obj_id)
            kids = [s.status for s in self.list_stories(obj_id)] if obj is not None else []
            table = "projects"
        else:
            raise ValueError("kind must be story|project")
        if obj is None or not kids:
            return False
        target = self._rollup_target(kids)
        if obj.status == target:
            return False
        with self._connect() as conn:
            conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (target.value, obj_id))
        self.log(actor, kind, "status", f"{kind} #{obj_id} -> {target.value} (rollup)")
        return True

    def _heal_parent(self, kind: str, obj_id: int, actor: str) -> None:
        """Recompute ancestors after a status write; childless rows keep manual status."""
        if kind == "task":
            t = self.get_task(obj_id)
            if t is None:
                return
            self._heal("story", t.story_id, actor)
            s = self.get_story(t.story_id)
            if s is not None:
                self._heal("project", s.project_id, actor)
        elif kind == "story":
            self._heal("story", obj_id, actor)
            s = self.get_story(obj_id)
            if s is not None:
                self._heal("project", s.project_id, actor)
        elif kind == "project":
            self._heal("project", obj_id, actor)

    def reconcile(self, actor: str = "human") -> list[dict]:
        """Recompute every parent from its children; childless rows untouched."""
        changes: list[dict] = []
        for p in self.list_projects():
            before_p = p.status
            for s in self.list_stories(p.id):
                before = s.status
                self._heal("story", s.id, actor)
                after = self.get_story(s.id)
                if after is not None and after.status != before:
                    changes.append({"kind": "story", "id": s.id, "to": after.status.value})
            self._heal("project", p.id, actor)
            after_p = self.get_project(p.id)
            if after_p is not None and after_p.status != before_p:
                changes.append({"kind": "project", "id": p.id, "to": after_p.status.value})
        return changes

    # -- status --------------------------------------------------------
    def set_status(self, kind: str, obj_id: int, status: Status, actor: str = "human") -> bool:
        """Move a row, heal the subtree state, and log the transition."""
        table = {"project": "projects", "story": "stories", "task": "tasks"}.get(kind)
        if table is None:
            raise ValueError("kind must be project|story|task")
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status.value, obj_id))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
            self._heal_parent(kind, obj_id, actor)
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
        priority: str | None = None,
        archived: str = "hide",
    ) -> list[tuple[Project, list[tuple[UserStory, list[Task]]]]]:
        """Nested projects, stories, and tasks with filters.

        archived: "hide" (default views), "only" (--archived), "show" (--status all).
        """
        if archived not in ("hide", "only", "show"):
            raise ValueError("archived must be hide|only|show")
        out = []
        for p in self.list_projects():
            if project_id is not None and p.id != project_id:
                continue
            arch = self.is_archived(p)
            if archived == "only" and not arch:
                continue
            if archived == "hide" and arch:
                continue
            stories = []
            for s in self.list_stories(p.id):
                tasks = self.list_tasks(s.id)
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
            if priority is not None and p.priority != priority and not stories:
                continue
            out.append((p, stories))
        return out

    def counts(self) -> dict[str, int]:
        """Project, story, and task totals, plus per-state project counts."""
        with self._connect() as conn:
            np = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
            ns = conn.execute("SELECT COUNT(*) c FROM stories").fetchone()["c"]
            nt = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
            nd = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"]
            npt = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='todo'").fetchone()[
                "c"
            ]
            npd = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='doing'").fetchone()[
                "c"
            ]
            npn = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='done'").fetchone()[
                "c"
            ]
        return {
            "projects": np,
            "stories": ns,
            "tasks": nt,
            "tasks_done": nd,
            "projects_todo": npt,
            "projects_doing": npd,
            "projects_done": npn,
        }
