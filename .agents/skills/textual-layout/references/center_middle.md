# CenterMiddle

**Textual:** 8.2.8 · **Import:** `from textual.containers import CenterMiddle`
**Official:** https://textual.textualize.io/guide/layout/

Centers children on both axes.

## Constructor and usage

```python
CenterMiddle(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with CenterMiddle():
    yield LoadingIndicator()
```

## Pitfalls

- The container must have a height to center vertically.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
