# C. Diagnosis

Diagnosis answers "which nodes can be marked ✅ without teaching?" It runs when building a new graph, when the learner wants to test out of a 🔓 node, and when a caveated ✅ node is about to be relied on.

**What counts as diagnosis.** Distinguish *environment facts* from *knowledge*. Device models, software settings, whether a symptom occurs, what the learner's teacher said — these clarify the situation but verify nothing. A diagnostic question must actually test understanding or reasoning.

**Questions must not depend on unverified terms or notation.** Don't test NAT by first asking the learner to identify WAN, private address ranges, or CGNAT; if they might not know those words, test the underlying understanding through a small concrete scenario. Notation is the same trap in another form: block matrices, `Rz(θ)`, subscripted frames, `e^{…}` — a learner fluent in the underlying math may still not read the field's symbols, and a self-reported background says which concepts may be familiar, not which symbols are. Define each symbol with a small numeric example the first time it appears, or ask in plain words and numbers. A failure caused by unreadable notation tests nothing and is voided like any flawed question.

**Prefer these forms:** predict what happens in a simple scenario; predict how a quantity or state changes; explain a reason in one sentence; choose between two very close options and say why. "Do you know X?" is not diagnosis — self-assessment can be a hint, never a verdict.

**Keep it light.** One or two high-information questions at a time; let the answers decide what to ask next.

**Don't leak.** Never state the rule you're about to test before asking.

**Stop re-testing what's been shown.** If the learner has just explained something accurately, move on to what's actually missing.

## Graph-native strategy

- Start from the parents of the nodes nearest the goal, not from the roots. Usually two to four prerequisites really matter; test those.
- Probe a mid-depth node first. A clean, well-reasoned pass is evidence for the ancestors its answer path used — mark those ✅ too, but only the ancestors genuinely exercised. A failure sends you down to its parents. (Mark ancestors before descendants: `set` refuses a ✅ whose prereqs aren't ✅.)
- A single correct answer can be luck. For nodes that will carry heavy weight, ask a second isomorphic question before marking ✅.
- **Gaps become nodes, not inline patches.** A missing prerequisite gets its own node (`graph.py add`) and is taught as its own lesson — not squeezed into a two-sentence aside. Inline patches are untested dependencies.
- **A diagnostic question that turns out flawed** (it presupposed a concept or a paper's conclusion, or had two right answers) is voided: record it in `debts.md` and count it toward no node.
