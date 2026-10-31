# Workers

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/workers/

Run blocking work off the UI thread and bring results back safely.

## What it covers

- run_worker
- thread workers
- exclusive
- call_from_thread
- worker state

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.run_worker
- Worker
- @work

## Related references

Guides:

- [events](events.md)
- [testing](testing.md)

Reference files:

- [events](../../textual-events/SKILL.md)

## Example

```python
self.run_worker(self.load, thread=True, exclusive=True)
```

## Pitfalls

- Never touch widgets from a worker; marshal with call_from_thread.
