# Show

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/show/

A widget was shown.

## Handler

`def on_show(self, event: events.Show) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_show(self) -> None:
    self.refresh_data()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Show` docstring
