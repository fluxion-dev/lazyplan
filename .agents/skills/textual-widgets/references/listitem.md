# ListItem

**Textual:** 8.2.8 · **Import:** `from textual.widgets import ListItem`
**Official:** https://textual.textualize.io/widgets/listitem/

One row inside a ListView.

## Constructor

```python
ListItem(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True) -> 'None'
```

## Key properties and methods

- id
- disabled

## Messages

- None.

## CSS

- ListItem — row; ListView handles selection and highlighting.

## Example

```python
yield ListItem(Label("First"))
```

## Pitfalls

- Use ListView's index/child API rather than reaching into internals.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.ListItem)`
