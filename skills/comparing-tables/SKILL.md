---
name: comparing-tables
description: "Compares two Excel, CSV, or TSV tables with a deterministic CLI. Use when asked to compare spreadsheets, find added/deleted/changed rows, compare by primary key, or produce diff.xlsx reports."
---

# Comparing Tables

Use this skill for reproducible table comparison. Let the CLI find differences deterministically; ask the user for comparison rules, then use the agent to explain results and flag suspicious changes.

## Dev environment on this machine

This machine has a project-local `uv` environment for this skill at `~/Projects/CYQ`:

```sh
cd ~/Projects/CYQ
uv sync
uv run python scripts/compare-tables.py --help
```

The environment includes `openpyxl` for Excel I/O and `pandas` for future table-normalization work. Prefer this project venv for development and repeated CLI use. The skill also keeps a bundled copy of the script at `~/.config/agents/skills/comparing-tables/scripts/compare-tables.py` for portability.

## Workflow

1. Identify the comparison meaning before running anything:
   - **Primary-key comparison**: preferred for business tables where row order may change.
   - **Position comparison**: only for files with identical layout where `B12` should match `B12`.
2. Always ask which file is **old/baseline** and which file is **new/compared** unless the user has already said so unambiguously. In the report, state that:
   - `Added` means present in the new file but absent from the old file.
   - `Deleted` means present in the old file but absent from the new file.
3. For Excel inputs, always ask the user for the worksheet/sheet name before comparing unless they already provided it. Do not inspect sheets and infer the target sheet for them.
4. For primary-key comparison, always ask the user for the key column before comparing unless they already provided it. Do not infer the row key from table contents or domain heuristics.
5. Ask for these optional rules when missing and important:
   - Ignored columns, e.g. `更新时间`, `导出时间`.
   - Numeric tolerance, e.g. `0.01`.
   - Blank handling: the script treats `NULL`, blank cells, and empty strings as equal by default.
6. Before trusting a primary-key diff, check whether the user-selected key is unique in both inputs. Duplicate keys usually indicate bad source data or the wrong key. Do not silently pair duplicate-key rows or invent a composite key unless the user explicitly approves that rule.
7. For Excel inputs, ignore formatting-only worksheet extents. Use the true used range from non-empty cells rather than `worksheet.max_row` / `worksheet.max_column` alone, because Excel metadata can report huge stale ranges such as column `16384`.
8. Run the CLI with `uv run python scripts/compare-tables.py ...` from `~/Projects/CYQ`; do not use system `python` or `python3` for this skill.
9. Inspect the terminal summary.
10. Return the useful result to the user: counts, output file paths, and the highest-risk changes.

## Primary-key comparison

Use this for normal data diffing:

```sh
cd ~/Projects/CYQ
uv run python scripts/compare-tables.py \
  old.xlsx new.xlsx \
  --sheet 成绩表 \
  --key 学号 \
  --ignore-cols 更新时间,导出时间 \
  --tolerance 0.01 \
  --out diff.xlsx \
  --json diff_summary.json
```

Outputs:

- `Summary`: old/new row counts and added/deleted/changed/unchanged counts.
- `Added`: rows present only in the new file.
- `Deleted`: rows present only in the old file.
- `Changed`: one row per changed field with key, field, old value, new value, and numeric delta when applicable.
- Optional JSON summary for downstream agent/script use.

Exit codes:

- `0`: no differences found.
- `1`: differences found; comparison completed successfully.
- `2`: comparison failed, e.g. missing sheet, missing key, duplicate key, unreadable file.

### Duplicate-key handling

Assume the chosen primary key should be unique. The first validation step for a keyed comparison is therefore:

1. Count key values in the old file.
2. Count key values in the new file.
3. If either file has duplicate keys, stop and report the duplicate keys and counts.
4. Ask the user whether to fix the source data, choose a different key, use a composite key, or fall back to position/full-row comparison.

Do not automatically treat duplicate keys as normal. Automatic duplicate matching can hide source-data problems and can create false “changed” records by pairing the wrong rows.

## Position comparison

Use only when both files have the same layout and cell positions should match:

```sh
cd ~/Projects/CYQ
uv run python scripts/compare-tables.py \
  old.xlsx new.xlsx \
  --mode position \
  --sheet Sheet1 \
  --out diff.xlsx
```

The `Changed` sheet then reports row, column, field/header, old value, and new value.

## Supported inputs

- `.xlsx`, `.xlsm`, `.xltx`, `.xltm` through `openpyxl`.
- `.csv` and `.tsv` through Python's standard CSV reader.

For Excel formulas, the script reads the workbook formula text rather than cached calculated values. That makes formula edits visible in the diff.

## Excel used-range guidance

Excel files often contain stale formatting or metadata that makes a sheet appear much larger than the real table. Before comparing Excel sheets, determine the actual used range from cells whose values are non-empty after normalization. Ignore rows and columns outside that true value-bearing range.

This prevents slow or noisy comparisons when a workbook reports a maximum column such as `16384` even though the real table only has a small number of populated columns.

## Header and domain-specific heuristics

Automatic header detection, record-region detection, Chinese engineering-sheet defaults, and domain-specific key guesses can be useful for explaining or validating results after the user has chosen the sheet and key, but they may not generalize. Do not use these heuristics to select the sheet or key without asking the user first.

If using such heuristics, make them explicit in the report, for example:

- “Detected header row by matching `序号` and `电缆编号`.”
- “Ignored section-heading rows where the key column is blank.”
- “Used `电缆编号` as the key because the user confirmed it.”

Ask the user for the key/sheet/direction when those choices affect the meaning of added, deleted, or changed rows.

## Reporting guidance

For a simple compare request, report:

```markdown
Compared old `old.xlsx` to new `new.xlsx` by `学号` on sheet `成绩表`.
`Added` means present only in the new file; `Deleted` means present only in the old file.

- Added: 5
- Deleted: 2
- Changed rows: 8
- Changed fields: 11
- Unchanged: 105

Wrote `diff.xlsx` and `diff_summary.json`.
Most suspicious: score for `20260005` changed from `85` to `58` (`-27`).
```

Do not present the agent's interpretation as the audit source of truth. The generated diff files are the source of truth; the agent explanation is a review layer.
