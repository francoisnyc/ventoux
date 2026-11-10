#!/bin/bash
# usage: mutate.sh NAME FILE OLD NEW TESTS...
set -u
name=$1; file=$2; old=$3; new=$4; shift 4
python3 - "$file" "$old" "$new" <<'PY'
import sys
f, old, new = sys.argv[1:4]
s = open(f).read()
assert s.count(old) == 1, f"{old!r} found {s.count(old)} times"
open(f, "w").write(s.replace(old, new))
PY
out=$(uv run pytest -q -p no:cacheprovider "$@" 2>&1 | tail -4)
git checkout -q HEAD -- "$file"
echo "== $name: $(echo "$out" | grep -E 'passed|failed|error' | tail -1)"
echo "$out" | grep -E '^FAILED|^ERROR' | head -3 | cut -c1-200
