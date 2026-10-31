# Reactivity

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/reactivity/

Reactive attributes, watchers, recomposition, and validation.

## What it covers

- reactive
- var
- watch_*
- validate_*
- recompose

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- reactive
- var
- Widget.watch

## Related references

Guides:

- [events](events.md)
- [widgets](widgets.md)

Reference files:

- [events](../../textual-events/SKILL.md)
- [widgets](../../textual-widgets/SKILL.md)

## Example

```python
count = reactive(0)

def watch_count(self, value: int) -> None:
    self.query_one(Label).update(str(value))
```

## Pitfalls

- Watchers run on assignment; avoid mutating the same attribute inside one.
