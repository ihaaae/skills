# Retro and keeping ✅

Read section I when `graph.py next` suggests a retro or the learner sounds stuck; read section J when a ✅ node turns out to have faded.

## I. Retrospective: the outer loop

The session loop (diagnose, teach, record) never asks whether the goal, the route or the teaching style still serve the learner. Left alone, that question surfaces only when the learner is already frustrated. A retro asks it on a schedule.

**When.** `next` suggests one when:
- the learner comes back after a long gap;
- many status changes have happened since the last retro;
- several ✅ nodes were demoted (hollow mastery);
- a whole group has just been finished.

Also hold one whenever the learner sounds stuck or unmotivated, whatever the script says.

**How.** Keep it to about five minutes, one or two questions at a time, as a conversation:
1. **Meaning.** Read each goal's `question` aloud. Is it still what the learner cares about? Answer as much of it as the ✅ nodes now allow; this shows progress in the learner's terms.
2. **Method.** What felt off in recent lessons: pace, question difficulty, too much or too little big picture, example quality?
3. **Route.** Given 1 and 2, does the next stretch of the route still make sense? Which group needs its map node next?

**Record.**
- Append a dated `## YYYY-MM-DD` entry to `retro.md`: what was said, and what changed.
- Apply each change at the right layer ("Where things live" in files.md): goal and route → `goals.md` / `topic.yaml`; topic rule → `rules.md`; teaching method → the skills; learner-wide preference → workspace `AGENTS.md`.
- Promote any auto-memories collected since the last retro, and delete them once promoted.

## J. Keeping ✅: spaced repetition, not review lessons

A ✅ records that the learner showed understanding *on that day*; weeks later it may have faded. Keeping it is not this skill's job. With the spaced-repetition skill installed, each ✅ node's key facts become small atoms, and Anki's scheduler decides when each one comes back. This skill doesn't schedule reviews, and lessons don't open with a review question.

Two things stay here:

- **A gap that review exposes.** When a card keeps failing because the understanding is missing (not because the card is badly written), the learner may set the node back: `set ID taught`. The demotion warning lists the ✅ descendants to re-check. Re-teach briefly (usually one example and two questions), then `set ID mastered` again.
- **Misconception retests** (`debts.md`) serve the current goals. When the content in question lies outside them (a deferred phase, a non-goal), wait until that scope returns, even if the node is an ancestor of something on the path; a needed correction can be stated in one line without a question.
