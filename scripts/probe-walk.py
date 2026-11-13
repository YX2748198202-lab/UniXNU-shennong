#!/usr/bin/env python3
"""Walk reset probes forward through the early kernel boot, one question per boot.

The kernel cannot print before its own console exists, so the early boot is
measured with reset probes: a probe waits N seconds at its site, then issues
PSCI SYSTEM_RESET. A device that reboots (landing in recovery) proves the CPU
reached that site; a device that stays dark proves it did not. That gives a
monotone answer per boot, so walking the sites from the earliest to the latest
finds the first site that is *not* reached while paying one hang per bracket.

Each round here is fully automatic: build the probe kernel from the pristine
kernel, assemble the boot image with the same payload the working image uses,
refuse to boot anything the package verifier rejects, boot it, time the reboot,
then come back to fastboot through the recovery's adb (adb reboot bootloader)
and go on.

The clock starts when the image actually starts, not when `fastboot boot`
returns: the device keeps answering as `????????????  fastboot` for a few
seconds after the handover, and counting from the handover made an earlier walk
report a reboot at 15 s that had not happened. The reboot is timed from the
moment the bootloader gadget disappears.

Counting from there, a probe that is reached resets `delay` seconds after its
site; a kernel that panics first resets `--panic-reset` seconds after panic(),
which is much earlier. `--hit-after` is the threshold between the two.

Usage:
  scripts/probe-walk.py --pristine KERNEL.macho [--start N] [--delay 10]
                        spec [spec ...]

  spec := SYMBOL[@FUNCTION][:before]

Examples:
  scripts/probe-walk.py --pristine kernel.macho _vm_set_page_size@_arm_vm_init
  scripts/probe-walk.py --pristine kernel.macho _arm_vm_prot_init@_arm_vm_init:before

Only `fastboot boot` is used: no partition is written.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ART = Path(os.environ.get('UNIXNU_ARTIFACTS', '/home/yoox/android/artifacts/UniXNU-shennong'))
PATCH = HERE / 'patch-xnu-entry-probe.py'
VERIFY = HERE / 'verify-boot-package.py'
MAKE = ROOT / 'firmware' / 'make-boot-image.py'


def run(args, timeout=None, check=False):
    """Run a command with stdin closed (mtools asks questions on a terminal)."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, check=check)


def devices(command):
    result = run([command, 'devices'], timeout=20)
    return result.stdout


def fastboot_entries():
    """[(serial, state)] for every line of `fastboot devices`."""
    entries = []
    for line in devices('fastboot').splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == 'fastboot':
            entries.append((parts[0], 'fastboot'))
    return entries


def adb_entries():
    """[(serial, state)] for every line of `adb devices` below the header."""
    entries = []
    for line in devices('adb').splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] in ('device', 'recovery', 'sideload', 'rescue', 'bootloader'):
            entries.append((parts[0], parts[-1]))
    return entries


def on_usb():
    """Any state that means the CPU is past the kernel: recovery shell or bootloader."""
    return fastboot_entries() or adb_entries()


def wait_boot_started(limit=60):
    """Wait until the device leaves the bootloader, i.e. the image actually started.

    `fastboot boot` hands over and the device keeps answering as `????????????  fastboot` for a
    few seconds; treating that as "the probe came back" is what made an earlier walk read a
    reboot at 15 s that had not happened yet. The reliable signal is the disappearance of the
    bootloader gadget.
    """
    deadline = time.time() + limit
    while time.time() < deadline:
        time.sleep(1)
        if not fastboot_entries():
            return True
    return False


def wait_for_fastboot(limit=180):
    deadline = time.time() + limit
    while time.time() < deadline:
        if fastboot_entries():
            return True
        if adb_entries():
            run(['adb', 'reboot', 'bootloader'], timeout=30)
        time.sleep(5)
    return False


def to_fastboot():
    """Get the device into fastboot from wherever the last round left it."""
    if fastboot_entries():
        return True
    if adb_entries():
        print('device is in adb; asking for the bootloader', flush=True)
        run(['adb', 'reboot', 'bootloader'], timeout=30)
    return wait_for_fastboot()


def decode_fingerprint(elapsed, calibration, slice_spec):
    """Turn one measured reboot into the slice of panic()'s format-string address.

    The calibration round reboots BASE seconds after the same panic with no slice
    encoded, so subtracting it removes the boot time and the recovery's own startup:
    what is left is the slice times STEP.
    """
    shift, bits, base, step = (int(part, 0) for part in slice_spec.split(':'))
    if calibration is None:
        return {'error': 'no --calibration given, cannot place the delay on the scale'}
    offset = elapsed - calibration
    steps = round(offset / step)
    limit = (1 << bits) - 1
    if not 0 <= steps <= limit:
        return {'error': f'{offset} s is {steps} steps, outside 0..{limit}',
                'offset': offset}
    return {'shift': shift, 'bits': bits, 'base': base, 'step': step,
            'steps': steps, 'slice': steps, 'offset': offset}


