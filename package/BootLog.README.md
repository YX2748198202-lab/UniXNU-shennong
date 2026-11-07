# BootLog.c

Source: the sibling reference port **UniXNU/UniXNU-sheng** (`package/BootLog.c`, plus its only
local includes `BootLatencyFiles.h` and `ShengAudioAbi.h`), taken unchanged.

It is required by the kernel build, not optional: `scripts/build-sheng-source-storage.py`
compiles `BootLog.c` into `libShengSourceStorage.a` and derives `BootLogDefaults.c` from its weak
imports, so the ShengUfs component cannot build without the file.

The file is the kernel log writer: it publishes boot records into the storage log reserve and
reads the board's diagnostic counters. On this board every one of its 248 data sources is a
`weak_import`, and the generated `BootLogDefaults.c` supplies zeroed defaults for the ones that
are not built in, so it links and runs before a reserve is configured. Wiring the reserve — and
the counters it reads — is what turns it into a live log channel.

Products of this board live in `package/` and are registered through `board.toml`; this file only
satisfies the storage archive's input contract until the board's own log reserve exists.
