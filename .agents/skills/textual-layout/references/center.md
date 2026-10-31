# Center

**Textual:** 8.2.8 · **Import:** `from textual.containers import Center`
**Official:** https://textual.textualize.io/guide/layout/

Centers children horizontally.

## Constructor and usage

```python
Center(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Center():
    yield Button("OK")
```

## Pitfalls

- Center is horizontal only; use Middle for vertical.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
