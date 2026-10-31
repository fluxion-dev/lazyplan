# Click

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/click/

A mouse button was clicked on a widget.

## Handler

`def on_click(self, event: events.Click) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button, shift, meta, ctrl`

## Example

```python
def on_click(self, event: events.Click) -> None:
    self.log(f"clicked at {event.x},{event.y}")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Click` docstring
