#!/usr/bin/env bash
# lint-ui.sh — catch UI design system violations before they ship.
# Run: bash scripts/lint-ui.sh [--fix]
# Exit code: 0 = clean, 1 = violations found
#
# Checks frontend/web/src/ for:
#   1. Hardcoded hex colors (should use COLOR.* tokens)
#   2. Instant show/hide without Collapse (should animate)
#   3. Raw CircularProgress for content loading (should use SectionLoading)
#   4. Raw Dialog for bottom sheets (should use SheetDialog)
#   5. Inline nowTs() definitions (should import from utils/time)
#   6. Hardcoded #95EC69 (should use COLOR.wechatGreen)
#   7. Hardcoded #fffef5 (should use HIGHLIGHT_ROW_SX)

set -euo pipefail

SRC="frontend/web/src"
VIOLATIONS=0
FIX=false
[[ "${1:-}" == "--fix" ]] && FIX=true

# Colors for output
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

warn() {
  echo -e "${YELLOW}⚠  $1${NC}"
  echo "   $2"
  VIOLATIONS=$((VIOLATIONS + 1))
}

section() {
  echo ""
  echo -e "${NC}── $1 ──${NC}"
}

# ── 1. Hardcoded hex colors in v2 (admin legitimately uses MUI hex; v1 deleted) ──
section "Hardcoded hex colors"

