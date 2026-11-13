#!/usr/bin/env python3
"""Contract test for the verdict classifier in scripts/probe-walk.py.

The classifier is the part of the walk that has to be right: a wrong verdict
either moves the bisection past the real death point or stops it before it. It
already got this wrong once — `fastboot boot` returns while the device still
answers as `????????????  fastboot`, so "a fastboot device is visible" was read
as "the probe came back" and a round that had not even started reported a
reboot at 15 s.

The test replaces `fastboot` and `adb` with stubs that replay a timed device
timeline, then asks the real `boot_and_watch` for its verdict:

  hit          the device leaves the bootloader, then comes back late
  panic        same timeline, but earlier than --hit-after
  unknown      comes back so early that the loader must have failed
  boot-failed  the device never leaves the bootloader
  miss         never comes back inside the timeout

Usage:
  scripts/test-probe-walk.py [--keep]
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

STUB = '''#!/usr/bin/env python3
import json, os, sys, time
state = os.environ["STUB_STATE"]
with open(state) as handle:
    st = json.load(handle)
if "t0" not in st:
    st["t0"] = time.time()
    with open(state, "w") as handle:
        json.dump(st, handle)
elapsed = time.time() - st["t0"]
name = os.path.basename(sys.argv[0])
command = sys.argv[1] if len(sys.argv) > 1 else "devices"
if command == "devices":
    for until, text in st.get(name, []):
        if elapsed <= until:
            sys.stdout.write(text)
            break
elif name == "fastboot":
    # `fastboot boot IMAGE`: fastboot writes its progress to stderr.
    sys.stderr.write("Sending 'boot.img' (198948 KB)                     OKAY [  5.117s]\\n")
    sys.stderr.write("Booting                                            OKAY [  0.079s]\\n")
    sys.stderr.write("Finished. Total time: 6.396s\\n")
else:
    pass
sys.exit(0)
'''

# The device answers as `????????????  fastboot` until the handover, then the
# gadget vanishes, then it either comes back or it does not.
FASTBOOT_PRESENT = "????????????\tfastboot\n"
FASTBOOT_GONE = ""
ADB_RECOVERY = "List of devices attached\n9f72e95c\trecovery\n"
ADB_EMPTY = "List of devices attached\n"

CASES = [
    # name, fastboot timeline, adb timeline, hit_after, timeout, expected verdict, expected text
    ('hit', [(1.5, FASTBOOT_PRESENT), (999, FASTBOOT_GONE)],
     [(6.0, ADB_EMPTY), (999, ADB_RECOVERY)], 4, 30, 'hit', 'back on usb after'),
    ('panic', [(1.5, FASTBOOT_PRESENT), (999, FASTBOOT_GONE)],
     [(6.0, ADB_EMPTY), (999, ADB_RECOVERY)], 60, 30, 'panic', 'threshold 60 s'),
    ('unknown', [(1.5, FASTBOOT_PRESENT), (999, FASTBOOT_GONE)],
     [(0.5, ADB_EMPTY), (999, ADB_RECOVERY)], 4, 30, 'unknown', 'only'),
    ('boot-failed', [(9999, FASTBOOT_PRESENT)],
     [(9999, ADB_EMPTY)], 4, 12, 'boot-failed', 'never left the bootloader'),
    ('miss', [(1.5, FASTBOOT_PRESENT), (999, FASTBOOT_GONE)],
     [(9999, ADB_EMPTY)], 4, 12, 'miss', 'no usb for'),
]


def load_module():
    spec = importlib.util.spec_from_file_location('probe_walk', HERE / 'probe-walk.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_stubs(root: Path) -> Path:
    stubs = root / 'stubs'
    stubs.mkdir()
    for name in ('fastboot', 'adb'):
        path = stubs / name
        path.write_text(STUB)
        path.chmod(0o755)
    return stubs


def run_case(module, stubs: Path, case, keep: bool) -> None:
    name, fastboot, adb, hit_after, timeout, expected, expected_text = case
    work = Path(tempfile.mkdtemp(prefix=f'walk-{name}-'))
    state = work / 'state.json'
    state.write_text(json.dumps({'fastboot': fastboot, 'adb': adb}))
    image = work / 'image.img'
    image.write_bytes(b'\0' * 16)

    os.environ['STUB_STATE'] = str(state)
    os.environ['PATH'] = f'{stubs}:{os.environ.get("PATH", "")}'
    module.HERE = HERE
    verdict, detail, evidence = module.boot_and_watch(image, timeout, hit_after=hit_after)

    problems = []
    if verdict != expected:
        problems.append(f'verdict is {verdict!r}, expected {expected!r}')
    if expected_text not in detail:
        problems.append(f'evidence {detail!r} does not mention {expected_text!r}')
    if verdict in ('hit', 'panic', 'unknown') and not evidence.get('samples'):
        problems.append('no samples were recorded for a round that saw the device')
    if problems:
        print(f'FAIL {name}: ' + '; '.join(problems))
        print(f'     boot.log: {(work / "boot.log").read_text()[:200]!r}')
        raise SystemExit(1)
    print(f'ok   {name}: {detail}')
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--keep', action='store_true', help='keep the per-case work directories')
    args = parser.parse_args()

    for tool in ('fastboot', 'adb'):
        if shutil.which(tool) is None:
            print(f'{tool} is not on PATH; the stubs still shadow it, continuing')
    module = load_module()
    root = Path(tempfile.mkdtemp(prefix='walk-stubs-'))
    stubs = install_stubs(root)
    try:
        for case in CASES:
            run_case(module, stubs, case, args.keep)
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
    print('\nprobe-walk classifier: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
