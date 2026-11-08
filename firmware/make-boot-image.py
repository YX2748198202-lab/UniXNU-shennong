#!/usr/bin/env python3
"""Pack a rebuilt UEFI firmware volume into a v0 Android boot image that BootShim runs.

The layout was recovered from the known-good Mu-shennong image this port already boots:

    file  = 4096-byte header page | gzip(BootShim + FD) | payload FAT volume
    header: v0, kernel_addr 0x8000, ramdisk_addr 0x1000000, tags_addr 0x1e00000

BootShim.S copies FD_SIZE bytes from its own _Payload label to FD_BASE and jumps there, so the
compressed kernel must be exactly shim.bin followed by the firmware volume, and the volume must
be FD_SIZE bytes long (the compile-time constant the shim compares with).

Usage:
    make-boot-image.py --uefi <aloha tree> --fd <SM8650_EFI.fd> --payload <payload.img> \
        --template <known-good Mu-*.img> --out <new.img>
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


def align(value, page=4096):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uefi", required=True, help="Mu-Silicium checkout that has BootShim/BootShim.S")
    ap.add_argument("--fd", required=True)
    ap.add_argument("--payload", required=True)
    ap.add_argument("--template", required=True, help="known-good v0 image to copy the header constants from")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tmpl = Path(args.template).read_bytes()[:4096]
    if tmpl[:8] != b"ANDROID!":
        sys.exit("template is not an Android boot image")
    (_, kernel_addr, _, ramdisk_addr, _, _, tags_addr, page) = struct.unpack_from("<8I", tmpl, 8)
    version = struct.unpack_from("<I", tmpl, 40)[0]
    os_version = struct.unpack_from("<I", tmpl, 44)[0]
    if version != 0 or page != 4096:
        sys.exit("template must be a v0 image with 4096-byte pages (got v%d, %d)" % (version, page))

    fd = Path(args.fd).read_bytes()
    if len(fd) != FD_SIZE:
        sys.exit("firmware volume is %d bytes, BootShim is built for %d; rebuild with matching FD_SIZE"
                 % (len(fd), FD_SIZE))
    payload = Path(args.payload).read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        shim = compile_shim(Path(args.uefi), Path(tmp))
    raw = shim + fd
    kernel = gzip.compress(raw, 9, mtime=0)

    header = bytearray(4096)
    header[0:8] = b"ANDROID!"
    struct.pack_into("<8I", header, 8, len(kernel), kernel_addr, len(payload), ramdisk_addr,
                     0, 0, tags_addr, page)
    struct.pack_into("<I", header, 40, 0)
    struct.pack_into("<I", header, 44, os_version)
    header[48:64] = tmpl[48:64]
    header[64:64 + 512] = tmpl[64:64 + 512]

    out = bytes(header) + kernel + bytes(align(len(kernel)) - len(kernel)) + payload
    Path(args.out).write_bytes(out)
    print("shim %d bytes, firmware %d bytes, kernel %d bytes (gzip)" % (len(shim), len(fd), len(kernel)))
    print("written %s (%d bytes)" % (args.out, len(out)))
    print("sha256 %s" % hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    main()
