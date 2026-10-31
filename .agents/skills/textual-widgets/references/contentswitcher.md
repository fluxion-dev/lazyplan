# ContentSwitcher

**Textual:** 8.2.8 · **Import:** `from textual.widgets import ContentSwitcher`
**Official:** https://textual.textualize.io/widgets/contentswitcher/

Shows one child at a time by id, useful for tabs and wizards.

## Constructor

```python
ContentSwitcher(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, initial: 'str | None' = None) -> 'None'
```

## Key properties and methods

- current
- initial

## Messages

- None.

## CSS

- ContentSwitcher — the visible child is the one whose id matches current.

## Example

```python
yield ContentSwitcher(Static("A", id="a"), Static("B", id="b"), initial="a")
```

## Pitfalls

- current must match a child id; missing ids show nothing.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.ContentSwitcher)`
