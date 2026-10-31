# MouseMove

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_move/

The mouse moved over the widget.

## Handler

`def on_mouse_move(self, event: events.MouseMove) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button`

## Example

```python
def on_mouse_move(self, event: events.MouseMove) -> None:
    self.cursor = (event.x, event.y)
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseMove` docstring
