#!/usr/bin/env bash
# Staged DEVELOPMENT link, optionally with a RELEASE mapping reference.
# No IPSW, prelink, boot packaging or device writes.
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 || ! $1 =~ ^(plan|build)(-reference)?$ ]]; then
    echo "usage: $0 {plan|build|plan-reference|build-reference} FRAMEWORK_CHECKOUT NEW_ARTIFACT_DIR [EXISTING_FEEDS_CACHE]" >&2
    exit 2
fi
mode=${1%%-reference}
reference=no
if [[ $1 == *-reference ]]; then reference=yes; fi
framework=$(cd "$2" && pwd -P)
out="$3"
cache=${4:-}
device=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
pin=c740efb5b23e94453bb179f7801eb592baafacf6
profile=ios-27.0.1-24A446-iphone16pro
xnu=ac9718fb1af618d5ce8678d0dc6e8a58f252216f
soc=a9f45dc60c035084b95463781538380f4c3606c9
jobs=${JOBS:-3}
[[ $jobs =~ ^[1-9][0-9]*$ ]]
if [[ $mode == plan && -z $cache ]]; then
    echo 'plan mode requires an existing feed cache' >&2
    exit 2
fi
if [[ $mode == build && $(uname -s) != Darwin ]]; then
    echo 'build mode requires macOS and the validated Apple Clang; use plan on Linux' >&2
    exit 2
fi
if [[ -n $cache ]]; then cache=$(cd "$cache" && pwd -P); fi
out=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$out")
case "$out/" in
    "$device/"*|"$framework/"*) echo 'artifact directory must be outside both checkouts' >&2; exit 2 ;;
esac
if [[ -n $cache && $out/ == "$cache/"* ]]; then
    echo 'artifact directory must not be inside the feed cache' >&2
    exit 2
fi
for path in "$device" "$framework" "$out"; do
    [[ ! $path =~ [[:space:]] ]] || { echo "unsupported whitespace in: $path" >&2; exit 2; }
done
head=$(git -C "$device" rev-parse HEAD)
git -C "$framework" cat-file -e "$pin^{commit}"
mkdir "$out"  # Fail rather than reuse an earlier experiment.
exec > >(tee "$out/run.log") 2>&1
printf 'mode=%s reference=%s jobs=%s device=%s framework=%s\n' "$mode" "$reference" "$jobs" "$head" "$pin"
date -u +%FT%TZ
mkdir "$out/device" "$out/build"
git -C "$device" archive "$head" | tar -x -C "$out/device"
git clone --quiet --shared --no-checkout "$framework" "$out/framework"
git -C "$out/framework" checkout --quiet --detach "$pin"
git -C "$framework" ls-tree -r "$pin" | awk '$1 == "160000" {print $3, $4}' > "$out/submodules.txt"
[[ -s $out/submodules.txt ]]
while read -r revision path; do
    [[ $(git -C "$framework/$path" rev-parse --show-toplevel) == "$framework/$path" ]]
    git clone --quiet --shared --no-checkout "$framework/$path" "$out/framework/$path"
    git -C "$out/framework/$path" checkout --quiet --detach "$revision"
done < "$out/submodules.txt"
GIT_ALLOW_PROTOCOL=file git -C "$out/framework" submodule update --init --recursive
git -C "$out/framework" submodule status --recursive > "$out/submodule-status.txt"
if grep -qE '^[-+U]' "$out/submodule-status.txt"; then
    echo 'isolated framework has an uninitialized or wrong-revision submodule' >&2
    exit 2
fi
[[ ! -e $out/framework/profiles/os/$profile ]]
cp -R "$out/device/profiles/os/$profile" "$out/framework/profiles/os/$profile"
if [[ -n $cache ]]; then cp -R "$cache" "$out/build/feeds"; fi

python3 - "$out/device" "$reference" <<'PY'
from pathlib import Path
import sys

device = Path(sys.argv[1])
board, cfg = device/'board.toml', device/'configs/shennong_defconfig'

