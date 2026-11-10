#!/usr/bin/env python3
"""Generate the shennong UEFI platform package for a Mu-Silicium tree.

The port needs a `Platforms/Xiaomi/shennongPkg` plus `Resources/Configs/shennong.toml`;
neither exists upstream (Mu-Silicium has no SM8650 Xiaomi board). Both are derived here
from data we can point at, not from guesses:

  * platform skeleton      <- Platforms/OnePlus/giuliaPkg (same SoC: LanaiPkg, SM8650)
  * memory map             <- firmware/shennong-memory-map.toml, extracted from this
                              phone's own xbl_config (see scripts/extract-xbl-memory-map.py)
  * memory descriptor policy <- the sibling Xiaomi SM8650 port (houji), whose generated
                              MemoryMapLib.c carries one row per region with the same
                              resource/attribute conventions
  * SMBIOS + panel size    <- board identity (23116PN5BC / Xiaomi 14 Pro) and dts/shennong.dts
  * UniXNU modules         <- the required-integration list in UniXNU's
                              docs/porting/uefi-firmware.md

Every substituted value is reported on stdout with its source, so a later reader can
re-derive the package instead of trusting it.

Usage:
    make-shennong-uefi-pkg.py --uefi /path/to/uefi-sheng
    make-shennong-uefi-pkg.py --uefi ... --vendor-binaries giulia --force
"""
import argparse
import re
import shutil
import sys
import tomllib
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = "shennongPkg"
DEVICE = "shennong"

# Deterministic so a rebuild produces the same DSC GUID.
PLATFORM_GUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://unixnu.com/porting/shennongPkg")).upper()

SMBIOS = {
    "manufacturer": "Xiaomi",
    "retail_model": "shennong",
    "model": "Xiaomi 14 Pro",
    "sku": "23116PN5BC",
    "board": "shennong",
}

# Xiaomi 14 Pro (23116PN5BC) panel resolution, from dts/shennong.dts panel node.
FRAME_BUFFER = (1440, 3200)

# One row per xbl_config region: (HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttribute).
# Values are the ones the sibling Xiaomi SM8650 port (houji) generates for the same region names;
# base/size always come from this phone's xbl_config, never from the sibling.
POLICY = {
    "RSRV0": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "Reserv", "WRITE_BACK_XN"),
    "XBL_DT": ("AddMem", "MEM_RES", "SYS_MEM_CAP", "Reserv", "WRITE_BACK_XN"),
    "Minidump_Regions": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "UEFI_Log": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "SMEM": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "PvmFw": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "Reserv", "WRITE_BACK_XN"),
    "XBL_Ramdump": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "PIL_Reserved": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "Display_Demura": ("AddMem", "MEM_RES", "SYS_MEM_CAP", "Reserv", "WRITE_THROUGH_XN"),
    "DBI_Dump": ("NoHob", "MMAP_IO", "INITIALIZED", "Conv", "UNCACHED_UNBUFFERED_XN"),
    "UEFI_FD_Reserved": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK"),
    "CPU_Vectors": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK"),
    "Info_Blk": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "RtData", "WRITE_BACK_XN"),
    "MMU_PageTables": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK_XN"),
    "Log_Buffer": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "RtData", "WRITE_BACK_XN"),
    "UEFI_Stack": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK_XN"),
    "SEC_Heap": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK_XN"),
    "Sched_Heap": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "BsData", "WRITE_BACK_XN"),
    "Kernel": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "Reserv", "WRITE_BACK_XN"),
    "DXE_Heap": ("AddMem", "SYS_MEM", "SYS_MEM_CAP", "Conv", "WRITE_BACK_XN"),
    "TZApps_Reserved": ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    "Display_Reserved": ("AddMem", "MEM_RES", "SYS_MEM_CAP", "Reserv", "WRITE_THROUGH_XN"),
    "IMEM": ("NoHob", "MMAP_IO", "INITIALIZED", "Conv", "NS_DEVICE"),
    "IMEM_Cookie_Base": ("AddDev", "MMAP_IO", "INITIALIZED", "Conv", "NS_DEVICE"),
}
DEFAULT_POLICY_DDR = ("AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN")
DEFAULT_POLICY_IO = ("AddDev", "MMAP_IO", "UNCACHEABLE", "MmIO", "NS_DEVICE")
SPAN_REGIONS = {"DDR", "NOMAP"}

