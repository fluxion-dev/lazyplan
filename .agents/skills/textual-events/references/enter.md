# Enter

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/enter/

The mouse pointer entered the widget.

## Handler

`def on_enter(self, event: events.Enter) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y`

## Example

```python
def on_enter(self) -> None:
    self.add_class("hover")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Enter` docstring
