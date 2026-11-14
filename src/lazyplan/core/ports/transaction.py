"""The transaction scope shared by read and write surfaces."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol


class TransactionPort(Protocol):
    """One scoped connection that nested reads join."""

    def transaction(self) -> AbstractContextManager[None]: ...