UNIXNU_DSC_COMPONENTS = [
    ("UniXNUPkg/Application/UniXNU/UniXNU.inf", "boot menu, payload RAM disk and XNU loader"),
    ("UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf", "registers the menu as a boot option"),
    ("UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf", "publishes the fastboot ramdisk as a block device"),
    ("UniXNUPkg/Driver/AdvancedLogDxe/AdvancedLogDxe.inf", "Advanced Logger -> QR export under Tools"),
    ("DarwinBootPkg/Driver/DarwinBoot.inf", "the XNU loader"),
    ("MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf", "block access for the FAT driver"),
    ("FatPkg/EnhancedFatDxe/Fat.inf", "the payload FAT volume"),
]
UNIXNU_LIBRARIES = [
    ("UniXNULib", "UniXNUPkg/Library/UniXNULib/UniXNULib.inf"),
    # AdvancedLogDxe (the Tools > Advanced Logger QR export) pulls both of these.
    ("AdvancedLoggerAccessLib", "AdvLoggerPkg/Library/AdvancedLoggerAccessLib/AdvancedLoggerAccessLib.inf"),
    ("QrEncoderLib", "MsGraphicsPkg/Library/QrEncoderLib/QrEncoderLib.inf"),
    ("HobLib", "MdePkg/Library/DxeHobLib/DxeHobLib.inf"),
    ("FdtLib", "MdePkg/Library/BaseFdtLib/BaseFdtLib.inf"),
]

notes = []


def note(text):
    notes.append(text)
    print("  " + text)


def read(path):
    return path.read_text()


