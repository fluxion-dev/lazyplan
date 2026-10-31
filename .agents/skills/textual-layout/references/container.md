# Container

**Textual:** 8.2.8 · **Import:** `from textual.containers import Container`
**Official:** https://textual.textualize.io/guide/layout/

A plain vertical container with no extra layout rules.

## Constructor and usage

```python
Container(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key behavior

- children
- id
- classes

## Example

```python
with Container():
    yield Header()
    yield Static("body")
```

## Pitfalls

- Container defaults to vertical layout; set layout in CSS when needed.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
