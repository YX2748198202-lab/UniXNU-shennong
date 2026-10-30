#!/usr/bin/env python3
"""Extract the payload FAT volume (and optionally kernel.macho) from a
UniXNU boot image.

Because `unixnu payload` always emits a fixed 201,326,592 byte (192 MiB) FAT
volume, a boot image built by `scripts/repack-v0-bootimg.py` contains a
complete, byte-exact copy of that payload at a computable offset. That makes
a single flashed image self-sufficient: the payload and the kernel inside it
can always be recovered from it, even after the CI artifact expires.

Layout of a v0 boot image produced by this project:

    offset 0                                  header (v0, page = 4096)
    offset 4096                               kernel  = gzip(BootShim + UEFI FD)
    offset page + align(kernel_size, page)    ramdisk = payload FAT volume

Usage
-----
    # just the payload
    python3 extract-payload-from-bootimg.py --image Mu-shennong-smp.img \
        --out payload.img

    # payload + kernel.macho out of ::/EFI/UniXNU/Payloads/
    python3 extract-payload-from-bootimg.py --image Mu-shennong-smp.img \
        --out payload.img --kernel kernel.macho

`--kernel` needs mtools (`mcopy`) on PATH. The extracted kernel is the
post-prelink Mach-O, i.e. exactly what the loader executes.
"""

import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True, help="where to write the payload FAT volume")
    ap.add_argument("--kernel", help="also extract ::/EFI/UniXNU/Payloads/kernel.macho here")
    args = ap.parse_args()

    data = open(args.image, "rb").read()
    if data[:8] != b"ANDROID!":
        sys.exit("not an Android boot image")

    (ksize, kaddr, rsize, raddr,
     ssize, saddr, tags, page) = struct.unpack_from("<8I", data, 8)
    version = struct.unpack_from("<I", data, 40)[0]

    print("header: version=%d page=%d kernel=%d ramdisk=%d "
          "kernel_addr=%#x ramdisk_addr=%#x" %
          (version, page, ksize, rsize, kaddr, raddr))

    if version != 0:
        sys.exit("this helper assumes a v0 image (BootShim needs v0 ramdisk_addr)")

    off = page + (ksize + page - 1) // page * page
    payload = data[off:off + rsize]
    if len(payload) != rsize:
        sys.exit("image is truncated: wanted %d bytes of ramdisk at %d, got %d"
                 % (rsize, off, len(payload)))
    if payload[:2] != b"\xeb\x58":
        sys.exit("ramdisk does not look like a FAT volume")

    open(args.out, "wb").write(payload)
    print("payload  %s  %d bytes  sha256 %s" %
          (args.out, len(payload), hashlib.sha256(payload).hexdigest()))

    if args.kernel:
        tmpdir = tempfile.mkdtemp(prefix="payload-x-")
        vol = os.path.join(tmpdir, "payload.img")
        try:
            open(vol, "wb").write(payload)
            r = subprocess.run(
                ["mcopy", "-o", "-i", vol, "::/EFI/UniXNU/Payloads/kernel.macho", args.kernel],
                capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit("mcopy failed: %s" % (r.stderr.strip() or r.stdout.strip()))
        finally:
            try:
                os.remove(vol)
            except OSError:
                pass
            os.rmdir(tmpdir)
        blob = open(args.kernel, "rb").read()
        print("kernel   %s  %d bytes  sha256 %s" %
              (args.kernel, len(blob), hashlib.sha256(blob).hexdigest()))


if __name__ == "__main__":
    main()