# ProgressBar

**Textual:** 8.2.8 · **Import:** `from textual.widgets import ProgressBar`
**Official:** https://textual.textualize.io/widgets/progressbar/

A horizontal progress bar for determinate or indeterminate work.

## Constructor

```python
ProgressBar(total: 'float | None' = None, *, show_bar: 'bool' = True, show_percentage: 'bool' = True, show_eta: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, clock: 'Clock | None' = None, gradient: 'Gradient | None' = None)
```

## Key properties and methods

- total
- progress
- show_percentage
- show_eta

## Messages

- None.

## CSS

- ProgressBar — track.
- progress-bar--bar, progress-bar--percentage — parts.

## Example

```python
yield ProgressBar(total=100, progress=40)
```

## Pitfalls

- Set total before progress; use advance() for incremental updates.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.ProgressBar)`
