#!/usr/bin/env python3
"""Inventory the firmware volumes inside a bootloader or firmware image.

Stock Qualcomm blobs (`abl`, `xbl`) and built firmware volumes are both containers of
FV -> FFS file -> sections, but nothing in them is labelled: an FFS file is a GUID and a
type byte, and the driver's name only appears inside a UI section. This walks the whole
structure and reports it, so a driver set can be compared or extracted instead of guessed.

Handles what actually appears in these images:
  * FV header length from the header itself (block map / extended header included),
  * FFS v1 headers and the extended (FFS_FILE_HEADER2) form used by large files,
  * section chains: PE32, PIC, TE, UI (driver name), GUID_DEFINED (compressed payload),
    FIRMWARE_VOLUME_IMAGE (a nested FV), COMPRESSION, VERSION, DXE_DEPEX,
  * PE32 payloads inside a nested FV or a guided section after decompression.

Usage:
    scan-uefi-fv.py IMAGE                     # list volumes, files and section types
    scan-uefi-fv.py IMAGE --names             # one line per FFS file with its UI name
    scan-uefi-fv.py IMAGE --extract-guided DIR  # write guided-section payloads for tools/bin/lzma-decode
    scan-uefi-fv.py IMAGE --extract-pe DIR    # write PE32 sections as DIR/<name>/<guid>.efi
    scan-uefi-fv.py IMAGE --json              # machine-readable
"""
import argparse
import json
import struct
import sys
import uuid
from pathlib import Path

FV_SIGNATURE = b"_FVH"
SECTION_PE32 = 0x10
SECTION_PIC = 0x11
SECTION_TE = 0x12
SECTION_DXE_DEPEX = 0x13
SECTION_VERSION = 0x14
SECTION_UI = 0x15
SECTION_COMPRESSION = 0x01
SECTION_GUID_DEFINED = 0x02
SECTION_FV_IMAGE = 0x17

SECTION_NAMES = {
    0x01: "COMPRESSION", 0x02: "GUID_DEFINED", 0x03: "PE32_DISPOSABLE", 0x10: "PE32",
    0x11: "PIC", 0x12: "TE", 0x13: "DXE_DEPEX", 0x14: "VERSION", 0x15: "UI",
    0x16: "COMPAT16", 0x17: "FV_IMAGE", 0x18: "FREEFORM_SUBTYPE_GUID", 0x19: "RAW",
    0x1B: "PEI_DEPEX", 0x1C: "SMM_DEPEX",
}

PAD_FFS_TYPE = 0xF0

FFS_TYPE_NAMES = {
    0x01: "RAW", 0x02: "FREEFORM", 0x03: "SECURITY_CORE", 0x04: "PEI_CORE", 0x05: "DXE_CORE",
    0x06: "PEIM", 0x07: "DRIVER", 0x08: "COMBINED_PEIM_DRIVER", 0x09: "APPLICATION",
    0x0A: "SMM", 0x0B: "FIRMWARE_VOLUME_IMAGE", 0x0C: "COMBINED_SMM_DXE",
    0x0D: "SMM_CORE", 0x0F: "MM_STANDALONE", 0xF0: "PAD",
}

LZMA_GUID = "ee4e5898-3914-4259-9d6e-dc7bd79403cf"
TIANO_GUID = "a31280ad-481e-41b6-95e8-127f4c984779"


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def ui_name(data, limit=256):
    """Driver name from a UI section body (UTF-16LE, NUL-terminated)."""
    text = data[:limit]
    if len(text) % 2:
        text = text[:-1]
    try:
        decoded = text.decode("utf-16-le", "ignore")
    except Exception:
        return ""
    return decoded.split("\x00")[0].strip()


