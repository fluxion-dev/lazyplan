# Grid

**Textual:** 8.2.8 · **Import:** `from textual.containers import Grid`
**Official:** https://textual.textualize.io/guide/layout/

A grid container using grid-columns, grid-rows, and spans.

## Constructor and usage

```python
Grid(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Grid():
    yield Static("a")
    yield Static("b")
```

## Pitfalls

- Set grid-size or explicit grid tracks; default tracks may surprise.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