# Scope: v2 only. Admin (pages/admin/) uses MUI and hex is fine there.
# Known exceptions: theme.js, debug HUD, avatar color palette, lint-ui-ignore.
HARDCODED_HEX=$(grep -rn --include="*.jsx" --include="*.js" \
  -E '"#[0-9a-fA-F]{3,8}"' "$SRC/v2" \
  | grep -v 'theme\.js' \
  | grep -v 'KeyboardDebugHUD' \
  | grep -v 'constants\.jsx.*AVATAR' \
  | grep -v '\.test\.' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$HARDCODED_HEX" ]]; then
  COUNT=$(echo "$HARDCODED_HEX" | wc -l | tr -d ' ')
  warn "$COUNT hardcoded hex color(s) found" "Use COLOR.* tokens from theme.js instead"
  echo "$HARDCODED_HEX" | head -15
  [[ $COUNT -gt 15 ]] && echo "   ... and $((COUNT - 15)) more"
else
  echo -e "${GREEN}✓ No hardcoded hex colors${NC}"
fi

# ── 2. Instant show/hide without Collapse ──
section "Missing Collapse transitions"

# Pattern: {someVar && (<Box or <div — should use <Collapse in={someVar}>
# Only check page files, not components (components may have valid reasons)
INSTANT_TOGGLE=$(grep -rn --include="*.jsx" \
  -E '\{(open|expanded|show)\s*&&\s*\(' "$SRC/pages" \
  | grep -v 'Collapse' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$INSTANT_TOGGLE" ]]; then
  COUNT=$(echo "$INSTANT_TOGGLE" | wc -l | tr -d ' ')
  warn "$COUNT instant show/hide pattern(s) — consider Collapse" "Wrap with <Collapse in={flag}> for smooth animation"
  echo "$INSTANT_TOGGLE" | head -10
else
  echo -e "${GREEN}✓ No instant show/hide patterns${NC}"
fi

# ── 3. Raw CircularProgress in v2 (admin uses MUI CircularProgress legitimately) ──
section "Raw CircularProgress for content loading"

RAW_SPINNER=$(grep -rn --include="*.jsx" \
  '<CircularProgress' "$SRC/v2" \
  | grep -v 'AppButton\|loading.*prop\|isProcessing\|size={10}\|size={12}' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$RAW_SPINNER" ]]; then
  COUNT=$(echo "$RAW_SPINNER" | wc -l | tr -d ' ')
  warn "$COUNT raw CircularProgress in page files" "Use <SectionLoading> for content loading, AppButton loading prop for buttons"
  echo "$RAW_SPINNER" | head -10
else
  echo -e "${GREEN}✓ No raw content spinners${NC}"
fi

# ── 4. Inline nowTs() definitions ──
section "Duplicate utility functions"

INLINE_NOWTS=$(grep -rn --include="*.jsx" --include="*.js" \
  'function nowTs' "$SRC" \
  | grep -v 'utils/time' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$INLINE_NOWTS" ]]; then
  warn "Inline nowTs() definition(s)" "Import from utils/time.js instead"
  echo "$INLINE_NOWTS"
else
  echo -e "${GREEN}✓ No duplicate nowTs()${NC}"
fi

# ── 5. Specific hardcoded values that have tokens ──
section "Known token violations"

WECHAT_GREEN=$(grep -rn --include="*.jsx" '"#95EC69"' "$SRC" \
  | grep -v 'theme\.js' | grep -v '// lint-ui-ignore' || true)
HIGHLIGHT_BG=$(grep -rn --include="*.jsx" '"#fffef5"' "$SRC" \
  | grep -v 'theme\.js' | grep -v '// lint-ui-ignore' || true)

if [[ -n "$WECHAT_GREEN" ]]; then
  warn "Hardcoded #95EC69 — use COLOR.wechatGreen" ""
  echo "$WECHAT_GREEN"
fi
if [[ -n "$HIGHLIGHT_BG" ]]; then
  warn "Hardcoded #fffef5 — use COLOR.highlightBg or HIGHLIGHT_ROW_SX" ""
  echo "$HIGHLIGHT_BG"
fi
[[ -z "$WECHAT_GREEN" && -z "$HIGHLIGHT_BG" ]] && echo -e "${GREEN}✓ No known token violations${NC}"

# ── 6. Hardcoded fontSize in v2 (breaks tier scaling) ──
# v2 uses FONT.*/ICON.* CSS-var tokens that scale with the accessibility
# text tier (compact/standard/large/extraLarge). Hardcoded px values are
# frozen at 1.0× — large-text users see no change. Allow theme.js (defines
# tokens), debug HUDs, and explicit "// lint-ui-ignore" opt-outs.
section "Hardcoded fontSize in v2 (breaks tier scaling)"

HARDCODED_FONTSIZE=$(grep -rn --include="*.jsx" --include="*.js" \
  -E '(fontSize:\s*[0-9]+|fontSize:\s*"[0-9]+px")' "$SRC/v2" \
  | grep -v 'theme\.js' \
  | grep -v 'KeyboardDebugHUD' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$HARDCODED_FONTSIZE" ]]; then
  COUNT=$(echo "$HARDCODED_FONTSIZE" | wc -l | tr -d ' ')
  warn "$COUNT hardcoded fontSize value(s) in v2" "Use FONT.* (text) or ICON.* (icons) tokens from v2/theme.js — hardcoded px bypasses accessibility tier scaling"
  echo "$HARDCODED_FONTSIZE" | head -15
  [[ $COUNT -gt 15 ]] && echo "   ... and $((COUNT - 15)) more"
else
  echo -e "${GREEN}✓ No hardcoded fontSize in v2${NC}"
fi

# ── 7. Raw Dialog for bottom sheets ──
section "Raw Dialog usage"

RAW_DIALOG=$(grep -rn --include="*.jsx" \
  'import.*Dialog.*from "@mui/material"' "$SRC" \
  | grep -v 'ConfirmDialog\|SheetDialog\|components/' \
  | grep -v '// lint-ui-ignore' \
  || true)

if [[ -n "$RAW_DIALOG" ]]; then
  warn "Raw MUI Dialog import in page files" "Use ConfirmDialog or SheetDialog wrappers"
  echo "$RAW_DIALOG"
else
  echo -e "${GREEN}✓ No raw Dialog imports in pages${NC}"
fi

# ── Summary ──
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $VIOLATIONS -eq 0 ]]; then
  echo -e "${GREEN}✓ All UI design system checks passed${NC}"
  exit 0
else
  echo -e "${RED}✗ $VIOLATIONS violation(s) found${NC}"
  echo "  Add '// lint-ui-ignore' on the line to suppress false positives."
  echo "  See CLAUDE.md § 'UI Design System' for rules."
  exit 1
fi
