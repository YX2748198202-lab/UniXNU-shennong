# Root policies for build 24A446

The directory name follows the framework's build-id convention: `scripts/policies/*<build_id>`
must match exactly one directory, because the ShengUfs component builds source storage through
`build-arm-driver.py`, which calls `build-sheng-source-storage.py` without `--policy-dir`. The
framework ships `scripts/policies/ipados-27.0.1-24A446/prelink-regression.json`, and the device
copy is merged into the same directory.

Contents are **not** iPadOS: they are the signed VerifiedRoot policies for the iPhone 17,1
(iOS 27.0.1, build 24A446) windows this board carries, produced by `scripts/make-root-policy.py`
with the board's own RSA-3072 key over the composed userdata image:

- `OS`        volume `C3A4D926-411E-4365-9855-1B66A5CE0263`, 2,499,072 blocks
- `SystemOS`  volume `ECFE851C-29F1-40D4-86BD-13597F9A1EE8`, 1,470,464 blocks

Each directory holds the 544-byte signed header (`manifest.header.bin`), the 395-byte trust
anchor (`trusted-key.bin`) and `verification.json`. The full block hash tables stay objects of
the userdata image (`XNU_SOURCE_STORAGE_TABLES=userdata`).
