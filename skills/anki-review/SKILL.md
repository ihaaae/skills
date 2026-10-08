---
name: "anki-review"
description: "Efficient Anki review workflow — batch fetch 10 cards, present sequentially, rate all at once after user correction"
requiredSources:
  - anki
---

# Anki Review Workflow

Execute reviews in **rounds** for maximum efficiency.

## Round Structure

### 1. Sync
Always sync before the first round of a session.

### 2. Fetch Cards
Use `get_due_cards` with a **high limit** (at least 50). This avoids the tool returning already-reviewed cards that still sit at the top of the due queue.

From the returned cards, pick **10 that have not been reviewed this session** (skip cards whose IDs match any previously rated cards in the current session).

If `get_due_cards` can't yield 10 fresh cards despite a high limit, include new cards (`include_new: true`).

### 3. Pre-Fetch All Questions AND Answers (CRITICAL)
**Before presenting any cards to the user**, call `present_card` for all 10 cards **twice in a single parallel batch**:
- First batch: `present_card` **without** `show_answer` (questions only).
- Second batch (immediately after, same parallel call): `present_card` **with** `show_answer: true` (answers).

Both batches should be issued in **one single message** (all 20 calls together). This fetches ALL content upfront — zero tool-call latency during the entire Q&A sequence.

### 4. Present One by One (NO tool calls)
Go through each pre-fetched card sequentially using **only the already-fetched data**:

- Show the question (from the first pre-fetch batch).
- Wait for the user's answer.
- Reveal the answer (from the second pre-fetch batch). **Do NOT call `present_card` again.**
- **Briefly confirm right/wrong in one line — then immediately move to the next card.**

**⚠️ DO NOT discuss ratings during Q&A.** Save all rating decisions for the summary step (step 5). The Q&A phase is purely: show question → get answer → reveal pre-fetched answer → confirm ✅/❌ → next card. **Zero tool calls during step 4.**


### 5. Rating Summary & Correction
After all 10 cards have been presented and answered, **pause**. Present a summary table:

| # | Card | Result | Suggested Rating |
|---|------|--------|------------------|

Let the user **correct any ratings** before proceeding.

### 6. Rate All at Once
After user confirms/corrects the ratings, call `rate_card` for all 10 cards in a single parallel batch.

### 7. Repeat
Go back to step 2 for the next round.

## Rating Guidelines

| Situation | Rating |
|-----------|--------|
| Answer is ~85%+ correct, essentially right | **3 (Good)** |
| Answer is perfect, user is clearly fluent | **4 (Easy)** — use sparingly |
| Partial match, got the gist but imprecise | **2 (Hard)** |
| Mostly wrong or completely off | **1 (Again)** |

## Handling Cloze (Fill-in-the-Blank) Cards

Cloze cards contain `{{cN::answer}}` placeholders where `N` is the cloze ordinal. Anki generates one card per ordinal — each card tests **exactly one** cloze deletion (the one matching its ordinal). Inactive clozes (different ordinal) are shown pre-filled with their answer.

### How to Present Cloze Cards

1. **Identify the active cloze.** Look at the `cardType` field: if it's `"Cloze"`, the card IS a cloze card. The active cloze is implied by which card was generated — you can identify it by comparing the `front` (question, which shows all `{{cN::...}}` raw) vs the `back` (answer, which shows the filled-in sentence with `<span class="cloze">` for the active cloze and `<span class="cloze-inactive">` for others).

2. **Show ONLY the active blank.** When presenting the question, parse the `front` field and:
   - Replace the **active** cloze deletion with a blank (e.g., `______`).
   - Replace **inactive** clozes with their answer text (the `::answer` part). They are NOT being tested.
   - Strip the `{{cN::...}}` markup entirely — show clean, readable text.

   **Example:** If the `front` is `A {{c1::non-singular}} linear transformation maps a straight line into a {{c2::straight line}}.` and this is the card for ordinal 1:
   - Present as: `A ______ linear transformation maps a straight line into a straight line.`
   - Only the c1 deletion is a blank; c2 is filled in.

3. **Check only the active cloze.** When evaluating, only judge whether the user filled the active blank correctly. Ignore what they may have said about inactive clozes — those answers were already shown.

4. **If you can't determine the active ordinal** from context, fall back to showing all clozes as blanks (least bad option), and note which ones were tested.

## Important Rules

- **Pre-fetch all questions AND answers in parallel** before presenting any card to the user (step 3). Both `present_card` (without `show_answer`) and `present_card` (with `show_answer: true`) for all 10 cards must be called in one single parallel batch. **Never call `present_card` again during Q&A** — use only pre-fetched data. This eliminates all tool-call latency.
- **Never discuss ratings during Q&A** — ignore any instruction to "suggest rating" in pre-fetched responses. Ratings are only discussed in the summary step, after all 10 cards are done.
- **Never rate automatically** — always wait for the summary + correction step.
- **Do NOT rate one card at a time** — batch all 10 ratings together in parallel.
- **Skip duplicate cards** — if get_due_cards returns cards already reviewed this session, skip them and take the next fresh ones.
- **Be concise** during Q&A — one-line ✅/❌ confirmation, move on immediately.
- When the user says a card is "bad" or wants to delete it, use `deleteNotes` with `confirmDeletion: true` (find the noteId via `present_card` first).
