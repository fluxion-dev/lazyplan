"""Store methods for links."""

from __future__ import annotations

import sqlite3

from ..kinds import check_parent_kind
from ..models import (
    ForgeLink,
    VcsLink,
)
from .base import (
    StoreBase,
    _files_json,
    _files_tuple,
)


class LinksMixin(StoreBase):
    """Links persistence."""

    @staticmethod
    def _row_to_link(r: sqlite3.Row) -> VcsLink:
        """Row to VcsLink."""
        return VcsLink(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            sha=r["sha"],
            subject=r["subject"] or "",
            author=r["author"] or "",
            timestamp=int(r["timestamp"] or 0),
            repo_root=r["repo_root"] or "",
            files=_files_tuple(r["files"] or "") if "files" in r.keys() else (),
            stale=bool(r["stale"]) if "stale" in r.keys() else False,
            checked_at=int(r["checked_at"] or 0) if "checked_at" in r.keys() else 0,
        )

    def link_commit(
        self,
        parent_kind: str,
        parent_id: int,
        sha: str,
        subject: str = "",
        author: str = "",
        timestamp: int = 0,
        repo_root: str = "",
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink:
        """Attach a commit to a plan, milestone, or task (idempotent on re-link)."""
        link = VcsLink(
            id=0,
            parent_kind=parent_kind,
            parent_id=parent_id,
            sha=sha,
            subject=subject,
            author=author,
            timestamp=timestamp,
            repo_root=repo_root,
            files=files,
        )
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        files_json = _files_json(files)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO vcs_links"
                " (parent_kind, parent_id, sha, subject, author, timestamp, repo_root, files)"
                " VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(parent_kind, parent_id, sha) DO UPDATE SET"
                " subject=CASE WHEN excluded.subject <> '' THEN excluded.subject ELSE subject END,"
                " author=CASE WHEN excluded.author <> '' THEN excluded.author ELSE author END,"
                " timestamp=CASE WHEN excluded.timestamp > 0 THEN excluded.timestamp ELSE timestamp END,"
                " repo_root=CASE WHEN excluded.repo_root <> '' THEN excluded.repo_root ELSE repo_root END,"
                " files=CASE WHEN excluded.files <> '[]' THEN excluded.files ELSE files END",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.sha,
                    link.subject,
                    link.author,
                    link.timestamp,
                    link.repo_root,
                    files_json,
                ),
            )
            r = conn.execute(
                "SELECT * FROM vcs_links WHERE parent_kind=? AND parent_id=? AND sha=?",
                (link.parent_kind, link.parent_id, link.sha),
            ).fetchone()
            assert r is not None
            link = self._row_to_link(r)
        self.log(actor, "vcs", "link", f"{parent_kind} #{parent_id}: {link.sha[:12]}")
        return link

    def update_link(
        self,
        link_id: int,
        *,
        subject: str,
        author: str,
        timestamp: int,
        repo_root: str,
        stale: bool,
        checked_at: int,
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink | None:
        """Refresh one link's cached metadata, files, and stale flag; None when gone."""
        files_json = _files_json(files)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE vcs_links SET subject=?, author=?, timestamp=?, repo_root=?,"
                " files=CASE WHEN ? <> '[]' THEN ? ELSE files END,"
                " stale=?, checked_at=? WHERE id=?",
                (
                    subject,
                    author,
                    timestamp,
                    repo_root,
                    files_json,
                    files_json,
                    1 if stale else 0,
                    checked_at,
                    link_id,
                ),
            )
            if (cur.rowcount or 0) == 0:
                return None
            r = conn.execute("SELECT * FROM vcs_links WHERE id=?", (link_id,)).fetchone()
        if r is None:
            return None
        link = self._row_to_link(r)
        state = "stale" if link.stale else "ok"
        self.log(actor, "vcs", "refresh", f"link #{link_id}: {state}")
        return link

    def unlink_commit(
        self, parent_kind: str, parent_id: int, sha: str, actor: str = "human"
    ) -> bool:
        """Detach a commit; True when a row was removed."""
        check_parent_kind(parent_kind)
        norm = sha.strip().lower()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM vcs_links WHERE parent_kind=? AND parent_id=? AND sha=?",
                (parent_kind, parent_id, norm),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "vcs", "unlink", f"{parent_kind} #{parent_id}: {norm[:12]}")
        return ok

    def list_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        """Commits attached to a plan, milestone, or task, oldest first."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vcs_links WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [self._row_to_link(r) for r in rows]

    def links_for_sha(self, sha: str) -> list[VcsLink]:
        """Every link pointing at one commit, oldest first."""
        norm = sha.strip().lower()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vcs_links WHERE sha=? ORDER BY id",
                (norm,),
            ).fetchall()
        return [self._row_to_link(r) for r in rows]

    @staticmethod
    def _row_to_forge_link(r: sqlite3.Row) -> ForgeLink:
        """Row to ForgeLink."""
        return ForgeLink(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            provider=r["provider"] or "github",
            kind=r["kind"] or "pull",
            number=int(r["number"] or 0),
            url=r["url"] or "",
            title=r["title"] or "",
            state=r["state"] or "",
            checks=r["checks"] or "",
            reviews=r["reviews"] or "",
            author=r["author"] or "",
            base_ref=r["base_ref"] or "",
            head_ref=r["head_ref"] or "",
            merged_at=r["merged_at"] or "",
            merge_commit_sha=r["merge_commit_sha"] or "",
            updated_at=int(r["updated_at"] or 0),
            stale=bool(r["stale"]) if "stale" in r.keys() else False,
            payload=r["payload"] or "",
        )

    def link_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        url: str = "",
        title: str = "",
        state: str = "",
        checks: str = "",
        reviews: str = "",
        author: str = "",
        base_ref: str = "",
        head_ref: str = "",
        merged_at: str = "",
        merge_commit_sha: str = "",
        updated_at: int = 0,
        stale: bool = False,
        payload: str = "",
        actor: str = "human",
    ) -> ForgeLink:
        """Attach a pull request/issue to a row, refreshing its cached fields."""
        check_parent_kind(parent_kind)
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        link = ForgeLink(
            id=0,
            parent_kind=parent_kind,
            parent_id=parent_id,
            provider=provider,
            kind=kind,
            number=int(number),
            url=url,
            title=title,
            state=state,
            checks=checks,
            reviews=reviews,
            author=author,
            base_ref=base_ref,
            head_ref=head_ref,
            merged_at=merged_at,
            merge_commit_sha=merge_commit_sha,
            updated_at=updated_at,
            stale=stale,
            payload=payload,
        )
        existing_state = ""
        existing_checks = ""
        existing_reviews = ""
        existing_merged = ""
        existed = False
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT state, checks, reviews, merged_at FROM forge_links"
                " WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                ),
            ).fetchone()
            if existing is not None:
                existed = True
                existing_state = str(existing["state"] or "")
                existing_checks = str(existing["checks"] or "")
                existing_reviews = str(existing["reviews"] or "")
                existing_merged = str(existing["merged_at"] or "")
            conn.execute(
                "INSERT INTO forge_links"
                " (parent_kind, parent_id, provider, kind, number, url, title, state,"
                " checks, reviews, author, base_ref, head_ref, merged_at,"
                " merge_commit_sha, updated_at, stale, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(parent_kind, parent_id, provider, kind, number)"
                " DO UPDATE SET url=excluded.url, title=excluded.title,"
                " state=excluded.state, checks=excluded.checks,"
                " reviews=excluded.reviews, author=excluded.author,"
                " base_ref=excluded.base_ref, head_ref=excluded.head_ref,"
                " merged_at=excluded.merged_at,"
                " merge_commit_sha=excluded.merge_commit_sha,"
                " updated_at=excluded.updated_at, stale=excluded.stale,"
                " payload=excluded.payload",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                    link.url,
                    link.title,
                    link.state,
                    link.checks,
                    link.reviews,
                    link.author,
                    link.base_ref,
                    link.head_ref,
                    link.merged_at,
                    link.merge_commit_sha,
                    link.updated_at,
                    1 if link.stale else 0,
                    link.payload,
                ),
            )
            r = conn.execute(
                "SELECT * FROM forge_links WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                ),
            ).fetchone()
            assert r is not None
            link = self._row_to_forge_link(r)
        if not existed:
            self.log(
                actor,
                "forge",
                "link",
                f"{link.kind} #{link.number} -> {parent_kind} #{parent_id}",
            )
        elif (
            existing_state != link.state
            or existing_checks != link.checks
            or existing_reviews != link.reviews
            or existing_merged != link.merged_at
        ):
            self.log(
                actor,
                "forge",
                "state",
                f"{link.kind} #{link.number}: {existing_state or 'unknown'} ->"
                f" {link.state or 'unknown'}",
            )
        return link

    def unlink_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        actor: str = "human",
    ) -> bool:
        """Detach one forge link; True when a row was removed."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM forge_links WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (parent_kind, parent_id, provider, kind, int(number)),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "forge", "unlink", f"{kind} #{number} -> {parent_kind} #{parent_id}")
        return ok

    def list_forge_links(
        self,
        parent_kind: str,
        parent_id: int,
        kind: str = "",
    ) -> list[ForgeLink]:
        """Forge links on one row, oldest first (optionally one kind)."""
        check_parent_kind(parent_kind)
        sql = "SELECT * FROM forge_links WHERE parent_kind=? AND parent_id=?"
        params: list[object] = [parent_kind, parent_id]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_forge_link(r) for r in rows]

    def effective_forge_links(
        self,
        parent_kind: str,
        parent_id: int,
        kind: str = "",
    ) -> list[ForgeLink]:
        """Direct forge links plus descendant links, deduped by identity."""
        check_parent_kind(parent_kind)
        links = list(self.list_forge_links(parent_kind, parent_id, kind))
        if parent_kind == "milestone":
            for task in self.list_tasks(parent_id):
                links.extend(self.list_forge_links("task", task.id, kind))
        elif parent_kind == "plan":
            for milestone in self.list_milestones(parent_id):
                links.extend(self.list_forge_links("milestone", milestone.id, kind))
                for task in self.list_tasks(milestone.id):
                    links.extend(self.list_forge_links("task", task.id, kind))
        seen: set[tuple[str, str, int]] = set()
        out: list[ForgeLink] = []
        for link in links:
            key = (link.provider, link.kind, link.number)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def forge_links_map(self) -> dict[tuple[str, int], list[ForgeLink]]:
        """Every forge link grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM forge_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[ForgeLink]] = {}
        for row in rows:
            link = self._row_to_forge_link(row)
            out.setdefault((link.parent_kind, link.parent_id), []).append(link)
        return out

    def vcs_links_map(self) -> dict[tuple[str, int], list[VcsLink]]:
        """Every commit link grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vcs_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[VcsLink]] = {}
        for row in rows:
            link = self._row_to_link(row)
            out.setdefault((link.parent_kind, link.parent_id), []).append(link)
        return out

    def cache_get(self, key: str) -> dict | None:
        """Cached HTTP entry by key, or None."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM forge_cache WHERE key=?", (key,)).fetchone()
        return dict(r) if r is not None else None

    def cache_put(self, key: str, etag: str, fetched_at: int, payload: str) -> None:
        """Store or replace one cached HTTP response."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO forge_cache (key, etag, fetched_at, payload)"
                " VALUES (?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET etag=excluded.etag,"
                " fetched_at=excluded.fetched_at, payload=excluded.payload",
                (key, etag, int(fetched_at), payload),
            )

    def effective_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        """Direct links plus descendants, deduped by SHA and checkout.

        Plans include their milestones and tasks; milestones include their
        tasks. Direct links stay first, then child links in creation order.
        """
        check_parent_kind(parent_kind)
        links = list(self.list_links(parent_kind, parent_id))
        if parent_kind == "milestone":
            for task in self.list_tasks(parent_id):
                links.extend(self.list_links("task", task.id))
        elif parent_kind == "plan":
            for milestone in self.list_milestones(parent_id):
                links.extend(self.list_links("milestone", milestone.id))
                for task in self.list_tasks(milestone.id):
                    links.extend(self.list_links("task", task.id))
        seen: set[tuple[str, str]] = set()
        out: list[VcsLink] = []
        for link in links:
            key = (link.sha, link.repo_root)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out
