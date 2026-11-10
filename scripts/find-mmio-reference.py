#!/usr/bin/env python3
"""Name the module behind a data abort without another device round trip.

The phone prints `FAR 0x...` and `ELR 0x...` when our UEFI faults, but not the
module that was executing.  AArch64 reaches a fixed physical address through a
PC-relative `adrp` pair, so the page of every referenced address is encoded in
the module's machine code.  Scanning the `.text` of every PE image in the FD for
an `adrp` that lands on the faulting page therefore names the culprit offline.

usage: find-mmio-reference.py --fd FD --address 0x8E2000 [--rva 0x6E50]
"""

import argparse
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load_scanner():
    spec = importlib.util.spec_from_file_location("scan_uefi_fv", HERE / "scan-uefi-fv.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pe_text_sections(data, offset):
    """(.text raw bytes, its RVA) pairs for the PE image that starts at offset."""
    if data[offset:offset + 2] != b"MZ":
        return []
    pe = offset + struct.unpack_from("<I", data, offset + 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    section_count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    result = []
    for index in range(section_count):
        header = table + index * 40
        name = data[header:header + 8].rstrip(b"\0").decode("latin-1")
        if name not in (".text", "text"):
            continue
        virtual_size, virtual_address = struct.unpack_from("<II", data, header + 8)
        raw_size, raw_pointer = struct.unpack_from("<II", data, header + 16)
        size = min(virtual_size or raw_size, raw_size)
        if size:
            result.append((data[raw_pointer:raw_pointer + size], virtual_address))
    return result


def adrp_target(word, pc):
    if word & 0x9F000000 != 0x90000000:
        return None
    immlo = (word >> 29) & 3
    immhi = (word >> 5) & 0x7FFFF
    immediate = (immhi << 2) | immlo
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return ((pc & ~0xFFF) + (immediate << 12)) & 0xFFFFFFFFFFFFFFFF


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fd", required=True)
    parser.add_argument("--address", action="append", required=True,
                        help="physical address whose page is searched (hex, may repeat)")
    parser.add_argument("--rva", type=lambda value: int(value, 0), default=None,
                        help="faulting RVA inside the module (hex); hits near it rank first")
    args = parser.parse_args()

    scanner = load_scanner()
    data = pathlib.Path(args.fd).read_bytes()
    report = scanner.scan(data)
    pages = {int(address, 0) & ~0xFFF for address in args.address}

    hits = []
    for entry in report["files"]:
        pe_offset = None
        for section in entry["sections"]:
            if section["type"] == scanner.SECTION_PE32:
                pe_offset = section["offset"] + 4
                break
        if pe_offset is None:
            continue
        for body, section_rva in pe_text_sections(data, pe_offset):
            for offset in range(0, len(body) - 4, 4):
                word = struct.unpack_from("<I", body, offset)[0]
                rva = section_rva + offset
                target = adrp_target(word, rva)
                if target in pages:
                    hits.append({
                        "ui": entry.get("ui", ""),
                        "guid": entry["guid"],
                        "rva": rva,
                        "target": target,
                        "near": args.rva is not None and abs(rva - args.rva) <= 0x400,
                    })

    if not hits:
        print(f"no adrp references pages {sorted(hex(page) for page in pages)} in {args.fd}")
        return 1
    print(f"{len(hits)} adrp reference(s) to {sorted(hex(page) for page in pages)}:")
    for hit in sorted(hits, key=lambda item: (not item["near"], item["guid"], item["rva"])):
        mark = "  <== within 0x400 of the faulting RVA" if hit["near"] else ""
        name = hit["ui"] or "(no UI section)"
        print(f"  {name:<28} {hit['guid']}  rva 0x{hit['rva']:06X} -> 0x{hit['target']:X}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
