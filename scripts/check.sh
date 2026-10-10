#!/bin/sh
set -eu
VNCMING_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
/usr/bin/python3 "$VNCMING_ROOT/app/viewer.py" --validate
/usr/bin/python3 -m compileall -q "$VNCMING_ROOT/app" "$VNCMING_ROOT/scripts" "$VNCMING_ROOT/tests"
c++ -std=c++11 "$VNCMING_ROOT/tests/verify_native_messages.cxx" \
    -o "$VNCMING_ROOT/build/verify-native-messages" -lfltk -lX11
echo '源码、地址解析及原生弹窗测试程序构建检查通过。'