def write(path, text, force):
    if path.exists() and not force:
        existing = path.read_text()
        if existing == text:
            return
        raise SystemExit(f"{path} exists with different content; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def render_memory_map(regions, fd_base, fd_size):
    """Turn the xbl_config regions into MemoryMapLib rows."""
    rows = []
    explicit = {region["name"] for region in regions}
    for region in regions:
        name = region["name"]
        if name in SPAN_REGIONS:
            continue
        base, size = region["base"], region["size"]
        if name == "UEFI_FD":
            # xbl reserves one span; split it around the volume BootShim copies in.
            if base != fd_base - 0x100000 or base + size < fd_base + fd_size:
                note(f"UEFI_FD span 0x{base:X}+0x{size:X} does not bracket FD 0x{fd_base:X}+0x{fd_size:X}; "
                     f"keeping one row")
                rows.append((name, base, size, POLICY["UEFI_FD_Reserved"], "xbl_config"))
                continue
            rows.append(("FD_Reserved", base, 0x100000, POLICY["UEFI_FD_Reserved"], "xbl_config UEFI_FD split"))
            rows.append(("UEFI_FD", fd_base, fd_size, POLICY["UEFI_FD_Reserved"], "xbl_config UEFI_FD split"))
            tail = base + size - (fd_base + fd_size)
            if tail:
                rows.append(("UEFI_FD_Reserved", fd_base + fd_size, tail,
                             POLICY["UEFI_FD_Reserved"], "xbl_config UEFI_FD split"))
            continue
        policy = POLICY.get(name)
        if policy is None:
            ram = base >= 0x8000_0000
            policy = DEFAULT_POLICY_DDR if ram else DEFAULT_POLICY_IO
            note(f"no policy for xbl region {name}; default {'DDR' if ram else 'IO'} row")
        rows.append((name, base, size, policy, "xbl_config"))

    width = max(len(row[0]) for row in rows) + 3
    body = ""
    for name, base, size, (hob, restype, attr, memtype, armattr), source in rows:
        body += (f'  {{"{name}",'.ljust(4 + width + 1)
                 + f'0x{base:08X}, 0x{size:08X}, '
                 + f'{hob}, {restype}, {attr}, {memtype}, {armattr}}},'
                 + f"  // {source}\n")
    return rows, body


MEMORY_MAP_HEADER = """// SPDX-License-Identifier: BSD-2-Clause-Patent
//
// Generated by scripts/make-shennong-uefi-pkg.py for Xiaomi 14 Pro (shennong, SM8650).
//
// Region base/size: this phone's stock xbl_config (firmware/shennong-memory-map.toml,
// see scripts/extract-xbl-memory-map.py). Descriptor policy (HobOption / ResourceType /
// ResourceAttribute / MemoryType / ArmAttribute per region name): the sibling Xiaomi
// SM8650 port (houji), whose generated MemoryMapLib.c covers the same region names.
// The UEFI_FD row is split around FD_BASE/FD_SIZE so the volume BootShim copies in is
// reserved exactly and nothing else claims it.
//
#include <Library/MemoryMapLib.h>

STATIC
EFI_MEMORY_REGION_DESCRIPTOR
gMemoryDescriptor[] = {
  // Name, Address, Length, HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttribute
"""

MEMORY_MAP_FOOTER = """};

VOID
GetMemoryMap (
  OUT EFI_MEMORY_REGION_DESCRIPTOR **MemoryDescriptor,
  OUT UINT8                         *MemoryDescriptorCount)
{
  // Pass Data
  *MemoryDescriptor      = gMemoryDescriptor;
  *MemoryDescriptorCount = ARRAY_SIZE (gMemoryDescriptor);
}
"""


def patch_platform_files(pkg_dir, template_dir, vendor, force):
    """Copy the SM8650 platform skeleton and retarget it at shennong."""
    # Order matters: the Binaries rule must run before the bare device rename, or
    # Binaries/giulia/ would be rewritten to Binaries/shennong/ and the build would look
    # for vendor drivers that do not exist yet.
    renames = [
        (re.compile(r"Binaries/giulia/"), f"Binaries/{vendor}/"),
        (re.compile(r"\bgiuliaPkg\b"), f"{PACKAGE}"),
        (re.compile(r"\bgiulia\b"), DEVICE),
        (re.compile(r"\bGiulia\b"), "Shennong"),
        (re.compile(r"\bGIULIA\b"), "SHENNONG"),
    ]

    def retarget(text):
        for pattern, replacement in renames:
            text = pattern.sub(replacement, text)
        # The bare device rename also rewrites the vendor binaries path; put the chosen
        # vendor directory back.
        if vendor != DEVICE:
            text = text.replace(f"Binaries/{DEVICE}/", f"Binaries/{vendor}/")
        return text

    for source in sorted(template_dir.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        rel = source.relative_to(template_dir)
        if rel.name in ("giulia.dec", "giulia.dsc", "giulia.fdf"):
            rel = rel.with_name(rel.name.replace("giulia", DEVICE))
        if rel.parts[:3] == ("Library", "MemoryMapLib", "MemoryMapLib.c"):
            continue  # generated from the xbl map instead
        destination = pkg_dir / str(rel)
        try:
            text = retarget(read(source))
        except UnicodeDecodeError:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            note(f"copied binary {rel} from {source.parent.name}/{source.name}")
            continue
        write(destination, text, force)
        note(f"copied {rel} from {source.parent.name}/{source.name}")



SOC_SOURCES = []  # filled in main(): SoC package files that also list modules


def existing_infs(pkg_dir):
    """INF paths the copied platform already pulls in (include fragments and FDF)."""
    infs = set()
    candidates = list(pkg_dir.glob("Include/*.inc")) + [pkg_dir / f"{DEVICE}.fdf", pkg_dir / f"{DEVICE}.dsc"] + SOC_SOURCES
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("INF "):
                infs.add(line[4:].strip())
            elif line.endswith(".inf") and not line.startswith("#"):
                infs.add(line.split()[0])
    return infs


def patch_dsc(path, vendor, force, fd_base, fd_size):
    text = read(path)
    text = text.replace('PLATFORM_NAME                  = ' + DEVICE,
                        'PLATFORM_NAME                  = ' + DEVICE, 1)
    text = re.sub(r"^  PLATFORM_GUID\s*=.*$", f"  PLATFORM_GUID                  = {PLATFORM_GUID}",
                  text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^  OUTPUT_DIRECTORY\s*=.*$", f"  OUTPUT_DIRECTORY               = Build/{PACKAGE}",
                  text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^  FLASH_DEFINITION\s*=.*$", f"  FLASH_DEFINITION               = {PACKAGE}/{DEVICE}.fdf",
                  text, count=1, flags=re.MULTILINE)

    # SMBIOS identity: manufacturer/model/sku of this board.
    text = re.sub(r'^(  gSiliciumPkgTokenSpaceGuid\.PcdSmbiosSystemManufacturer\|).*$',
                  lambda m: m.group(1) + f'"{SMBIOS["manufacturer"]}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'^(  gSiliciumPkgTokenSpaceGuid\.PcdSmbiosSystemRetailModel\|).*$',
                  lambda m: m.group(1) + f'"{SMBIOS["retail_model"]}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'^(  gSiliciumPkgTokenSpaceGuid\.PcdSmbiosSystemBoardModel\|).*$',
                  lambda m: m.group(1) + f'"{SMBIOS["board"]}"', text, count=1, flags=re.MULTILINE)
    # The template carries a DEVICE_MODEL switch over two retail models; shennong has one.
    text = re.sub(r"^!if \$\(DEVICE_MODEL\) == 0\n", "", text, count=1, flags=re.MULTILINE)
    text = re.sub(r'^  gSiliciumPkgTokenSpaceGuid\.PcdSmbiosSystemModel\|.*$',
                  f'  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"{SMBIOS["model"]}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'^  gSiliciumPkgTokenSpaceGuid\.PcdSmbiosSystemRetailSku\|.*$',
                  f'  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"{SMBIOS["sku"]}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^!elseif \$\(DEVICE_MODEL\) == 1\n(?:(?!^!endif).)*^!endif\n", "", text, count=1,
                  flags=re.MULTILINE | re.DOTALL)

    text = re.sub(r"^(  gSiliciumPkgTokenSpaceGuid\.PcdFrameBufferWidth\|).*$",
                  lambda m: m.group(1) + str(FRAME_BUFFER[0]), text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^(  gSiliciumPkgTokenSpaceGuid\.PcdFrameBufferHeight\|).*$",
                  lambda m: m.group(1) + str(FRAME_BUFFER[1]), text, count=1, flags=re.MULTILINE)

    # UniXNU integration: components plus the libraries their drivers pull in.
    # A module that the SoC package already provides must not be listed twice: GenFv
    # rejects an FV with two files of the same GUID.
    present = existing_infs(path.parent)
    extra = "\n  #\n  # UniXNU / DarwinBoot (docs/porting/uefi-firmware.md required integration)\n  #\n"
    for inf, why in UNIXNU_DSC_COMPONENTS:
        if inf in present:
            note(f"{inf} already provided by the platform; not listed again")
            continue
        extra += f"  {inf}   # {why}\n"
    text = text.rstrip("\n") + "\n" + extra if "[Components]" in text else text.rstrip("\n") + "\n[Components]\n" + extra
    library_lines = "".join(f"  {name}|{inf}\n" for name, inf in UNIXNU_LIBRARIES)
    text = re.sub(r"(\[LibraryClasses\]\n)", r"\1" + library_lines.replace("\\", "\\\\"), text, count=1)
    write(path, text, True)
    note(f"DSC: PLATFORM_GUID {PLATFORM_GUID}, SMBIOS {SMBIOS['model']} / {SMBIOS['sku']}, "
         f"framebuffer {FRAME_BUFFER[0]}x{FRAME_BUFFER[1]}, vendor binaries Binaries/{vendor}")


def patch_fdf(path, force):
    text = read(path)
    present = existing_infs(path.parent)
    infs = ""
    for inf, _ in UNIXNU_DSC_COMPONENTS:
        if inf in present:
            note(f"FDF: {inf} already in the volume via the platform includes")
            continue
        infs += f"  INF {inf}\n"
    if not infs:
        note("FDF: every UniXNU module is already in the volume")
        return
    marker = "  !include QcomPkg/Extra.fdf.inc\n"
    if marker not in text:
        raise SystemExit(f"{path}: cannot find the QcomPkg include to anchor the UniXNU modules")
    text = text.replace(marker, infs + "\n" + marker, 1)
    write(path, text, True)
    note("FDF: UniXNU / DarwinBoot / DiskIo / Fat modules added to FvMain")


def write_device_config(path, force):
    text = f"""#
# Generated by scripts/make-shennong-uefi-pkg.py for Xiaomi 14 Pro (shennong).
#
[status]
model_count = 1

#
# Boot Shim Configs
#
[boot_shim]
requires_kernel_header = true

#
# UEFI FD Configs (must match board.toml ["firmware"."defines"])
#
[uefi_fd]
base = 0xA7100000
size = 0x300000
blocks = 0x300

#
# Android Boot Image Kernel Configs
#
# header v4 cannot carry an ABL-provided DTB for `fastboot boot`, which is the only way
# this port starts the phone, so the image stays at v0 with the DTB appended.
#
[boot_image_kernel]
kernel_compression = "gzip"
append_dtb         = true

#
# Android Boot Image Configs
#
[boot_image]
header_version = 0
os_version     = "16.0.0"
os_patch_level = "2026-07"
"""
    write(path, text, force)
    note(f"wrote {path.name}: FD 0xA7100000/0x300000, header v0 + append_dtb")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uefi", type=Path, required=True, help="Mu-Silicium (or uefi-sheng) checkout")
    parser.add_argument("--template", default="Platforms/OnePlus/giuliaPkg", help="SM8650 platform package to derive from")
    parser.add_argument("--memory-map", type=Path, default=REPO / "firmware/shennong-memory-map.toml")
    parser.add_argument("--vendor-binaries", default="shennong",
                        help="Binaries/<name> directory the platform pulls its prebuilt QcomPkg drivers from")
    parser.add_argument("--fd-base", type=lambda value: int(value, 0), default=0xA7100000)
    parser.add_argument("--fd-size", type=lambda value: int(value, 0), default=0x300000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    uefi = args.uefi.resolve()
    template = uefi / args.template
    if not template.is_dir():
        raise SystemExit(f"template package not found: {template}")
    if not (uefi / "Mu_Basecore/BaseTools").is_dir():
        raise SystemExit(f"{uefi} is not a Mu tree (no Mu_Basecore/BaseTools)")

    vendor_dir = uefi / "Binaries" / args.vendor_binaries
    if not vendor_dir.is_dir():
        raise SystemExit(f"vendor binaries not present: {vendor_dir} (extract them from the phone first)")
    if args.vendor_binaries != DEVICE:
        note(f"WARNING vendor binaries are Binaries/{args.vendor_binaries}, not Binaries/{DEVICE}: "
             f"same-SoC SM8650 stand-in until this phone's own DXEs are extracted")

    SOC_SOURCES.extend([
        uefi / "Silicon/Qualcomm/LanaiPkg/LanaiPkg.dsc.inc",
        uefi / "Silicon/Qualcomm/QcomPkg/QcomPkg.dsc.inc",
        uefi / "Silicon/Silicium/SiliciumPkg/SiliciumPkg.dsc.inc",
        uefi / "Silicon/Qualcomm/QcomPkg/Extra.fdf.inc",
        uefi / "Silicon/Silicium/SiliciumPkg/Common.fdf.inc",
    ])
    pkg_dir = uefi / "Platforms/Xiaomi" / PACKAGE
    print(f"shennongPkg -> {pkg_dir}")

    regions = tomllib.loads(args.memory_map.read_text())["region"]
    rows, body = render_memory_map(regions, args.fd_base, args.fd_size)
    print(f"  memory map: {len(rows)} descriptors from {args.memory_map.name}")

    if args.dry_run:
        print(MEMORY_MAP_HEADER + body + MEMORY_MAP_FOOTER)
        return

    patch_platform_files(pkg_dir, template, args.vendor_binaries, args.force)
    write(pkg_dir / "Library/MemoryMapLib/MemoryMapLib.c", MEMORY_MAP_HEADER + body + MEMORY_MAP_FOOTER, args.force)
    note("generated Library/MemoryMapLib/MemoryMapLib.c")
    patch_dsc(pkg_dir / f"{DEVICE}.dsc", args.vendor_binaries, args.force, args.fd_base, args.fd_size)
    patch_fdf(pkg_dir / f"{DEVICE}.fdf", args.force)
    write_device_config(uefi / "Resources/Configs" / f"{DEVICE}.toml", args.force)

    print(f"\n{len(notes)} steps applied. Next:")
    print(f"  cd {uefi} && python3 build_uefi.py -d {DEVICE} -r DEBUG")


if __name__ == "__main__":
    main()
