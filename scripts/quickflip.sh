#!/bin/bash
# Wait for a kernel build, fetch its artifact, verify the board ADT is the one in
# the payload and repack a v0 boot image ready for `fastboot boot`.
#
#   quickflip.sh <run-id> [variant ...]
#
# variants (default: plain): plain | xpu | plain+smp | xpu+smp
# The image is written to .artifacts/shennong/run-<id>/Mu-<variant>.img
set -euo pipefail

RUN=${1:?run id required}
shift
VARIANTS=("$@"); [ ${#VARIANTS[@]} -gt 0 ] || VARIANTS=(plain)

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
ART=/home/yoox/android/workspace/.artifacts/shennong/run-$RUN
LOG=$ART/quickflip.log
mkdir -p "$ART"
exec > >(tee -a "$LOG") 2>&1

TOKEN_FILE=${GH_TOKEN_FILE:-/mnt/c/Users/yoox/AppData/Local/Temp/unixnu-shennong/gh_token.txt}
TOKEN=$(tr -d '\r\n' < "$TOKEN_FILE")
GH_REPO=${REPO:-YX2748198202-lab/UniXNU-shennong}

gh_api() {
	python3 - "$GH_REPO" "$RUN" "$TOKEN" "$1" <<'PY'
import json, sys, urllib.request
repo, run, token, what = sys.argv[1:5]
def get(path):
    req = urllib.request.Request('https://api.github.com' + path)
    req.add_header('Authorization', 'token ' + token)
    req.add_header('Accept', 'application/vnd.github+json')
    return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
if what == 'status':
    run_info = get(f'/repos/{repo}/actions/runs/{run}')
    print(run_info['status'], run_info['conclusion'] or 'none')
elif what == 'artifact':
    for artifact in get(f'/repos/{repo}/actions/runs/{run}/artifacts')['artifacts']:
        if artifact['name'] == 'shennong-kernel-1':
            print(artifact['id'], artifact['size_in_bytes'])
            break
elif what == 'failed':
    for job in get(f'/repos/{repo}/actions/runs/{run}/jobs?per_page=5')['jobs']:
        print('job', job['name'], job['status'], job['conclusion'])
        for step in job['steps']:
            if step['conclusion'] not in ('success', 'skipped', None):
                print('  FAILED', step['number'], step['name'], step['conclusion'])
PY
}

echo "== waiting for run $RUN =="
for _ in $(seq 1 240); do
	read -r STATUS CONCLUSION <<<"$(gh_api status)"
	case "$STATUS" in
	completed) break ;;
	esac
	sleep 20
done
echo "run: ${STATUS:-?} ${CONCLUSION:-?}"
if [ "${CONCLUSION}" != "success" ]; then
	gh_api failed
	echo "build did not succeed; nothing to fetch"
	exit 1
fi

echo "== fetching artifact =="
"$REPO_DIR/scripts/fetch-artifact.sh" "$RUN" "$ART/shennong-kernel-1.zip"

echo "== checking the payload ADT =="
rm -rf "$ART/work"; mkdir -p "$ART/work"
unzip -o -q "$ART/shennong-kernel-1.zip" "*/payload/payload.img" -d "$ART/work"
PAYLOAD=$(find "$ART/work" -name payload.img | head -1)
mcopy -o -i "$PAYLOAD" ::/EFI/UniXNU/Payloads/kernel.macho.adt "$ART/adt-in-payload.bin"
python3 - "$ART/adt-in-payload.bin" <<'PY'
import sys
data = open(sys.argv[1], 'rb').read()
ipad = b'iPad7,1' in data or b'J120AP' in data or b'cpu7' in data
print(f'adt {len(data)} bytes; iPad tree: {ipad}')
if ipad:
    raise SystemExit('the payload still carries the iPad device tree')
PY

echo "== repacking =="
TEMPLATE=${UNIXNU_V0_TEMPLATE:-/mnt/c/Users/yoox/AppData/Local/Temp/unixnu-shennong/Mu-shennong-smp.img}
for v in "${VARIANTS[@]}"; do
	case "$v" in
	xpu*) python3 "$REPO_DIR/scripts/patch-applearmcpu-ioname.py" --payload "$PAYLOAD" \
			--out "$ART/payload-$v.img" >/dev/null ;;
	*) cp "$PAYLOAD" "$ART/payload-$v.img" ;;
	esac
	if [[ "$v" == *smp* ]]; then
		python3 "$REPO_DIR/scripts/patch-payload-args.py" --payload "$ART/payload-$v.img" \
			--add sheng-smp=1 >/dev/null
	fi
	python3 "$REPO_DIR/scripts/repack-v0-bootimg.py" --template "$TEMPLATE" \
		--payload "$ART/payload-$v.img" --out "$ART/Mu-$v.img" | tail -3
done
echo "== ready =="
ls -l "$ART"/Mu-*.img
sha256sum "$ART"/Mu-*.img
