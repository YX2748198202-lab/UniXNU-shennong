#!/bin/bash
# Download a GitHub Actions artifact from WSL.
#
# github.com/codeload are unreachable from WSL here (direct connection is reset),
# but the Windows side has a working proxy on 127.0.0.1:7890, and api.github.com
# itself is reachable. So: run Windows curl with the proxy, and it follows the
# redirect to the Azure blob storage that the plain WSL curl cannot reach.
#
# usage: fetch-artifact.sh <run-id> <out.zip> [artifact-name]
#   artifact-name defaults to shennong-kernel-1
set -euo pipefail

RUN=${1:?run id required}
OUT=${2:?output zip required}
NAME=${3:-shennong-kernel-1}
TOKEN_FILE=${GH_TOKEN_FILE:-/mnt/c/Users/yoox/AppData/Local/Temp/unixnu-shennong/gh_token.txt}
REPO=${REPO:-YX2748198202-lab/UniXNU-shennong}
PROXY=${WIN_PROXY:-http://127.0.0.1:7890}

TOKEN=$(tr -d '\r\n' < "$TOKEN_FILE")
[ -n "$TOKEN" ] || { echo "no token in $TOKEN_FILE" >&2; exit 1; }

ART_ID=$(python3 - "$REPO" "$RUN" "$NAME" "$TOKEN" <<'PY'
import json, sys, urllib.request
repo, run, name, token = sys.argv[1:5]
req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs/{run}/artifacts')
req.add_header('Authorization', 'token ' + token)
req.add_header('Accept', 'application/vnd.github+json')
for artifact in json.loads(urllib.request.urlopen(req, timeout=40).read().decode())['artifacts']:
    if artifact['name'] == name:
        print(artifact['id'])
        break
PY
)
[ -n "$ART_ID" ] || { echo "artifact $NAME not found on run $RUN" >&2; exit 1; }

WIN_OUT=$(wslpath -w "$OUT")
rm -f "$OUT"
/mnt/c/Windows/System32/curl.exe -sL -x "$PROXY" --max-time 900 \
	-H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
	-o "$WIN_OUT" -w "artifact $ART_ID http=%{http_code} bytes=%{size_download}\n" \
	"https://api.github.com/repos/$REPO/actions/artifacts/$ART_ID/zip"
ls -l "$OUT"
sha256sum "$OUT"
