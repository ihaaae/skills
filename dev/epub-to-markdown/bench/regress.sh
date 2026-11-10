#!/usr/bin/env bash
# Regression check: re-convert the reference books and compare output hashes
# with bench/golden.tsv. Books are matched by the sha256 of the .epub, so the
# file names in books/ don't matter; books that are not present are skipped.
#
#   bench/regress.sh            compare
#   bench/regress.sh --update   record the current outputs as the new golden
#
# Output differs slightly between pandoc versions, so golden rows are keyed by
# pandoc version too. A mismatch is not automatically a bug: look at the diff
# (out/<book>/skill.md vs. the previous run) and update the golden on purpose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/../../skills/epub-to-markdown/scripts/epub2md.py"
GOLDEN="$ROOT/bench/golden.tsv"
PV="$(pandoc --version | head -1 | awk '{print $2}')"
sha() { if command -v shasum >/dev/null; then shasum -a 256 "$1"; else sha256sum "$1"; fi | cut -d' ' -f1; }
fail=0; tmp="$(mktemp)"; touch "$GOLDEN"

for book in "$ROOT"/books/*.epub; do
  [ -f "$book" ] || continue
  in="$(sha "$book")"
  ref="$(awk -F'\t' -v i="$in" -v p="$PV" '$1==i && $3==p {print $4}' "$GOLDEN")"
  label="$(awk -F'\t' -v i="$in" '$1==i {print $2; exit}' "$GOLDEN")"
  [ -n "$label" ] || { echo "skip  $(basename "$book") (not a reference book)"; continue; }
  # name the copy after the label so the `source:` field matches the golden run
  work="$(mktemp -d)"; cp "$book" "$work/$label.epub"
  mkdir -p "$ROOT/out/$label"
  python3 "$SCRIPT" "$work/$label.epub" -o "$ROOT/out/$label/skill.md" 2>/dev/null
  got="$(sha "$ROOT/out/$label/skill.md")"; rm -rf "$work"
  if [ "${1:-}" = "--update" ]; then
    printf '%s\t%s\t%s\t%s\n' "$in" "$label" "$PV" "$got" >> "$tmp"; echo "rec   $label (pandoc $PV)"
  elif [ -z "$ref" ]; then echo "new   $label: no golden for pandoc $PV (run with --update to record)"
  elif [ "$ref" = "$got" ]; then echo "ok    $label (pandoc $PV)"
  else echo "DIFF  $label (pandoc $PV)"; fail=1; fi
done

if [ "${1:-}" = "--update" ]; then
  # keep rows for other pandoc versions / books not re-run, replace the rest
  awk -F'\t' 'NR==FNR {k[$1"\t"$3]=1; next} !(($1"\t"$3) in k)' "$tmp" "$GOLDEN" > "$GOLDEN.new" || true
  cat "$tmp" >> "$GOLDEN.new"; sort -k2,2 -k3,3 "$GOLDEN.new" > "$GOLDEN"; rm -f "$GOLDEN.new"
fi
rm -f "$tmp"; exit $fail
