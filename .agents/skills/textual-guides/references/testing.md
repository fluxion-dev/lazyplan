# Testing

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/testing/

Headless pilot tests for keys, clicks, screens, and app state.

## What it covers

- run_test
- Pilot
- press
- click
- pause
- workers

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.run_test
- Pilot

## Related references

Guides:

- [app](app.md)
- [screens](screens.md)
- [workers](workers.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)
- [layout](../../textual-layout/SKILL.md)

## Example

```python
async with app.run_test() as pilot:
    await pilot.press("q")
    await pilot.pause()
```

## Pitfalls

- Await workers and pauses; assertions before settle are flaky.
