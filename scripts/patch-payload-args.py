#!/usr/bin/env python3
"""Edit /EFI/UniXNU/unixnu.toml inside a UniXNU payload FAT volume.

The payload produced by `unixnu payload` is an mtools-formatted FAT volume
with volume label UNIXNU (SHENNONGESP on shennong). The boot menu and the
kernel command line live in `::/EFI/UniXNU/unixnu.toml`, so small bootarg
changes do not require re-running the CI build.

This wrapper exists because the edit must be verified: mtools silently
keeps the old cluster chain in some layouts, and a stale file means the
board boots with the old command line while everything looks fine.

Requires mtools (`mcopy`, `mtype`) on PATH.

Usage
-----
    # inspect
    python3 patch-payload-args.py --payload payload.img --show

    # add a bootarg (inserted right after the anchor, which must exist)
    python3 patch-payload-args.py --payload payload.img \
        --add sheng-smp=1 --anchor sheng-pmgr=2

    # replace the whole args line
    python3 patch-payload-args.py --payload payload.img \
        --set-args "-v serial=3 debug=0x14e sheng-smp=1 sheng-pmgr=2"

The script reads the file back with `mtype` and fails if the change did not
land.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

TOML_PATH = "::/EFI/UniXNU/unixnu.toml"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def read_toml(image):
    r = run(["mtype", "-i", image, TOML_PATH])
    if r.returncode != 0:
        sys.exit("mtype failed: %s" % (r.stderr.strip() or r.stdout.strip()))
    return r.stdout


def write_toml(image, text):
    tmpdir = tempfile.mkdtemp(prefix="payload-toml-")
    path = os.path.join(tmpdir, "unixnu.toml")
    try:
        with open(path, "w", newline="\n") as fh:
            fh.write(text)
        r = run(["mcopy", "-o", "-i", image, path, TOML_PATH])
        if r.returncode != 0:
            sys.exit("mcopy failed: %s" % (r.stderr.strip() or r.stdout.strip()))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def get_args_line(text):
    for line in text.splitlines():
        if line.startswith("args"):
            return line
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    ap.add_argument("--show", action="store_true", help="print the file and exit")
    ap.add_argument("--add", help="bootarg to insert, e.g. sheng-smp=1")
    ap.add_argument("--anchor", help="insert --add immediately before this token")
    ap.add_argument("--set-args", help="replace the whole args value")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.payload):
        sys.exit("no such payload: %s" % args.payload)

    text = read_toml(args.payload)
    line = get_args_line(text)
    if line is None:
        sys.exit("no `args` line in %s" % TOML_PATH)
    print("current:", line)

    if args.show:
        print("--- file ---")
        print(text)
        return

    if not args.add and not args.set_args:
        sys.exit("nothing to do; use --add/--set-args/--show")

    if args.set_args:
        new_text = text.replace(line, 'args = "%s"' % args.set_args, 1)
    else:
        current = line.split("=", 1)[1].strip().strip('"')
        if args.add in current.split():
            print("already present, nothing to do")
            return
        anchor = args.anchor
        if anchor and anchor in current:
            updated = current.replace(anchor, "%s %s" % (args.add, anchor), 1)
        elif anchor:
            sys.exit("anchor %r not found in args" % anchor)
        else:
            updated = current + " " + args.add
        new_text = text.replace(line, 'args = "%s"' % updated, 1)

    if args.dry_run:
        print("--- would write ---")
        print(new_text)
        return

    write_toml(args.payload, new_text)

    back = read_toml(args.payload)
    new_line = get_args_line(back)
    print("after:  ", new_line)
    if new_line != get_args_line(new_text):
        sys.exit("verification failed: readback differs")
    print("ok")


if __name__ == "__main__":
    main()