def parse_sections(data, start, end, report, depth):
    """Walk the section chain of one FFS file."""
    pos = start
    while pos + 4 <= end:
        raw = struct.unpack_from("<I", data, pos)[0]
        size = raw & 0xFFFFFF
        stype = (raw >> 24) & 0xFF
        if size < 4 or pos + size > end:
            return
        entry = {"offset": pos, "type": stype, "name": SECTION_NAMES.get(stype, f"0x{stype:02X}"),
                 "size": size}
        if stype == SECTION_UI:
            entry["ui"] = ui_name(data[pos + 4:pos + size])
            report["ui_names"].append(entry["ui"])
        elif stype == SECTION_GUID_DEFINED:
            guid = str(uuid.UUID(bytes_le=data[pos + 4:pos + 20]))
            data_offset, attributes = struct.unpack_from("<HH", data, pos + 20)
            entry.update(guid=guid, data_offset=data_offset, attributes=attributes)
            entry["algorithm"] = ("lzma" if guid == LZMA_GUID else
                                  "tiano" if guid == TIANO_GUID else "unknown")
        elif stype == SECTION_FV_IMAGE:
            report["sections"].append(entry)
            parse_volume(data, pos + 4, pos + size, report, depth + 1)
            pos += align(size, 4)
            continue
        report["sections"].append(entry)
        pos += align(size, 4)


def parse_ffs(data, offset, report, depth):
    """One FFS file: header, name, size, then its section chain."""
    if offset + 24 > len(data):
        return None
    name = data[offset:offset + 16]
    attributes = data[offset + 19]
    size = data[offset + 20] | (data[offset + 21] << 8) | (data[offset + 22] << 16)
    header_size = 24
    if size == 0xFFFFFF:  # FFS_FILE_HEADER2 carries a 64-bit size
        if offset + 32 > len(data):
            return None
        size = struct.unpack_from("<Q", data, offset + 24)[0]
        header_size = 32
    if size < header_size or offset + size > len(data):
        return None
    file_type = data[offset + 18]
    # A PAD file has an all-0xFF name and type 0xF0; free space runs to the end of the FV
    # and reads as 0xFF through the size field. Skipping the pad by its recorded size is
    # what keeps the chain going — treating 0xFF as "end" stops at the first pad, and every
    # EDK II volume starts with one.
    if name == b"\xff" * 16 and file_type == PAD_FFS_TYPE:
        return align(size, 8)
    if name == b"\xff" * 16:
        return None
    entry = {
        "offset": offset,
        "guid": str(uuid.UUID(bytes_le=name)),
        "type": file_type,
        "type_name": FFS_TYPE_NAMES.get(file_type, f"0x{file_type:02X}"),
        "size": size,
        "attributes": attributes,
        "depth": depth,
    }
    report["files"].append(entry)
    report["ui_names"] = []
    parse_sections(data, offset + header_size, offset + size, report, depth)
    entry["ui"] = report["ui_names"][-1] if report["ui_names"] else ""
    entry["sections"] = [s for s in report["sections"] if s.get("_file") is entry]
    return align(size, 8)


def plausible_volume(data, base, limit):
    """Cheap FV test: signature, sane header length, length that fits the image.

    The leading 16-byte zero vector is *not* usable as a test — EDK II's own output can
    carry non-zero bytes there (the image we build has `00 04 00 14` at offset 0).
    """
    if base < 0 or base + 56 > limit:
        return False
    if data[base + 40:base + 44] != FV_SIGNATURE:
        return False
    header_size = struct.unpack_from("<H", data, base + 48)[0]
    if not 0x38 <= header_size <= 0x1000:
        return False
    volume_size = struct.unpack_from("<Q", data, base + 32)[0]
    return volume_size == 0 or volume_size >= header_size


def parse_volume(data, base, limit, report, depth=0):
    """One FV: header, block map, then an FFS chain."""
    if not plausible_volume(data, base, limit):
        return
    guid = str(uuid.UUID(bytes_le=data[base + 16:base + 32]))
    volume_size = struct.unpack_from("<Q", data, base + 32)[0]
    header_size = struct.unpack_from("<H", data, base + 48)[0]
    attributes = struct.unpack_from("<I", data, base + 44)[0]
    extent = min(base + volume_size, limit) if volume_size else limit
    volume = {"offset": base, "length": extent - base, "guid": guid,
              "header_size": header_size, "attributes": attributes, "depth": depth}
    report["volumes"].append(volume)
    pos = base + header_size
    while pos + 24 <= extent:
        step = parse_ffs(data, pos, report, depth)
        if step is None:
            break
        pos += step


