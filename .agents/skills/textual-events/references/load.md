# Load

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/load/

The app finished loading and is ready to run.

## Handler

`def on_load(self, event: events.Load) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_load(self) -> None:
    self.log("ready")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Load` docstring
