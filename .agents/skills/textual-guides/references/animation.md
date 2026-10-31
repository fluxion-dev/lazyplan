# Animation

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/animation/

Animate styles and offsets with easing and timers.

## What it covers

- animate
- easing
- duration
- delay
- on_complete

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Widget.animate
- Animatable
- EasingFunction

## Related references

Guides:

- [styles](styles.md)
- [events](events.md)

Reference files:

- [styles](../../textual-styles/SKILL.md)

## Example

```python
self.styles.animate("opacity", 0.0, duration=0.2)
```

## Pitfalls

- Do not animate layout-critical properties in a tight loop.
