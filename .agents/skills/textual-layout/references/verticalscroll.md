# VerticalScroll

**Textual:** 8.2.8 · **Import:** `from textual.containers import VerticalScroll`
**Official:** https://textual.textualize.io/guide/layout/

A vertical container that scrolls its children.

## Constructor and usage

```python
VerticalScroll(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, can_focus: 'bool | None' = None, can_focus_children: 'bool | None' = None, can_maximize: 'bool | None' = None) -> 'None'
```

## Key behavior

- children
- id
- classes
- can_focus

## Example

```python
with VerticalScroll():
    yield Static(long_text)
```

## Pitfalls

- A fixed child height is needed to create overflow.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
