# MouseScrollUp

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_scroll_up/

The mouse wheel scrolled up over the widget.

## Handler

`def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button`

## Example

```python
def on_mouse_scroll_up(self) -> None:
    self.scroll_up(animate=False)
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseScrollUp` docstring