def parse_spec(text):
    site, _, flags = text.partition(':')
    symbol, _, function = site.partition('@')
    return {'symbol': symbol,
            'function': function or '_arm_vm_init',
            'before': flags.strip() == 'before',
            'spec': text}


def build(pristine, spec, delay, out_dir, panic_reset=0, candidates=None, candidate_step=6,
          zero_slide=False):
    """Patch the pristine kernel, put it in the payload, assemble and verify the image."""
    out_dir.mkdir(parents=True, exist_ok=True)
    kernel = out_dir / 'kernel.macho'
    shutil.copyfile(pristine, kernel)
    if spec is None:
        # No site probe: the round is only about what panic() says.
        cmd = [sys.executable, str(PATCH), str(kernel), '--no-reset']
    else:
        cmd = [sys.executable, str(PATCH), str(kernel), '--reset-delay', str(delay),
               '--reset-after', spec['symbol'], '--in', spec['function']]
        if spec['before']:
            cmd.append('--reset-before')
    if candidates:
        cmd += ['--panic-candidates', str(candidates), '--candidate-step', str(candidate_step)]
    if zero_slide:
        # physmap_slide = 0 is what lets arm_vm_init get past early_random on this port; every
        # round after that frontier must carry the same patch or the probe never runs.
        cmd.append('--zero-physmap-slide')
    if panic_reset:
        # A second hook on panic(): it resets much earlier than the site probe does, so a
        # round that dies in a panic ends in a reboot instead of a device that has to be
        # power cycled by hand. The delay gap is what tells the two outcomes apart.
        cmd += ['--panic-reset', str(panic_reset)]
    result = run(cmd, timeout=600)
    (out_dir / 'patch.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        what = spec['spec'] if spec else 'panic candidates'
        raise SystemExit(f'patch failed for {what}:\n{result.stdout}{result.stderr}')

    payload = out_dir / 'payload.img'
    shutil.copyfile(ART / 'payload' / 'payload-fd46.img', payload)
    if run(['mcopy', '-o', '-i', str(payload), str(kernel),
            '::/EFI/UniXNU/Payloads/kernel.macho'], timeout=600).returncode:
        raise SystemExit('mcopy of the kernel into the payload failed')

    image = out_dir / 'image.img'
    result = run([sys.executable, str(MAKE),
                  '--uefi', '/home/yoox/android/sources/uefi-sheng',
                  '--fd', str(ART / 'boot' / 'SILICIUM_UEFI-fd43.fd'),
                  '--payload', str(payload),
                  '--template', str(ART / 'boot' / 'Mu-shennong-fd46.img'),
                  '--append-dtb', '/home/yoox/android/sources/uefi-sheng/Resources/DTBs/shennong.dtb',
                  '--out', str(image), '--verify'], timeout=900)
    (out_dir / 'make-image.log').write_text(result.stdout + result.stderr)
    if result.returncode or not image.exists():
        raise SystemExit(f'image assembly failed for {spec["spec"] if spec else "panic candidates"}')

    result = run([sys.executable, str(VERIFY), '--image', str(image),
                  '--fd', str(ART / 'boot' / 'SILICIUM_UEFI-fd43.fd'),
                  '--payload', str(payload)], timeout=900)
    (out_dir / 'verify.log').write_text(result.stdout + result.stderr)
    failures = [line for line in result.stdout.splitlines() if 'failure' in line]
    if result.returncode or not failures or not failures[-1].startswith('0 failure'):
        raise SystemExit(f'preflight rejected {spec["spec"] if spec else "panic candidates"}: '
                         f'{failures or result.stderr[:300]}')
    return image


def boot_and_watch(image, timeout, hit_after=0):
    """Boot one image and time the reboot, counted from the moment the image started."""
    result = run(['fastboot', 'boot', str(image)], timeout=600)
    # fastboot writes its progress to stderr, so judge the combined output.
    combined = result.stdout + result.stderr
    (Path(image).parent / 'boot.log').write_text(combined)
    if result.returncode or 'Booting' not in combined or 'OKAY' not in combined:
        return 'boot-failed', combined, {}

    if not wait_boot_started():
        return 'boot-failed', 'the device never left the bootloader', {}

    started = time.time()
    deadline = started + timeout
    samples = []
    while time.time() < deadline:
        time.sleep(3)
        elapsed = int(time.time() - started)
        fastboots, adbs = fastboot_entries(), adb_entries()
        samples.append({'elapsed': elapsed,
                        'fastboot': [f'{s} {t}' for s, t in fastboots],
                        'adb': [f'{s} {t}' for s, t in adbs]})
        if not fastboots and not adbs:
            continue
        evidence = {'t_boot_started': round(started, 3), 'samples': samples}
        if elapsed < 5:
            # A bounce this early is the loader dying before the kernel is entered, not a probe.
            return 'unknown', f'back on usb after only {elapsed} s', evidence
        if not hit_after:
            return 'hit', f'back on usb after {elapsed} s', evidence
        # With a panic hook armed every round reboots; what separates a reached site from an
        # early panic is when the reboot happens.
        verdict = 'hit' if elapsed >= hit_after else 'panic'
        return verdict, f'back on usb after {elapsed} s (threshold {hit_after} s)', evidence
    return 'miss', f'no usb for {timeout} s', {'t_boot_started': round(started, 3),
                                               'samples': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pristine', required=True, type=Path, help='the unpatched kernel.macho')
    parser.add_argument('--delay', type=int, default=10, help='seconds the probe waits before resetting')
    parser.add_argument('--timeout', type=int, default=200, help='seconds to wait for the reboot')
    parser.add_argument('--panic-reset', type=int, default=0, metavar='SECONDS',
                        help='also reboot this many seconds after panic(), so a round that dies in a panic still comes back')
    parser.add_argument('--hit-after', type=int, default=0, metavar='SECONDS',
                        help='with --panic-reset: a reboot later than this means the site was reached')
    parser.add_argument('--fingerprint', metavar='SHIFT:BITS:BASE:STEP',
                        help='the round used --panic-fingerprint with this slice; decode the reboot')
    parser.add_argument('--calibration', type=float, metavar='SECONDS',
                        help='elapsed reboot time of a --panic-reset BASE round, measured on this device')
    parser.add_argument('--out', type=Path, default=ART / 'probe-walk', help='where the rounds are kept')
    parser.add_argument('--zero-physmap-slide', action='store_true',
                        help='patch out _early_random in every round (physmap_slide = 0)')
    parser.add_argument('--no-site', action='store_true',
                        help='build a probe with no site at all; pair it with --panic-reset or '
                             '--panic-candidates to ask panic() a question')
    parser.add_argument('--panic-candidates', type=Path, metavar='FILE',
                        help='candidate table for the fingerprint round')
    parser.add_argument('--candidate-step', type=int, default=6, metavar='SECONDS',
                        help='delay spacing of the candidate table (default 6 s)')
    parser.add_argument('spec', nargs='*', help='SYMBOL[@FUNCTION][:before]')
    args = parser.parse_args()

    if args.no_site:
        args.spec = ['none']
    elif not args.spec:
        parser.error('give at least one spec, or --no-site')
    specs = [None] if args.no_site else [parse_spec(text) for text in args.spec]
    if not to_fastboot():
        raise SystemExit('no device in fastboot and none reachable over adb')
    args.out.mkdir(parents=True, exist_ok=True)
    report = []
    for index, spec in enumerate(specs, 1):
        if spec is None:
            name = f'{index:02d}-no-site'
        else:
            name = f'{index:02d}-{spec["symbol"]}{"-before" if spec["before"] else ""}'
        out_dir = args.out / name
        what = 'no site probe' if spec is None else f'{spec["function"]} -> {spec["symbol"]}'
        print(f'[{name}] building ({what})', flush=True)
        image = build(args.pristine, spec, args.delay, out_dir, args.panic_reset,
                      args.panic_candidates, args.candidate_step, args.zero_physmap_slide)
        for attempt in (1, 2):
            print(f'[{name}] booting {image.name} ({image.stat().st_size} bytes), attempt {attempt}',
                  flush=True)
            verdict, detail, evidence = boot_and_watch(image, args.timeout,
                                                      hit_after=args.hit_after)
            if verdict != 'unknown':
                break
            print(f'[{name}] {verdict}: {detail}; retrying once', flush=True)
            if not to_fastboot():
                break
        print(f'[{name}] {verdict}: {detail}', flush=True)
        slice_info = None
        if args.fingerprint and verdict in ('hit', 'panic'):
            measured = int(detail.split('after ')[1].split(' s')[0])
            slice_info = decode_fingerprint(measured, args.calibration, args.fingerprint)
            if 'error' in slice_info:
                print(f'[{name}] fingerprint: {slice_info["error"]}', flush=True)
            else:
                print(f'[{name}] fingerprint: panic() fmt bits {slice_info["shift"]}'
                      f'..{slice_info["shift"] + slice_info["bits"] - 1} = '
                      f'0x{slice_info["slice"]:x} (delay {slice_info["base"]}'
                      f'+{slice_info["slice"]}x{slice_info["step"]} s)', flush=True)
        report.append({**spec, 'round': name, 'verdict': verdict, 'detail': detail,
                       **({'fingerprint': slice_info} if slice_info else {}),
                       'image': str(image), 'when': time.strftime('%Y-%m-%d %H:%M:%S'),
                       **evidence})
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
        if verdict not in ('hit', 'panic'):
            print(f'[{name}] walk stops here: {verdict}. Last reached site is the one before this one.',
                  flush=True)
            break
        if verdict == 'panic':
            print(f'[{name}] the kernel panicked before this site; continuing to the next round',
                  flush=True)
        if not to_fastboot():
            print(f'[{name}] device did not come back to fastboot; stopping', flush=True)
            break
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
