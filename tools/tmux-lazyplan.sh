#!/usr/bin/env bash
# tmux dashboard: lazyplan + agent + files.
# Usage: ./tools/tmux-lazyplan.sh [session] [directory]
#   directory defaults to cwd; `lpui` resolves that repo's .plan/ from there.
set -euo pipefail
SESSION="${1:-lazyplan}"
DIR="${2:-$PWD}"
missing=()
command -v tmux >/dev/null || missing+=("tmux")
command -v lpui >/dev/null || missing+=("lpui  (pipx install lazyplan-tui)")
command -v opencode >/dev/null || missing+=("opencode")
command -v lazygit >/dev/null || missing+=("lazygit  (hint: ~/go/bin not on PATH?)")
if ((${#missing[@]})); then
  printf 'missing tools:\n  - %s\n' "${missing[@]}" >&2
  exit 1
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "attaching to existing session: $SESSION"
  exec tmux attach -t "$SESSION"
fi
tmux new-session -d -s "$SESSION" -n "plan" -c "$DIR" "lpui ui"
tmux select-pane -T "plan" -t "$SESSION:plan.0"
tmux split-window -h -c "$DIR" -t "$SESSION:plan" "opencode"
tmux select-pane -T "agent" -t "$SESSION:plan.1"
tmux split-window -v -c "$DIR" -t "$SESSION:plan.1" "lazygit"
tmux select-pane -T "files" -t "$SESSION:plan.2"
tmux select-pane -t "$SESSION:plan.0"
tmux attach -t "$SESSION"
