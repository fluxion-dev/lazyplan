# DataTable

**Textual:** 8.2.8 · **Import:** `from textual.widgets import DataTable`
**Official:** https://textual.textualize.io/widgets/datatable/

A scrollable, cursor-driven table with columns, rows, and cell keys.

## Constructor

```python
DataTable(*, show_header: 'bool' = True, show_row_labels: 'bool' = True, fixed_rows: 'int' = 0, fixed_columns: 'int' = 0, zebra_stripes: 'bool' = False, header_height: 'int' = 1, show_cursor: 'bool' = True, cursor_foreground_priority: "Literal['renderable', 'css']" = 'css', cursor_background_priority: "Literal['renderable', 'css']" = 'renderable', cursor_type: 'CursorType' = 'cell', cell_padding: 'int' = 1, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- cursor_type
- zebra_stripes
- show_header
- fixed_columns
- fixed_rows

## Messages

- RowSelected — emitted when a row is activated.
- CellSelected — emitted for cell selection.
- HeaderSelected — emitted for header selection.

## CSS

- DataTable — grid.
- datatable--header, datatable--cursor, datatable--hover — parts.

## Example

```python
table = DataTable(); table.add_columns("Plan", "Tasks"); table.add_row("P1", 3)
```

## Pitfalls

- Add columns before rows; row keys must be unique.
- Large tables should update cells instead of rebuilding.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.DataTable)`
