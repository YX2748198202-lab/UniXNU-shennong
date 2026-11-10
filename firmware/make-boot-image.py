#!/usr/bin/env python3
"""Pack a rebuilt UEFI firmware volume into a v0 Android boot image that BootShim runs.

The layout was recovered from the known-good Mu-shennong image this port already boots:

    file  = 4096-byte header page | gzip(BootShim + FD) | payload FAT volume
    header: v0, kernel_addr 0x8000, ramdisk_addr 0x1000000, tags_addr 0x1e00000

BootShim.S copies FD_SIZE bytes from its own _Payload label to FD_BASE and jumps there, so the
compressed kernel must be exactly shim.bin followed by the firmware volume, and the volume must
be FD_SIZE bytes long (the compile-time constant the shim compares with).

The header constants are the documented ones above, so the image no longer needs a known-good
template; `--template` is still accepted to copy a header (and to check that the constants have
not drifted). `--verify` re-reads the produced file and re-checks the whole layout, which is how
a rebuilt firmware gets a byte-level acceptance check before it touches the phone.

Usage:
    make-boot-image.py --uefi <Mu tree> --fd SILICIUM_UEFI.fd --payload payload.img --out Mu-shennong.img
    make-boot-image.py ... --template Mu-shennong-old.img     # copy header fields from a known image
    make-boot-image.py ... --out Mu-shennong.img --verify     # unpack and check what was written
"""
import argparse
import gzip
import hashlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

FD_BASE = 0xA7100000
FD_SIZE = 0x300000

PAGE_SIZE = 4096
KERNEL_ADDR = 0x00008000
RAMDISK_ADDR = 0x01000000
TAGS_ADDR = 0x01E00000
BOARD_NAME = b"UniXNU-shennong"


def align(value, page=PAGE_SIZE):
    return (value + page - 1) // page * page


def compile_shim(uefi: Path, scratch: Path) -> bytes:
    source = uefi / "BootShim/BootShim.S"
    if not source.is_file():
        sys.exit("missing %s" % source)
    obj = scratch / "shim.o"
    bin_ = scratch / "shim.bin"
    subprocess.run(["clang", "--target=aarch64-none-elf", "-c", "-DFD_BASE=%#x" % FD_BASE,
                    "-DFD_SIZE=%#x" % FD_SIZE, "-DREQUIRES_KERNEL_HEADER=1",
                    str(source), "-o", str(obj)], check=True)
    subprocess.run(["llvm-objcopy", "-O", "binary", str(obj), str(bin_)], check=True)
    shim = bin_.read_bytes()
    names = subprocess.run(["llvm-nm", "-n", str(obj)], check=True, capture_output=True, text=True).stdout
    payload = next((int(line.split()[0], 16) for line in names.splitlines()
                    if line.endswith("_Payload")), None)
    if payload != len(shim):
        sys.exit("a literal pool or padding separates _Payload (%s) from the shim end (%d)"
                 % (payload, len(shim)))
    if shim[56:60] != b"ARM\x64":
        sys.exit("the ARM64 image header did not land at offset 56")
    base, size = struct.unpack_from("<QQ", shim, 8)
    if base != FD_BASE or size != len(shim) + FD_SIZE:
        sys.exit("shim header describes %#x/%d, expected %#x/%d"
                 % (base, size, FD_BASE, len(shim) + FD_SIZE))
    return shim


def read_template(path: Path):
    """Header fields from a known-good image, for cross-checking the constants above."""
    tmpl = path.read_bytes()[:PAGE_SIZE]
    if tmpl[:8] != b"ANDROID!":
        sys.exit("template is not an Android boot image")
    (_, kernel_addr, _, ramdisk_addr, _, _, tags_addr, page) = struct.unpack_from("<8I", tmpl, 8)
    version = struct.unpack_from("<I", tmpl, 40)[0]
    if version != 0 or page != PAGE_SIZE:
        sys.exit("template must be a v0 image with 4096-byte pages (got v%d, %d)" % (version, page))
    if (kernel_addr, ramdisk_addr, tags_addr) != (KERNEL_ADDR, RAMDISK_ADDR, TAGS_ADDR):
        sys.exit("template addresses %#x/%#x/%#x differ from the documented %#x/%#x/%#x"
                 % (kernel_addr, ramdisk_addr, tags_addr, KERNEL_ADDR, RAMDISK_ADDR, TAGS_ADDR))
    return tmpl


