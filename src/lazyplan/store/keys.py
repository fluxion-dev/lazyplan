"""Stable document keys for idempotent plan apply."""

from __future__ import annotations

from ..core.kinds import check_kind
from .base import StoreBase


class KeysMixin(StoreBase):
    """Map a document key to one row per kind."""

    def set_entity_key(self, kind: str, row_id: int, key: str, actor: str = "human") -> None:
        """Attach a stable key to one row; re-setting the same pair is a no-op."""
        del actor
        check_kind(kind)
        text = key.strip()
        if not text:
            raise ValueError("entity key must not be empty")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT row_id FROM entity_keys WHERE kind=? AND key=?", (kind, text)
            ).fetchone()
            if existing is not None:
                if int(existing["row_id"]) == row_id:
                    return
                raise ValueError(f"{kind} key {text!r} already belongs to #{existing['row_id']}")
            current = conn.execute(
                "SELECT key FROM entity_keys WHERE kind=? AND row_id=?", (kind, row_id)
            ).fetchone()
            if current is not None:
                raise ValueError(f"{kind} #{row_id} already has key {current['key']!r}")
            conn.execute(
                "INSERT INTO entity_keys (kind, key, row_id) VALUES (?,?,?)",
                (kind, text, row_id),
            )

    def get_entity_key(self, kind: str, key: str) -> int | None:
        """Row id for a stable key, or None."""
        check_kind(kind)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT row_id FROM entity_keys WHERE kind=? AND key=?",
                (kind, key.strip()),
            ).fetchone()
        return int(row["row_id"]) if row is not None else None
