#!/bin/bash
# Turn one CI artifact zip into ready-to-boot v0 images.
#
# The CI already writes payload.img (untouched kernel) and payload-xpu.img
# (AppleARMCPU IONameMatch rewritten cpu -> xpu) into the same artifact, so a
# single build can drive several device experiments without another rebuild.
#
# usage: prep-payload-variants.sh <artifact.zip> <out-dir> [variant ...]
#   variants: plain  xpu  plain+smp  xpu+smp  plain+noufs  ...
#   default:  plain xpu
set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
ZIP=${1:?artifact zip required}
OUT=${2:?output dir required}
shift 2
if [ $# -eq 0 ]; then set -- plain xpu; fi

TEMPLATE=${UNIXNU_V0_TEMPLATE:-/mnt/c/Users/yoox/AppData/Local/Temp/unixnu-shennong/Mu-shennong-smp.img}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUT"
echo "artifact: $ZIP ($(stat -c %s "$ZIP") bytes)"
sha256sum "$ZIP"
unzip -o -q "$ZIP" -d "$WORK"
PAYLOAD=$(find "$WORK" -name payload.img -type f | head -1)
XPU=$(find "$WORK" -name payload-xpu.img -type f | head -1)
[ -n "$PAYLOAD" ] || { echo "payload.img not found in artifact" >&2; exit 1; }
echo "payload    : $PAYLOAD $(stat -c %s "$PAYLOAD")"
sha256sum "$PAYLOAD"
[ -n "$XPU" ] && { echo "payload-xpu: $XPU"; sha256sum "$XPU"; }

for V in "$@"; do
	BASE=$PAYLOAD
	case "$V" in
	xpu*) BASE=${XPU:-} ;;
	esac
	[ -n "$BASE" ] || { echo "variant $V needs payload-xpu.img, absent" >&2; exit 1; }

	IMG=$OUT/payload-$V.img
	cp "$BASE" "$IMG"

	# boot-arg knobs that need no rebuild
	ARGS=""
	case "$V" in
	*smp*) ARGS="$ARGS --add sheng-smp=1" ;;
	esac
	if [ -n "$ARGS" ]; then
		# shellcheck disable=SC2086
		python3 "$REPO_DIR/scripts/patch-payload-args.py" --payload "$IMG" $ARGS
	fi
	python3 "$REPO_DIR/scripts/patch-payload-args.py" --payload "$IMG" --show

	BOOT=$OUT/Mu-$V.img
	python3 "$REPO_DIR/scripts/repack-v0-bootimg.py" \
		--template "$TEMPLATE" --payload "$IMG" --out "$BOOT"
	echo "== $V =="
	stat -c '%n %s' "$BOOT"
	sha256sum "$BOOT"
done
