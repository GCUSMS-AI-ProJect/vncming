#!/bin/sh
# Requires an X11 display; uses local surfaces and no remote device.
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$VNCMING_ROOT/build/test-results"
c++ -std=c++11 -O2 \
  -I"$VNCMING_ROOT/vendor/tigervnc/common" \
  -I"$VNCMING_ROOT/vendor/tigervnc/vncviewer" \
  "$VNCMING_ROOT/tests/verify_scaled_damage.cxx" \
  "$VNCMING_ROOT/vendor/tigervnc/vncviewer/Surface.cxx" \
  "$VNCMING_ROOT/vendor/tigervnc/vncviewer/Surface_X11.cxx" \
  "$VNCMING_ROOT/vendor/tigervnc/common/rdr/Exception.cxx" \
  -o "$VNCMING_ROOT/build/verify-scaled-damage" -lfltk -lX11 -lXrender
"$VNCMING_ROOT/build/verify-scaled-damage" > "$VNCMING_ROOT/build/test-results/scaled-damage.txt"
cat "$VNCMING_ROOT/build/test-results/scaled-damage.txt"
