# AppFocus

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/app_focus/

The application gained focus.

## Handler

`def on_app_focus(self, event: events.AppFocus) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_app_focus(self) -> None:
    self.query_one(Status).update("active")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.AppFocus` docstring
