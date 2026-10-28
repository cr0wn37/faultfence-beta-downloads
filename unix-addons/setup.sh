#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"

echo '=== FaultFence public beta local setup (macOS / Linux) ==='
command -v python3 >/dev/null 2>&1 || { echo 'ERROR: Python 3 not found.' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"' || exit 1
command -v docker >/dev/null 2>&1 || { echo 'ERROR: Install Docker Desktop (macOS) or Docker Engine (Linux).' >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo 'ERROR: Start Docker and confirm your user has permission to use it.' >&2; exit 1; }

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check "$ROOT/wheel/faultfence-0.8.0.dev0-py3-none-any.whl"
docker build --pull -t faultfence-isolated:6b -f "$ROOT/docker/Dockerfile" "$ROOT/docker"
docker run --rm --network none --read-only --cap-drop ALL faultfence-isolated:6b python -c 'import os; assert os.geteuid() == 65534'
"$ROOT/.venv/bin/faultfence" --help
printf '\nSETUP COMPLETE. Next run: bash try_sample.sh\n'
