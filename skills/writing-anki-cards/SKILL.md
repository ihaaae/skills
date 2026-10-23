---
name: writing-anki-cards
description: How to write a good spaced-repetition card (an "atom") from a lesson the learner has already understood. The method is Piotr Wozniak's "Twenty rules of formulating knowledge" (SuperMemo); this skill applies those rules to atoms and collects what review sessions teach us. Use when drafting, rewriting or splitting Anki cards or atoms (写卡片、改卡片、拆卡片、cloze), alone or from the spaced-repetition skill.
---

# Writing Anki Cards

A card is worth keeping only if the learner can answer it in a few seconds, the answer is unambiguous, and recalling it strengthens something the lesson already taught. Most bad review sessions come from bad cards, not bad memory.

**The method is Wozniak's twenty rules:** Piotr Wozniak, [*Effective learning: Twenty rules of formulating knowledge*](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge) (SuperMemo, 1999). Read the article when a rule below is unclear; it has worked examples for each. Below, each rule keeps the article's number and name, with one line on how it applies to atoms here. Details the article doesn't cover go in "Learned from review", added as flagged cards teach us something.

Writing a card is a different job from writing a lesson: a lesson builds understanding step by step, a card retrieves one piece of it. Wording rules that apply to anything the learner reads (one word for one thing, no coined words, self-contained code) are in the **writing-for-learners** skill, and the learner's preferences in context (the workspace `AGENTS.md`) override both. Where cards live and how they reach Anki is the **spaced-repetition** skill.

## The atom format

An atom is one card's source text, kept in YAML (with spaced-repetition: `<topic>/srs/<node ID>.yaml`, one file per node).

```yaml
node: C3
atoms:
  - id: index-is-byte          # [a-z0-9-]+, unique in the file, never reused
    section: string 是一串 byte（ASCII）   # optional: the part of the node it comes from
    front: |
      `s := "Go!"`，`fmt.Println(s[0])` 打印什么？
    back: |
      `71`。
  - id: len-counts-bytes
    cloze: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。"
    extra: "按 code point 数用 `utf8.RuneCountInString(s)`。"   # optional, shown with the answer
```

- An atom is either `front` + `back` (basic) or `cloze` (+ optional `extra`). Text is Markdown.
- The card shows a context line "topic · node title · section" above the front, so the front needn't repeat it.
- The id names the fact, not the wording, and is the card's identity: a wording fix keeps it (and the schedule); a card that now asks a different fact, or changes between basic and cloze, gets a new id.

## The twenty rules

1. **Do not learn if you do not understand.** Atoms come only from a node that was taught and passed. A card never introduces a fact; it keeps one.
2. **Learn before you memorize.** The lesson gives the big picture; atoms are the pieces of it worth keeping exact.
3. **Build upon the basics.** Simple facts (what `len(s)` counts) before derived ones (why reversing `[]byte` breaks é). An atom may rely on earlier mastered nodes, never on later ones.
4. **Stick to the minimum information principle.** One fact per card. If the back has "and", or two sentences that could be asked separately, split it.
5. **Cloze deletion is easy and effective.** Turn a claim from the node into a sentence with the key term hidden. Hide the part that carries the knowledge, not filler words.
6. **Use imagery.** A card may describe a table from the lesson in a line ("a/é/语/😀 各占几个 byte？"), but must not depend on a figure that isn't on the card.
7. **Use mnemonic techniques.** Only for the few facts that keep failing; never invent a mnemonic name the lesson didn't use.
8. **Graphic deletion is as good as cloze deletion.** Not used yet: atoms are text only.
9. **Avoid sets.** Ask about one member at a time, or a question whose answer is one item ("哪种 conversion 不复制数据？").
10. **Avoid enumerations.** If order matters, ask "what comes after X?" as separate cards, or use overlapping clozes.
11. **Combat interference.** Confusable facts (`[]byte(s)` vs `[]rune(s)`) get cards that force the distinction, worded clearly differently.
12. **Optimize wording.** The front makes the question obvious in one read, and has one correct answer the learner can check against the back without help. If the honest answer is "it depends", the front is missing a condition.
13. **Refer to other memories.** Link to what the learner already knows: "和 C 的 `char*` 一样，`s[i]` 是什么？"
14. **Personalize and provide examples.** Prefer a small "what does this print?" snippet from the learner's own lesson, including the mistakes they made.
15. **Rely on emotional states.** A surprising result ("`string(65)` 得到什么？") is memorable; use it lightly.
16. **Context cues simplify wording.** The card already shows "topic · node title · section" above the front; don't repeat it in the question.
17. **Redundancy does not contradict minimum information principle.** "What does `len` count?" and "how do you count characters?" are two cards, not duplicates.
18. **Provide sources.** In the topic's files, not on the card: the context line points to the node, the node to the book.
19. **Provide date stamping.** If a fact depends on a version ("since Go 1.22, …"), say so on the card.
20. **Prioritize.** Prefer facts the learner will apply, facts they got wrong, and facts later nodes build on. Skip trivia, history and motivation unless the learner asks.

