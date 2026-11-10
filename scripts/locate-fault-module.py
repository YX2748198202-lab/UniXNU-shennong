#!/usr/bin/env python3
"""Map a faulting address back to the DXE module that owned it.

A data abort dump on shennong names ELR/FAR/LR but never the module: the
console holds about 40 lines and the dump needs about 60, so a printed trace is
always scrolled away.  BootTraceDxe works around that by storing the dispatch
order in an NV variable and replaying it, newest first, on the next boot.  The
lines on that screen look like

    BT 07 base 0x0cf8b1000 +0x000a54 DxeCore.efi

This script takes those lines (typed or pasted from the photograph), the fault
addresses, and reports the owning module plus the offset inside it, then can
disassemble around that offset with llvm-objdump.

    locate-fault-module.py --records BT.txt --address 0xcf8b6e60 --address 0xcf8a7588
    locate-fault-module.py --records BT.txt --address 0xcf8b6e60 --pe-dir /tmp/fv6/pe
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

RECORD = re.compile(
    r"BT\s+(?P<index>\d+)\s+base\s+(?P<base>0x[0-9a-fA-F]+)\s+\+\s*(?P<size>0x[0-9a-fA-F]+)\s+(?P<name>\S+)"
)


def parse_records(path: Path) -> list[dict]:
    """Return the dispatch records in the order they appear on screen."""
    records = []
    for line in path.read_text(errors="replace").splitlines():
        match = RECORD.search(line)
        if match is None:
            continue
        records.append(
            {
                "index": int(match.group("index")),
                "base": int(match.group("base"), 16),
                "size": int(match.group("size"), 16),
                "name": match.group("name"),
            }
        )
    return records


def owner_of(records: list[dict], address: int) -> tuple[dict | None, str]:
    """Find the module holding address.

    LoadedImage.ImageSize covers the whole allocation, so nested spans happen;
    the innermost (largest base) match is the module that actually owns the
    address.  A record whose size is implausible is still reported, because a
    wrong span is itself a finding.
    """
    candidates = [r for r in records if r["base"] <= address < r["base"] + r["size"]]
    if not candidates:
        above = [r for r in records if r["base"] <= address]
        hint = ""
        if above:
            nearest = max(above, key=lambda r: r["base"])
            hint = (
                f" (highest module below the address: {nearest['name']} "
                f"base 0x{nearest['base']:x} +0x{nearest['size']:x})"
            )
        return None, f"0x{address:x} is inside no recorded module{hint}"
    best = max(candidates, key=lambda r: r["base"])
    return best, ""


def disassemble(pe_dir: Path, module: str, rva: int, span: int) -> None:
    """Print the instructions around rva, and the nearest exported symbols."""
    tool = shutil.which("llvm-objdump") or shutil.which("aarch64-linux-gnu-objdump")
    if tool is None:
        print("no AArch64 disassembler on PATH", file=sys.stderr)
        return

    images = sorted((pe_dir / module).glob("*.efi"))
    if not images:
        print(f"no PE image for {module} under {pe_dir}", file=sys.stderr)
        return

    image = images[0]
    start = max(rva - span, 0)
    stop = rva + span
    command = [
        tool,
        "-d",
        "--triple=aarch64",
        f"--start-address=0x{start:x}",
        f"--stop-address=0x{stop:x}",
        str(image),
    ]
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    body = result.stdout or result.stderr
    for line in body.splitlines():
        text = line.rstrip()
        if re.match(r"^\s*[0-9a-f]+:", text):
            mark = "  <== fault" if f" {rva:x}:" in f" {text.strip().split(':')[0]}:" else ""
            print(f"{text}{mark}")
    if result.returncode != 0:
        print(f"disassembler exit {result.returncode}: {result.stderr.strip()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, required=True, help="text holding the BT replay lines")
    parser.add_argument("--address", type=lambda v: int(v, 16), action="append", required=True,
                        help="faulting address, hex, may repeat")
    parser.add_argument("--pe-dir", type=Path, help="directory of extracted PE images for disassembly")
    parser.add_argument("--span", type=int, default=0x30, help="bytes before and after the fault offset")
    args = parser.parse_args()

    records = parse_records(args.records)
    if not records:
        print(f"no BT lines found in {args.records}", file=sys.stderr)
        return 1

    print(f"{len(records)} dispatch records, lowest base 0x{min(r['base'] for r in records):x}, "
          f"highest end 0x{max(r['base'] + r['size'] for r in records):x}")

    missing = 0
    for address in args.address:
        owner, note = owner_of(records, address)
        if owner is None:
            print(f"0x{address:08x}  {note}")
            missing += 1
            continue
        rva = address - owner["base"]
        print(f"0x{address:08x}  {owner['name']}  base 0x{owner['base']:x} size 0x{owner['size']:x}  rva +0x{rva:x}")
        if args.pe_dir:
            disassemble(args.pe_dir, owner["name"], rva, args.span)

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
