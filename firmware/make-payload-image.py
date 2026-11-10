#!/usr/bin/env python3
"""Assemble the boot payload volume (the FAT ramdisk `fastboot boot` carries).

This is the offline path to `payload.img`. The framework's own step
(`scripts/unixnu/payload.py`) does the same job but insists on inputs this machine cannot
produce right now: a root-policy bundle built from the iOS 27 IPSW (`build/sheng-source-storage/
root-policies.bin`, absent) and, through `ctx.tree`, a composed UniXNU work tree. Everything
that *is* available here is used unchanged, and the volume layout is byte-for-byte the layout
the framework writes, so the loader cannot tell which script made it:

    EFI/UniXNU/unixnu.toml                  menu: driver line + xnu entry + reset/power off
    EFI/UniXNU/Payloads/kernel.macho        the prelinked kernel
    EFI/UniXNU/Payloads/kernel.macho.adt    platform description (chosen node, memory map)
    EFI/UniXNU/Payloads/DarwinBoot.efi      required because board.toml [payload] loader = "payload"
    EFI/UniXNU/Payloads/kernel.macho.trustcache   optional
    EFI/UniXNU/Payloads/kernel.macho.vroot        optional

The volume is written with mtools (no mount, no root) and every timestamp is pinned to
1980-01-01, so the volume listing, the boot sector and every file inside it reproduce exactly.
The image as a whole is not byte-identical between runs: this host's mformat leaves about 19
bytes of uninitialised stack in the final sector, which no loader reads (see
firmware/test-make-payload-image.py, which pins everything that *is* stable).

Usage:
    make-payload-image.py --kernel kernel.macho --darwinboot DarwinBoot.efi --out payload.img --verify
    make-payload-image.py --kernel K --adt A --trust-cache T --vroot V --out payload.img
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

EPOCH = 315532800  # 1980-01-01: the first FAT timestamp, same constant the framework uses.
HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        sys.exit(f"failed: {' '.join(str(part) for part in command)}\n{result.stderr.strip()}")
    return result.stdout


def board_payload_spec(board_path):
    with open(board_path, "rb") as stream:
        board = tomllib.load(stream)
    return board.get("payload", {})


def write_config(stage, spec):
    """Same shape as scripts/unixnu/payload.py: a driver line only when the loader travels here."""
    args = " ".join(spec.get("kernel_args", []))
    loader = '' if spec.get("loader", "firmware") == "firmware" else '[[driver]]\npath = "Payloads/DarwinBoot.efi"\n'
    config = (f'version = 1\n[boot]\ntimeout = {spec.get("timeout", 3)}\ndefault = "xnu"\n[kits]\nautoload = false\n{loader}'
              f'[[entry]]\nid = "xnu"\ntitle = "{spec.get("title", "UniXNU")}"\ntype = "xnu"\n'
              f'path = "Payloads/kernel.macho"\nargs = "{args}"\n')
    config += ('[[entry]]\nid = "reset"\ntitle = "Restart"\ntype = "action"\naction = "reset"\n'
               '[[entry]]\nid = "shutdown"\ntitle = "Power off"\ntype = "action"\naction = "shutdown"\n')
    (stage / "EFI/UniXNU/unixnu.toml").write_text(config)
    return config


def make_adt(stage, spec, trust_cache):
    """Generate kernel.macho.adt with the device's own generator (offline, SM8650 specific)."""
    adt_spec = spec.get("adt", {})
    output = stage / "EFI/UniXNU/Payloads/kernel.macho.adt"
    command = [sys.executable, str(REPO / "scripts/make-shennong-adt.py"),
               "--output", str(output),
               "--dram-size", str(spec.get("dram_size", "0x10000000")),
               "--psci-method", str(adt_spec.get("psci_method", "smc")),
               "--cpu-regs", str(adt_spec.get("cpu_regs", 0))]
    if adt_spec.get("owned_memory_size"):
        command += ["--owned-memory-size", str(adt_spec["owned_memory_size"])]
    if adt_spec.get("root_match_volume_uuid"):
        command += ["--root-match-volume-uuid", str(adt_spec["root_match_volume_uuid"])]
    if trust_cache:
        command.append("--trust-cache")
    run(command)
    return output


