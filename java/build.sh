#!/usr/bin/env bash
# Build pm970-encoder.jar — only JniUtils stubs + EncodeBridge (no d8/dex2jar).
#
# Usage:
#   ./build.sh /path/to/tablecard.apk
#
# Requires: javac, jar, unzip

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <tablecard.apk>" >&2
  exit 1
fi

APK="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
CLASSES_DIR="$BUILD_DIR/classes"
NATIVE_DIR="$SCRIPT_DIR/native"
SRC_DIR="$SCRIPT_DIR/com"

if [ ! -f "$APK" ]; then
  echo "APK not found: $APK" >&2
  exit 1
fi

rm -rf "$BUILD_DIR"
mkdir -p "$CLASSES_DIR" "$NATIVE_DIR"

echo "Extracting libbluetoothhelper.so from APK..."
SO_PATH="$(unzip -Z1 "$APK" 'lib/*/libbluetoothhelper.so' 2>/dev/null | head -n 1 || true)"
if [ -z "$SO_PATH" ]; then
  echo "libbluetoothhelper.so not found in APK" >&2
  exit 1
fi
unzip -qo "$APK" "$SO_PATH" -d "$BUILD_DIR/apk_libs"
cp "$BUILD_DIR/apk_libs/$SO_PATH" "$NATIVE_DIR/libbluetoothhelper.so"
echo "Extracted: $SO_PATH"

echo "Compiling JniUtils + EncodeBridge..."
javac -encoding UTF-8 -d "$CLASSES_DIR" \
  "$SRC_DIR/bupin/blesdk/jni/JniUtils.java" \
  "$SCRIPT_DIR/EncodeBridge.java"

echo "Creating pm970-encoder.jar..."
jar cf "$SCRIPT_DIR/pm970-encoder.jar" -C "$CLASSES_DIR" .

echo ""
echo "Done: $SCRIPT_DIR/pm970-encoder.jar"
echo "Native lib: $NATIVE_DIR/libbluetoothhelper.so"
