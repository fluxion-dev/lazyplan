# Static

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Static`
**Official:** https://textual.textualize.io/widgets/static/

A general-purpose widget for Rich renderables and plain text.

## Constructor

```python
Static(content: 'VisualType' = '', *, expand: 'bool' = False, shrink: 'bool' = False, markup: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- content
- markup

## Messages

- None.

## CSS

- Static — block.

## Example

```python
yield Static("[bold]Ready[/]", markup=True)
```

## Pitfalls

- The old renderable argument name changed; use content.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Static)`