## Learned from review

Add a line here when fixing a flagged card shows a pattern the twenty rules don't already name (what went wrong, and the rule that prevents it).

- An atom names another node by its title, never its ID: the learner doesn't remember what IDs stand for.
- One card must not test both a concept and its application; write them as two atoms. A code-output card whose back also explains the rule mixes the two, and the learner can't tell which part they recalled. The **concept atom** asks the rule directly; the **application atom** asks what a snippet does, and its back gives the answer only, without restating the rule.

  ```yaml
  # Before: one card, the back explains the rule
  - id: raw-string-output
    front: |
      `` fmt.Println(`a\nb`) `` 打印什么？
    back: |
      `a\nb`（一行）。backquote 表示的 raw string 不解释 escape。

  # After: two atoms
  - id: raw-string-no-escape
    front: |
      backquote 表示的 raw string 会解释 escape 吗？
    back: |
      不会。
  - id: raw-string-output
    front: |
      `` fmt.Println(`a\nb`) `` 打印什么？
    back: |
      `a\nb`（一行）。
  ```
- A definition card gives the term and asks for its meaning, not the other way round. "反复抽 ε、算出 f(ε)，这些 x 的 distribution 叫 {{c1::…}}" only tests the name; "generated distribution q 是哪些样本的 distribution？" tests the idea, which is what later lessons build on.
- If the back contrasts the answer with something else ("X, not Y"), the contrast is a clue and belongs on the front. "判断 q ≈ p 时，比较的是什么？" admits many answers the learner can't check; "比较的不是单个样本像不像真的，而是 {{c1::各类样本的比例}}" admits one. In general, when a front could be answered correctly in several ways ("A 和 B 是什么关系？"), add the condition that pins down the one on the back.

## Checks before showing drafts to the learner

```
- [ ] each atom asks one thing; the back is one fact (plus at most one line of why, except on an application atom)
- [ ] no card tests both a concept and its application
- [ ] the answer can be checked against the back without help
- [ ] every fact used was taught in this node or an earlier mastered one
- [ ] the writing-for-learners checklist passes, and the learner's preferences in context are followed
- [ ] every line in "Learned from review" is followed (`srs.py check` warns about node IDs)
- [ ] confusable pairs have cards that force the distinction
- [ ] front ≲ 200 characters, back ≲ 300 (srs.py check warns past that)
```

## Example: atoms from a string/rune/byte/UTF-8 lesson

```yaml
node: C3
atoms:
  - id: index-is-byte
    section: string 是一串 byte（ASCII）
    front: |
      `s := "Go!"`，`fmt.Println(s[0])` 打印什么？
    back: |
      `71`。
  - id: len-counts-bytes
    section: string 是一串 byte（ASCII）
    cloze: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。"
  - id: string-immutable
    section: string 是一串 byte（ASCII）
    front: |
      `s := "go"; s[0] = 'G'` 能编译吗？
    back: |
      不能（`cannot assign to s[0]`）：string 是 immutable。`s = "Go"` 重新赋值变量是合法的。
  - id: utf8-byte-widths
    section: UTF-8 与 rune
    front: |
      UTF-8 里 `a`、`é`、`语`、`😀` 各占几个 byte？
    back: |
      1、2、3、4。ASCII 1 个 byte，其他 2–4 个。
  - id: rune-is-type
    section: UTF-8 与 rune
    cloze: "rune 是表示一个 {{c1::code point}} 的 type，是 {{c2::int32}} 的 alias。"
  - id: string-from-int
    section: conversion
    front: |
      `fmt.Println(string(65))` 打印什么？
    back: |
      `A`，不是 `65`：int 转 string 得到这个 code point 的字符。`go vet` 会报。数字转 string 用 strconv。
  - id: reverse-via-runes
    section: 按字符处理
    front: |
      反转 `"hé"` 时，为什么交换 `[]byte` 的元素会出错？
    back: |
      é 占 2 个 byte，交换会打乱它内部的 byte 顺序，得到非法 UTF-8。先转成 `[]rune` 再反转。
```

`rune-is-type` has two clozes, so it makes two cards; that's fine because "code point" and "int32" are recalled independently.
