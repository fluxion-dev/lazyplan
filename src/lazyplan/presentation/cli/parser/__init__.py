"""Argument parsing for the lpui CLI."""

from .builder import build_parser
from .common import package_version

__all__ = ["build_parser", "package_version"]
