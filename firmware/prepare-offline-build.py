#!/usr/bin/env python3
"""Make an Aloha/Mu-Silicium tree buildable without inbound GitHub release access.

Three things in the stock tree need the network and cannot get it from this host
(github.com release assets are unreachable, nuget.org works):

  * Mu-Basetools     released tarball   -> built locally from BaseTools/Source/C and
                                          registered with a path-env descriptor
  * mu_nasm          nuget package      -> system nasm behind a path-env override
  * edk2-acpica-iasl nuget package      -> system iasl behind a path-env override
  * Mu_CryptoBin     released zip       -> dropped: secure boot is off on this board
                                          (board.toml ENABLE_SECUREBOOT=0), so the
                                          prebuilt crypto drivers are not part of this
                                          firmware

Usage: prepare-offline-build.py <aloha-base>
"""
import json
import os
import re
import sys
from pathlib import Path

TOOLOVERRIDES = None  # set to <aloha-base>/Build/tooloverrides in main()


def write_descriptor(directory: Path, name: str, body: str, links=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(body)
    for link_name, target in (links or {}).items():
        link = directory / link_name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)


def path_env(directory_name: str, payload: str, links=None):
    directory = TOOLOVERRIDES / directory_name
    write_descriptor(directory, directory_name + "_path_env.yaml", payload, links)


