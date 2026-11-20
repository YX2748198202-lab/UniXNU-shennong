#!/usr/bin/env python3
"""Compile and link small Darwin Mach-O fixtures, then run the layout check."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHECK = Path(__file__).with_name("check-console-layout.py")


def link(work, name, pointer_segment, pointer_section, *, move_const=False, omit_kputc=False):
    source, obj, image = (work / f"{name}{ext}" for ext in (".s", ".o", ".macho"))
    source.write_text(f"""\
.text
.globl _start
_start:
    ret
.section __DATA_CONST,__const
.globl _fixture_immutable
_fixture_immutable:
    .quad 42
.section {pointer_segment},{pointer_section}
.globl _PE_putc
_PE_putc:
    .quad 0
""" + ("" if omit_kputc else ".globl _PE_kputc\n_PE_kputc:\n    .quad 0\n"))
    subprocess.run(["clang", "--target=arm64-apple-macos14", "-c", str(source), "-o", str(obj)], check=True)
    linker = shutil.which("ld64.lld") or shutil.which("ld64.lld-18") or "ld64.lld"
    move = ["-rename_section", "__DATA_CONST", "__const", "__KLDDATA", "__const"] if move_const else []
    subprocess.run([linker, "-arch", "arm64", "-platform_version", "macos", "14.0", "14.0",
                    "-e", "_start", *move, "-o", str(image), str(obj)], check=True)
    return image


def run(image, status, lines):
    result = subprocess.run([sys.executable, str(CHECK), str(image)], capture_output=True, text=True)
    if result.returncode != status or not all(line in result.stdout for line in lines):
        raise AssertionError(f"{image.name}: expected exit {status} and {lines}; got {result.returncode}\n"
                             f"{result.stdout}{result.stderr}")


def main():
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # Existing behavior: indiscriminate rename moves startup writes too.
        bad = link(work, "coalesced", "__DATA_CONST", "__const", move_const=True)
        run(bad, 1, ("FAIL _PE_putc", "FAIL _PE_kputc", "(__KLDDATA,__const)"))
        # Separate late-initialized data before moving the immutable section.
        good = link(work, "split", "__DATA_CONST", "__late_const", move_const=True)
        run(good, 0, ("OK   _PE_putc", "OK   _PE_kputc", "(__DATA_CONST,__late_const)"))
        nm = subprocess.check_output(["llvm-nm", "-m", str(good)], text=True)
        assert any("(__KLDDATA,__const)" in line and line.endswith(" _fixture_immutable")
                   for line in nm.splitlines()), nm
        data = link(work, "always-writable", "__DATA", "__data")
        run(data, 1, ("FAIL _PE_putc", "FAIL _PE_kputc", "(__DATA,__data)"))
        missing = link(work, "missing", "__DATA_CONST", "__late_const", omit_kputc=True)
        run(missing, 1, ("OK   _PE_putc", "FAIL _PE_kputc: no section-backed definition"))
        run(work / "missing-file.macho", 2, ())
    print("console-layout: all checks passed (4 linked fixtures and missing input)")


if __name__ == "__main__":
    main()
