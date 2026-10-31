"""Widget gallery used by the Textual skill suite examples."""

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    Select,
    Static,
    Switch,
    Tree,
)


class WidgetGallery(App):
    """Mount one representative widget from each family."""

    CSS = """
    #gallery { padding: 1 2; }
    DataTable { height: 6; }
    Tree { height: 6; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Widget gallery")
        with Vertical(id="gallery"):
            yield Input(placeholder="Filter…", id="filter")
            yield Checkbox("Enabled", value=True, id="enabled")
            yield Switch(value=True, id="switch")
            yield Select([("One", 1), ("Two", 2)], prompt="Pick one", id="select")
            yield Button("Save", id="save", variant="primary")
            table = DataTable(id="table")
            table.add_columns("Plan", "Tasks")
            table.add_row("P1", 3)
            yield table
            tree = Tree("plans", id="tree")
            tree.root.add("P1", data={"id": 1})
            tree.root.expand()
            yield tree
            yield Static("Static output", id="output")
