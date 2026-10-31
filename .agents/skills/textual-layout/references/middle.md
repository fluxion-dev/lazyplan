# Middle

**Textual:** 8.2.8 · **Import:** `from textual.containers import Middle`
**Official:** https://textual.textualize.io/guide/layout/

Centers children vertically.

## Constructor and usage

```python
Middle(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Middle():
    yield Label("middle")
```

## Pitfalls

- Middle is vertical only; combine with Center or use CenterMiddle.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
