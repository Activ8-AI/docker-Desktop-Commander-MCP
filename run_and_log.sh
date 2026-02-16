#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: ./run_and_log.sh stacks/<stack>.yaml <persona> <role> [payload-json]" >&2
  exit 1
fi

STACK_PATH="$1"
PERSONA="$2"
ROLE="$3"
PAYLOAD="${4:-{}}"
STACKS_DIR="$(dirname "${STACK_PATH}")"
TS="$(date -u +%Y-%m-%d/%H%M%S)"
RUN_DIR="PreservationVault/runs/${TS}"
mkdir -p "${RUN_DIR}/outputs"

python3 codex_relay.py \
  --persona "${PERSONA}" \
  --role "${ROLE}" \
  --payload "${PAYLOAD}" \
  --stacks-dir "${STACKS_DIR}" \
  --stack-file "${STACK_PATH}" \
  --run-dir "${RUN_DIR}" > "${RUN_DIR}/relay.json"

python3 codex_logger.py --run-dir "${RUN_DIR}" --record-env
cp codex_evaluation.json "${RUN_DIR}/evaluation.json"

if git -C PreservationVault rev-parse --git-dir > /dev/null 2>&1; then
  git -C PreservationVault add .
  if ! git -C PreservationVault commit -m "Run ${TS}" > /dev/null 2>&1; then
    echo "PreservationVault commit skipped (nothing to commit)"
  fi
else
  echo "PreservationVault is not a git repository; skipping commit step"
fi
