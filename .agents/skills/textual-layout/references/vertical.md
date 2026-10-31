# Vertical

**Textual:** 8.2.8 · **Import:** `from textual.containers import Vertical`
**Official:** https://textual.textualize.io/guide/layout/

A container that lays children out top to bottom.

## Constructor and usage

```python
Vertical(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Vertical():
    yield Label("top")
    yield Static("body")
```

## Pitfalls

- Nested vertical containers need a height or 1fr to fill.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
