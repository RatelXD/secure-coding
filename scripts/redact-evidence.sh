#!/usr/bin/env bash
set -euo pipefail

if (($# != 2)); then
  echo 'usage: scripts/redact-evidence.sh INPUT_TEXT OUTPUT_TEXT' >&2
  exit 64
fi
input=$1
output=$2
[[ -f $input ]] || { echo 'input must be a regular file' >&2; exit 66; }
[[ $output == artifacts/sanitized/* ]] || { echo 'output must be under artifacts/sanitized/' >&2; exit 65; }
[[ $input != private-submission/* && $input != */private-submission/* ]] || { echo 'user-private input is forbidden' >&2; exit 77; }
mkdir -p "$(dirname "$output")"

python3 - "$input" "$output" <<'PY'
from pathlib import Path
import re, sys
source, destination = map(Path, sys.argv[1:])
body = source.read_bytes()
if b'\x00' in body:
    raise SystemExit('binary evidence requires a dedicated metadata-strip workflow')
text = body.decode('utf-8')
for forbidden in (r'(?i)LMS\s*(?:ID|password|credential|cookie|session)', r'\[WHS\].*\([^)]{4}\)\.pdf'):
    if re.search(forbidden, text):
        raise SystemExit('identity/LMS material is forbidden, not redactable by Team')
patterns = [
    (r'(?i)(authorization:\s*(?:bearer|token)\s+)\S+', r'\1[REDACTED]'),
    (r'(?i)(cookie:\s*)\S+', r'\1[REDACTED]'),
    (r'(?i)(session(?:id|_key)?[=:]\s*)\S+', r'\1[REDACTED]'),
    (r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', '[IP-REDACTED]'),
    (r'/home/[^/\s]+/', '/home/[USER]/'),
    (r'(?i)https://[a-z0-9-]+\.ngrok-free\.app', 'https://[RC-HOST]'),
]
for pattern, replacement in patterns:
    text = re.sub(pattern, replacement, text)
destination.write_text(text, encoding='utf-8', newline='\n')
PY

echo "Redacted text written to $output; independent L5 review is required before publication."
