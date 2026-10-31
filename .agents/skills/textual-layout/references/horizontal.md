# Horizontal

**Textual:** 8.2.8 · **Import:** `from textual.containers import Horizontal`
**Official:** https://textual.textualize.io/guide/layout/

A container that lays children out left to right.

## Constructor and usage

```python
Horizontal(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Horizontal():
    yield Tree("nav")
    yield Static("preview")
```

## Pitfalls

- Children share width; use 1fr or explicit widths for panes.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
