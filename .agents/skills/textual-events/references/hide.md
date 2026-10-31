# Hide

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/hide/

A widget was hidden.

## Handler

`def on_hide(self, event: events.Hide) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_hide(self) -> None:
    self.pause_timer()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Hide` docstring
