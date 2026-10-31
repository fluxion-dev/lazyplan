# MouseScrollDown

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_scroll_down/

The mouse wheel scrolled down over the widget.

## Handler

`def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button`

## Example

```python
def on_mouse_scroll_down(self) -> None:
    self.scroll_down(animate=False)
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseScrollDown` docstring
