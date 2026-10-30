#!/usr/bin/env python3
"""Repack a UniXNU payload FAT volume into a v0 Android boot image.

Why this script exists
----------------------
`unixnu bootimg` has two traps (verified on 2026-10-30):

1. It emits a **v4** boot header. BootShim needs the v0 `ramdisk_addr`
   field, and v4 has no such field. A v4 image makes UniXNU report
   `no boot entry found` and UEFI end with `Failed to Find an Operating
   System`, because the payload FAT volume is never located.
2. Its `verify()` parses a v4 image with a v0 layout and always raises
   `boot image header does not match the requested parameters`, even
   though the file was written correctly.

So instead of shelling out to mkbootimg we reuse the header + kernel area
of a known-good v0 image and append a new ramdisk. This only works when
the new ramdisk is exactly the same length as the old one, which is the
case here: `unixnu payload` always produces a fixed 201,326,592 byte
(192 MiB) FAT volume.

Usage
-----
    python3 repack-v0-bootimg.py \
        --template Mu-shennong-6-pmgr2.img \
        --payload  payload.img \
        --out      Mu-shennong-new.img

The script prints the resulting sha256 and the parsed header so the result
can be checked before flashing.
"""

import argparse
import hashlib
import struct
import sys


def align(value, page):
    return (value + page - 1) // page * page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True,
                    help="known-good v0 boot image whose header+kernel are reused")
    ap.add_argument("--payload", required=True,
                    help="FAT volume produced by `unixnu payload`")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    old = open(args.template, "rb").read()
    pay = open(args.payload, "rb").read()

    if old[:8] != b"ANDROID!":
        sys.exit("template is not an Android boot image")

    (ksize, kaddr, rsize, raddr,
     ssize, saddr, tags, page) = struct.unpack_from("<8I", old, 8)
    version = struct.unpack_from("<I", old, 40)[0]

    print("template header:")
    print("  kernel_size=%d kernel_addr=%#x" % (ksize, kaddr))
    print("  ramdisk_size=%d ramdisk_addr=%#x" % (rsize, raddr))
    print("  tags=%#x page=%d header_version=%d" % (tags, page, version))

    if version != 0:
        sys.exit("template must be a v0 image, got v%d" % version)
    if len(pay) != rsize:
        sys.exit("payload is %d bytes but the header declares %d; "
                 "a size change would require rewriting the header"
                 % (len(pay), rsize))

    head_len = page + align(ksize, page)
    out = old[:head_len] + pay
    open(args.out, "wb").write(out)

    print("written %s (%d bytes)" % (args.out, len(out)))
    print("sha256   %s" % hashlib.sha256(out).hexdigest())
    print("ramdisk  %s" % hashlib.sha256(pay).hexdigest())

    # Re-parse the result so a truncated write cannot go unnoticed.
    check = open(args.out, "rb").read()
    (k2, ka2, r2, ra2, s2, sa2, t2, p2) = struct.unpack_from("<8I", check, 8)
    ok = (check[:8] == b"ANDROID!" and k2 == ksize and ka2 == kaddr
          and r2 == rsize and ra2 == raddr and s2 == 0 and p2 == page)
    print("header preserved:", ok)
    if not ok:
        sys.exit("header check failed")


if __name__ == "__main__":
    main()