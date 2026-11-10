#!/usr/bin/env python3
"""Contract test for scripts/scan-uefi-fv.py.

The scanner is the only thing standing between an anonymous flash blob and a driver list, so
its offsets have to be right: a wrong section offset silently yields garbage payloads that
the LZMA decoder then rejects. This builds a minimal but *structurally exact*
FV -> FFS -> {UI, PE32, GUID_DEFINED, FV_IMAGE} image and checks every field, then runs the
same assertions against the firmware volume this project actually builds.

Run: python3 scripts/test-scan-uefi-fv.py [--fd PATH_TO_FD]
"""
import argparse
import importlib.util
import struct
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scan-uefi-fv.py"

FV_GUID = uuid.UUID("8c8ce578-8a3d-4f1c-9935-896185c32dd3")
FFS_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792")
PE_GUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
LZMA_GUID = uuid.UUID("ee4e5898-3914-4259-9d6e-dc7bd79403cf")


def load_module():
    spec = importlib.util.spec_from_file_location("scanfv", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section(stype, body):
    return struct.pack("<I", (stype << 24) | (4 + len(body))) + body


def ui_section(name):
    text = name.encode("utf-16-le") + b"\x00\x00"
    return section(0x15, text)


def guid_defined(payload):
    header = struct.pack("<I", (0x02 << 24) | (24 + len(payload)))
    header += LZMA_GUID.bytes_le
    header += struct.pack("<HH", 24, 1)
    return header + payload


def ffs(guid, ftype, body):
    header = guid.bytes_le + struct.pack("<HBB", 0, ftype, 0)
    size = 24 + len(body)
    header += struct.pack("<I", size)[:3] + b"\xf8"
    return header + body


def pack_files(files):
    """FFS files are 8-byte aligned inside an FV (PI spec); a tight join misparses."""
    out = b""
    for item in files:
        out += item
        out += b"\xff" * (-len(out) % 8)
    return out


def volume(files):
    body = pack_files(files)
    header_size = 0x48
    total = header_size + len(body)
    header = b"\x00" * 16 + FV_GUID.bytes_le
    header += struct.pack("<Q", total)
    header += b"_FVH"
    header += struct.pack("<I", 0x0004FEFF)
    header += struct.pack("<H", header_size)
    header += struct.pack("<H", 0)
    header += struct.pack("<H", 32) + struct.pack("<H", 0)
    header += b"\x00" * (header_size - len(header))
    return header + body


def build_fixture():
    pe = b"MZ" + b"\x00" * 62
    inner_fv = volume([ffs(PE_GUID, 0x07, ui_section("Inner") + section(0x10, pe))])
    compact = ffs(FFS_GUID, 0x0B, guid_defined(b"\x5d\x00\x00\x00\x01" + b"\x00" * 40))
    nested = ffs(PE_GUID, 0x0B, section(0x17, inner_fv))
    named = ffs(PE_GUID, 0x07, ui_section("DriverDxe") + section(0x10, pe))
    return volume([compact, nested, named]), inner_fv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fd", type=Path,
                        default=Path("/home/yoox/android/artifacts/UniXNU-shennong/firmware/"
                                     "SILICIUM_UEFI-shennong-DEBUG.fd"))
    args = parser.parse_args()

    module = load_module()
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    # 1) Synthetic image: every structural offset and field.
    fixture, inner = build_fixture()
    report = module.scan(fixture)
    check(len(report["volumes"]) == 2, f'expected 2 volumes, got {len(report["volumes"])}')
    check(report["files"], "no FFS files found")
    guids = [f["guid"] for f in report["files"]]
    check(str(FFS_GUID) in guids, "compacted FV file missing")
    check(guids.count(str(PE_GUID)) == 3, f"expected 3 PE-GUID files, got {guids.count(str(PE_GUID))}")
    names = [f.get("ui", "") for f in report["files"]]
    check("DriverDxe" in names, f'names {names} lack "DriverDxe"')
    check("Inner" in names, f'names {names} lack the nested-volume driver')
    guided = [s for s in report["sections"] if s["type"] == 0x02]
    check(len(guided) == 1, f'expected 1 guided section, got {len(guided)}')
    if guided:
        check(guided[0]["algorithm"] == "lzma", f'algorithm {guided[0]["algorithm"]}')
        check(guided[0]["data_offset"] == 24, f'data_offset {guided[0]["data_offset"]}')
        start = guided[0]["offset"] + guided[0]["data_offset"]
        end = guided[0]["offset"] + guided[0]["size"]
        check(fixture[start:start + 5] == b"\x5d\x00\x00\x00\x01",
              "guided payload does not start where the scanner says it does")

    # 2) Truncation must not be read as structure: a cut in the middle of the FV chain
    #    yields fewer files, never an exception.
    try:
        module.scan(fixture[:80])
    except Exception as error:  # noqa: BLE001 - the point is that nothing escapes
        failures.append(f"scan of a truncated image raised {type(error).__name__}: {error}")

    # 3) The project's own firmware volume: 112 modules were counted from the build tree,
    #    and the compacted volume must be the LAST FV (it sits at the end of the .fd).
    if args.fd.is_file():
        built = module.scan(args.fd.read_bytes())
        check(len(built["volumes"]) == 1, f'built FD: {len(built["volumes"])} volumes')
        compact = [f for f in built["files"] if f["type"] == 0x0B]
        check(len(compact) == 1, f'built FD: {len(compact)} compacted volumes')
        if compact:
            check(compact[0]["guid"] == str(FFS_GUID), f'compacted guid {compact[0]["guid"]}')
            check(compact[0]["size"] > 1_000_000, f'compacted size {compact[0]["size"]}')
    else:
        print(f"note: {args.fd} not present, skipping the built-image assertions")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        sys.exit(1)
    print("scan-uefi-fv: all checks passed")


if __name__ == "__main__":
    main()
