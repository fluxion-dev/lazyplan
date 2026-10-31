# Input

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/input/

Keyboard, mouse, focus, and text input handling.

## What it covers

- Key events
- focus
- mouse capture
- paste
- binding priority

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- events.Key
- events.Click
- Widget.focus
- Screen.BINDINGS

## Related references

Guides:

- [events](events.md)
- [widgets](widgets.md)

Reference files:

- [events](../../textual-events/SKILL.md)
- [widgets](../../textual-widgets/SKILL.md)

## Example

```python
def on_key(self, event: events.Key) -> None:
    if event.key == "escape":
        self.dismiss()
```

## Pitfalls

- Bindings can consume keys before on_key; check priority and focus.
