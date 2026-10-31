# Sparkline

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Sparkline`
**Official:** https://textual.textualize.io/widgets/sparkline/

A compact inline chart for a numeric series.

## Constructor

```python
Sparkline(data: 'Sequence[float] | None' = None, *, min_color: 'Color | str | None' = None, max_color: 'Color | str | None' = None, summary_function: 'Callable[[Sequence[float]], float] | None' = None, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- data
- summary_function

## Messages

- None.

## CSS

- Sparkline — inline chart.

## Example

```python
yield Sparkline([1, 3, 2, 5, 4])
```

## Pitfalls

- The series is rendered as bars; normalize or summarize large ranges.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Sparkline)`
