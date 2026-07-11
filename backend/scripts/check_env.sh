#!/usr/bin/env bash
# Pre-deployment check: ensure no placeholder values remain in .env
# Exit code 1 if any placeholder is found.

set -euo pipefail

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

PLACEHOLDERS=(
  "your-deepseek-api-key"
  "your-wechat-app-id"
  "your-wechat-app-secret"
  "your-wechat-mch-id"
  "your-wechat-api-key-v3"
  "change-me-in-production"
)

EXIT_CODE=0
for pattern in "${PLACEHOLDERS[@]}"; do
  if grep -q "$pattern" "$ENV_FILE" 2>/dev/null; then
    echo "FAIL: $ENV_FILE still contains placeholder '$pattern'"
    EXIT_CODE=1
  fi
done

if [ $EXIT_CODE -eq 0 ]; then
  echo "OK: $ENV_FILE has no placeholder values"
fi

exit $EXIT_CODE
