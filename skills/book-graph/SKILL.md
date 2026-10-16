---
name: book-graph
description: "Build a topic-graph learning topic from one reference book: convert it to Markdown, map every section of the book to a node or an explicit non-goal (coverage), give each node a depth (write / read / aware) with stated evidence, cut sections into teachable nodes by explicit split/merge rules, derive prerequisites from the book's own cross-references, and calibrate the cut by sampling with the learner. A bundled script checks coverage and reports section sizes and cross-references. Extends topic-graph (which still owns node files, status and the session loop) and pairs with progressive-learning and epub-to-markdown. Use this when a learning topic is to be built around a book (\"learn X from this book\"), or when an existing book-based topic is restructured: re-mapping sections, splitting or merging nodes, changing depths, re-checking coverage (按一本书建知识图谱、书的章节映射、覆盖检查). Not needed for an ordinary lesson in a book-based topic: topic-graph covers the node fields `source` and `depth` that lessons use."
---

# Book Graph

topic-graph builds a graph by chaining backward from a goal. That works when nobody has organized the subject yet, but its quality depends on what the agent happens to think of: a missing concept stays missing until the learner trips over it. A good book has already done the organizing. An expert chose what matters, in what order, with motivation, history, examples, pitfalls and exercises. Building on it raises two floors at once:

- **The graph's floor.** Coverage becomes checkable: every section of the book is either in the graph or out of it for a stated reason, so nothing is dropped by accident.
- **Each lesson's floor.** Every node points at the pages that explain it, so preflight starts from the author's framing instead of a blank page.

The book is a scaffold, not the authority on order or depth. The learner's goal decides how deep each part goes, and the dependency structure (not the chapter order) decides the sequence.

## How this fits with the other skills

| Skill | Owns |
|---|---|
| **book-graph** (this) | Turning a book into the plan: the section → node map, coverage, depth, cut rules, prerequisites from the text, calibration with the learner |
| **topic-graph** | Node files, statuses, `graph.py`, the session loop, review, retro — unchanged. Everything there applies unless this skill says otherwise below |
| **progressive-learning** | Teaching one node |
| **epub-to-markdown** | Converting the `.epub` into one line-numbered Markdown file |

Where this skill overrides topic-graph:

- **topic-graph A.4 ("don't build the whole domain").** With a book the whole map is cheap and checkable, so map the entire book up front. Node *bodies* still get filled lazily, at preflight.
- **topic-graph A.2 ("chain backward").** Prerequisites come from the text first (see Prerequisites) and from backward chaining only for gaps the book leaves.

## Layout

On top of the topic-graph layout:

```
references/<book>/<book>.md        the converted book; line numbers below refer to it
references/<book>/<book>-media/    its images
book-map.md                        the section → node map: the plan and the coverage ledger
```

- The `.epub` stays out of version control (gitignore `*.epub`); the Markdown is the working copy. Register the book in `sources.md`.
- The book is a **reference**, not the study object: it goes in `references/`, not `material/`. The object of study is the subject the book teaches.
- Each node's front matter gets two extra fields, which `graph.py` ignores:

  ```yaml
  source: "learning-go.md:1846-2184, 2516-2655"   # the line ranges the node is built from
  depth: "write"                                  # write | read | aware, see below
  ```

## Two separate questions: coverage and cut

"How fine-grained should the graph be?" mixes two questions, which have different answers and different deciders. Keep them apart.

| Question | Asks | Decided by |
|---|---|---|
| **Coverage** | Which parts of the book are learned, and how deeply? | The agent proposes from evidence. The learner confirms the *goal*, not the individual parts |
| **Cut** | How is the covered material divided into nodes? | Rules (below), calibrated once by sampling with the learner |

Making a node "coarser" doesn't drop material, it only puts more into one node. Dropping material is a coverage decision and must be written down as one.

### Coverage: depth instead of in/out

A learner who hasn't studied the subject can't judge whether a section matters. Asking them is asking the wrong person. So coverage is not a yes/no per section but a **depth**, proposed by the agent with its evidence written next to it:

| Depth | Learner can… | Tested by |
|---|---|---|
| **write** | produce it correctly | writing code / a solution, finding the bug |
| **read** | recognize it in someone else's work, say what it does and where it bites | reading a snippet and predicting behavior |
| **aware** | know it exists and when to look it up | one "you meet situation X — what do you reach for?" question |

Evidence for the depth, strongest first:

1. **The author's own verdict.** Books say so outright: "you probably don't need these", "use sparingly", "never use these", "a last resort". That is an expert's priority, more reliable than the agent's guess. Quote it in the evidence column.
2. **The goal.** A goal that includes *reading* other people's work almost removes "skip": you may never write a feature, but you'll meet it. It lowers depth, not coverage.
3. **Centrality.** A section many later sections build on can't be shallow.

Only material unrelated to the subject (tool and editor choices, publisher pages, acknowledgements) becomes a **non-goal**, with a reason. Depth is provisional. After the learner has learned a part, they can judge it, so depth may be raised or lowered then (record it in `goals.md`). A node can hold a lower-depth sub-item ("write; goto=aware").

### Cut rules

A row in `book-map.md` is a node. Size it by these rules, then by topic-graph's 25-minute tests at preflight.

