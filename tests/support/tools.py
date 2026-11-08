"""Load repo tool scripts by file name."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

from tests.support.paths import ROOT


def load_tool(script: str) -> ModuleType:
    """Import ``tools/<script>.py`` under a stable module name."""
    name = script.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{script}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
