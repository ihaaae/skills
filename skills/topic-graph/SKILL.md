---
name: topic-graph
description: Plans and tracks the learning of a difficult subject as a prerequisite graph of small topic nodes, each teachable in under 25 minutes including exercises, stored one file per node in a topic directory with topic.yaml. A bundled script computes locked/unlockable status, the frontier, the retest queue and the next node to learn. Covers building the graph, diagnosing what the learner already knows, choosing the next node, keeping explanations and exercises from relying on unlearned concepts, and recording progress. Use when someone wants to learn a complex topic across multiple sessions, works in a directory containing topic.yaml or nodes/, asks what to learn next, wants a roadmap or curriculum with prerequisites, or asks to be taught something too big for one short lesson (知识图谱、学习进度、下一步学什么), even if they never say "graph".
---

# Topic Graph

Teaching a hard subject to someone without the background fails in four predictable ways: explanations quietly lean on concepts the learner doesn't have yet; lessons are too large to tell whether they landed; across sessions, nobody remembers what was verified versus merely said; and a long run of small, verified, bottom-up nodes leaves the learner unable to say what any of it is for, so motivation drains away. A topic graph cuts the subject into small nodes, each listing the nodes it depends on, and records which nodes the learner has *demonstrably* mastered. Those files are the only memory that survives between sessions, so most of this skill is about keeping them trustworthy.

**Facts vs. derived state.** Only two things are hand-maintained: each node's prerequisites and each node's mastery status. Everything else — 🔓/🔒, the frontier, which 📝 nodes can be retested, what to learn next, the overview diagram — is computed by `scripts/graph.py`. Never hand-edit derived state, and never trust a recollection over the script.

## Reference files

Read the matching file in full when its situation comes up:

| File | Read when |
|---|---|
| [files.md](files.md) | creating a topic directory, editing `topic.yaml` or other topic files by hand, deciding where a rule or preference belongs |
| [nodes.md](nodes.md) | adding or reshaping nodes; at preflight, sizing a node (25-minute tests) or using its `source`, `depth`, `mode` or `references/` texts |
| [building.md](building.md) | A. building a new graph; H. the learner changes their goal |
| [diagnosis.md](diagnosis.md) | C. diagnosing what the learner already knows |
| [upkeep.md](upkeep.md) | I. `next` suggests a retro or the learner seems stuck; J. `next` names a node due for review |

## The script

Run from anywhere inside the topic directory (or pass `--root`). The script declares its dependency (pyyaml) inline per PEP 723, so `uv` prepares the environment automatically:

```
uv run <skill-dir>/scripts/graph.py <command>
```

In the `Learn/` workspace, `mise run graph <command>` does the same from the current directory. Tests: `mise run test`.

| Command | Use |
|---|---|
| `check` | Validate: unknown/retired prereqs, cycles, duplicate IDs, a ✅ whose prereqs aren't all ✅, ✅/📝 nodes with no summary, unrecorded forward references. Exit 1 on errors. |
| `next [-n N] [--json]` | Compute what to learn next, and for the top pick, the chain of nodes leading from it to each goal it serves. Above it, any reasons to hold a retro first (section I); below it, the ✅ node most due for review (section J). |
| `preflight ID` | Refuses a node whose prereqs aren't all ✅. Otherwise prints the route from this node to each goal it serves (plus the goal's `question`, if set), the permitted concepts, caveated ✅ nodes, direct prereqs' summaries, and the node's existing body. |
| `show ID` | Node, its status, prereqs, dependents. |
| `set ID mastered\|taught\|new [--caveat "…"]` | Record status. `mastered` also stamps `verified` with today's date. Refuses `mastered` if prereqs aren't ✅; warns when demoting a node that ✅ descendants rely on. |
| `add ID --title T --prereq A,B [--target X] [--group-title G]` | Create a node (rolls back if it breaks the graph). |
| `retire ID --into ID2` | Retire a node; the ID is never reused. |
| `sync` | `check`, then regenerate `STATE.md` (overview, progress toward goals, next step, all nodes). |

Whenever `check` or `sync` reports errors: fix the files, re-run, and continue only when it passes.

**How `next` chooses.** The ranking is lexicographic, so it is explainable:

1. **📝 nodes whose prereqs are all ✅** (retest due) come first — retests are cheap while content is fresh and each one unlocks a subtree.
2. **Main-track groups** (`[track] main` in `topic.yaml`) before side groups.
3. **On a goal path** (an ancestor of a `[[goal]]` target, or the target itself) before off-path.
4. **Bottleneck**: more transitive dependents first.
5. Track order, then ID.

It also names one side-group node as a "change of pace". The output is a recommendation with reasons; the learner picks. If the learner's real problem points elsewhere (section E), that overrides the ranking — but only among nodes the script says are teachable.

## Statuses

Stored (`status`): `new`, `taught`, `mastered`, `retired`. Derived: 🔓 = `new` with every prereq mastered; 🔒 = `new` with some prereq not mastered.