def patch_once(text: str, pattern: str, replacement: str, what: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count == 0 and replacement.strip() not in text:
        raise SystemExit("cannot patch %s (pattern %r)" % (what, pattern))
    return new


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare-offline-build.py <aloha-base>")
    base = Path(sys.argv[1]).resolve()
    global TOOLOVERRIDES
    # The environment scanner only walks the workspace, so the descriptors must live there.
    TOOLOVERRIDES = base / "Build/tooloverrides"

    # 1) BaseTools: Mu's own builder writes the descriptor that overrides edk-tools-bin.
    edk_tools_build = base / "MU_BASECORE/BaseTools/Edk2ToolsBuild.py"
    if not edk_tools_build.is_file():
        raise SystemExit("missing %s" % edk_tools_build)

    # 1b) register the BaseTools built above; the descriptor's own directory is what
    #     EDK_TOOLS_BIN ends up pointing at, so the binaries live next to it.
    bt_bin = base / "MU_BASECORE/BaseTools/Source/C/bin"
    tools = sorted(x.name for x in bt_bin.iterdir() if x.is_file() and not x.name.endswith(".o"))
    if not tools:
        raise SystemExit("BaseTools are not built at %s" % bt_bin)
    write_descriptor(TOOLOVERRIDES / "basetools", "basetoolsbin_path_env.yaml",
                     '{\n  "scope": "global",\n  "override_id": "edk-tools-bin",\n'
                     '  "flags": ["set_shell_var", "set_path"],\n  "var_name": "EDK_TOOLS_BIN"\n}\n',
                     {name: str(bt_bin / name) for name in tools})

    # 2) nasm / iasl: descriptors live next to the tool they publish, the override simply
    #    points the same id at this directory so no download happens.
    path_env("nasm", '{\n  "scope": "edk2-build",\n  "override_id": "nasm-1",\n  "flags": ["set_path"]\n}\n',
             {"nasm": "/usr/bin/nasm"})
    path_env("uncrustify", '{\n  "scope": "cibuild",\n  "override_id": "uncrustify-ci-1",\n  "flags": ["set_path"]\n}\n',
             {"uncrustify": "/usr/bin/uncrustify" if Path("/usr/bin/uncrustify").exists() else "/bin/true"})
    path_env("iasl", '{\n  "scope": "cibuild",\n  "override_id": "iasl-ci-1",\n  "flags": ["set_path"]\n}\n',
             {"iasl": "/usr/bin/iasl"})

    # 3) crypto: give the descriptor an id and override it, then drop every include that
    #    would have consumed the prebuilt drivers.
    crypto_desc = base / "MU_BASECORE/CryptoPkg/Binaries/BaseCryptoDriver_ext_dep.json"
    data = json.loads(crypto_desc.read_text())
    if "id" not in data:
        data["id"] = "basecrypto-1"
        crypto_desc.write_text(json.dumps(data, indent=2) + "\n")
    path_env("crypto", '{\n  "scope": "global",\n  "override_id": "basecrypto-1",\n  "flags": ["set_build_var"],\n'
                       '  "var_name": "BLD_*_SHARED_CRYPTO_PATH"\n}\n')

    for rel in ("Platforms/AndromedaPkg/Andromeda.dsc.inc",):
        p = base / rel
        t = p.read_text()
        if "# !include $(SHARED_CRYPTO_PATH)/Driver/Bin/CryptoDriver.inc.dsc" not in t:
            t = re.sub(r"^(\s*)!include \$\(SHARED_CRYPTO_PATH\)/Driver/Bin/CryptoDriver\.inc\.dsc\s*$",
                       r"\1# !include $(SHARED_CRYPTO_PATH)/Driver/Bin/CryptoDriver.inc.dsc", t, count=1,
                       flags=re.MULTILINE)
        p.write_text(t)
    for rel in ("Platforms/AndromedaPkg/Frontpage.fdf.inc",):
        p = base / rel
        t = p.read_text()
        for inc in ("CryptoDriver.DXE.inc.fdf", "CryptoDriver.RUNTIMEDXE.inc.fdf"):
            # Remove the line instead of commenting it: this GenFds version still feeds the
            # text after # to PreprocessIncludeFile and aborts on the empty macro.
            t = re.sub(r"^[ \t]*#?[ \t]*!include \$\(SHARED_CRYPTO_PATH\)/Driver/Bin/" + re.escape(inc) + r"\s*$\n?",
                       "", t, flags=re.MULTILINE)
            continue
            t = re.sub(r"^(\s*)!include \$\(SHARED_CRYPTO_PATH\)/Driver/Bin/" + re.escape(inc) + r"\s*$",
                       r"\1" + target, t, count=1, flags=re.MULTILINE)
        p.write_text(t)

    # 3b) The known-good firmware for this board carries no crypto driver either (the dumped
    #     FV has 92 PE images, none of which references gEdkiiCryptoProtocolGuid), so the
    #     platform's hard-wired CryptoDriverBin_ALL lines are commented out too.
    for rel in ("Platforms/ShennongPkg/Device/xiaomi-shennong/DXE.dsc.inc",
                "Platforms/ShennongPkg/Device/xiaomi-shennong/DXE.inc",
                "Platforms/ShennongPkg/Device/xiaomi-shennong/APRIORI.inc",
                "Platforms/ShennongPkg/Device/xiaomi-shennong/profiles/DXE.full.inc",
                "Platforms/ShennongPkg/Device/xiaomi-shennong/profiles/APRIORI.full.inc"):
        f = base / rel
        if not f.is_file():
            continue
        text = f.read_text()
        # DSC fragments list components bare, FDF fragments list them after INF.
        text = re.sub(r"^(\s*)(INF\s+)?CryptoPkg/Binaries/edk2-basecrypto-driver-bin_extdep/\S+$",
                      r"\1# no prebuilt crypto driver on this board: secure boot is off\n"
                      r"\1# \2CryptoPkg/Binaries/edk2-basecrypto-driver-bin_extdep/Driver/Bin/CryptoDriverBin_ALL_Dxe_RELEASE_AARCH64.inf",
                      text, count=1, flags=re.MULTILINE)
        f.write_text(text)

    # 3c) The device package references SurfaceDuoACPI/8650/builtin/*.aml, which does not exist
    #     in any revision of the ACPI submodule. UniXNU boots from the ADT/DT (DtPlatformDxe),
    #     not ACPI, so the table bundle is left out rather than faked from another SoC.
    fdf = base / "Platforms/ShennongPkg/Shennong.fdf"
    text = fdf.read_text()
    if "!include $(PACKAGE_NAME)/Include/ACPI.inc" in text:
        text = text.replace("  # ACPI Tables\n  !include $(PACKAGE_NAME)/Include/ACPI.inc\n",
                            "  # ACPI tables omitted: the 8650 bundle is not in the ACPI submodule\n")
        fdf.write_text(text)

    # 4) platform: secure boot off, matching board.toml's ENABLE_SECUREBOOT = 0.
    dsc = base / "Platforms/ShennongPkg/Shennong.dsc"
    t = dsc.read_text()
    t = patch_once(t, r"^  SECURE_BOOT\s*=\s*1$", "  SECURE_BOOT                    = 0", str(dsc))
    t = patch_once(t, r"^  DXE_CRYPTO_SERVICES\s*=\s*STANDARD$",
                   "  DXE_CRYPTO_SERVICES            = NONE", str(dsc))
    dsc.write_text(t)

    print("prepared offline build环境：" + str(base))
    print("本地工具覆盖目录：" + str(TOOLOVERRIDES))


if __name__ == "__main__":
    main()
