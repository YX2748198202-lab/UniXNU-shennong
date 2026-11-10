#!/usr/bin/env bash
# Build tools/lzma-decode against EDK II's own 7-Zip SDK decoder.
#
# The decoder sources come from the Mu checkout so the tool is bit-for-bit the same code
# path the firmware uses; nothing is downloaded.
#
# Usage: build-lzma-decode.sh [UEFI_TREE] [OUT_PATH]
set -euo pipefail

UEFI_TREE="${1:-${UEFI_TREE:-/home/yoox/android/sources/uefi-sheng}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${2:-$HERE/bin/lzma-decode}"

SDK="$UEFI_TREE/Mu_Basecore/BaseTools/Source/C/LzmaCompress/Sdk/C"
if [ ! -f "$SDK/LzmaDec.c" ] || [ ! -f "$SDK/7zTypes.h" ]; then
  echo "missing EDK II 7-Zip SDK at $SDK" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cc="${CC:-gcc}"
# 7-Zip's decoder is C99; -w keeps its warnings out of the build log, and the only
# symbols we need are LzmaDecode plus the allocator callbacks we supply ourselves.
"$cc" -O2 -std=c99 -w -I"$SDK" \
  "$HERE/lzma-decode.c" "$SDK/LzmaDec.c" \
  -o "$OUT"

echo "built $OUT"
"$OUT" 2>&1 | head -2 || true