1. **A node is a set of claims that can be tested on their own and taught in one sitting.** Line counts are only a signal: about 170+ lines of prose (code excluded) → check whether to split; about 60 or fewer → check whether to merge. `bookmap.py stats` reports both.
2. **Split** when a range holds several groups of claims that don't depend on each other and each could be tested alone. (Learning Go's "predeclared types" section held literals, integers, floats, complex numbers and strings — a dozen claims — and became two nodes.)
3. **Merge** when a section can't fill a lesson and its main point is another node's motivation or explanation. (Arrays: their key fact, "the size is part of the type", is *why* slices exist. They became the opening of the slice node.)
4. **Merge** sections that are different faces of one mechanism. (Interfaces and nil, interface comparison and type assertions all follow from "an interface value is a (type, value) pair" and became one node.)
5. **Depth sets capacity.** A read or aware node can hold more, because nothing in it is tested by writing.
6. **Leaving the book's order is allowed when stated.** Put a phenomenon and its explanation together when the book separates them by chapters ("Go is call by value" in Ch5 and "why maps and slices behave differently" in Ch6 became one node after pointers). Write the reason in the evidence column.
7. **At preflight, topic-graph's 25-minute tests have the last word.** If a row fails them, it becomes several nodes: the original ID keeps the first part, `graph.py add` creates the others, and the `book-map.md` row lists all of them with their sub-ranges.
8. **A node's scope is its topic, not every paragraph in its range.** A sidebar on another topic belongs to the node that owns that topic: note the move in both nodes' evidence columns, and if the owning node comes later, record it in `debts.md` as a forward reference. (Learning Go's `go fmt` section holds a "Semicolon Insertion Rule" sidebar. A toolchain lesson built an example on it; the learner pointed out it is syntax, not toolchain, and it moved to the syntax node.)

### Prerequisites

1. **Back-references in the text** ("As I discussed in…", internal links `](#…)`) are prerequisite candidates. `bookmap.py refs` lists them per node.
2. **Implicit dependencies** show up only when reading the section: a pitfall that can only be explained with an idea from elsewhere. (A custom error type returning a typed nil is only explainable once "an interface value is a (type, value) pair" is known.) Read before you commit an edge.
3. **Forward references** ("covered in Chapter 14") are flagged in the evidence column as *used early*. In the lesson, teach only what the example needs ("`ctx.Done()` is a channel that gets closed") and record it in `debts.md` as a forward reference.

## Workflow

### 1. Convert and register

Convert with epub-to-markdown (`--media` for the images), place the result under `references/<book>/`, gitignore the `.epub`, add a `sources.md` entry (edition, year, which language/library version it targets).

### 2. Pin the goal

As in topic-graph A.1, plus one question specific to books: **write, read, or both?** It sets the default depth. Altitude and non-goals go in `goals.md` as usual.

### 3. Map the whole book

Read the book's TOC (the front matter `toc`, or all level 2–4 headings), then read each chapter, not just its headings. Headings over-promise and under-promise, and implicit dependencies are only visible in the text. Write `book-map.md`, one table per chapter (= one topic-graph group, one letter):

```markdown
| Node | Sections (lines) | Depth | Prereqs | Evidence |
|---|---|---|---|---|
| C1 array's limits → slice basics: len, append, capacity, make | 1758–2184 | write | B3, B4 | arrays merged as the opening (cut rule 3) |
| — non-goal | Choose Your Tools 771–849 | — | — | editor choice isn't Go knowledge |
```

At the top, record the goal, the depth legend, and the cut rules with the examples from this book. Exercises sections feed the questions of their chapter's write nodes. Summary sections ("Wrapping Up") are not nodes. Both are excluded from the coverage check with `--ignore`.

Then run:

```
python3 <skill-dir>/scripts/bookmap.py check BOOK.md book-map.md --from <first chapter line> --to <last chapter end> --ignore '^(Exercises|Wrapping Up)$'
python3 <skill-dir>/scripts/bookmap.py stats BOOK.md book-map.md
python3 <skill-dir>/scripts/bookmap.py refs  BOOK.md book-map.md
```

`check` must report complete coverage (each heading covered exactly once). Work through every `<<` / `>>` from `stats` against cut rules 1–5, and every back-reference from `refs` against the prerequisites column.

### 4. Calibrate with the learner by sampling

The learner can't review 60 rows and shouldn't have to. Draw a few nodes at random (add one by hand if the draw misses a whole part of the book, and say that you did), read their sections, and for each give: what the section covers, your verdict (too big / too small / right) and the proposed fix.

**Describe them in terms the learner can judge before learning.** Count and plain description work ("a dozen separate facts", "one fact, which is really the reason for the next topic"). Jargon doesn't: a learner told that a node covers "sentinel errors and custom error types" can't tell whether that's too much. Where the learner can't judge yet, say so and fall back on the rules. Re-sample a chapter after the learner has finished it, when they can judge it.

Each verdict the learner confirms becomes a calibration example in `book-map.md`'s rules. Rules that hold across books belong in this skill.

### 5. Create the graph

- One group per chapter. A chapter that is all non-goal gets no group. A chapter merged into another goes into that group.
- `graph.py add` every row, with `--prereq` from the map. Put `source` and `depth` into the front matter. Bodies stay empty until preflight.
- Map and synthesis nodes (topic-graph "Big picture and meaning", in teaching.md): the book usually supplies them. A chapter introduction is a natural map node, and the "Wrapping Up" and design-advice sections ("Accept interfaces, return structs") are natural synthesis material. Add a map node where a chapter lacks an overview.
- Goals and `[track] main` in `topic.yaml` as usual. Then `graph.py sync`.

### 6. Teaching from the book

A lesson in a book-based topic is an ordinary topic-graph lesson: the node's `source` and `depth` fields work as topic-graph "Source and depth" describes, and the learner doesn't read the book unless a reading node assigns sections (topic-graph core rule 10, in teaching.md). This skill comes back into play only when the plan changes:

- When a node is split or its range changes, update its `book-map.md` row in the same edit, then re-run `check`.
- When a lesson finds a sidebar on another topic inside the node's range, move it under cut rule 8 instead of teaching it here.
- When the learner, having learned a part, wants its depth raised or lowered, change the node's `depth`, its `book-map.md` row, and record why in `goals.md`.
