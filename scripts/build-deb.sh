#!/bin/sh
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$VNCMING_ROOT/scripts/build.sh"
exec /usr/bin/python3 "$VNCMING_ROOT/scripts/package_deb.py" "$@"
