#!/usr/bin/env bash
# Apply, inspect, or preview the committed main-protection ruleset.
#
# Usage:
#   tools/protect-main.sh [--repo OWNER/NAME]
#   tools/protect-main.sh --dry-run [--repo OWNER/NAME]
#   tools/protect-main.sh --status [--repo OWNER/NAME]
#
# The payload in .github/rulesets/main.json is the single source of truth.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAYLOAD="$ROOT/.github/rulesets/main.json"
if [ ! -f "$PAYLOAD" ]; then
  echo "error: missing ruleset payload at $PAYLOAD" >&2
  exit 1
fi
NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$PAYLOAD")"
REPO=""
MODE="apply"

usage() {
  cat <<'EOF'
Usage:
  tools/protect-main.sh [--repo OWNER/NAME]
  tools/protect-main.sh --dry-run [--repo OWNER/NAME]
  tools/protect-main.sh --status [--repo OWNER/NAME]

Applies the payload in .github/rulesets/main.json when no mode is given.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --status) MODE="status" ;;
    --repo)
      REPO="${2:-}"
      if [ -z "$REPO" ]; then
        echo "error: --repo needs OWNER/NAME" >&2
        exit 2
      fi
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh is not installed; install it and authenticate with admin on the repo" >&2
  exit 1
fi

if [ -z "$REPO" ]; then
  if ! REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)"; then
    echo "error: could not resolve the repository; run inside a checkout or pass --repo OWNER/NAME" >&2
    exit 1
  fi
fi

case "$REPO" in
  */*) ;;
  *)
    echo "error: --repo must be OWNER/NAME, got '$REPO'" >&2
    exit 2
    ;;
esac

ADMIN="$(gh api "repos/$REPO" --jq .permissions.admin 2>/dev/null || true)"
if [ "$ADMIN" != "true" ]; then
  echo "error: gh needs admin on $REPO to manage the ruleset" >&2
  exit 1
fi

EXISTING="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$NAME\") | .id" 2>/dev/null || true)"

if [ "$MODE" = "status" ]; then
  if [ -z "$EXISTING" ]; then
    echo "no ruleset named '$NAME' on $REPO"
    exit 0
  fi
  gh api "repos/$REPO/rulesets/$EXISTING" --jq '{id, name, target, enforcement, conditions, bypass: [.bypass_actors[] | {actor_type, actor_id, bypass_mode}], rules: [.rules[].type]}'
  exit 0
fi

if [ "$MODE" = "dry-run" ]; then
  echo "would upsert ruleset '$NAME' on $REPO"
  python3 -m json.tool "$PAYLOAD"
  exit 0
fi

matches() {
  CURRENT_JSON="$1" python3 - "$PAYLOAD" <<'PY'
import json
import os
import sys

desired = json.load(open(sys.argv[1]))
current = json.loads(os.environ["CURRENT_JSON"])


def rules(doc):
    out = []
    for rule in doc.get("rules", []):
        kind = rule.get("type")
        params = rule.get("parameters", {})
        if kind == "pull_request":
            out.append(
                (
                    kind,
                    params.get("required_approving_review_count", 0),
                    params.get("require_extra_approval_for_unattributed_changes", True),
                    tuple(params.get("allowed_merge_methods", ["merge", "squash", "rebase"])),
                )
            )
        elif kind == "required_status_checks":
            checks = params.get("required_status_checks", [])
            out.append(
                (
                    kind,
                    tuple(sorted(check.get("context", "") for check in checks)),
                    params.get("strict_required_status_checks_policy", False),
                )
            )
        else:
            out.append((kind,))
    return tuple(sorted(out))


def bypass(doc):
    return tuple(
        sorted(
            (actor.get("actor_type"), actor.get("actor_id"), actor.get("bypass_mode"))
            for actor in doc.get("bypass_actors", [])
        )
    )


def refs(doc):
    conditions = doc.get("conditions", {}).get("ref_name", {})
    return (
        tuple(conditions.get("include", [])),
        tuple(conditions.get("exclude", [])),
    )

same = (
    current.get("name") == desired.get("name")
    and current.get("target") == desired.get("target")
    and current.get("enforcement") == desired.get("enforcement")
    and refs(current) == refs(desired)
    and bypass(current) == bypass(desired)
    and rules(current) == rules(desired)
)
sys.exit(0 if same else 1)
PY
}

if [ -n "$EXISTING" ]; then
  CURRENT="$(gh api "repos/$REPO/rulesets/$EXISTING")"
  if matches "$CURRENT"; then
    echo "no change: ruleset '$NAME' ($EXISTING) already matches on $REPO"
    exit 0
  fi
  gh api -X PUT "repos/$REPO/rulesets/$EXISTING" --input "$PAYLOAD" >/dev/null
  echo "updated ruleset '$NAME' ($EXISTING) on $REPO"
  exit 0
fi

gh api -X POST "repos/$REPO/rulesets" --input "$PAYLOAD" >/dev/null
NEW_ID="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$NAME\") | .id")"
echo "created ruleset '$NAME' ($NEW_ID) on $REPO"
