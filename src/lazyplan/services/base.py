"""Shared service types."""

from __future__ import annotations


class GateError(RuntimeError):
    """A completion gate rejected the finish."""
