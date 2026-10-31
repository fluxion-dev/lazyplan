# MouseUp

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_up/

A mouse button was released over the widget.

## Handler

`def on_mouse_up(self, event: events.MouseUp) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button`

## Example

```python
def on_mouse_up(self) -> None:
    self.release_mouse()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseUp` docstring