def write_volume(stage, image, label, size_mib):
    """Mirror scripts/unixnu/payload.py:write_volume exactly (same mtools flags, same env)."""
    for tool in ("mformat", "mcopy"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found; install mtools")
    image.unlink(missing_ok=True)
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1", TZ="UTC")
    run(["mformat", "-C", "-F", "-T", str(size_mib * 2048), "-v", label[:11],
         "-N", "53484e47", "-i", image, "::"], env=env)
    for entry in sorted(stage.iterdir()):
        run(["mcopy", "-i", image, "-s", "-Q", "-m", str(entry), "::/"], env=env)


def verify(image, staged):
    """Read the volume back with mtools and compare every file against what was staged."""
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1", TZ="UTC")
    listing = run(["mdir", "-i", str(image), "-/", "::"], env=env)
    problems = []
    for source in sorted(staged.rglob("*")):
        if not source.is_file():
            continue
        inner = "::/" + str(source.relative_to(staged)).replace(os.sep, "/")
        if source.name not in listing:
            problems.append(f"{inner} missing from the volume listing")
            continue
        # mtype writes bytes to stdout; read them through a pipe without text decoding.
        raw = subprocess.run(["mtype", "-i", str(image), inner], capture_output=True, env=env)
        if raw.returncode != 0:
            problems.append(f"{inner}: mtype failed: {raw.stderr.decode(errors='replace').strip()}")
            continue
        if hashlib.sha256(raw.stdout).hexdigest() != sha256(source):
            problems.append(f"{inner}: content differs from {source}")
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--board", type=Path, default=REPO / "board.toml")
    parser.add_argument("--adt", type=Path, help="use this ADT instead of generating one")
    parser.add_argument("--darwinboot", type=Path, help="DarwinBoot.efi to place in Payloads/")
    parser.add_argument("--trust-cache", type=Path)
    parser.add_argument("--vroot", type=Path)
    parser.add_argument("--size-mib", type=int)
    parser.add_argument("--volume", help="FAT label (default: board.toml [payload] volume)")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--keep-stage", type=Path, help="keep the staged tree here for inspection")
    parser.add_argument("--json", type=Path, help="write a build report here")
    args = parser.parse_args()

    spec = board_payload_spec(args.board)
    if not args.kernel.is_file():
        sys.exit(f"kernel not found: {args.kernel}")
    if args.kernel.read_bytes()[:4] not in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
        sys.exit(f"{args.kernel} is not a little-endian Mach-O (kernel.macho is a thin arm64 Mach-O)")

    size_mib = args.size_mib or int(spec.get("size_mib", 192))
    label = args.volume or spec.get("volume", "UNIXNU")
    stage = Path(tempfile.mkdtemp(prefix="payload-stage-")) if args.keep_stage is None else args.keep_stage
    shutil.rmtree(stage, ignore_errors=True)
    payloads = stage / "EFI/UniXNU/Payloads"
    payloads.mkdir(parents=True)

    shutil.copyfile(args.kernel, payloads / "kernel.macho")
    if args.adt:
        shutil.copyfile(args.adt, payloads / "kernel.macho.adt")
    else:
        make_adt(stage, spec, args.trust_cache)
    if args.trust_cache:
        shutil.copyfile(args.trust_cache, payloads / "kernel.macho.trustcache")
    if args.vroot:
        shutil.copyfile(args.vroot, payloads / "kernel.macho.vroot")
    darwinboot = args.darwinboot
    if darwinboot is None and spec.get("loader", "firmware") != "firmware":
        sys.exit("board.toml sets loader = payload, so --darwinboot is required")
    if darwinboot:
        if not darwinboot.is_file():
            sys.exit(f"DarwinBoot not found: {darwinboot}")
        shutil.copyfile(darwinboot, payloads / "DarwinBoot.efi")
    write_config(stage, spec)

    for path in [stage, *stage.rglob("*")]:
        os.utime(path, (EPOCH, EPOCH))

    content = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    if content > size_mib * 1024 * 1024 * 0.95:
        sys.exit(f"payload files take {content >> 20} MiB; raise --size-mib (now {size_mib})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_volume(stage, args.out, label, size_mib)

    files = {str(p.relative_to(stage)): {"bytes": p.stat().st_size, "sha256": sha256(p)}
             for p in sorted(stage.rglob("*")) if p.is_file()}
    report = {"volume": label[:11], "size_mib": size_mib, "image": str(args.out),
              "image_bytes": args.out.stat().st_size, "image_sha256": sha256(args.out),
              "kernel_args": " ".join(spec.get("kernel_args", [])), "files": files}
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")

    print(f"payload image: {args.out} ({report['image_bytes']} bytes, {size_mib} MiB FAT, label {label[:11]})")
    print(f"sha256: {report['image_sha256']}")
    for name, info in files.items():
        print(f"  {name:<44} {info['bytes']:>10}  {info['sha256'][:16]}")

    if args.verify:
        verify(args.out, stage)
        print("verify: every staged file reads back from the volume with the same sha256")

    if args.keep_stage is None:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
