"""External reference actions: link and unlink a plan pointer."""

from __future__ import annotations

from ... import services
from .context import ContextMixin
from .screens import FilterPromptScreen, RefScreen


class ReferenceMixin(ContextMixin):
    """Manage read-only pointers from the selected plan to external work."""

    def action_link_ref(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (references are plan scope)")
            return

        def cb(data: dict[str, str] | None) -> None:
            if not data:
                return
            url = data.get("url", "").strip()
            if not url:
                self.notify("a reference needs a URL", timeout=3)
                return
            kind = data.get("kind", "").strip() or "issue"
            try:
                ref = services.link_ref(
                    self.store,
                    plan_id,
                    url,
                    kind=kind,
                    title=data.get("title", ""),
                    actor="tui",
                )
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            self._record_override("ref link", f"P{plan_id}", url)
            self.notify(f"linked {ref.provider}/{ref.kind} to P{plan_id}", timeout=4)
            self._saved("reference linked")

        self.push_screen(
            RefScreen({"kind": "issue"}, context=f"P{plan_id}"),
            cb,
        )

    def action_unlink_ref(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (references are plan scope)")
            return

        def cb(text: str | None) -> None:
            if not text:
                return
            try:
                ref_id = int(text)
            except ValueError:
                removed = services.unlink_ref(self.store, plan_id, url=text, actor="tui")
            else:
                removed = services.unlink_ref(self.store, plan_id, ref_id=ref_id, actor="tui")
            if not removed:
                self.notify("no matching reference", timeout=4)
                return
            self._record_override("ref unlink", f"P{plan_id}", text)
            self.notify(f"unlinked reference from P{plan_id}", timeout=4)
            self._saved("reference unlinked")

        self.push_screen(
            FilterPromptScreen(
                title=f"Unlink a reference from P{plan_id} (id or URL)",
                placeholder="reference id or URL",
                submit_label="Unlink",
            ),
            cb,
        )
