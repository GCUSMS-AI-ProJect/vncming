#!/bin/sh
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cmake -S "$VNCMING_ROOT/vendor/tigervnc" -B "$VNCMING_ROOT/build" \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_GNUTLS=ON -DENABLE_NLS=OFF \
    -DBUILD_JAVA=OFF -DBUILD_VIEWER=ON -DINSTALL_SYSTEMD_UNITS=OFF
cmake --build "$VNCMING_ROOT/build" --target vncviewer -j "${VNCMING_JOBS:-4}"
