#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
python_bin="${PYTHON:-python3}"
if [[ -z "${PYTHON:-}" && -x "$root/.venv/bin/python" ]]; then
  python_bin="$root/.venv/bin/python"
fi

export PYTHONPATH="$root/src"
mkdir -p "$root/runs"
output="$(mktemp -d "$root/runs/review.XXXXXX")"

"$python_bin" -m labproof demo --output "$output/replay"
"$python_bin" -m labproof verify-artifacts "$output/replay"
"$python_bin" -m labproof brief "$output/replay" --demo --output "$output/remediation"
"$python_bin" -m labproof verify-brief "$output/replay" "$output/remediation"
"$python_bin" -m labproof export-viewer "$output/replay" \
  evidence/local-python-01 evidence/local-typescript-01 evidence/local-rust-01 evidence/local-c-03 \
  --brief "$output/remediation" --output "$output/review.json"

printf '\nImport %s in the LabProof viewer.\n' "$output/review.json"
