# Writing atoms

A card is worth keeping only if the learner can answer it in a few seconds, the answer is unambiguous, and recalling it strengthens something the lesson actually taught. Most bad review sessions come from bad cards, not bad memory. These rules are adapted from Piotr Wozniak, *Effective learning: Twenty rules of formulating knowledge* (SuperMemo, 1999), the standard reference for this, plus what this learner needs.

## Before writing: the knowledge must already be understood

1. **Don't learn what you don't understand.** Atoms come only from a node that was taught and passed. A card never introduces a fact; it keeps one.
2. **Learn before you memorize.** The lesson gives the big picture, motivation and examples. Atoms are the residue: the pieces of that picture worth keeping exact.
3. **Build on basics.** Cover the simple facts first (what `len(s)` counts) before the derived ones (why reversing `[]byte` breaks é). An atom may rely on facts from earlier nodes the learner has mastered, never on later ones.

## Shape of a card

4. **Minimum information principle.** One fact per card. If the back has "and", or two sentences that could be asked separately, split it. A small card is answered fast, failed precisely, and rescheduled alone.
5. **Cloze deletion is easy and effective.** Turn a claim from the node into a sentence with the key term removed: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。" Hide the part that carries the knowledge, not filler words. One cloze per atom unless the deletions are truly independent.
6. **Use concrete examples.** A small code snippet with "what does this print?" beats an abstract rule. Every snippet is self-contained: declare every variable, type and method it uses.
7. **Use imagery where it helps.** A card may describe a table or a diagram from the lesson in a line or two ("a/é/语/😀 各占几个 byte？"), but must not depend on seeing a figure that isn't on the card.
8. **Avoid sets.** "List all five X" is nearly impossible to recall reliably. Ask about one member at a time, or ask a question whose answer is one item ("哪种 conversion 不复制数据？").
9. **Avoid enumerations.** Ordered lists are sets made worse. If order matters, ask "what comes after X?" as separate cards, or use overlapping clozes.
10. **Combat interference.** When two facts are easy to confuse (`[]byte(s)` vs `[]rune(s)`), write cards that force the distinction ("`len([]rune(\"hé\"))` 是多少？" next to "`len(\"hé\")` 是多少？"), and make each card's wording clearly different.
11. **Optimize wording.** Cut every word that doesn't help recall. The front should make the question obvious in one read.
12. **Refer to other memories.** Link to what the learner already knows: "和 C 的 `char*` 一样，`s[i]` 是什么？" Context makes the fact stick and narrows the answer.
13. **Personalize.** Use the examples from the learner's own lesson, including the mistakes they made. A card built on the exact confusion they had is the one that pays off.
14. **Rely on emotional states** only lightly: a surprising result ("`string(65)` 得到什么？") is memorable; use it.
15. **Context cues simplify wording.** The card already shows "topic · node title · section" above the front. Don't repeat that context in the question.
16. **Redundancy is fine** when it comes from different directions: "what does `len` count?" and "how do you count characters?" are two cards about related facts, not duplicates.
17. **Provide sources** in the topic's files, not on the card: the card's context line points to the node; the node points to the book.
18. **Date-stamp facts that change.** If a fact depends on a version ("since Go 1.22, …"), say so on the card.
19. **Prioritize.** Not every claim in a node deserves a card. Prefer facts the learner will need to apply, facts they got wrong, and facts that later nodes build on. Skip trivia, history and motivation paragraphs unless the learner asks.
20. **Every card must have one correct answer** the learner can check themself against the back without the agent's help. If the honest answer is "it depends", the front is missing a condition.

## This learner's rules

These come from the workspace's `AGENTS.md` (learner preferences) and apply to every card in every topic. Check them on every draft.

- **Language.** Card text is Chinese, but concepts and operations are English words: byte, rune, encoding, conversion, slice, tick, watchdog. Never 编码/组包/喂狗-style translations. If unsure whether a word is a term, use English.
- **No coined words.** No invented names for categories or steps; use the field's standard term or describe it plainly.
- **Node names, not IDs.** A card that refers to another lesson says "slicing slices 与 shared backing array 那一课", never "C2". `srs.py check` warns about node IDs in card text.
- **Precise wording.** One word for one thing throughout (not 字符 and 文字 for the same thing). No ambiguous words like 结果/变长/画成/在哪一层; name the operation. Don't equate concepts at different levels with 也就是 (rune is a type, UTF-32 is an encoding). Describe code with the language's own operation names (赋值给 interface 变量, 传参数), not spatial metaphors (放进).
- **Self-contained code.** Every snippet shows the full declarations it needs.
- **Only what was taught.** Every fact a card needs must be in the lesson or on the card itself. The learner doesn't read the source material.

## Checks before showing drafts to the learner

```
- [ ] each atom asks one thing; the back is one fact (plus at most one line of why)
- [ ] the answer can be checked against the back without help
- [ ] every fact used was taught in this node or an earlier mastered one
- [ ] code is self-contained; terms are English; no coined words; no node IDs
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
      `71`。`s[i]` 是第 i 个 byte，一个 `uint8` 数字。
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