| Mark | Meaning | Satisfies prerequisites? |
|---|---|---|
| ✅ `mastered` | Verified by diagnosis or by passing the lesson's retests | Yes |
| ✅ ⚠️ | `mastered` with a `caveat` (scope limit) | Yes, within the caveat |
| 📝 `taught` | Delivered but not verified (discussed, or the session ended before retest) | **No** |
| 🔓 | Unlockable | — |
| 🔒 | Locked | — |

📝 is honest bookkeeping for content delivered faster than it was verified, not a failure, but a 📝 node unlocks nothing until it is retested.

## Core rules

These apply to every topic. A topic's `rules.md` adds domain rules; those take precedence.

1. **Recommend only from the frontier.** "What next" means a 🔓 node or a 📝 node due for retest — i.e. what `next` returns — never a node with an unmastered prerequisite.
2. **Explain only with ✅ concepts.** If an explanation genuinely needs a concept from a node that isn't ✅, stop and say "this needs X first" rather than slipping it in. Slipped-in concepts are how the graph silently rots: the learner appears to follow, nobody tested the dependency, and later lessons build on it.
3. **Exercises and examples obey rule 2 too.** Before posing a diagnostic, practice or retest question, trace its correct answer and check every concept on that path. Examples are held to the same rule: a device type or domain term an example leans on is either tied to a ✅ concept or defined in one plain sentence on first use. A lookup fact the question needs but doesn't test (a standard number, a code value, a vendor's meaning for a field) goes into the stem, so the question tests the reasoning step only.
4. **Use the field's established terms; don't coin names.** If no standard term seems to exist, first suspect the distinction itself — maybe it isn't real — and research before inventing. A coined name that survives is marked as a mnemonic in the glossary, next to the standard term.
5. **Precisely defined concepts are always used with their full definition.** Examples must match the definition, not a nearby approximation.
6. **Mark attribution boundaries.** A simplified teaching model must not claim to be the *whole* cause of a phenomenon when other causal paths exist, even if those are still locked. Say "this is one path; another (node X, not yet learned) also produces this."
7. **✅ can be relied on without re-teaching.** Don't re-teach it unless it is caveated or the learner stumbles on it.
8. **Separate mechanism from statistics.** A statement about how the system works holds regardless of who is involved. A measurement of a population, and advice derived from it, must name the population — and if the learner's context differs, say so.
9. **Reconcile outside instructions before judging them.** Learners bring in cues from teachers, books, videos, and other tools. When one conflicts with the model or another cue, first ask whether they govern different axes, phases, or conditions before concluding either is wrong.
10. **The learner doesn't read the source material** unless a reading node assigned it. Every fact an answer depends on must have been taught, or be given in the stem.
11. **Define notation before using it.** A learner fluent in the underlying ideas may still not read the field's symbols (see diagnosis.md). The first time a symbol appears, in a lesson or a question, define it with a small concrete example, or say it in words and numbers.
12. **Don't trust hand memory over the script.** If your recollection of a status or the frontier disagrees with `graph.py`, the script (and the files behind it) wins; fix the files.

## Big picture and meaning

Verified bottom-up knowledge is necessary but not sufficient. A learner who can only recite a formula and compute with it has not understood it until they also know what problem it solved, what it looks like, and what it is for. Three duties follow.

**1. Every lesson knows what it is for.**
- In `topic.yaml`, each `[[goal]]` carries a `question`: one concrete question, in the learner's own terms, that they will be able to answer at the end. `preflight` and `next` print the chain from the current node to that goal's target, together with this question.
- Each lesson opens and closes by placing itself on that chain.
- A node that sits on no goal path must be justified by the learner's choice (a change of pace, curiosity). Otherwise don't recommend it.

**2. Every node gets more than the bare claim.** A node's draft and its lesson carry its motivation and a picture or table, and where they exist a connection to a field the learner knows and the consequence for the learner's purpose (for a design-altitude learner: what it constrains in the design). Don't invent history or force an analogy.

**3. Zoom out regularly.** Map and synthesis nodes (nodes.md) do this structurally. In addition:
- When the learner returns after a break, starts a new group, or seems to be losing the thread, open with a one-minute "you are here" view: the group map with ✅ parts marked.
- After a group's last node, revisit the goal's `question` and answer as much of it as the ✅ nodes allow. This shows progress in terms the learner cares about, not in node counts.

## Workflow

No topic directory yet → section A in building.md. Otherwise a session runs this loop; copy the checklist and track progress:

```
Session progress:
- [ ] B.1 Read rules.md and goals.md
- [ ] B.2 graph.py check — fix and re-run until clean
- [ ] B.3 graph.py next — offer a retro if suggested; recommend; learner picks; skim debts.md
- [ ] B.4 One review question if next names a node due (upkeep.md, J)
- [ ] D.2 graph.py preflight ID — draft the node body, check claims against the source
- [ ] D.4 Write the node summary; graph.py set
- [ ] G   Update debts/open-questions/glossary/sources; graph.py sync until clean
```

