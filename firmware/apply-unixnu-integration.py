#!/usr/bin/env python3
"""Wire UniXNU, DarwinBoot and the Advanced Logger into an Aloha shennong DSC/FDF.

Follows the module list UniXNU's docs/porting/uefi-firmware.md marks as required and the
wiring lonzzi/UniXNU-houji uses for the same SoC (SM8650):

    UniXNUPkg/Application/UniXNU        boot menu / configuration reader
    UniXNUPkg/Driver/UniXNUDxe          registers the application as boot option
    UniXNUPkg/Driver/UniXNURamDiskDxe   publishes the fastboot ramdisk as a block device
    (DarwinBoot stays out of the firmware volume: the reference ports for this SoC inject it
     from the payload, and the DarwinBoot repo ships no package descriptor that a platform
     DSC could reference)
    MdeModulePkg DiskIoDxe + FatPkg Fat disk access for that ramdisk
    DarwinBootPkg/Driver/DarwinBoot     the XNU loader (this port was missing it)
    UniXNUPkg/Driver/AdvancedLogDxe     Advanced Logger -> QR export under Tools

Usage: apply-unixnu-integration.py <aloha-base>
"""
import sys
from pathlib import Path

COMPONENTS = [
    ("UniXNUPkg/Application/UniXNU/UniXNU.inf",
     "UniXNU menu, boot option, payload RAM disk and the XNU loader."),
    ("UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf", None),
    ("UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf", None),
    ("UniXNUPkg/Driver/AdvancedLogDxe/AdvancedLogDxe.inf",
     "Advanced Logger -> QR export; the only firmware-side log channel on this board."),
]

FXF_ENTRIES = [path for path, _ in COMPONENTS] + [
    # DiskIoDxe and Fat are already components (Device/xiaomi-shennong/Binaries/DXE.dsc.inc).
    # Fat is in the FV already; DiskIoDxe is not, so the FAT driver has no block device
    # protocol to bind to and the payload volume never appears.
    "MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf",
]

LIBS = [
    # UniXNURamDiskDxe pulls the Mu-Silicium FDT handoff apart to publish the ramdisk.
    "HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf",
    "FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf",
    "UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf",
    "AdvancedLoggerAccessLib|AdvLoggerPkg/Library/AdvancedLoggerAccessLib/AdvancedLoggerAccessLib.inf",
    "QrEncoderLib|MsGraphicsPkg/Library/QrEncoderLib/QrEncoderLib.inf",
]

PCDS = [
    'gUniXNUPkgTokenSpaceGuid.PcdUniXNUDeviceModel|"shennong"',
]


def insert_after(text, anchor, addition):
    if addition.strip() in text:
        return text
    i = text.find(anchor)
    if i < 0:
        raise SystemExit("anchor not found: %r" % anchor)
    j = text.find("\n", i) + 1
    return text[:j] + addition + text[j:]


def patch_dsc(path):
    t = path.read_text()
    t = insert_after(t, "  DEFINE SHENNONG_USB_FAULT_TRACE = 1", "")
    block = "".join(
        "  %s\n" % line if line else "\n"
        for line in COMPONENTS_BLOCK
    )
    t = insert_after(t, "  AndromedaPkg/Driver/SimpleFbDxe/SimpleFbDxe.inf", block)
    t = insert_after(t, "  PlatformConfigurationMapLib|$(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Library/PlatformConfigurationMapLib/PlatformConfigurationMapLib.inf",
                    "".join("  %s\n" % lib for lib in LIBS))
    t = insert_after(t, '  gAndromedaPkgTokenSpaceGuid.PcdABLProduct|"shennong"',
                    "".join("  %s\n" % pcd for pcd in PCDS))
    path.write_text(t)


def patch_fdf(path):
    t = path.read_text()
    t = insert_after(t, "  INF FatPkg/EnhancedFatDxe/Fat.inf",
                    "".join("  INF %s\n" % e for e in FXF_ENTRIES))
    path.write_text(t)


COMPONENTS_BLOCK = []
for component, comment in COMPONENTS:
    if comment:
        COMPONENTS_BLOCK.append("")
        COMPONENTS_BLOCK.append("# " + comment)
    COMPONENTS_BLOCK.append(component)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-unixnu-integration.py <aloha-base>")
    base = Path(sys.argv[1])
    dsc = base / "Platforms/ShennongPkg/Shennong.dsc"
    fdf = base / "Platforms/ShennongPkg/Shennong.fdf"
    for p in (dsc, fdf):
        if not p.is_file():
            raise SystemExit("missing %s" % p)
    patch_dsc(dsc)
    patch_fdf(fdf)
    print("patched", dsc)
    print("patched", fdf)


if __name__ == "__main__":
    main()
