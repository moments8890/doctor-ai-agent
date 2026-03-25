#!/bin/bash
# Run promptfoo eval for all prompts — one prompt per eval to avoid cross-product.
# Usage: ./run.sh                        — run all 9 prompts
#        ./run.sh doctor-extract routing — run specific prompts only
# Key is loaded from config/runtime.json automatically.

set -euo pipefail
cd "$(dirname "$0")"

export OPENAI_API_KEY=$(python3 -c "
import json
with open('../../config/runtime.json') as f:
    data = json.load(f)
print(data['categories']['llm']['settings']['GROQ_API_KEY']['value'])
")

ALL_PROMPTS=(
  doctor-extract patient-extract routing
  interview patient-interview query general
  diagnosis vision-ocr
)

if [ $# -gt 0 ]; then
  PROMPTS=("$@")
else
  PROMPTS=("${ALL_PROMPTS[@]}")
fi

TOTAL_P=0
TOTAL_F=0

for name in "${PROMPTS[@]}"; do
  echo "━━━ $name ━━━"
  result=$(npx promptfoo eval \
    -c "promptfooconfig.yaml" \
    -p "wrappers/${name}.md" \
    -t "cases/${name}.yaml" \
    --no-table --no-write 2>&1) || true

  echo "$result" | grep -E "passed|failed|errors|Duration|Tokens"

  p=$(echo "$result" | sed -n 's/.*\([0-9][0-9]*\) passed.*/\1/p' | head -1)
  f=$(echo "$result" | sed -n 's/.*\([0-9][0-9]*\) failed.*/\1/p' | head -1)
  TOTAL_P=$((TOTAL_P + ${p:-0}))
  TOTAL_F=$((TOTAL_F + ${f:-0}))
  echo ""
done

TOTAL=$((TOTAL_P + TOTAL_F))
echo "════════════════════════════════════"
echo "TOTAL: $TOTAL tests | $TOTAL_P passed | $TOTAL_F failed"
echo "════════════════════════════════════"

[ "$TOTAL_F" -eq 0 ] && exit 0 || exit 1