def edit(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        sys.exit(f'{path}: unexpected input; cannot stage experiment')
    path.write_text(text.replace(old, new))

if sys.argv[2] == "no":
    edit(board, '  "build-fileset-release-reference.py --tree . --lto",\n', '')
edit(board, '"os:patches/xnu/series"]',
     '"os:patches/xnu/series", "device:patches/experiments/console-native.series"]')
edit(cfg, 'CONFIG_XNU_EXTRA_LD_ARCHIVES=""',
     'CONFIG_XNU_EXTRA_LD_ARCHIVES="-Wl,-rename_section,__DATA_CONST,__const,__KLDDATA,__const"')
patch_dir = device/'patches/experiments'
(patch_dir/'console-native.series').write_text('pexpert-late-write-section.patch\n')
PY

cd "$out/framework"
export PYTHONDONTWRITEBYTECODE=1
if [[ $mode == plan ]]; then export GIT_ALLOW_PROTOCOL=file; fi
args=(-D "$out/device" --out "$out/build" -j "$jobs")
./unixnu defconfig shennong_defconfig "${args[@]}"
./unixnu status --json "${args[@]}" > "$out/status.json"
python3 - "$out/status.json" "$xnu" "$soc" "$reference" <<'PY'
import json
from pathlib import Path
import sys

status = json.loads(Path(sys.argv[1]).read_text())
board = status['board']
if (status['schema_version'] != 2 or status['configuration'] != 'shennong_defconfig'
        or board['ipsw']['build'] != '24A446' or board['ipsw']['product'] != 'iPhone17,1'
        or board['os']['arch'] != 'arm64e'
        or board['os']['xnu_revision'] != sys.argv[2]
        or len(status['patch_order']) != 72
        or Path(status['patch_order'][-1]).name != 'pexpert-late-write-section.patch'):
    sys.exit('unexpected native experiment configuration or patch order')
archives = board['kernel']['archives']
recipe = 'build-fileset-release-reference.py --tree . --lto'
references = [a for a in archives if 'build-fileset-release-reference.py' in a]
expected = [recipe] if sys.argv[4] == 'yes' else []
if references != expected or (expected and archives[-1] != recipe):
    sys.exit('unexpected RELEASE reference archive plan')
cfg = Path(status['config_path']).read_text()
for name, value in {
    'XNU_EXTRA_LD_ARCHIVES': '"-Wl,-rename_section,__DATA_CONST,__const,__KLDDATA,__const"',
    'XNU_KERNEL_CHAINED_FIXUPS': 'y',
}.items():
    if [line for line in cfg.splitlines() if line.startswith(f'CONFIG_{name}=')] != [f'CONFIG_{name}={value}']:
        sys.exit(f'unexpected effective CONFIG_{name}')
actual = {m['name']: m['revision'] for m in status['modules'] if m['kind'] == 'soc'}
if actual.get('sm8550') != sys.argv[3]:
    sys.exit('unexpected SoC feed revision')
print('verified format 2 / 24A446 / arm64e / 72 patches / '
      + ('RELEASE LTO reference last' if expected else 'no RELEASE reference'))
PY
if [[ $mode == plan ]]; then
    ./unixnu tree "${args[@]}"
    printf 'host plan only: %s\n' "$out/status.json"
    exit 0
fi
xcodebuild -version
cc=$(xcrun --sdk iphoneos --find clang)
shasum -a 256 "$cc"
python3 "$out/device/scripts/check-ptrauth-codegen.py" "$cc" --out "$out/ptrauth"
./unixnu build kernel --skip-prelink "${args[@]}"
work="$out/build/shennong/$profile/shennong"
native="$work/kernel/kernel.macho"
shasum -a 256 "$native" "$work/kernel/kernel.json" "$work/xnu-inputs.json"
xcrun otool -l "$native" > "$out/native-load-commands.txt"
grep -qw LC_SEGMENT_SPLIT_INFO "$out/native-load-commands.txt"
grep -qw LC_DYLD_CHAINED_FIXUPS "$out/native-load-commands.txt"
python3 "$out/device/scripts/check-console-layout.py" --experiment "$native" --nm "$(xcrun --find nm)"
if [[ $reference == yes ]]; then
    ref="$work/tree/build/xnu/fileset-reference/mach.release.bcm2837.unstripped.noctf"
    python3 - "$out" "$work" "$ref" "$head" "$pin" <<'PYTHON'
import hashlib
import json
from pathlib import Path
import struct
import sys

out, work, ref = map(Path, sys.argv[1:4])
status = json.loads((out / 'status.json').read_text())
record = json.loads((work / 'kernel/kernel.json').read_text())
ref_record = json.loads(ref.with_suffix('.json').read_text())


def arm64e_execute_digest(path):
    with path.open('rb') as stream:
        magic, cpu, subtype, filetype = struct.unpack('<4I', stream.read(16))
        if (magic, cpu, subtype & 0xffffff, filetype) != (0xfeedfacf, 0x100000c, 2, 2):
            sys.exit(f'not an arm64e MH_EXECUTE: {path}')
        stream.seek(0)
        return hashlib.file_digest(stream, 'sha256').hexdigest()


native_digest = arm64e_execute_digest(work / 'kernel/kernel.macho')
ref_digest = arm64e_execute_digest(ref)
os_profile = status['board']['os']
if (record['mode'] != 'native-only' or record['prelink_skipped'] is not True
        or record['boot_verified'] is not False or record['kernelcache_kexts_added'] is not False
        or record['native_sha256'] != native_digest or record['candidate_sha256'] != native_digest
        or ref_digest == native_digest or ref_record['sha256'] != ref_digest
        or ref_record['inputs']['mode'] != 'lto'
        or ref_record['inputs']['versions'] != {
            'UNIXNU_IOS_VERSION': os_profile['ios_version'],
            'UNIXNU_XNU_DARWIN': os_profile['darwin'],
            'UNIXNU_XNU_VERSION': os_profile['xnu_version'],
        }):
    sys.exit('unexpected DEVELOPMENT/RELEASE artifacts or mismatched reference provenance')
pair = {
    'device_revision': sys.argv[4],
    'framework_revision': sys.argv[5],
    'xnu_revision': os_profile['xnu_revision'],
    'build': status['board']['ipsw']['build'],
    'native_sha256': native_digest,
    'release_reference_sha256': ref_digest,
    'expected_donor_kernelcache_sha256': status['board']['kernel']['prelink']['kernelcache_sha256'],
    'prelink_skipped': True,
    'boot_verified': False,
}
(out / 'native-reference-pair.json').write_text(json.dumps(pair, indent=2) + '\n')
print(f'RELEASE comparison-only MH_EXECUTE sha256 {ref_digest}')
PYTHON
fi
