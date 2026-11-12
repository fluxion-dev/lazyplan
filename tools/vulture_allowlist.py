"""Vulture allowlist: names that look unused but are live.

- Textual framework dispatch: lifecycle, message handlers, key actions,
  and widget class attributes are called by name/convention, never by
  direct reference. Listed per method so genuinely dead actions still fail.
- Tested API kept deliberately: criteria_progress (P#32 contract),
  STARTERS/ensure_templates (template scaffold seams), vcs registry.
- Session API kept deliberately: the store and port surface is consumed
  by the session commands and resume reads cut in T1436 and T1437.
  auto_closed is display metadata for idle-reaped rows.
- Metrics dashboard contract: snapshot fields are consumed by the chart
  cards and their tests; attention_ids is the set form of the preview map.
- Poll seams kept for tests: rebuilds counts full tree rebuilds and poll_now
  drives one poll on the calling thread; both are read by the headless Pilot
  tests, never by production call sites.
- sqlite3 API noise: row_factory.
- `_status_keep_ids` is the bounded keep-set helper asserted directly by trim tests.
- shlex API noise: whitespace and whitespace_split configure the lexer.
"""

_.compose
_.on_mount
_.on_key
_.on_unmount
_.on_resize
_.on_button_pressed
_.on_tree_node_highlighted
_.on_tree_node_collapsed
_.on_tree_node_expanded
_.on_tree_node_selected
_._open_link
_.action_toggle_node
_.action_toggle_expand_all
_.action_fold
_.action_fold_left
_.action_fold_right
_.action_refresh
_.action_help
_.action_new_context
_.action_new_plan
_.action_new_milestone
_.action_new_task
_.action_delete
_.action_toggle_status
_.action_fold_all
_.action_cancel
_.action_export_md
_.action_move
_.action_add_criterion
_.action_edit_selection
_.action_filter_text
_.action_quit
_.action_apply_archive
_.action_apply_trim
_.action_apply_vacuum
_.action_restore
_status_keep_ids
_.export_plan
_.render_plan_markdown
_.rebuilds
_.poll_now
_.cursor_line
BINDINGS
auto_closed
CSS
tool_actions
tool_labels
CSS_PATH
TITLE
border_title
ENABLE_COMMAND_PALETTE
VERBS
NOUNS
LEGACY_COMMANDS
PALETTE_COMMANDS
PALETTE_SECTIONS
context
tui_only
_.display
_.row_factory
_.whitespace
_.whitespace_split
_.criteria_progress
_.day
_.percent
_.elapsed_seconds
attention_ids
_.taxonomy
_.deprecated_in
_.removal
SURFACES
TAXONOMY
PALETTE_TO_ACTION
_.daily_rate
_.eta_days
_.complete
STARTERS
KEYMAP
ensure_templates
_.is_available
backends
current_head
forges
detect_forge
redact
_.provider
_.files
_.unlink_forge
_.cache_get
_.cache_put
_.claim_task
_.renew_claim
_.release_claim
_.list_claims
_.unrelate_criterion
_.criterion_tasks
_.task_criteria
_.restore_comment
GitHubClient
_.pulls_for_commit
_.pull
_.checks
_.reviews
_.from_cache
default_scope
repos_map
_.action_toggle_edit
_.action_back
_.action_save
_.action_advance_status
_.action_add_child
_.action_delete_row
_.action_open_source
_.action_open
_.action_copy
_.action_filter
_.check_action
_._on_click
_._on_highlight
_._folder_selected
_._file_selected
_._export_pressed
_._cancel_pressed
_._path_submitted
_._on_filter_changed
_._on_filter_submitted
_._create
_._cancel
_._confirm
_._close
_._filter
_._run_first
_._pick
_._apply
_._submit
_.watch_rev
_._on_selection_changed
_._on_row_action
_.action_clear_filter
# Textual widget state and screen handlers dispatched by decorator.
border_subtitle
highlighted
disabled
_._later
_._download
_._save
bubble
rev
run_wizard
# Diff model metadata: parsed, tested, and part of the read-only source API.
old_start
old_count
new_start
new_count
ask_migration
_skills_dir_override
prompt_confirm
# Docs metadata is read by tools/gen-man.py and the docs-truth test.
ENVIRONMENT
FILES
# Compatibility helper kept for tests and callers outside the CLI.
default_choice
# Public read helpers kept for tests and callers outside the tree path.
plan_activity
_.plan_uid
# Metrics chart-row helpers kept for the core metrics API and its tests.
activity_weeks
milestone_bars
status_bars
# Snapshot scope fields kept for callers and tests outside the timeline card.
plan_title
# Trace helper kept for the timeline card tests.
active_segments
# Textual Tree reactive read by the framework, set as a subclass default.
show_root
# Public selection helper kept for callers outside the overlap-aware service.
_.next_claimable_task
# Policy helper exercised by the coordination policy tests.
touchpoints_overlap
# Provenance, activity, and edit hubs: Textual key actions and message handlers.
_.action_open_trust_hubs
_._highlight
_._select
_.action_add
_.action_hub_toggle
_.action_prove
_.action_force
_.action_note
_.action_relate
_.action_unrelate
_.action_open_value
_.action_source_hub
_.action_edit_row
_.action_filter_actor
_.action_filter_kind
_.action_open_owner
_.action_open
_.action_copy
_.action_filter
_.check_action
_._on_click
_.can_focus
on_root
_.on_click
_.load_children
