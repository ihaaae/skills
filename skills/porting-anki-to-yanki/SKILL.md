---
name: porting-anki-to-yanki
description: Converts Anki "Notes in Plain Text (.txt)" exports into yanki-compatible Markdown notes inside an Obsidian vault. Use when asked to port, import, migrate, or convert an Anki deck/export into Obsidian for the yanki plugin.
---

# Porting Anki Decks to Yanki (Obsidian)

Converts an Anki `.txt` export (one deck) into a folder of one-note-per-card Markdown files that the [yanki](https://github.com/kitschpatrol/yanki-obsidian) Obsidian plugin will sync back to Anki.

## When to use

Trigger when the user provides:
- an Anki text export (typically named like `A__Math__0-Terms.txt`, where `__` is Anki's deck-hierarchy separator), AND
- a destination inside an Obsidian vault (typically a `Flashcards/...` folder watched by yanki).

## Defaults for this user

- Vault: `~/Documents/Obsidian/Main`
- Yanki watched root: `~/Documents/Obsidian/Main/04 Flashcards/Obsidian`
- Deck `A__B__C` → folder `04 Flashcards/Obsidian/A/B/C/`

Confirm with the user before assuming.

## Workflow

1. **Read the export header** (first ~3 lines) to confirm the format. The script assumes:
   - `#separator:tab`
   - `#html:true`
   - 3 columns: front, back, tags

   If the export uses different separators / column counts, stop and ask the user (or adapt `parse_anki_export` in [scripts/convert.py](scripts/convert.py)).

2. **Decide the destination folder.** Mirror the deck hierarchy below the yanki-watched root. Per yanki's [folder→deck rules](https://github.com/kitschpatrol/yanki-obsidian#watched-folder-list), a lone subfolder chain collapses to a single deck in Anki. To preserve a multi-level hierarchy like `A::Math::0-Terms`, the user must also place a (possibly suspended) note in each intermediate folder.

3. **Dry-run first** to verify the row count and basic/cloze split:
   ```bash
   python3 ~/.config/agents/skills/porting-anki-to-yanki/scripts/convert.py \
     <source.txt> <dest_dir> --dry-run
   ```

4. **Convert**:
   ```bash
   python3 ~/.config/agents/skills/porting-anki-to-yanki/scripts/convert.py \
     <source.txt> <dest_dir>
   ```

5. **Spot-check** a few generated `.md` files — especially any with LaTeX, cloze, or heavy HTML — to confirm the conversions look right.

6. **Tell the user the next steps in Obsidian**:
   - Add the destination folder (or its yanki root) to yanki's watched-folder list.
   - Ensure Anki is running with AnkiConnect.
   - Run command `Yanki: Sync flashcard notes to Anki`.

## Conversions performed by the script

| Anki source                       | Yanki Markdown output                |
| --------------------------------- | ------------------------------------ |
| 3-col TSV row (front, back, tags) | one `.md` file per row               |
| `<strong>` / `<b>`                | `**bold**`                           |
| `<em>` / `<i>`                    | `*italic*`                           |
| `<br>`                            | newline                              |
| `<span>`, `<a>`, `<div>`, `<font>` | tags stripped, inner text kept       |
| `&nbsp;`, HTML entities           | decoded; nbsp → regular space        |
| `\(x\)` inline LaTeX              | `$x$` (GitHub-style math, yanki-parsed) |
| `\[x\]` display LaTeX             | `$$\nx\n$$`                          |
| `{{c1::text}}` / `{{c1::text::hint}}` | `~~text~~` (yanki cloze)         |
| basic card (front + back)         | `front\n\n---\n\nback`               |
| cloze card                        | front with `~~...~~`; `---` + back only if back is non-empty |
| non-empty `tags` column           | YAML frontmatter `tags:` list        |

Filenames are derived from the first non-empty content line of the note, sanitized for the filesystem and deduplicated with `(2)`, `(3)`, … suffixes.

## When to extend the script

Edit [scripts/convert.py](scripts/convert.py) when an export uses something this skill does not yet handle, e.g.:
- different separator (`#separator:semicolon`) → adjust `csv.reader` delimiter
- more than 3 columns / extra fields → extend `parse_anki_export` and `build_note`
- non-default Anki note types (Image Occlusion, custom types) → these are not supported by yanki itself and should be skipped or flagged.
