# Switch

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Switch`
**Official:** https://textual.textualize.io/widgets/switch/

A sliding on/off control.

## Constructor

```python
Switch(value: 'bool' = False, *, animate: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None)
```

## Key properties and methods

- value
- disabled

## Messages

- Changed — emitted when toggled.

## CSS

- Switch — track.
- switch--slider — part.

## Example

```python
yield Switch(value=True, id="enabled")
```

## Pitfalls

- Prefer Switch for settings and Checkbox inside forms.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Switch)`
