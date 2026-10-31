# TabbedContent

**Textual:** 8.2.8 · **Import:** `from textual.widgets import TabbedContent`
**Official:** https://textual.textualize.io/widgets/tabbedcontent/

A Tabs header paired with a ContentSwitcher body.

## Constructor

```python
TabbedContent(*titles: 'ContentType', initial: 'str' = '', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False)
```

## Key properties and methods

- active
- initial

## Messages

- TabActivated — emitted when a tab becomes active.

## CSS

- TabbedContent — frame.
- TabbedContent Tabs, TabbedContent ContentSwitcher — children.

## Example

```python
with TabbedContent("One", "Two"):\n    with TabPane("One", id="one"):\n        yield Static("A")
```

## Pitfalls

- Use TabPane children; ids tie tabs to panes.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.TabbedContent)`
