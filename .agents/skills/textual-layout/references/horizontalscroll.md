# HorizontalScroll

**Textual:** 8.2.8 · **Import:** `from textual.containers import HorizontalScroll`
**Official:** https://textual.textualize.io/guide/layout/

A horizontal container that scrolls its children.

## Constructor and usage

```python
HorizontalScroll(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, can_focus: 'bool | None' = None, can_focus_children: 'bool | None' = None, can_maximize: 'bool | None' = None) -> 'None'
```

## Key behavior

- children
- id
- classes
- can_focus

## Example

```python
with HorizontalScroll():
    for card in cards:
        yield card
```

## Pitfalls

- Set child widths; auto-width children may not overflow.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
