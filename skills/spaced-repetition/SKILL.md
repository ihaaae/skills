---
name: spaced-repetition
description: Keeps learned material alive with spaced repetition on Anki's collection format and FSRS scheduler. Knowledge is written as small atoms (one fact per card, basic or cloze) in YAML files kept in git; a bundled script (official `anki` Python package, no AnkiConnect or AnkiWeb) syncs them into a local collection that the learner reviews in the Anki desktop app. Use when the learner wants cards made from a mastered lesson, asks what is due, or wants to fix cards they flagged in Anki or keep failing (复习、间隔重复、记忆卡片、到期、flag、leech), in a directory with topic.yaml or the workspace above it.
---

# Spaced Repetition

Lessons make knowledge; review keeps it. This skill handles the second part, and lets Anki's scheduler decide **when** each piece of knowledge comes back. The learner reviews in the Anki desktop app; the agent writes the atoms, syncs them into the collection, and fixes the cards the learner flags.

Three ideas carry it:

- **The unit is an atom, not a lesson.** An atom is one fact the learner can recall in a few seconds: "`len(s)` counts bytes", not "the string lesson". Failing one atom reschedules only that atom.
- **The scheduler decides, not the agent.** Due dates, intervals, lapses and leeches come from Anki's FSRS scheduler and the review log. The agent never changes a card's schedule, never tells the learner a card is "probably fine", and doesn't suggest reviewing in place of the lesson the learner chose.
- **The YAML is the source, Anki is the player.** Card content lives in the topic's YAML; the collection is generated from it. Edits made to a card inside Anki are overwritten by the next `sync`, so every content fix goes into the YAML.

## Where things live

| What | Where | In git? |
|---|---|---|
| Atom text (the source of truth for card content) | `<topic>/srs/<node ID>.yaml` | yes |
| Collection: notes, cards, schedule, review log | `$LEARN_SRS_COLLECTION` (the workspace's mise env sets it; required, no default). Query the collection only through this path | **never** |
| Backups | `backups/` next to the collection | no |

One collection for all topics; one deck per topic, `Learn::<topic directory name>`. Card *content* changes only by editing YAML and running `sync`; card *schedule* changes only by reviewing in Anki (plus `flag` / `suspend`). Never edit the collection with any other tool.

**Close Anki first.** The Anki desktop app must not have the collection open while `srs.py` writes to it (`sync --apply`, `flag`, `suspend`, `unsuspend`). Ask the learner to quit Anki before these, and to reopen it afterwards.

## The script

Run from inside a topic directory (or pass `--root`). Run from the workspace root above several topics, it covers all of them (deck `Learn`).

```
uv run <skill-dir>/scripts/srs.py <command>
```

| Command | Use |
|---|---|
| `check` | Lint the atom files. Exit 1 on errors. |
| `sync [--apply] [--delete]` | Show what would change in the collection; `--apply` writes it (backup first). |
| `counts` | New / learning / review cards due now, per deck. |
| `flagged` / `leeches` | List cards that need maintenance. |
| `card ATOM` | An atom's text, schedule and review history. |
| `flag N ATOM` | Set flag 1–7 on the atom's cards; 0 clears. |
| `suspend ATOM` / `unsuspend ATOM` | Keep an atom out of review / bring it back. |
| `stats` | Cards by state, reviews and retention. |
| `backup` | Make a backup now. |

`ATOM` is `<node>/<atom id>` inside a topic, or `<topic>/<node>/<atom id>` anywhere.

## Writing atoms

After a node is mastered (with topic-graph: after `graph.py set … mastered`), draft its atoms. How to write a good atom, and the YAML format, is the **writing-anki-cards** skill; read it (and writing-for-learners, which it points to) first. Every atom must pass its checks.

1. Draft `srs/<node ID>.yaml` from what was **actually taught**: the node body's claims, examples and the learner's mistakes. Nothing from the source that the lesson skipped.
2. Show the drafts to the learner as front/back pairs. The learner approves, edits or drops each one. Only approved atoms stay in the file.
3. `srs.py check`, fix until clean; `srs.py sync` to show the plan, then `sync --apply`.
4. Commit the YAML with the lesson's other files.

**Identity.** The atom id is the card's identity. Editing an atom's text keeps its schedule; that is right for fixing wording, not for asking a different question. If the fact being asked changes, give it a new id (the old one is retired and its history kept). Changing an atom between basic and cloze also needs a new id.

**Removing.** Deleting an atom from YAML, or retiring its node, makes `sync --apply` suspend its cards and tag them `retired`; history stays. `--delete` removes them for good; use it only when the learner asks.

## Fixing flagged cards

While reviewing in Anki, the learner flags cards they think are badly written. When they come back to fix them (or `leeches` lists cards failed 8 times, which Anki tags `leech`), go through them **with the learner**, one at a time:

```
Fix loop:
- [ ] srs.py flagged (and leeches) — list what needs fixing
- [ ] for each card: srs.py card ATOM, and print its full front and back in the reply
- [ ] the learner decides: keep, rewrite, split, delete, or record a gap
- [ ] edit srs/<node>.yaml, never the card in Anki
- [ ] if the fix shows a pattern the twenty rules don't name, add a line to writing-anki-cards' "Learned from review" (a PR to ihaaae/skills)
- [ ] after all cards: quit Anki → check → sync → sync --apply (--delete if anything was deleted) → flag 0 on kept or rewritten atoms
- [ ] commit the YAML
```

- **Show the card itself.** The learner can't see the card from the atom id. Before discussing a card, print its front and back (cloze: the text with its blanks, and `extra`) in the reply, and do the same for the rewritten version before applying it.
- **Badly written atom** (ambiguous, two facts, answer not recallable from the front): rewrite it in YAML, following writing-anki-cards. A wording fix keeps the id and the schedule; if the question now asks a different fact, or the atom changes between basic and cloze, use a new id. Splitting means new ids for the parts; the old id is removed.
- **Delete.** When the learner says to delete a card, they mean the atom: remove it from the YAML and run `sync --apply --delete`. Without `--delete` it would only be retired.
- **Real gap in understanding**: the atom is fine, the knowledge isn't. Record it in the topic's `debts.md` and `suspend ATOM` until the node is retaught. With topic-graph, the learner may choose to set the node back (`graph.py set ID taught`).
- **Clear the flag** with `flag 0 ATOM` on every atom that stays, so it leaves the `flagged` list. Atoms removed from the YAML don't need it.

Never delete a card's history to make the numbers look better.

## Checklist for every change

```
- [ ] Anki desktop is closed while srs.py writes
- [ ] srs.py check passes
- [ ] srs.py sync shows only the changes you intended; then sync --apply
- [ ] the YAML is committed; the collection is not
```
