#!/usr/bin/env bash
# Run our converter and the baselines on every book in books/, then print
# the comparison table and the invariant checks for our output.
#
#   bench/run.sh                 all books in books/
#   bench/run.sh books/x.epub    one book
#
# Baselines are skipped when not installed:
#   pandoc         brew install pandoc                       (also required by our script)
#   markitdown     uv tool install 'markitdown[all]'         (or uvx is used automatically)
#   books-for-bots cargo install --git https://github.com/prime-radiant-inc/books-for-bots
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/.claude/skills/epub-to-markdown/scripts/epub2md.py"
BOOKS=("$@"); [ ${#BOOKS[@]} -eq 0 ] && BOOKS=("$ROOT"/books/*.epub)

for book in "${BOOKS[@]}"; do
  [ -f "$book" ] || { echo "no books found; put .epub files in books/" >&2; exit 1; }
  name="$(basename "$book" .epub)"; out="$ROOT/out/$name"; mkdir -p "$out"
  echo "== $name"
  python3 "$SCRIPT" "$book" -o "$out/skill.md" 2> "$out/skill.report.json" || { cat "$out/skill.report.json"; exit 1; }
  pandoc -f epub -t gfm-raw_html --wrap=none "$book" -o "$out/pandoc.md"
  if command -v markitdown >/dev/null; then markitdown "$book" -o "$out/markitdown.md"
  elif command -v uvx >/dev/null; then uvx markitdown "$book" -o "$out/markitdown.md"
  else echo "   (markitdown not installed, skipped)"; fi
  if command -v books-for-bots >/dev/null; then
    rm -rf "$out/bfb"; books-for-bots "$book" --output-dir "$out/bfb" >/dev/null
    cp "$(find "$out/bfb" -name '*.md' | head -1)" "$out/bfb.md"
  else echo "   (books-for-bots not installed, skipped)"; fi
  (cd "$out" && python3 "$ROOT/bench/metrics.py" *.md)
  python3 "$ROOT/bench/check.py" "$out/skill.md" || true
done