def scan(data):
    report = {"volumes": [], "files": [], "sections": []}
    seen = set()
    pos = 0
    while True:
        found = data.find(FV_SIGNATURE, pos)
        if found < 0:
            break
        base = found - 40
        pos = found + 1
        if base in seen or not plausible_volume(data, base, len(data)):
            continue
        seen.add(base)
        parse_volume(data, base, len(data), report)
        for volume in report["volumes"]:
            seen.add(volume["offset"])
    return report


def dump(report, show_sections):
    for volume in report["volumes"]:
        indent = "  " * volume["depth"]
        print(f'{indent}FV @0x{volume["offset"]:X} len=0x{volume["length"]:X} '
              f'guid={volume["guid"]} hdr=0x{volume["header_size"]:X}')
    if not show_sections:
        return
    for entry in report["files"]:
        indent = "  " * entry["depth"]
        name = f' "{entry["ui"]}"' if entry.get("ui") else ""
        print(f'{indent}  FFS @0x{entry["offset"]:X} {entry["type_name"]:<16} '
              f'size=0x{entry["size"]:X} {entry["guid"]}{name}')
        file_sections = [s for s in report["sections"]
                         if entry["offset"] < s["offset"] < entry["offset"] + entry["size"]]
        for section in file_sections:
            extra = ""
            if section["type"] == SECTION_GUID_DEFINED:
                extra = f' {section["guid"]} {section["algorithm"]} data_offset=0x{section["data_offset"]:X}'
            elif section["type"] == SECTION_UI:
                extra = f' "{section.get("ui", "")}"'
            print(f'{indent}     {section["name"]:<12} size=0x{section["size"]:X}{extra}')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--names", action="store_true", help="one line per FFS file")
    parser.add_argument("--extract-guided", type=Path, metavar="DIR",
                        help="write guided-section payloads (feed them to tools/bin/lzma-decode)")
    parser.add_argument("--extract-pe", type=Path, metavar="DIR",
                        help="write PE32 sections as DIR/<name>/<guid>.efi")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    data = args.image.read_bytes()
    report = scan(data)

    if not report["volumes"]:
        sys.exit(f"{args.image}: no firmware volume found")

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return

    if args.names:
        for entry in report["files"]:
            print(f'{entry["type_name"]:<16} {entry["guid"]} {entry["size"]:>9} {entry.get("ui", "")}')
    elif not args.quiet:
        dump(report, show_sections=True)
        named = sum(1 for entry in report["files"] if entry.get("ui"))
        print(f'\n{len(report["volumes"])} volumes, {len(report["files"])} files, '
              f'{named} with a UI name')

    if args.extract_guided:
        args.extract_guided.mkdir(parents=True, exist_ok=True)
        written = 0
        for volume in report["volumes"]:
            pass
        for section in report["sections"]:
            if section["type"] != SECTION_GUID_DEFINED:
                continue
            start = section["offset"] + section["data_offset"]
            end = section["offset"] + section["size"]
            payload = data[start:end]
            out = args.extract_guided / f'{section["algorithm"]}-{start:08X}.bin'
            out.write_bytes(payload)
            written += 1
        print(f"wrote {written} guided payloads to {args.extract_guided}")

    if args.extract_pe:
        args.extract_pe.mkdir(parents=True, exist_ok=True)
        written = 0
        for entry in report["files"]:
            file_sections = [s for s in report["sections"]
                             if entry["offset"] < s["offset"] < entry["offset"] + entry["size"]]
            for section in file_sections:
                if section["type"] not in (SECTION_PE32, SECTION_PIC, SECTION_TE):
                    continue
                name = entry.get("ui") or entry["guid"]
                out = args.extract_pe / name / f'{entry["guid"]}.efi'
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data[section["offset"] + 4:section["offset"] + section["size"]])
                written += 1
        print(f"wrote {written} PE images to {args.extract_pe}")


if __name__ == "__main__":
    main()
