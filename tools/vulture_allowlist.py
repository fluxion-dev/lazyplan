"""Vulture allowlist: names that look unused but are live.

- Textual dispatch: lifecycle handlers, key actions, private callbacks, and
  widget attributes are called by name or convention, never by direct
  reference. Every name is listed so a genuinely dead action still fails.
- Dataclass fields read through serialization: diff hunk counts, snapshot
  scopes, and registry deprecation metadata.
- sqlite3 and shlex API noise: row_factory and the lexer switches.
- Docs metadata: ENVIRONMENT and FILES are read by tools/gen-man.py.
- Kept-live seams: attention_ids (tools/perf_bench.py), criteria_progress
  (public metrics contract), the VCS backend contract (is_available), and the
  claim, plan-uid, poll, and trim helpers asserted by their own tests.
"""

# Textual dispatch: key actions, lifecycle handlers, and callbacks.
_._cancel, _._cancel_pressed, _._close, _._create
_._download, _._export_pressed, _._file_selected, _._folder_selected
_._highlight, _._later, _._never, _._on_click, _._on_expanded
_._on_filter_changed, _._on_filter_submitted, _._on_highlight, _._on_row_action
_._on_selection_changed, _._open_link, _._path_submitted, _._pick
_._run_first, _._save, _._select, _._submit
# Setup wizard panels and controls, dispatched by widget id.
_._back, _._checkbox_changed, _._hooks_changed, _._model_submitted
_._next, _._placement_selected, _._rail_selected, _._recheck
_._reset_roles, _._select_changed, _._theme_changed
_.action_add, _.action_apply_archive, _.action_apply_trim, _.action_apply_vacuum
_.action_back, _.action_clear, _.action_clear_filter, _.action_copy, _.action_edit_row
_.action_filter, _.action_filter_actor, _.action_filter_kind, _.action_fold_left
_.action_fold_right, _.action_force, _.action_hub_toggle, _.action_less
_.action_more, _.action_new_context, _.action_next_file, _.action_note
_.action_open, _.action_open_owner, _.action_open_value, _.action_prev_file
_.action_quit, _.action_relate, _.action_restore, _.action_source_hub
_.action_toggle_expand_all, _.action_toggle_fold, _.action_toggle_split, _.action_toggle_wrap
_.action_unrelate, _.on_click, _.on_key, _.on_notifications_changed, _.on_resize, _.on_tree_node_collapsed
_.on_tree_node_expanded, _.on_tree_node_highlighted, _.on_tree_node_selected, _.on_unmount
_.watch_rev
# Widget state and class attributes read by the framework.
_.BINDINGS, _.CSS_PATH, _.ENABLE_COMMAND_PALETTE, _.TITLE
_.border_subtitle, _.border_title, _.bubble, _.can_focus
_.compose, _.cursor_line, _.load_children, _.on_root
_.rev, _.show_root
# Dataclass fields consumed through serialization.
_.auto_closed, _.daily_rate, _.deprecated_in, _.elapsed_seconds
_.from_cache, _.handoff, _.host_session, _.new_count, _.old_count, _.rebuilds
_.rev, _.tui_only
# sqlite3/shlex API noise and docs metadata read by tools/gen-man.py.
_.ENVIRONMENT, _.FILES, _.row_factory, _.whitespace
_.whitespace_split
# Kept-live seams, each with a caller or contract outside src discovery.
_._status_keep_ids, _.attention_ids, _.criteria_progress, _.is_available
_.plan_uid, _.poll_now, _.task_criteria
