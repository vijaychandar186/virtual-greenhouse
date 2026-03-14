#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${ROOT_DIR}/env/bin/activate" ]]; then
  source "${ROOT_DIR}/env/bin/activate"
fi

python -m src.app
