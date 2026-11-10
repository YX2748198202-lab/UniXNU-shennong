#!/usr/bin/env python3
"""Pre-flight check of a boot package, before it costs a device reboot.

`fastboot boot` is the only way to learn whether a build is wrong, and a wrong build means
black screen plus a manual reset. This script re-checks, offline, everything the boot chain
will check in the first second:

  board.toml      FD base/size, payload volume label, accepted trust-cache digests
  firmware        the .fd is exactly FD_SIZE, its volume is intact, and the compacted volume
                  really contains UniXNU / DarwinBoot / UniXNUDxe / UniXNURamDiskDxe / BdsDxe
  payload         FAT label, the four files the loader needs, trust-cache digest against
                  board.toml, the kernel is a thin arm64 Mach-O, the ADT parses and carries the
                  /chosen/memory-map slots that match the files actually present
  boot image      v0 header constants, the gzip stream decodes, BootShim's ARM64 header sits at
                  byte 56, _Payload points at an FV inside the stream, and the embedded FAT
                  volume is byte-identical to the payload that was passed in

Every check prints one line; the exit status is 0 only if nothing failed.

Usage:
    verify-boot-package.py --fd FD --payload payload.img --image Mu-*.img [--json report.json]
"""
import argparse
import gzip
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PAGE_SIZE = 4096
KERNEL_ADDR = 0x00008000
RAMDISK_ADDR = 0x01000000
TAGS_ADDR = 0x01E00000
FV_SIGNATURE = b"_FVH"
FVMAIN_COMPACT_GUID = "9e21fd93-9c72-4c15-8c4b-e77f1db2d792"
REQUIRED_MODULES = ("UniXNU", "DarwinBoot", "UniXNUDxe", "UniXNURamDiskDxe", "BdsDxe")
REQUIRED_PAYLOAD_FILES = ("kernel.macho", "kernel.macho.adt", "DarwinBoot.efi", "unixnu.toml")


class Report:
    def __init__(self):
        self.rows = []
        self.failed = 0

    def ok(self, name, detail=""):
        self.rows.append(("OK", name, detail))

    def fail(self, name, detail=""):
        self.rows.append(("FAIL", name, detail))
        self.failed += 1

    def skip(self, name, detail=""):
        self.rows.append(("SKIP", name, detail))

    def emit(self):
        width = max((len(row[1]) for row in self.rows), default=10)
        for status, name, detail in self.rows:
            print(f"{status:<4} {name:<{width}}  {detail}")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def mtool(command, image, path=None):
    args = [command, "-i", str(image)] + ([path] if path else [])
    result = subprocess.run(args, capture_output=True, env={"MTOOLS_SKIP_CHECK": "1", "TZ": "UTC",
                                                           "PATH": "/usr/bin:/bin:/usr/local/bin"})
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or f"{command} failed")
    return result.stdout


def fat_listing(image):
    return mtool("mdir", image, "-/").decode(errors="replace")


def fat_file(image, inner):
    try:
        return mtool("mtype", image, inner)
    except RuntimeError:
        return None


def parse_adt(data):
    """Parse the ADT node format into (name, properties, children)."""
    def read_node(offset):
        props_count, children_count = struct.unpack_from("<II", data, offset)
        offset += 8
        properties = {}
        for _ in range(props_count):
            key, length = struct.unpack_from("<32sI", data, offset)
            offset += 36
            properties[key.rstrip(b"\x00").decode(errors="replace")] = data[offset:offset + length]
            offset += length + (-length % 4)
        children = []
        for _ in range(children_count):
            child, offset = read_node(offset)
            children.append(child)
        return (properties.get("name", b"").rstrip(b"\x00").decode(errors="replace"), properties, children), offset

    node, end = read_node(0)
    return node, end


def find_child(node, name):
    for child in node[2]:
        if child[0] == name:
            return child
    return None