Sections: A build and H change goal → building.md; C diagnosis → diagnosis.md; I retro and J review → upkeep.md; B, D, E, F, G below.

### B. Starting a session in an existing topic

1. Read `rules.md` (domain rules override the defaults) and `goals.md`.
2. Run `graph.py check`. Fix errors before recommending anything.
3. Run `graph.py next` (or read `STATE.md`). If it suggests a retro, offer that first (section I); the learner may postpone it. Otherwise offer a short recommendation with the reason, including the route to the goal, and let the learner pick. Also skim `debts.md` for items the chosen node is supposed to settle, including misconceptions to retest.
4. If `next` names a node due for review, open the lesson with one review question on it (section J).

### D. Teaching a node

1. **Choose** with `graph.py next`. The ranking encodes the priorities: retests, then main-track bottlenecks on the goal path, then side nodes for a change of pace.
2. **Pre-flight**: `graph.py preflight ID`. It refuses locked nodes. Its output is the *allowed vocabulary* for the explanation, every example, and every expected answer path. If a planned example needs anything outside it, either teach that node first or cut the example down.
   - Before teaching, fill the node's body with a draft (the claims to teach, the motivation, the planned picture or table, the source anchors) and check every claim against the source. If `references/` has a text covering the node, read it first and borrow its framing (nodes.md, "Reference texts").
   - Untaught nodes often have only a title. Titles are written while the graph is built, from a quicker read, and can over-claim. If the source says otherwise, correct the title first — the learner is about to be tested on it.
   - Check the node against the 25-minute tests (nodes.md); split it before teaching if it fails. A node with `source`, `depth` or `mode: "reading"` is prepared as nodes.md describes.
   - Teach consistently with the prereq summaries `preflight` printed.
3. **Mid-lesson gaps.** If the learner's question or a needed step reaches outside ✅ territory, stop and say what node it belongs to. If none exists, `graph.py add` it. Then either switch to it (and return) or mark the boundary explicitly and continue, recording a debt.
4. **Record.** Write the node's summary into its file (see "Writing node summaries"), then `graph.py set`. Every layer's two questions correct → `mastered`. Session ended mid-node, or content delivered without retest → `taught`, with a note in the body of where it stopped. A wrong second retest means not mastered, regardless of the first answer.

### E. Questions from outside the graph

Learners arrive with real problems, instructions from a teacher, claims they read. These show which parts of the graph matter, but they tempt you to answer with everything you know.

- **Locate it.** Which node(s) would answer it? If locked, say which path leads there (`graph.py show`), and answer only as far as ✅ nodes support.
- **Hold competing explanations open.** When several mechanisms could explain the observation, add an entry to `open-questions.md`: the candidates, which nodes each depends on, and a cheap self-test the learner can do to tell them apart. Don't pick a winner before the evidence does.
- **New nodes and corrections** the question reveals go into the graph right away.

### F. Simplifications and corrections

Teaching a simplified model first is the point of the approach; letting the simplification pass as the full truth is the danger.

- Every simplification in the learner's model is written in that node's body, with the node that will correct it.
- When a later node corrects an earlier ✅ node, edit the earlier node's summary in place and set a `caveat` stating the scope in which the old ✅ still holds (`graph.py set ID mastered --caveat "…"`). If the learner actually held the old belief, add it to `debts.md` as a misconception to retest.
- If you find you over-claimed earlier, say so plainly and fix the record. The learner is building on it.

### G. Ending a session

Update the files with targeted edits (never regenerate a file from memory — files drift when rewritten):

- node summaries and `graph.py set` for every node touched; new nodes via `add`
- `debts.md` (forward references, misconceptions to retest, skipped retests, flawed exercises), `open-questions.md`, `glossary.md`, `sources.md` as needed
- run `graph.py sync` — it validates and regenerates `STATE.md`, which is what the next session starts from

If `sync` reports errors, fix them and re-run before ending; the next session must start from a consistent graph.

## Writing node summaries

The summary in a node's body is the canonical model. The next session must teach consistently with what was taught, so it states the claim as taught, with the exact terms and the attribution boundaries. It is the learner's model, not an encyclopedia entry: compact, precise, flagged where simplified.

- **Current state, not history.** No "session 3: we covered…" logs (`log.jsonl` keeps the machine record). When something changed, the useful residue is the corrected statement, the scope of the old one, and — if the learner held it — a pitfall line in the node body (plus a `debts.md` retest item until it is retested).
- **Write in the learner's language,** with standard terms (usually English for technical fields) alongside.
- **Include**: the claim; why it exists (motivation, in a line); the picture or table used, kept in the body so the next session reuses it; terms introduced; attribution boundaries and known simplifications (⚠️, naming the node that corrects them); for `taught` nodes, where the lesson stopped.
- **Keep it lean as it grows.** Long-settled ✅ summaries can compress to a line or two. Resolved open questions shrink to their conclusion. Paid debts are deleted.
- Group-level material (a shared caveat, a preview of a group's target answer marked as *not yet learned*) goes in `_group.md`, not in any node.
