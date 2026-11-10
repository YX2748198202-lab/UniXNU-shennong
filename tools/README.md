# tools

Host-side helpers for taking firmware apart. Not part of the firmware build.

## lzma-decode

EDK II compacts a firmware volume into a "guided" LZMA section: a 13-byte LZMA-Alone header
(properties, dictionary size, uncompressed size) followed by the raw stream. General-purpose
tools get this wrong — `xz --format=lzma` stops after a few bytes and python-lzma reports
corrupt input on streams the firmware itself decodes fine. This tool links EDK II's own
7-Zip SDK decoder (the same source `BaseTools/Source/C/LzmaCompress` and
`MdeModulePkg/Library/LzmaCustomDecompressLib` use), so a firmware stream decodes exactly as
the firmware would decode it.

    tools/build-lzma-decode.sh [UEFI_TREE]      # builds tools/bin/lzma-decode
    tools/bin/lzma-decode IN OUT [--offset N] [--finish any|end]
    tools/bin/lzma-decode IN OUT --raw-props 0x5D --raw-dict 0x1000000 --raw-size 0x1480C8 --offset 13

`--finish any` tolerates a stream without an end marker; `--raw-*` decodes a bare stream whose
header you already know (useful when brute-forcing a header that looks wrong).

Self-test: decoding the guided payload of `SILICIUM_UEFI-shennong-DEBUG.fd` yields
`Build/shennongPkg/DEBUG_CLANGPDB/FV/FVMAIN.Fv` byte for byte, preceded by an 8-byte section
header. See `docs/handoff/VENDOR-DXE-EXTRACTION.md`.

The decoder sources stay in the Mu checkout; nothing is vendored here, and `tools/bin/` is
build output (not committed).
