# Pretty

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Pretty`
**Official:** https://textual.textualize.io/widgets/pretty/

A Rich pretty-printer for arbitrary data.

## Constructor

```python
Pretty(object: 'Any', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None) -> 'None'
```

## Key properties and methods

- data

## Messages

- None.

## CSS

- Pretty — printable block.

## Example

```python
yield Pretty({"plans": 3, "open": 7})
```

## Pitfalls

- Large or recursive structures should be summarized before rendering.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Pretty)`
