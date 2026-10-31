# Leave

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/leave/

The mouse pointer left the widget.

## Handler

`def on_leave(self, event: events.Leave) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y`

## Example

```python
def on_leave(self) -> None:
    self.remove_class("hover")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Leave` docstring
