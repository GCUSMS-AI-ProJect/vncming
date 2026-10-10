#!/bin/sh
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$VNCMING_ROOT/build/vncviewer/vncviewer" ]; then
    "$VNCMING_ROOT/scripts/build.sh"
fi
exec /usr/bin/python3 "$VNCMING_ROOT/scripts/install.py" "$@"
