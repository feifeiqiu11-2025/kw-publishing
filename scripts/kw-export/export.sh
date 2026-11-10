#!/bin/bash
# Clean re-export of one KindleWood story (Classic layout, A4) for the book path.
# Reads PROD read-only (service-role key in storyme-app/.env.local.prod-backup);
# ask the user before running it. Fixes vs the app export (LOCAL PRINT FIX):
# duplicate scene rows dropped, portrait photos can't push captions to an extra
# page, Chinese captions break at the author's own line breaks, back cover loads.
# Usage: export.sh <story-uuid> <out-dir>
set -euo pipefail
ID="$1"; OUT="$2"; K="$(cd "$(dirname "$0")" && pwd)"
R=/Users/feifeiq/Projects/StoryMe.AI/storyme-app
mkdir -p "$OUT"; cd "$R"; set -a; source .env.local.prod-backup; set +a
export PDF_BACK_COVER_SRC="$R/public/images/pdf-back-cover.png"
npx -y tsx --tsconfig "$R/tsconfig.json" "$K/export.tsx" "$ID" --format=a4 --layout=classic --out="$OUT"
