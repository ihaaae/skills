# Teaching within the graph

Read this when preparing or teaching a node, when a question from outside the graph comes up, or when a later node corrects an earlier one. Recommending and recording need only SKILL.md.

## Contents
- Core rules
- Big picture and meaning
- D. Teaching a node (steps 2–3)
- E. Questions from outside the graph
- F. Simplifications and corrections

## Core rules

These apply to every topic. A topic's `rules.md` adds domain rules; those take precedence. Rule numbers are referenced from other files and never change.

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

## D. Teaching a node

Step 1 (choose with `next`) and step 4 (record) are in SKILL.md.

2. **Pre-flight**: `graph.py preflight ID`. It refuses locked nodes. Its output is the *allowed vocabulary* for the explanation, every example, and every expected answer path. If a planned example needs anything outside it, either teach that node first or cut the example down.
   - Before teaching, fill the node's body with a draft (the claims to teach, the motivation, the planned picture or table, the source anchors) and check every claim against the source. If `references/` has a text covering the node, read it first and borrow its framing (nodes.md, "Reference texts").
   - Untaught nodes often have only a title. Titles are written while the graph is built, from a quicker read, and can over-claim. If the source says otherwise, correct the title first — the learner is about to be tested on it.
   - Check the node against the 25-minute tests (nodes.md); split it before teaching if it fails. A node with `source`, `depth` or `mode: "reading"` is prepared as nodes.md describes.
   - Teach consistently with the prereq summaries `preflight` printed.
3. **Mid-lesson gaps.** If the learner's question or a needed step reaches outside ✅ territory, stop and say what node it belongs to. If none exists, `graph.py add` it. Then either switch to it (and return) or mark the boundary explicitly and continue, recording a debt.

## E. Questions from outside the graph

Learners arrive with real problems, instructions from a teacher, claims they read. These show which parts of the graph matter, but they tempt you to answer with everything you know.

- **Locate it.** Which node(s) would answer it? If locked, say which path leads there (`graph.py show`), and answer only as far as ✅ nodes support.
- **Hold competing explanations open.** When several mechanisms could explain the observation, add an entry to `open-questions.md`: the candidates, which nodes each depends on, and a cheap self-test the learner can do to tell them apart. Don't pick a winner before the evidence does.
- **New nodes and corrections** the question reveals go into the graph right away.

## F. Simplifications and corrections

Teaching a simplified model first is the point of the approach; letting the simplification pass as the full truth is the danger.

- Every simplification in the learner's model is written in that node's body, with the node that will correct it.
- When a later node corrects an earlier ✅ node, edit the earlier node's summary in place and set a `caveat` stating the scope in which the old ✅ still holds (`graph.py set ID mastered --caveat "…"`). If the learner actually held the old belief, add it to `debts.md` as a misconception to retest.
- If you find you over-claimed earlier, say so plainly and fix the record. The learner is building on it.
