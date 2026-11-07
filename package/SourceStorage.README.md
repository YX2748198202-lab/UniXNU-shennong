# Source storage runtime

`SourceStorage.cpp`, `SourceRootPolicies.cpp`, `SourceRootBinding.cpp`, `BootReset.c`,
`WifiFirmware.c` and their local headers (`BootResetCore.h`, `WifiFirmware.h`) come unchanged from
the sibling reference port **UniXNU/UniXNU-sheng** (`package/`).

`scripts/build-sheng-source-storage.py` builds the arm64e source UFS runtime from exactly these
files and refuses to run when one is absent, so they are inputs of the kernel build rather than
optional board code:

- `SourceStorage.cpp` assembles the runtime and provides the boot log tick the log writer calls.
- `SourceRootBinding.cpp` defines `native_verified_block_root_authorized`,
  `native_verified_block_manifest_sha384` and `native_verified_block_volume_device`, the three
  symbols the owner-root patches call from `bsd_init` and `kern_exec`.
- `SourceRootPolicies.cpp` loads the signed policy bundle (`verified_root_key`,
  `vr_xnu_crypto` come from the `VerifiedRoot` component's `include/`).
- `BootReset.c` holds the guarded fastboot reset and `WifiFirmware.c` the addon firmware loader.

`verified_root.h` and `VerifiedBlockPolicy.h` are **not** copied here: the build gets them from the
`VerifiedRoot` component through `-I kits/VerifiedRoot/include`.
