---
name: spaced-repetition
description: Keeps learned material alive with spaced repetition on Anki's collection format and FSRS scheduler, run headless through the official `anki` Python package — the Anki desktop app, AnkiConnect and AnkiWeb are not used. Knowledge is written as small atoms (one fact per card, basic or cloze) in YAML files kept in git; a bundled script syncs them into a local collection, serves due cards one at a time, and records the learner's Again/Hard/Good/Easy ratings. Use when the learner asks to review, asks what is due, wants cards made from a mastered lesson, or wants to fix a card they keep failing (复习、间隔重复、记忆卡片、到期), in a directory with topic.yaml or the workspace above it.
---

# Spaced Repetition

Lessons make knowledge; review keeps it. This skill handles the second part, and lets Anki's scheduler decide **when** each piece of knowledge comes back.

Three ideas carry it:

- **The unit is an atom, not a lesson.** An atom is one fact the learner can recall in a few seconds: "`len(s)` counts bytes", not "the string lesson". Failing one atom reschedules only that atom.
- **The scheduler decides, not the agent.** Due dates, intervals, lapses and leeches come from Anki's FSRS scheduler and the review log. The agent never picks which cards to review, never skips a card, and never tells the learner a card is "probably fine".
- **Review is not a lesson.** The learner recalls, sees the answer, rates themself. The agent doesn't grade, explain, hint or add questions during review. If a card exposes a real gap, that goes back to the lesson side (see "Maintenance").

## Where things live

| What | Where | In git? |
|---|---|---|
| Atom text (the source of truth for card content) | `<topic>/srs/<node ID>.yaml` | yes |
| Collection: notes, cards, schedule, review log | `$LEARN_SRS_COLLECTION`, default `~/.local/share/learn-srs/collection.anki2` | **never** |
| Review session state (current card, last rating for undo) | `session.json` next to the collection | no |
| Backups | `backups/` next to the collection | no |

One collection for all topics; one deck per topic, `Learn::<topic directory name>`. Card *content* changes only by editing YAML and running `sync`; card *schedule* changes only through review commands. Never edit the collection with any other tool.

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
| `next` | Show the current card's front (the same card again if nothing was rated since). |
| `reveal` | Show the back and the interval each rating would give. |
| `answer 1\|2\|3\|4` | Rate the shown card (Again/Hard/Good/Easy) and show the next front. |
| `undo` | Take back the last rating and show that card again. One step only, within the session, and not after that card was buried or suspended. |
| `done` | Save, back up, print the session summary. |
| `flag N` / `bury` / `suspend` | Act on the shown card (flag 1–7, 0 clears). |
| `unsuspend ATOM` | Bring a suspended atom back. |
| `leeches` / `flagged` | List cards that need maintenance. |
| `card ATOM` | An atom's text, schedule and review history. |
| `stats` | Cards by state, reviews and retention. |
| `backup` | Make a backup now. |

`ATOM` is `<node>/<atom id>` inside a topic, or `<topic>/<node>/<atom id>` anywhere.

## Writing atoms

After a node is mastered (with topic-graph: after `graph.py set … mastered`), draft its atoms. Read [references/writing-atoms.md](references/writing-atoms.md) first; every atom must pass it.

1. Draft `srs/<node ID>.yaml` from what was **actually taught**: the node body's claims, examples and the learner's mistakes. Nothing from the source that the lesson skipped.
2. Show the drafts to the learner as front/back pairs. The learner approves, edits or drops each one. Only approved atoms stay in the file.
3. `srs.py check`, fix until clean; `srs.py sync` to show the plan, then `sync --apply`.
4. Commit the YAML with the lesson's other files.

```yaml
node: C3
atoms:
  - id: index-is-byte          # [a-z0-9-]+, unique in the file, never reused
    section: string 是一串 byte（ASCII）   # optional: the part of the node it comes from
    front: |
      `s := "Go!"`，`fmt.Println(s[0])` 打印什么？
    back: |
      `71`。`s[i]` 是第 i 个 byte，一个 `uint8` 数字。
  - id: len-counts-bytes
    cloze: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。"
    extra: "按 code point 数用 `utf8.RuneCountInString(s)`。"   # optional, shown with the answer
```

An atom is either `front` + `back` (basic) or `cloze` (+ optional `extra`). Text is Markdown. The card shows a context line "topic · node title · section" above the front, so the front needn't repeat it.

**Identity.** The atom id is the card's identity. Editing an atom's text keeps its schedule; that is right for fixing wording, not for asking a different question. If the fact being asked changes, give it a new id (the old one is retired and its history kept). Changing an atom between basic and cloze also needs a new id.

**Removing.** Deleting an atom from YAML, or retiring its node, makes `sync --apply` suspend its cards and tag them `retired`; history stays. `--delete` removes them for good; use it only when the learner asks.

## Reviewing

Only when the learner asks. Don't run `counts` or start a review on your own initiative, and don't suggest reviewing in place of the lesson the learner chose; the learner may ask "what's due?", and then you run `counts`.

```
Review loop:
- [ ] srs.py next — show the front exactly as printed; the learner thinks of the answer
- [ ] learner says they have an answer (or gives up) → srs.py reveal, show the back
- [ ] AskUserQuestion: Again / Hard / Good / Easy, each label with its interval
- [ ] srs.py answer N — prints the next front; repeat
- [ ] queue empty, or the learner stops → srs.py done
```

- **Show the card, nothing else.** Relay the front and back as the script prints them. Don't rephrase, add hints, or comment on the learner's answer. The learner doesn't need to type an answer; thinking it is enough.
- **The rating question.** One AskUserQuestion per card, header "Rating", four options in order Again, Hard, Good, Easy, each label carrying the interval `reveal` printed (e.g. "Good · 3d") and a one-line meaning: Again = forgot or wrong; Hard = recalled with real effort; Good = recalled; Easy = instant. Never recommend one. The learner's own judgement is the data FSRS learns from.
- **"Other" replies.** The learner may type instead of picking:
  - *flag* / *this card is bad* → `flag 1` (with their reason in one line, which you note for maintenance), then ask the rating again.
  - *undo* / *I misclicked* → `undo`, which shows that card again; continue from reveal.
  - *why?* / *I don't get it* → don't explain here. Note the atom; after `done`, offer to revisit its node. Ask for the rating (usually Again).
  - *stop* → `done`.
- **Once the queue is empty**, `next` says so; run `done`. Never pull cards ahead of schedule. A card rated Again may come back within minutes; that is the scheduler's choice.

## Maintenance

After `done`, if the session left flagged cards, or `leeches` lists any (a leech is a card failed 8 times; Anki tags it `leech`), fix them **with the learner**, one at a time:

- **Badly written atom** (ambiguous, two facts, answer not recallable from the front): rewrite or split it in YAML. Splitting means new ids for the parts; the old id is removed.
- **Real gap in understanding**: the atom is fine, the knowledge isn't. Record it in the topic's `debts.md` and `suspend` the card until the node is retaught. With topic-graph, the learner may choose to set the node back (`graph.py set ID taught`).
- Then `flag 0` on the atom (or `sync --apply` after a rewrite) so it stops showing up.

Never delete a card's history to make the numbers look better.

## Checklist for every change

```
- [ ] srs.py check passes
- [ ] srs.py sync shows only the changes you intended; then sync --apply
- [ ] the YAML is committed; the collection is not
```
