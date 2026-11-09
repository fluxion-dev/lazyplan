# Output contract fixtures

These fixtures pin user-visible output so refactors can prove they changed
structure, not behavior. Update a fixture only when an output change is
intentional and named in the changelog.

- `cli/baseline.json` — CLI default, `--porcelain`, and `--json` rows for
  list, show, add, move, brief, audit, feed, export, and share. Volatile
  timestamps and UIDs are normalized to `<ts>` and `<uid>`.
- `mcp/schema.json` — the `tools/list` and `resources/list` discovery schema,
  including tool input schemas and resource templates.
