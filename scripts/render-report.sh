#!/usr/bin/env bash
set -euo pipefail

usage() { echo 'usage: scripts/render-report.sh --release-sha <40-hex> --output dist/secure-coding-report-generic.pdf' >&2; exit 64; }

release_sha=''
output=''
while (($#)); do
  case "$1" in
    --release-sha) (($# >= 2)) || usage; release_sha=$2; shift 2 ;;
    --output) (($# >= 2)) || usage; output=$2; shift 2 ;;
    *) usage ;;
  esac
done
[[ $release_sha =~ ^[0-9a-f]{40}$ ]] || usage
[[ $output == dist/secure-coding-report-generic.pdf ]] || { echo 'generic output path is fixed' >&2; exit 65; }

head_sha=$(git rev-parse HEAD)
[[ $head_sha == "$release_sha" ]] || { echo "HEAD $head_sha differs from release SHA" >&2; exit 1; }
[[ -z $(git status --porcelain --untracked-files=all) ]] || { echo 'checkout is not clean' >&2; exit 1; }
mapfile -t rc_tags < <(git tag --points-at HEAD 'v*-rc.*')
((${#rc_tags[@]} == 1)) || { echo 'HEAD must have exactly one immutable RC tag' >&2; exit 1; }

image=$(python3 - <<'PY'
from pathlib import Path
import re
text=Path('docs/report/toolchain.lock.md').read_text()
match=re.search(r'^- Renderer OCI image: `([^`]+@sha256:[0-9a-f]{64})`$', text, re.M)
if not match:
    raise SystemExit('renderer OCI digest is absent from toolchain lock')
print(match.group(1))
PY
)

epoch=$(git show -s --format=%ct HEAD)
mkdir -p dist
rm -f "$output"
docker run --rm --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --user 65532:65532 \
  -e TZ=UTC -e LC_ALL=C.UTF-8 -e SOURCE_DATE_EPOCH="$epoch" \
  -e RELEASE_SHA="$release_sha" \
  -v "$PWD:/work:ro" \
  -v "$PWD/dist:/out:rw" \
  "$image" \
  /renderer/render --source /work --output /out/secure-coding-report-generic.pdf

test -s "$output"
sha256sum "$output"
pdfinfo "$output" | python3 -c "import sys; lines=sys.stdin.read(); assert 'Pages:' in lines; print(lines, end='')"
