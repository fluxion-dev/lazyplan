# Link

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Link`
**Official:** https://textual.textualize.io/widgets/link/

A clickable URL with link styling and a Link.Clicked message.

## Constructor

```python
Link(text: 'str', *, url: 'str | None' = None, tooltip: 'str | None' = None, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- text
- url

## Messages

- Clicked — emitted when the link is activated.

## CSS

- Link — inline text.
- link--text, link--url — parts.

## Example

```python
yield Link("Docs", url="https://textual.textualize.io/")
```

## Pitfalls

- Set the URL explicitly; the display text is not the target.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Link)`