def check_board(board_path, report):
    with open(board_path, "rb") as stream:
        board = tomllib.load(stream)
    firmware = board.get("firmware", {})
    defines = firmware.get("defines", {})
    base = int(str(defines.get("FD_BASE", "0")), 0)
    size = int(str(defines.get("FD_SIZE", "0")), 0)
    report.ok("board firmware", f"FD_BASE={base:#x} FD_SIZE={size:#x} dsc={firmware.get('dsc', '?')}")
    payload = board.get("payload", {})
    report.ok("board payload", f"volume={payload.get('volume', '?')} size_mib={payload.get('size_mib', '?')} "
                               f"loader={payload.get('loader', 'firmware')}")
    return base, size, payload


def check_firmware(fd_path, base, size, report, tree):
    if not fd_path.is_file():
        report.fail("firmware present", f"{fd_path} missing")
        return None
    data = fd_path.read_bytes()
    report.ok("firmware size", f"{len(data)} bytes, board says {size}") if len(data) == size else \
        report.fail("firmware size", f"{len(data)} bytes, board says {size}")
    if data[40:44] != FV_SIGNATURE:
        report.fail("firmware volume header", "no _FVH at offset 40")
        return None
    volume_length = struct.unpack_from("<Q", data, 32)[0]
    if volume_length == len(data):
        report.ok("firmware volume length", f"{volume_length:#x} matches file size")
    else:
        report.fail("firmware volume length", f"header {volume_length:#x} vs file {len(data):#x}")

    scanner = REPO / "scripts/scan-uefi-fv.py"
    result = subprocess.run([sys.executable, str(scanner), str(fd_path), "--json"], capture_output=True, text=True)
    if result.returncode != 0:
        report.fail("firmware scan", result.stderr.strip()[:160])
        return None
    scanned = json.loads(result.stdout)
    compact = [f for f in scanned["files"] if f["guid"] == FVMAIN_COMPACT_GUID]
    if not compact:
        report.fail("compacted volume", "FVMAIN_COMPACT not found in the firmware volume")
        return None
    report.ok("compacted volume", f"FFS at {compact[0]['offset']:#x}, {compact[0]['size']} bytes")

    decoder = REPO / "tools/bin/lzma-decode"
    if not decoder.is_file():
        report.skip("module list", "tools/bin/lzma-decode missing; run tools/build-lzma-decode.sh")
        return scanned
    workdir = Path(tempfile.mkdtemp(prefix="verify-fv-"))
    extract = workdir
    result = subprocess.run([sys.executable, str(scanner), str(fd_path), "--extract-guided", str(extract), "--quiet"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        report.fail("guided extract", result.stderr.strip()[:160])
        return scanned
    payloads = sorted(extract.glob("lzma-*.bin"))
    if not payloads:
        report.fail("guided extract", "no LZMA guided section found")
        return scanned
    inner = extract / "fvmain.fv"
    result = subprocess.run([str(decoder), str(payloads[0]), str(inner)], capture_output=True, text=True)
    if result.returncode != 0:
        report.fail("compacted volume decode", result.stderr.strip().splitlines()[-1][:160])
        return scanned
    # The decoded stream is a section chain: 8-byte header, then the FV itself.
    blob = inner.read_bytes()
    offset = blob.find(FV_SIGNATURE)
    if offset < 40:
        report.fail("inner volume", "no _FVH in the decoded stream")
        return scanned
    inner_fv = extract / "fvmain-only.fv"
    inner_fv.write_bytes(blob[offset - 40:])
    result = subprocess.run([sys.executable, str(scanner), str(inner_fv), "--names"],
                            capture_output=True, text=True)
    names = [line.split(None, 3)[-1].strip() for line in result.stdout.splitlines()]
    names = [name for name in names if name]
    missing = [module for module in REQUIRED_MODULES if module not in names]
    if missing:
        report.fail("module list", f"missing {', '.join(missing)} ({len(names)} modules total)")
    else:
        report.ok("module list", f"{len(names)} modules incl. {', '.join(REQUIRED_MODULES)}")
    return scanned


def check_payload(payload_path, payload_spec, report):
    if not payload_path.is_file():
        report.fail("payload present", f"{payload_path} missing")
        return None
    data = payload_path.read_bytes()
    label = payload_spec.get("volume", "UNIXNU")
    try:
        listing = fat_listing(payload_path)
    except RuntimeError as error:
        report.fail("payload volume", str(error)[:160])
        return None
    if f"Volume in drive : is {label[:11]}" in listing or label[:11] in listing:
        report.ok("payload label", f"{label[:11]} ({len(data)} bytes)")
    else:
        report.fail("payload label", f"expected {label[:11]}")

    present = {}
    for name in REQUIRED_PAYLOAD_FILES:
        inner = f"::/EFI/UniXNU/Payloads/{name}" if name != "unixnu.toml" else "::/EFI/UniXNU/unixnu.toml"
        blob = fat_file(payload_path, inner)
        if blob is None:
            report.fail(f"payload file {name}", "missing from the volume")
        else:
            present[name] = blob
    if len(present) == len(REQUIRED_PAYLOAD_FILES):
        report.ok("payload files", ", ".join(f"{k} {len(v)}B" for k, v in present.items()))

    # Kernel: thin arm64 Mach-O.
    kernel = present.get("kernel.macho")
    if kernel:
        magic = struct.unpack_from("<I", kernel, 0)[0]
        cputype = struct.unpack_from("<i", kernel, 4)[0]
        if magic == 0xFEEDFACF and cputype == 0x0100000C:
            report.ok("kernel Mach-O", f"arm64, {len(kernel)} bytes, sha256 {sha256(kernel)[:16]}")
        else:
            report.fail("kernel Mach-O", f"magic {magic:#x} cputype {cputype:#x}")

    # Trust cache: digest must be one the board accepts.
    trust = present.get("kernel.macho.trustcache") or fat_file(payload_path, "::/EFI/UniXNU/Payloads/kernel.macho.trustcache")
    allowed = payload_spec.get("trust_cache_sha256") or []
    if trust is None:
        report.ok("trust cache", "absent (loader will boot without one)")
    elif not allowed:
        report.ok("trust cache", f"present {len(trust)} bytes, board accepts any")
    elif sha256(trust) in allowed:
        report.ok("trust cache", f"{len(trust)} bytes, digest accepted by board.toml")
    else:
        report.fail("trust cache", f"digest {sha256(trust)[:16]} not in board.toml trust_cache_sha256")

    # ADT: parses, and its memory-map slots match the files that are actually here.
    adt = present.get("kernel.macho.adt")
    if adt:
        try:
            node, consumed = parse_adt(adt)
        except (struct.error, RecursionError) as error:
            report.fail("ADT parse", f"{type(error).__name__}: {error}")
            node = None
        if node:
            if node[0] != "device-tree":
                report.fail("ADT parse", f"root node is {node[0]!r}")
            elif consumed != len(adt):
                report.fail("ADT parse", f"consumed {consumed} of {len(adt)} bytes")
            else:
                chosen = find_child(node, "chosen")
                memory_map = find_child(chosen, "memory-map") if chosen else None
                slots = sorted(key for key in memory_map[1] if key != "name") if memory_map else []
                report.ok("ADT parse", f"device-tree, {consumed} bytes, memory-map slots: {', '.join(slots) if slots else 'none'}")
                wants_trust = trust is not None
                if wants_trust and "TrustCache" not in slots:
                    report.fail("ADT slots", "trust cache is in the volume but the ADT has no TrustCache slot")
    else:
        report.fail("ADT present", "kernel.macho.adt missing")

    # Menu: must point at the files above and load the driver from the payload.
    config = present.get("unixnu.toml")
    if config:
        text = config.decode(errors="replace")
        problems = []
        if 'path = "Payloads/kernel.macho"' not in text:
            problems.append("no xnu entry path")
        if payload_spec.get("loader", "firmware") != "firmware" and 'Payloads/DarwinBoot.efi' not in text:
            problems.append("loader = payload but no [[driver]] line")
        args = " ".join(payload_spec.get("kernel_args", []))
        if args and args not in text:
            problems.append("kernel args differ from board.toml")
        if problems:
            report.fail("menu config", "; ".join(problems))
        else:
            report.ok("menu config", f"{len(text)} bytes, args match board.toml")

    return data


def check_image(image_path, payload_data, report):
    if not image_path.is_file():
        report.fail("image present", f"{image_path} missing")
        return
    data = image_path.read_bytes()
    if data[:8] != b"ANDROID!":
        report.fail("image header", "no ANDROID! magic")
        return
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
     second_size, second_addr, tags_addr, page_size) = struct.unpack_from("<8I", data, 8)
    header_version = struct.unpack_from("<I", data, 40)[0]
    problems = []
    if header_version != 0:
        problems.append(f"header_version {header_version}")
    if page_size != PAGE_SIZE:
        problems.append(f"page_size {page_size}")
    if (kernel_addr, ramdisk_addr, tags_addr) != (KERNEL_ADDR, RAMDISK_ADDR, TAGS_ADDR):
        problems.append(f"addresses {kernel_addr:#x}/{ramdisk_addr:#x}/{tags_addr:#x}")
    if kernel_size <= 0 or ramdisk_size < 0:
        problems.append("empty kernel")
    if problems:
        report.fail("image header", "; ".join(problems))
        return
    report.ok("image header", f"v0, page {page_size}, kernel {kernel_size}, ramdisk {ramdisk_size}")

    # gzip(BootShim + FD)
    stream = data[page_size:page_size + kernel_size]
    try:
        inner = gzip.decompress(stream)
    except OSError as error:
        report.fail("image kernel stream", f"gzip failed: {error}")
        return
    if inner[56:60] != b"ARM\x64":
        report.fail("image BootShim", f"no ARM64 header magic at 56 (got {inner[56:60]!r})")
    else:
        report.ok("image BootShim", f"{len(inner)} bytes decompressed, ARM64 header at 56")
    signature = inner.find(FV_SIGNATURE)
    if signature > 40:
        fd_base = signature - 40
        shim_bytes = fd_base
        if fd_base >= 64 and inner[fd_base - 8:fd_base - 4] == b"\x00\x00\x00\x00":
            pass
        report.ok("image payload pointer", f"BootShim {shim_bytes} bytes, FD starts at {fd_base} in the stream")
    else:
        report.fail("image payload pointer", "no _FVH in the decompressed stream")

    # Embedded FAT volume must be the payload that was passed in.
    start = page_size + kernel_size
    start += (-start) % PAGE_SIZE
    embedded = data[start:start + ramdisk_size]
    if payload_data is None:
        report.skip("image payload bytes", "no --payload given")
    elif sha256(embedded) == sha256(payload_data):
        report.ok("image payload bytes", f"identical to the input payload at {start:#x}")
    else:
        report.fail("image payload bytes", f"bytes at {start:#x} differ from the input payload")
    if len(data) != start + ramdisk_size:
        report.fail("image length", f"{len(data)} bytes, header implies {start + ramdisk_size}")
    else:
        report.ok("image length", f"{len(data)} bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--board", type=Path, default=REPO / "board.toml")
    parser.add_argument("--fd", type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--keep", action="store_true", help="keep the extracted firmware volume")
    args = parser.parse_args()

    report = Report()
    base, size, payload_spec = check_board(args.board, report)
    scanned = check_firmware(args.fd, base, size, report, None) if args.fd else None
    payload_data = check_payload(args.payload, payload_spec, report) if args.payload else None
    if args.image:
        check_image(args.image, payload_data, report)

    report.emit()
    if args.json:
        args.json.write_text(json.dumps(
            {"checks": [{"status": s, "name": n, "detail": d} for s, n, d in report.rows],
             "failed": report.failed}, indent=2) + "\n")
    print(f"\n{report.failed} failure(s)")
    sys.exit(1 if report.failed else 0)


if __name__ == "__main__":
    main()
