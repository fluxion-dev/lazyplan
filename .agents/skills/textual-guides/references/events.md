# Events and Messages

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/events/

Built-in events, custom messages, handlers, bubbling, and prevention.

## What it covers

- on_<event>
- Message
- bubbling
- prevent_default
- stop

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Message
- events.Event
- @on

## Related references

Guides:

- [input](input.md)
- [actions](actions.md)

Reference files:

- [events](../../textual-events/SKILL.md)
- [widgets](../../textual-widgets/SKILL.md)

## Example

```python
class Saved(Message):
    pass

def on_saved(self) -> None:
    self.refresh()
```

## Pitfalls

- Message names map to on_<snake_case>; do not call handlers directly.
