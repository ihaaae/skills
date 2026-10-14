---
name: topic-graph
description: Tracks the learning of a difficult subject as a prerequisite graph of small topic nodes (each under 25 minutes including exercises), stored one file per node in a topic directory with topic.yaml. A bundled script computes the frontier, retests, reviews and the next node to learn, and records mastery. Covers building or re-goaling a graph, diagnosing prior knowledge, choosing the next node, and recording progress. Use when someone wants to learn a complex topic across multiple sessions, works in a directory containing topic.yaml or nodes/, asks what to learn next, wants a roadmap or curriculum with prerequisites, or asks to be taught something too big for one short lesson (知识图谱、学习进度、下一步学什么), even if they never say "graph".
---

# Topic Graph

A topic graph cuts a subject into small nodes, each listing the nodes it depends on, and records which nodes the learner has *demonstrably* mastered. These files are the only memory that survives between sessions, so keep them trustworthy.

**Facts vs. derived state.** Only two things are hand-maintained: each node's prerequisites and each node's mastery status. Everything else — 🔓/🔒, the frontier, retests, what to learn next, `STATE.md` — is computed by `scripts/graph.py`. Never hand-edit derived state, and when your recollection disagrees with the script, the script wins.

## Reference files

Most sessions need only this file. Read a reference in full when its situation comes up:

| File | Read when |
|---|---|
| [teaching.md](teaching.md) | preparing or teaching a node (core rules, preflight, big picture); a question from outside the graph; a later node corrects an earlier one |
| [building.md](building.md) | A. no topic directory yet; H. the learner changes their goal |
| [diagnosis.md](diagnosis.md) | C. testing what the learner already knows |
| [upkeep.md](upkeep.md) | I. `next` suggests a retro or the learner seems stuck; J. `next` names a node due for review |
| [nodes.md](nodes.md) | adding or reshaping nodes; node file format; sizing a node; `source`, `depth`, `mode`, `references/` |
| [files.md](files.md) | the topic directory layout, editing `topic.yaml` by hand, how `next` ranks, where a rule or preference belongs |

## The script

Run from anywhere inside the topic directory (or pass `--root`); `uv` installs its dependency:

```
uv run <skill-dir>/scripts/graph.py <command>
```

| Command | Use |
|---|---|
| `check` | Validate the graph. Exit 1 on errors. |
| `next [-n N] [--json]` | What to learn next, with reasons and the route to the goal; a retro to hold first, if any; the ✅ node most due for review. |
| `preflight ID` | Refuses a locked node; otherwise prints what a lesson on it may use. |
| `show ID` | Node, its status, prereqs, dependents. |
| `set ID mastered\|taught\|new [--caveat "…"]` | Record status. `mastered` stamps `verified` with today's date and refuses if prereqs aren't ✅. |
| `add ID --title T --prereq A,B [--target X] [--group-title G]` | Create a node. |
| `retire ID --into ID2` | Retire a node; the ID is never reused. |
| `sync` | `check`, then regenerate `STATE.md`. |

Whenever `check` or `sync` reports errors: fix the files, re-run, and continue only when it passes.

## Statuses

| Mark | Stored `status` | Meaning | Satisfies prerequisites? |
|---|---|---|---|
| ✅ | `mastered` | Verified by diagnosis or by passing the lesson's retests | Yes |
| ✅ ⚠️ | `mastered` + `caveat` | Holds only within the caveat's scope | Yes, within the caveat |
| 📝 | `taught` | Delivered but not verified | **No** |
| 🔓 / 🔒 | `new` | Every prereq ✅ / some prereq not ✅ | — |

📝 is honest bookkeeping, not a failure, but a 📝 node unlocks nothing until it is retested.

## Session loop

Copy the checklist and track progress:

```
Session progress:
- [ ] Read rules.md and goals.md
- [ ] graph.py check — fix and re-run until clean
- [ ] graph.py next — offer a retro if suggested; recommend; learner picks
- [ ] Teach the node (teaching.md; review question first if next names one — upkeep.md J)
- [ ] Record: node summary, then graph.py set
- [ ] Update debts/open-questions/glossary/sources; graph.py sync until clean
```

### B. Choosing the next node

1. Read `rules.md` (domain rules override the defaults) and `goals.md`. Run `graph.py check`; fix errors before recommending anything.
2. Run `graph.py next`. If it suggests a retro, offer that first (upkeep.md, I); the learner may postpone it.
3. Recommend **only what `next` returns** — a 🔓 node or a 📝 node due for retest, never a node with an unmastered prerequisite. Give the reason and the route to the goal in a line or two; the learner picks. If the learner's real problem points elsewhere, that may override the ranking, but only among nodes the script says are teachable.
4. Skim `debts.md` for items the chosen node is supposed to settle, including misconceptions to retest.

### D.4 Recording a lesson

Write the node's summary into its file first, then `graph.py set`:

- Every layer's two questions correct → `mastered`. A wrong second retest means not mastered, regardless of the first answer.
- Session ended mid-node, or content delivered without retest → `taught`, with a note in the body of where it stopped.
- A concept the lesson needed that has no node yet → `graph.py add` it; an unpaid gap goes to `debts.md`.

### G. Ending a session

Update the files with targeted edits (never regenerate a file from memory — files drift when rewritten):

- node summaries and `graph.py set` for every node touched; new nodes via `add`
- `debts.md` (forward references, misconceptions to retest, skipped retests, flawed exercises), `open-questions.md`, `glossary.md`, `sources.md` as needed
- `graph.py sync` until clean — the next session starts from `STATE.md`

## Writing node summaries

The body of a node is the canonical record of what was taught; the next session teaches consistently with it.

- **Only what was actually taught**, stated as taught: exact terms, attribution boundaries, and known simplifications (⚠️, naming the node that corrects them). It is the learner's model, not an encyclopedia entry; a correct statement the lesson didn't make goes in debts.md, not the body. Add the motivation in a line and the picture or table used, so the next session can reuse it.
- **Current state, not history.** No "session 3: we covered…" logs (`log.jsonl` keeps the machine record). A correction leaves the corrected statement, the scope of the old one, and — if the learner held the old belief — a pitfall line plus a `debts.md` retest item.
- **Learner's language**, with standard terms (usually English for technical fields) alongside.
- **Keep it lean.** Long-settled ✅ summaries compress to a line or two; paid debts are deleted. Group-level material goes in `_group.md`.
