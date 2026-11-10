#!/usr/bin/env python3
"""Contract test for firmware/make-payload-image.py.

The payload volume is the one artifact the loader reads by name, so the things worth pinning
are the ones a silent change would break: the path layout inside the FAT volume, the menu
config that points at those paths, the refusal when the board says the loader travels in the
payload but no DarwinBoot was given, and the size guard. A tiny stand-in Mach-O keeps the test
fast — the real kernel is 52 MB and the assembly is the same either way.

Run: python3 firmware/test-make-payload-image.py
"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "make-payload-image.py"
BOARD = HERE.parent / "board.toml"

FAKE_KERNEL = b"\xcf\xfa\xed\xfe" + b"\x0c\x00\x00\x01" + b"\x00" * 24 + b"payload-test-kernel"


def run(args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})))


def main():
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        kernel = tmp / "kernel.macho"
        kernel.write_bytes(FAKE_KERNEL)
        darwinboot = tmp / "DarwinBoot.efi"
        darwinboot.write_bytes(b"MZ" + b"\x00" * 126)
        adt = tmp / "kernel.macho.adt"
        adt.write_bytes(b"ADT\x00" + bytes(range(64)))
        image = tmp / "payload.img"

        # 1) A normal build: layout, label, config.
        result = run(["--kernel", str(kernel), "--adt", str(adt), "--darwinboot", str(darwinboot),
                      "--out", str(image), "--size-mib", "8", "--verify",
                      "--json", str(tmp / "report.json")])
        check(result.returncode == 0, f"build failed: {result.stderr.strip()}")
        if result.returncode == 0:
            check(image.is_file(), "no image written")
            env = dict(MTOOLS_SKIP_CHECK="1", TZ="UTC")
            listing = subprocess.run(["mdir", "-i", str(image), "-/", "::"], capture_output=True,
                                     text=True, env=dict(os.environ, **env)).stdout
            for name in ("kernel.macho", "kernel.macho.adt", "DarwinBoot.efi", "unixnu.toml", "PAYLOADS"):
                check(name.upper() in listing.upper() or name in listing,
                      f"{name} not in the volume listing")
            config = subprocess.run(["mtype", "-i", str(image), "::/EFI/UniXNU/unixnu.toml"],
                                    capture_output=True, text=True,
                                    env=dict(os.environ, **env)).stdout
            check('path = "Payloads/kernel.macho"' in config, "menu does not point at the kernel")
            check('[[driver]]' in config and 'Payloads/DarwinBoot.efi' in config,
                  "menu lacks the in-payload driver line")
            check('[boot]' in config  and 'default = "xnu"' in config, "menu header missing")
            # The kernel argument line is copied from board.toml verbatim.
            import tomllib
            board_args = " ".join(tomllib.loads(BOARD.read_text())["payload"]["kernel_args"])
            check(board_args in config, "kernel arguments differ from board.toml [payload] kernel_args")

        # 2) loader = payload without --darwinboot must be refused, not silently built.
        result = run(["--kernel", str(kernel), "--adt", str(adt), "--out", str(tmp / "x.img"),
                      "--size-mib", "8"])
        check(result.returncode != 0 and "darwinboot" in result.stderr.lower(),
              f"missing DarwinBoot was not refused: {result.returncode} {result.stderr.strip()}")

        # 3) The size guard: 8 MiB of files in a 1 MiB volume.
        big = tmp / "big.macho"
        big.write_bytes(FAKE_KERNEL + b"\x00" * (3 * 1024 * 1024))
        result = run(["--kernel", str(big), "--adt", str(adt), "--darwinboot", str(darwinboot),
                      "--out", str(tmp / "y.img"), "--size-mib", "1"])
        check(result.returncode != 0 and "raise --size-mib" in result.stderr,
              f"oversized payload not refused: {result.returncode} {result.stderr.strip()}")

        # 4) A non-Mach-O kernel is refused before any volume is written.
        text = tmp / "not-a-kernel.bin"
        text.write_bytes(b"hello world")
        result = run(["--kernel", str(text), "--adt", str(adt), "--darwinboot", str(darwinboot),
                      "--out", str(tmp / "z.img"), "--size-mib", "8"])
        check(result.returncode != 0 and "Mach-O" in result.stderr,
              f"non-Mach-O kernel accepted: {result.returncode} {result.stderr.strip()}")

        # 5) Repeatability of everything the loader reads: same inputs, same volume listing,
        #    same boot sector and byte-identical file contents. (The image as a whole is not
        #    byte-comparable: this host's mformat leaves ~19 bytes of uninitialised stack in
        #    the final sector, so two runs differ there and nowhere else.)
        first = tmp / "a.img"
        second = tmp / "b.img"
        for target in (first, second):
            run(["--kernel", str(kernel), "--adt", str(adt), "--darwinboot", str(darwinboot),
                 "--out", str(target), "--size-mib", "8"])
        if first.is_file() and second.is_file():
            left, right = first.read_bytes(), second.read_bytes()
            check(len(left) == len(right), "two runs produced different image sizes")
            check(left[:512] == right[:512], "boot sector differs between two runs")
            env = dict(os.environ, MTOOLS_SKIP_CHECK="1", TZ="UTC")
            for name in ("::/EFI/UniXNU/unixnu.toml", "::/EFI/UniXNU/Payloads/kernel.macho",
                         "::/EFI/UniXNU/Payloads/kernel.macho.adt",
                         "::/EFI/UniXNU/Payloads/DarwinBoot.efi"):
                a = subprocess.run(["mtype", "-i", str(first), name], capture_output=True, env=env).stdout
                b = subprocess.run(["mtype", "-i", str(second), name], capture_output=True, env=env).stdout
                check(a == b and a, f"{name} is not reproduced on a second run")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        sys.exit(1)
    print("make-payload-image: all checks passed")


if __name__ == "__main__":
    main()
