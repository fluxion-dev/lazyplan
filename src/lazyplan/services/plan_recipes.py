"""Packaged plan recipes: structural starting points for plan apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RECIPES = ("feature", "bugfix", "refactor")
_RECIPE_DIR = Path(__file__).resolve().parent.parent / "data" / "recipes"


class RecipeError(ValueError):
    """A recipe is unknown or unreadable."""


def names() -> tuple[str, ...]:
    """Available recipe names."""
    return RECIPES


def load(name: str) -> dict[str, Any]:
    """Read one packaged recipe document."""
    if name not in RECIPES:
        raise RecipeError(f"unknown recipe {name!r}; choose from {', '.join(RECIPES)}")
    path = _RECIPE_DIR / f"{name}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecipeError(f"cannot read recipe {name!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RecipeError(f"recipe {name!r} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise RecipeError(f"recipe {name!r} must be a JSON object")
    return raw
