#!/bin/sh
# /usr/bin/lpui (and /usr/bin/lazyplan) — system-package wrapper.
# Vendored libs live in /usr/lib/lazyplan (pip --target layout).
# No daemon, no root writes at runtime: DB stays in $LAZYPLAN_DB / .plan/ / ~/.local/share.
set -eu
export PYTHONPATH="/usr/lib/lazyplan${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m lazyplan "$@"
