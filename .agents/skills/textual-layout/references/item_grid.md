# ItemGrid

**Textual:** 8.2.8 · **Import:** `from textual.containers import ItemGrid`
**Official:** https://textual.textualize.io/guide/layout/

A responsive grid of equally sized items.

## Constructor and usage

```python
ItemGrid(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, min_column_width: 'int | None' = None, max_column_width: 'int | None' = None, stretch_height: 'bool' = True, regular: 'bool' = False) -> 'None'
```

## Key behavior

- min_column_width
- max_column_width
- stretch_height
- regular

## Example

```python
yield ItemGrid(*cards, min_column_width=20)
```

## Pitfalls

- Column sizing is automatic; do not also set explicit grid tracks.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
