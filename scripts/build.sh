#!/bin/sh
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cmake -S "$VNCMING_ROOT/vendor/tigervnc" -B "$VNCMING_ROOT/build" \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_GNUTLS=ON -DENABLE_NLS=ON \
    -DBUILD_JAVA=OFF -DBUILD_VIEWER=ON -DINSTALL_SYSTEMD_UNITS=OFF
cmake --build "$VNCMING_ROOT/build" --target vncviewer -j "${VNCMING_JOBS:-4}"
mkdir -p "$VNCMING_ROOT/build/locale/zh_CN/LC_MESSAGES"
msgfmt --check "$VNCMING_ROOT/vendor/tigervnc/po/zh_CN.po" \
    -o "$VNCMING_ROOT/build/locale/zh_CN/LC_MESSAGES/tigervnc.mo"
