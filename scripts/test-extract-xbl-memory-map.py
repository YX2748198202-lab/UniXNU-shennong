#!/usr/bin/env python3
"""Contract test for scripts/extract-xbl-memory-map.py.

The extractor reads a serialized region list out of a stock xbl_config blob. Getting the
byte order or the record layout wrong is silent — it yields plausible-looking garbage — so
the test builds a blob with known regions and checks every field, plus the two failure modes
(no records, overlapping carveouts).

Run: python3 scripts/test-extract-xbl-memory-map.py
"""
import importlib.util
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "extract-xbl-memory-map.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xblmap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(name, base, size, attrs=((0x5F, 4, 0x703C07), (0x71, 1, 0x00))):
    """One serialized region, exactly as the blob stores it (big-endian, unaligned)."""
    blob = struct.pack(">I", 0x000000B9)
    blob += struct.pack(">Q", base)
    blob += struct.pack(">Q", size)
    blob += struct.pack(">I", 3)                      # version
    name_field = name.encode() + b"\x00"
    blob += struct.pack(">I", len(name_field))
    blob += struct.pack(">I", 0x00000956)             # "V" marker
    blob += name_field
    for attribute_id, length, value in attrs:
        blob += struct.pack(">I", 0x00000003)
        blob += struct.pack(">I", length)
        blob += struct.pack(">I", attribute_id)
        blob += value.to_bytes(length, "big")
    return blob


def main():
    module = load_module()
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    # 1) Round trip: two carveouts plus a span entry, unaligned to 4 bytes on purpose.
    blob = b"\xAA\xBB\xCC" + record("DDR", 0x80000000, 0x80000000) \
        + record("RSRV0", 0x816E0000, 0x320000) \
        + record("TZApps_Reserved", 0xD8800000, 0x1B000000)
    rows = list(module.parse_entries(blob))
    check(len(rows) == 3, f"expected 3 regions, got {len(rows)}")
    if rows:
        first, second = rows[0], rows[1]
        check(first["name"] == "DDR", f"first name {first['name']!r}")
        check(first["base"] == 0x80000000, f"DDR base {first['base']:#x}")
        check(first["size"] == 0x80000000, f"DDR size {first['size']:#x}")
        check(second["attributes"].get("attr") == 0x703C07,
              f"RSRV0 attribute {second['attributes'].get('attr')!r}")
        check(second["attributes"].get("flag_q") == 0, f"RSRV0 flag_q {second['attributes']}")
        check(rows[2]["base"] + rows[2]["size"] == 0xF3800000, "TZApps end address")

    # 2) check() accepts the blob and rejects overlapping carveouts.
    module.check(rows, "fixture")
    overlap = list(module.parse_entries(
        record("A", 0x80000000, 0x1000) + record("B", 0x80000800, 0x1000)))
    try:
        module.check(overlap, "overlap fixture")
    except SystemExit:
        pass
    else:
        failures.append("overlapping carveouts were accepted")

    # 3) An empty/garbage blob must not look like a memory map.
    try:
        module.check(list(module.parse_entries(b"\x00" * 256)), "empty")
    except SystemExit:
        pass
    else:
        failures.append("garbage blob was accepted")

    # 4) CLI: --toml output must be loadable and keep the sha256 provenance line.
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "xbl_config.bin"
        source.write_bytes(record("RSRV0", 0x816E0000, 0x320000))
        out = Path(tmp) / "map.toml"
        subprocess.run([sys.executable, str(SCRIPT), str(source), "--toml", "--out", str(out)],
                       check=True, capture_output=True)
        text = out.read_text()
        check('sha256 =' in text, "toml output lost the sha256 provenance")
        import tomllib
        loaded = tomllib.loads(text)
        check(len(loaded["region"]) == 1, f"toml has {len(loaded.get('region', []))} regions")
        check(loaded["region"][0]["base"] == 0x816E0000, "toml base value")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        sys.exit(1)
    print("extract-xbl-memory-map: all checks passed")


if __name__ == "__main__":
    main()
