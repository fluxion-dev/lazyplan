# ScrollableContainer

**Textual:** 8.2.8 · **Import:** `from textual.containers import ScrollableContainer`
**Official:** https://textual.textualize.io/guide/layout/

A focusable container with scrolling and optional maximize.

## Constructor and usage

```python
ScrollableContainer(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, can_focus: 'bool | None' = None, can_focus_children: 'bool | None' = None, can_maximize: 'bool | None' = None) -> 'None'
```

## Key behavior

- children
- id
- classes
- can_focus
- can_maximize

## Example

```python
with ScrollableContainer():
    yield Static(long_document)
```

## Pitfalls

- Focus behavior changes key handling; set can_focus deliberately.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
