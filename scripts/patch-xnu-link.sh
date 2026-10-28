#!/bin/bash
# Prepend a MakeInc.def patch to every build-xnu script under out/ so the
# kernel link tolerates kext-class undefined symbols (resolved by prelink).
set -u
for S in $(find -L out -maxdepth 6 -name build-xnu-4k-baseline.sh -path '*scripts*' 2>/dev/null); do
  if grep -q DYNAMIC_LOOKUP_PATCH "$S"; then
    echo "already-patched $S"
    continue
  fi
  TMP=$(mktemp)
  {
    echo '# DYNAMIC_LOOKUP_PATCH'
    echo 'sed -i "s/-Wl,-headerpad,152/-Wl,-headerpad,152 -Wl,-undefined,dynamic_lookup/" .cache/xnu-work/makedefs/MakeInc.def 2>/dev/null || true'
    cat "$S"
  } > "$TMP"
  mv "$TMP" "$S"
  chmod +x "$S"
  echo "script-patched $S"
done
exit 0
