#!/usr/bin/env bash
set -euo pipefail

readonly OUTPUT_PATH='dist/secure-coding-report-generic.pdf'
readonly LOCK_PATH='docs/report/toolchain.lock.md'

usage() {
  echo "usage: scripts/render-report.sh --release-sha <40-hex> --output $OUTPUT_PATH" >&2
  exit 64
}

die() {
  echo "render-report: $*" >&2
  exit 1
}

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
[[ $output == "$OUTPUT_PATH" ]] || { echo 'generic output path is fixed' >&2; exit 65; }
command -v docker >/dev/null || die 'docker is required'
command -v git >/dev/null || die 'git is required'

head_sha=$(git rev-parse --verify HEAD)
[[ $head_sha == "$release_sha" ]] || die "HEAD $head_sha differs from release SHA"
[[ -z $(git status --porcelain --untracked-files=all) ]] || die 'checkout is not clean'
mapfile -t rc_tags < <(git tag --points-at HEAD 'v*-rc.*')
((${#rc_tags[@]} == 1)) || die 'HEAD must have exactly one immutable RC tag'

mapfile -t lock_values < <(python3 - "$LOCK_PATH" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
patterns = (
    r"^- Renderer OCI image \(linux/amd64\): `([^`]+@sha256:[0-9a-f]{64})`$",
    r"^- Renderer inventory SHA-256: `([0-9a-f]{64})`$",
)
for pattern in patterns:
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise SystemExit(f"toolchain lock must contain exactly one match for {pattern}")
    print(matches[0])
PY
)
((${#lock_values[@]} == 2)) || die 'invalid toolchain lock'
readonly image=${lock_values[0]}
readonly inventory_sha256=${lock_values[1]}

docker image inspect "$image" >/dev/null ||
  die "pinned renderer is not present locally; preload exactly $image"
resolved_digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$image")
[[ $resolved_digest == "$image" ]] ||
  die "local renderer digest mismatch: expected $image, found $resolved_digest"

python3 - "$release_sha" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

release_sha = sys.argv[1]
tracked = subprocess.run(
    ["git", "ls-files", "-z"], check=True, capture_output=True
).stdout.decode().split("\0")
for name in tracked:
    lowered = name.lower()
    if name and (
        name.startswith((".evidence-private/", "private-submission/", ".gjc/state/"))
        or "/.gjc/_session-" in name
        or "kroki" in lowered
    ):
        raise SystemExit(f"forbidden tracked render input: {name}")

metadata = Path("report/metadata.yaml").read_text(encoding="utf-8")
if not re.search(r"^date: 1970-01-01$", metadata, re.MULTILINE):
    raise SystemExit("report metadata date must be normalized")
if not re.search(r"^release-sha: RELEASE_SHA$", metadata, re.MULTILINE):
    raise SystemExit("report metadata must contain the deterministic release SHA placeholder")
PY

readonly epoch=$(git show -s --format=%ct HEAD)
mkdir -p dist
tmp_output=$(mktemp "$PWD/dist/.secure-coding-report.XXXXXX.pdf")
trap 'rm -f "$tmp_output"' EXIT

docker run --rm --pull=never --platform linux/amd64 --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e TZ=UTC \
  -e LC_ALL=C.UTF-8 \
  -e SOURCE_DATE_EPOCH="$epoch" \
  -e RELEASE_SHA="$release_sha" \
  -v "$PWD:/work:ro" \
  -v "$tmp_output:/out/report.pdf:rw" \
  "$image" \
  /renderer/render \
    --source /work \
    --metadata /work/report/metadata.yaml \
    --stylesheet /work/report/pdf.css \
    --output /out/report.pdf \
    --inventory-sha256 "$inventory_sha256" \
    --offline \
    --canonicalize-mermaid \
    --canonicalize-pdf

[[ -s $tmp_output ]] || die 'renderer produced an empty PDF'
docker run --rm --pull=never --platform linux/amd64 --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  --user "$(id -u):$(id -g)" \
  -v "$tmp_output:/input/report.pdf:ro" \
  "$image" \
  /renderer/inspect \
    --input /input/report.pdf \
    --require-font 'Noto Sans CJK KR' \
    --require-font 'Noto Sans Mono CJK KR' \
    --reject-metadata 'CreationDate|ModDate|Producer|Creator|Author' \
    --reject-uri-scheme 'https?'

mv -f "$tmp_output" "$output"
trap - EXIT
sha256sum "$output"