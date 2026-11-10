#!/usr/bin/env python3
"""Contract test for scripts/verify-boot-package.py.

The verifier is only useful if it fails on the mistakes that actually happen — a payload that
was rebuilt after the image was packed, a trust cache the board will not accept, a menu that
points somewhere else. This builds a miniature package (fake kernel, fake DarwinBoot, a real
ADT from the device generator, a real FAT volume from firmware/make-payload-image.py, a real
boot image from firmware/make-boot-image.py) and then breaks it in exactly those ways.

The firmware checks are skipped here because they need a real 3 MiB firmware volume; the test
therefore never passes --fd.

Run: python3 scripts/test-verify-boot-package.py
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VERIFY = HERE / "verify-boot-package.py"
BOARD = REPO / "board.toml"
MAKE_PAYLOAD = REPO / "firmware/make-payload-image.py"
MAKE_IMAGE = REPO / "firmware/make-boot-image.py"
MAKE_ADT = REPO / "scripts/make-shennong-adt.py"

FAKE_KERNEL = b"\xcf\xfa\xed\xfe" + struct.pack("<i", 0x0100000C) + b"\x00" * 56 + b"verify-test" * 64


def run(command, **kwargs):
    return subprocess.run([sys.executable, *command], capture_output=True, text=True, **kwargs)


def build_payload(tmp, trust_cache):
    kernel = tmp / "kernel.macho"
    kernel.write_bytes(FAKE_KERNEL)
    darwinboot = tmp / "DarwinBoot.efi"
    darwinboot.write_bytes(b"MZ" + b"\x00" * 254)
    adt = tmp / "adt.bin"
    result = run([str(MAKE_ADT), "--output", str(adt), "--dram-size", "0x10000000", "--trust-cache"])
    if result.returncode != 0:
        sys.exit(f"ADT generator failed: {result.stderr.strip()}")
    image = tmp / "payload.img"
    result = run([str(MAKE_PAYLOAD), "--kernel", str(kernel), "--adt", str(adt),
                  "--darwinboot", str(darwinboot), "--trust-cache", str(trust_cache),
                  "--out", str(image), "--size-mib", "8"])
    if result.returncode != 0:
        sys.exit(f"payload build failed: {result.stderr.strip()}")
    return image


def build_fake_fd(path, size=0x300000):
    """Enough of a firmware volume for make-boot-image.py, which pins FD_SIZE = 0x300000."""
    data = bytearray(size)
    data[40:44] = b"_FVH"
    struct.pack_into("<Q", data, 32, size)
    struct.pack_into("<H", data, 48, 0x48)
    path.write_bytes(bytes(data))
    return path


def board_with_digest(tmp, digest):
    text = BOARD.read_text()
    import re
    text = re.sub(r'"trust_cache_sha256" = \[[^\]]*\]',
                  f'"trust_cache_sha256" = ["{digest}"]', text)
    target = tmp / "board-digest.toml"
    target.write_text(text)
    return target


def main():
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        trust = tmp / "kernel.macho.trustcache"
        trust.write_bytes(bytes(range(64)))
        digest = hashlib.sha256(trust.read_bytes()).hexdigest()

        payload = build_payload(tmp, trust)
        fd = build_fake_fd(tmp / "fake.fd")
        boot = tmp / "boot.img"
        # A real image needs an appended DTB: ABL refuses one without it (Load Error).
        dtb = tmp / "fake.dtb"
        dtb.write_bytes(b"\xd0\x0d\xfe\xed" + b"\x00" * 60)
        uefi = Path(os.environ.get("UEFI_TREE", "/home/yoox/android/sources/uefi-sheng"))
        if not (uefi / "BootShim/BootShim.S").is_file():
            print(f"note: {uefi} has no BootShim/BootShim.S; skipping the boot-image checks")
            return 0
        result = run([str(MAKE_IMAGE), "--uefi", str(uefi), "--fd", str(fd),
                      "--payload", str(payload), "--append-dtb", str(dtb), "--out", str(boot)])
        if result.returncode != 0:
            sys.exit(f"boot image build failed: {result.stderr.strip()}")

        good_board = board_with_digest(tmp, digest)
        common = ["--payload", str(payload), "--image", str(boot)]

        # 1) A consistent package passes, with the checks that matter reported OK.
        result = run([str(VERIFY), "--board", str(good_board), *common])
        check(result.returncode == 0, f"clean package failed:\n{result.stdout}{result.stderr}")
        for line in ("payload files", "trust cache", "ADT parse", "menu config",
                     "image append_dtb", "image payload bytes"):
            check(f"OK   {line}" in result.stdout, f"clean package did not report OK for {line}")
        check("TrustCache" in result.stdout, "ADT slots line does not mention TrustCache")

        # 2) A payload rebuilt after packing: one flipped byte must be caught.
        broken = tmp / "boot-stale.img"
        data = bytearray(boot.read_bytes())
        header = struct.unpack_from("<8I", data, 8)
        page, kernel_size = header[7], header[0]
        start = page + kernel_size + (-(page + kernel_size) % page)
        data[start + 4096] ^= 0xFF
        broken.write_bytes(bytes(data))
        result = run([str(VERIFY), "--board", str(good_board), "--payload", str(payload),
                      "--image", str(broken)])
        check(result.returncode != 0, "a stale payload inside the image was accepted")
        check("FAIL image payload bytes" in result.stdout,
              f"stale payload not reported:\n{result.stdout}")

        # 3) A trust cache the board does not accept must be caught before flashing.
        wrong_board = board_with_digest(tmp, "0" * 64)
        result = run([str(VERIFY), "--board", str(wrong_board), *common])
        check(result.returncode != 0, "an unaccepted trust cache was accepted")
        check("FAIL trust cache" in result.stdout, f"trust cache not reported:\n{result.stdout}")

        # 4) An image without the appended DTB must be caught: that is what "Load Error" was.
        no_dtb = tmp / "boot-no-dtb.img"
        result = run([str(MAKE_IMAGE), "--uefi", str(uefi), "--fd", str(fd),
                      "--payload", str(payload), "--out", str(no_dtb)])
        check(result.returncode == 0, f"image build without a DTB failed: {result.stderr.strip()}")
        result = run([str(VERIFY), "--board", str(good_board), "--payload", str(payload),
                      "--image", str(no_dtb)])
        check(result.returncode != 0, "an image without an appended DTB was accepted")
        check("FAIL image append_dtb" in result.stdout,
              f"missing DTB not reported:\n{result.stdout}")

        # 5) A menu that lost its kernel path must be caught.
        bad_payload = tmp / "payload-bad-menu.img"
        bad_payload.write_bytes(payload.read_bytes())
        env = dict(os.environ, MTOOLS_SKIP_CHECK="1", TZ="UTC")
        config = subprocess.run(["mtype", "-i", str(bad_payload), "::/EFI/UniXNU/unixnu.toml"],
                                capture_output=True, env=env).stdout.decode(errors="replace")
        edited = tmp / "unixnu.toml"
        edited.write_text(config.replace('path = "Payloads/kernel.macho"', 'path = "Payloads/gone"'))
        subprocess.run(["mcopy", "-o", "-i", str(bad_payload), str(edited), "::/EFI/UniXNU/unixnu.toml"],
                       capture_output=True, env=env)
        result = run([str(VERIFY), "--board", str(good_board), "--payload", str(bad_payload)])
        check(result.returncode != 0, "a menu pointing at a missing kernel was accepted")
        check("FAIL menu config" in result.stdout, f"bad menu not reported:\n{result.stdout}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        sys.exit(1)
    print("verify-boot-package: all checks passed")


if __name__ == "__main__":
    main()
