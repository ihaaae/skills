---
name: syncing-notes-to-anki
description: "Authors plain-text Markdown flashcard notes in ~/Documents/Notes and syncs them to Anki with the user's yanki CLI fork, preserving card review history. Use when adding or editing flashcards, syncing notes to Anki, renaming decks, or troubleshooting the yanki sync."
---

# Syncing Notes to Anki (yanki CLI)

Turns plain-text Markdown notes into Anki cards via the user's fork of yanki
(<https://github.com/ihaaae/yanki>), a standalone Go CLI. No Obsidian, no plugin.

## Layout (this user)

- Notes root: `~/Documents/Notes`
- Config: `~/Documents/Notes/yanki.toml`
- CLI: `~/Projects/yanki/yanki` (built from the fork)
- AnkiConnect: `http://127.0.0.1:8765` (Anki desktop must be running)
- Namespace: `Yanki Obsidian - Vault ID ab51b05225fd4807`

The namespace is the identity of the whole collection. **Never change it** — it
is how the CLI recognizes (and only ever touches) its own notes. Changing it
orphans every existing note and creates duplicates, losing review history.

## Sync

```sh
~/Projects/yanki/yanki config ~/Documents/Notes        # settings + note count
~/Projects/yanki/yanki sync ~/Documents/Notes --dry-run # ALWAYS preview first
~/Projects/yanki/yanki sync ~/Documents/Notes           # apply
~/Projects/yanki/yanki list ~/Documents/Notes           # list managed notes
~/Projects/yanki/yanki clean ~/Documents/Notes          # DANGER: delete all managed notes
```

The steady state is `182 unchanged`. A `created` or `deleted` you did not cause
by adding/removing a file is a red flag — stop and investigate before applying.

## Review history is preserved by `noteId`

Each note file carries a managed frontmatter field:

```yaml
---
noteId: 1780891390878   # the Anki note id; never edit by hand
tags:
  - parent/child        # `/` becomes Anki's `::`
deckName: Custom Deck   # optional; overrides the inferred deck
---
```

The CLI matches a file to its Anki note by `noteId`. Updating content, moving a
note between decks, and renaming files all keep the same note id and therefore
the scheduling. Deleting the file deletes the note (and its history); deleting
`noteId` makes the next sync create a fresh note.

## Writing notes (Markdown → note type)

The note type is inferred from the body:

| Markdown in the file | Anki note type |
|---|---|
| `front` then `---` then `back` | Basic |
| two `---` in a row | Basic (and reversed card with extra) |
| last line `_answer_` | Basic (type in the answer) |
| `~~text~~` before the first `---` | Cloze |

Cloze details: `~~...~~` is one deletion; `---` adds back-of-card content; end a
cloze with `_hint_` for a hint; `~~1 ...~~` pins the cloze index so several
deletions reveal together. Cloze numbers are assigned in order — do not reorder
or renumber clozes in an existing note, or Anki regenerates cards and their
scheduling resets.

## Decks come from folders

The deck is the note's folder path relative to the longest common ancestor of
all synced files, joined with `::`. A folder segment is included in deck names
only when a note sits directly inside it — that is what the placeholder file is
for.

Current layout keeps the `New::` prefix:

```
~/Documents/Notes/New/New PlaceHolder.md   → deck "New"
~/Documents/Notes/New/Git/git log/x.md     → deck "New::Git::git log"
```

To change the prefix (e.g. `New` → `A`), rename the folder and sync; the cards
move decks and keep their history. Keep a placeholder file directly in that
folder, and do not name it the same as the folder.

Files whose name equals their parent folder's name are ignored
(`ignore_folder_notes = true`); they exist only to shape the folder tree.

## Adding a note

1. Write the `.md` file in the right deck folder (with no `noteId`).
2. `yanki sync ~/Documents/Notes --dry-run` → confirm exactly one `created`.
3. `yanki sync ~/Documents/Notes` → the CLI writes `noteId` into the file.

## Verification and recovery

Before a risky change, snapshot scheduling through AnkiConnect (`cardsInfo`) and
compare `due` / `interval` / `factor` / `reps` / `lapses` afterward. A healthy
content update or deck move changes none of these and no card ids.

AnkiConnect can drop a connection mid-sync (`connection reset by peer`); the
sync is idempotent, so re-run it and confirm the remainder reports `unchanged`.

## Rebuilding the CLI

`proxy.golang.org` and `golang.org` are unreachable directly on this machine, so
build through Surge:

```sh
cd ~/Projects/yanki
HTTPS_PROXY=http://127.0.0.1:6152 go build -o yanki ./cmd/yanki
```
