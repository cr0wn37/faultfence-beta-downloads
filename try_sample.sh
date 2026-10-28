#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CLI="$ROOT/.venv/bin/faultfence"
[[ -x "$CLI" ]] || { echo 'ERROR: Run bash setup.sh first.' >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo 'ERROR: Docker must be running.' >&2; exit 1; }

"$CLI" validate --project "$ROOT/sample-agent"
"$CLI" attacks
"$CLI" test --project "$ROOT/sample-agent" --attack all --runs 1 \
  --authorized-resource invoice_100 \
  --authorized-max-amount 100 --authorized-amount 100 \
  --authorized-currency INR --authorized-quantity 1 \
  --authorized-units 6 --units-per-pack 3
printf '\nSample finished. Reports: %s\n' "$ROOT/sample-agent/faultfence_reports/batches"
