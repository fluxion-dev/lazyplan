# Print

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/print/

The app received the print key binding (Ctrl+P by default).

## Handler

`def on_print(self, event: events.Print) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_print(self) -> None:
    self.screen.print()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Print` docstring
