#!/usr/bin/env bash
# sync-internal-wiki-docs.sh — copy source MDs into the wiki public dir.
#
# The wiki renders these via wiki-internal.html (marked.js client-side
# rendering) so the source of truth stays in the original .md files.
# Re-run this script before committing if any source changed; vite's
# build will pick up the latest copies.
#
# Hooked into deploy.sh on the Tencent host so production wiki always
# reflects gitee/main on every push.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT_DIR/frontend/web/public/wiki/internal-docs"
mkdir -p "$DEST"

# slug:source-path pairs. Bash 3.x compatible (no associative arrays).
DOCS=(
  "architecture:docs/architecture.md"
  "services:deploy/tencent/SERVICES.md"
  "runbook-subdomain-split:deploy/tencent/RUNBOOK-subdomain-split.md"
  "tencent-resources:docs/deploy/tecenet-deployment/资源清单.md"
  "glitchtip:deploy/tencent/glitchtip.md"
  "dbgate:deploy/tencent/adminer.md"
  "mysql-restore:deploy/tencent/mysql_restore.md"
  "product-strategy:docs/product/product-strategy.md"
)

for entry in "${DOCS[@]}"; do
  slug="${entry%%:*}"
  rel="${entry#*:}"
  src="$ROOT_DIR/$rel"
  dst="$DEST/${slug}.md"
  if [[ ! -f "$src" ]]; then
    echo "WARN: source missing: $src" >&2
    continue
  fi
  cp "$src" "$dst"
  printf "  copied %-30s ← %s\n" "${slug}.md" "$rel"
done

echo "OK — ${#DOCS[@]} internal wiki docs synced to $DEST"
