"""Vulture allowlist: names that look unused but are live.

- Textual framework dispatch: lifecycle, message handlers, key actions,
  and widget class attributes are called by name/convention, never by
  direct reference. Listed per method so genuinely dead actions still fail.
- Tested API kept deliberately: criteria_progress (P#32 contract),
  STARTERS/ensure_templates (template scaffold seams), vcs registry.
- sqlite3 API noise: row_factory.
"""

_.compose
_.on_mount
_.on_button_pressed
_.on_tree_node_highlighted
_.on_tree_node_collapsed
_.on_tree_node_expanded
_.on_tree_node_selected
_.action_toggle_node
_.action_toggle_expand_all
_.action_open_detail
_.action_fold
_.action_fold_left
_.action_fold_right
_.action_refresh
_.action_filter_status
_.action_filter_plan
_.action_toggle_show_all
_.action_help
_.action_new_context
_.action_new_plan
_.action_new_milestone
_.action_new_task
_.action_criteria
_.action_delete
_.action_toggle_status
_.action_fold_all
_.action_cancel
_.action_export_md
_.export_plan
_.render_plan_markdown
BINDINGS
CSS
TITLE
_.display
_.row_factory
_.criteria_progress
STARTERS
KEYMAP
ensure_templates
_.is_available
backends
default_scope
repos_map
