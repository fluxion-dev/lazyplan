"""Human documentation text shared by the doc-contract tests."""

from __future__ import annotations

from tests.support.paths import ROOT


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


README = _read("README.md")
USAGE = _read("docs/usage.md")
MAN = _read("docs/lpui.1").replace("\\-", "-").replace("\\.", ".")