def build(image: Path):
    data = image.read_bytes()
    if len(data) < PAGE_SIZE or data[:8] != b"ANDROID!":
        sys.exit("%s is not an Android boot image" % image)
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
     second_size, second_addr, tags_addr, page) = struct.unpack_from("<8I", data, 8)
    version, os_version = struct.unpack_from("<II", data, 40)
    problems = []
    if version != 0:
        problems.append("header version %d, expected 0" % version)
    if page != PAGE_SIZE:
        problems.append("page size %d, expected %d" % (page, PAGE_SIZE))
    if (kernel_addr, ramdisk_addr, tags_addr) != (KERNEL_ADDR, RAMDISK_ADDR, TAGS_ADDR):
        problems.append("addresses %#x/%#x/%#x, expected %#x/%#x/%#x"
                        % (kernel_addr, ramdisk_addr, tags_addr, KERNEL_ADDR, RAMDISK_ADDR, TAGS_ADDR))
    if second_size or second_addr:
        problems.append("second stage present (%d bytes @ %#x)" % (second_size, second_addr))
    kernel = data[PAGE_SIZE:PAGE_SIZE + kernel_size]
    if not kernel.startswith(b"\x1f\x8b"):
        problems.append("kernel section is not gzip")
    else:
        raw = gzip.decompress(kernel)
        if len(raw) < FD_SIZE:
            problems.append("decompressed kernel %d bytes, shorter than the firmware volume" % len(raw))
        else:
            fd = raw[len(raw) - FD_SIZE:]
            if fd[40:44] != b"_FVH":
                problems.append("the last %#x bytes do not start with an FV header" % FD_SIZE)
            shim = raw[:len(raw) - FD_SIZE]
            base, size = struct.unpack_from("<QQ", shim, 8)
            if base != FD_BASE or size != len(raw):
                problems.append("shim header %#x/%d does not describe %#x/%d"
                                % (base, size, FD_BASE, len(raw)))
    payload_start = PAGE_SIZE + align(kernel_size)
    payload = data[payload_start:payload_start + ramdisk_size]
    if ramdisk_size and len(payload) != ramdisk_size:
        problems.append("ramdisk section truncated: %d of %d bytes" % (len(payload), ramdisk_size))
    if len(data) != payload_start + align(ramdisk_size):
        problems.append("file is %d bytes, layout says %d"
                        % (len(data), payload_start + align(ramdisk_size)))
    return problems, dict(kernel_size=kernel_size, ramdisk_size=ramdisk_size,
                          total=len(data), payload_offset=payload_start, os_version=os_version)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uefi", required=True, help="Mu-Silicium checkout that has BootShim/BootShim.S")
    ap.add_argument("--fd", required=True)
    ap.add_argument("--payload", help="payload FAT volume; omit for an empty ramdisk section")
    ap.add_argument("--template", help="known-good v0 image whose header is copied and checked")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true", help="re-read the output and check its layout")
    args = ap.parse_args()

    tmpl = read_template(Path(args.template)) if args.template else None
    if tmpl is None:
        print("no template: header built from the documented v0 constants")

    fd = Path(args.fd).read_bytes()
    if len(fd) != FD_SIZE:
        sys.exit("firmware volume is %d bytes, BootShim is built for %d; rebuild with matching FD_SIZE"
                 % (len(fd), FD_SIZE))
    if fd[40:44] != b"_FVH":
        sys.exit("%s does not start with an FV header" % args.fd)
    payload = Path(args.payload).read_bytes() if args.payload else b""

    with tempfile.TemporaryDirectory() as tmp:
        shim = compile_shim(Path(args.uefi), Path(tmp))
    raw = shim + fd
    kernel = gzip.compress(raw, 9, mtime=0)

    header = bytearray(PAGE_SIZE)
    header[0:8] = b"ANDROID!"
    struct.pack_into("<8I", header, 8, len(kernel), KERNEL_ADDR, len(payload), RAMDISK_ADDR,
                     0, 0, TAGS_ADDR, PAGE_SIZE)
    struct.pack_into("<I", header, 40, 0)          # header_version 0
    struct.pack_into("<I", header, 44, 0)          # os_version: not used by fastboot boot
    header[48:64] = BOARD_NAME.ljust(16, b"\x00")[:16]
    if tmpl is not None:
        header[48:64] = tmpl[48:64]
        header[64:64 + 512] = tmpl[64:64 + 512]

    out = bytes(header) + kernel + bytes(align(len(kernel)) - len(kernel)) + payload
    Path(args.out).write_bytes(out)
    print("shim %d bytes, firmware %d bytes, kernel %d bytes (gzip), payload %d bytes"
          % (len(shim), len(fd), len(kernel), len(payload)))
    print("written %s (%d bytes)" % (args.out, len(out)))
    print("sha256 %s" % hashlib.sha256(out).hexdigest())

    if args.verify:
        problems, info = build(Path(args.out))
        if problems:
            for problem in problems:
                print("verify: %s" % problem, file=sys.stderr)
            sys.exit("verification failed")
        print("verify: ok (kernel %d, ramdisk %d, payload at %#x, total %d)"
              % (info["kernel_size"], info["ramdisk_size"], info["payload_offset"], info["total"]))


if __name__ == "__main__":
    main()
