# Nodes

Read this when building or reshaping the graph, adding a node, or preparing a node at preflight (sizing it, using its `source` and `depth`).

## Contents
- Node file
- What a node is
- Map, mechanism and synthesis nodes
- Reading nodes
- Source and depth
- Reference texts
- The 25-minute rule
- IDs, groups, and edges

## Node file

`nodes/<G>/<ID>.md`:

```
---
id: "T6"
title: "hop < 帧长 ⇒ STFT 是过完备/冗余表示"
prereqs: ["T4", "D7"]
targets: []               # optional, see "IDs, groups, and edges"
status: "mastered"        # new | taught | mastered | retired
caveat: ""                # optional: scope in which a ✅ still holds
updated: 2026-09-29
verified: 2026-09-29      # written by `set … mastered`; drives review (section J)
mode: ""                  # optional: "reading" for a reading node
source: ""                # optional: where the node's material is, e.g. "book.md:1312-1381"
depth: ""                 # optional: write | read | aware
---
Body: the summary of what was actually taught (see "Writing node summaries" in SKILL.md).
```

## What a node is

A node is one claim, one distinction, or one mechanism that the learner could state in a sentence once they understand it. Good node titles read like the thing to be understood, not a chapter heading: "Vocal fold tension → pitch" rather than "Pitch"; "Connection direction ≠ data direction" rather than "TCP basics". A node whose whole point is the relationship between two things ("independently controllable, but coupled in effect") is still one node.

## Map, mechanism and synthesis nodes

A graph built only by chaining backward is purely bottom-up: every node is a detail, and the learner meets the whole only at the very end, if at all. Good learning alternates — see the whole roughly, go down into one part, come back up and see the whole more sharply. Build that rhythm into the graph with three kinds of node:

- **Map node** (top-down, at the entry of a group or a big subtree): "X consists of these parts; each part answers this question." Example: "CANopen = object dictionary + communication objects + device states + device profiles; each answers one question about a device." Teach it early, roughly, as a scaffold, and mark it a prerequisite of the group's first detail nodes. Test it by classification ("a new requirement appears — which part handles it?"), never by the parts' details. Every later detail lesson points back to its place on this map.
- **Mechanism / claim node** (bottom-up, the default): one claim, one distinction, one mechanism, as described above.
- **Synthesis node** (top-down again, after several details): one cross-cutting idea that only becomes visible once the parts are known — a comparison table across them, a classification, a design trade-off. Example: "the communication objects fall into three interaction models: master/slave, client/server, producer/consumer". Its prereqs are the details it unifies. Test it by applying the classification to a case not taught before.

Each main-track group should have a map node near its entry and at least one synthesis node near its end. A group's `_group.md` carries the map as a picture or table, with each part linked to the node that teaches it, so the learner can always see where they are.

## Reading nodes

Usually the tutor teaches and the learner never reads the source. But a well-written outside text — a good tutorial, a book chapter — can give a top-down view faster than lessons can, and a learner who chooses to read it should get credit for doing so. A **reading node** (`mode: "reading"`) assigns a short reading instead of teaching. The node body lists the exact sections assigned and the claims they are meant to establish. Reading suits map nodes and motivation/history best. A mechanism that needs worked examples is still taught.

## Source and depth

Both fields are optional; `graph.py` ignores them and they shape the lesson.

- **`source`** points at the text the node is built from (line ranges in a file under `references/`, a section of a standard). At preflight, read it first and borrow its structure, motivation and examples (see "Reference texts"). Exercises found there are question material, still under core rule 3. Facts that may have aged are checked against the current authoritative source.
- **`depth`** says what the learner should be able to do with the node, and so how it is taught and tested:

| Depth | Learner can… | Lesson and questions |
|---|---|---|
| write | produce it correctly | a full lesson; questions require producing or fixing |
| read | recognize it in someone else's work, say what it does and where it bites | predict-the-behavior questions on short snippets |
| aware | know it exists and when to look it up | several aware items can share one lesson, one "you meet situation X — what do you reach for?" question each |

A node can hold a lower-depth sub-item ("write; complex=aware"). Both fields are set when the graph is built (book-graph sets them for every node of a book-based topic); a session only reads them.

## Reference texts

An agent writing a lesson from scratch often produces a flatter explanation than a good human-written tutorial: it has less history, fewer well-chosen pictures, and less sense of what matters first. So a topic may keep such texts in `references/` (one subdirectory per publisher or series is fine). They are saved verbatim, every one gets an entry in `sources.md` with its credibility, and the learner may add more at any time.

- **When drafting a node (D.2), read the matching sections first.** Borrow their structure, motivation, history and pictures, and say in your own words what they say; don't paste long passages. Facts are still checked against the authoritative source the reference rests on (a standard, the official docs). A vendor tutorial is good at explaining and weak as an authority.
- **Reading nodes assign sections from here.** The learner reads the original text, not a summary of it.
- **Record conflicts.** When a reference contradicts an authority or another reference, the conflict goes in `open-questions.md`.
- **They are not the study object.** `material/` holds the thing being studied; `references/` holds texts that help explain it. Core rule 10 never covers `references/`, and the learner can read them freely.

## The 25-minute rule

Each node, including its exercises, should take under 25 minutes: one lesson. Size nodes by these tests:

- **One-paragraph test.** The first layer's explanation can be written in a short paragraph that introduces no new term besides the node's own subject. If it needs a second new term, that term is probably its own node.
- **Ladder test.** Each later layer of the lesson adds one real-world variable the learner already knows, or one more piece of the node's own mechanism. If a layer would need a concept that is neither ✅ nor part of this node, the concept becomes a separate node and this node gets smaller. If the node needs more than four layers, split it.
- **Question test.** You can write two isomorphic questions whose answers depend only on this node plus ✅ nodes. If you can't, the node is either too vague (sharpen the claim) or too thin (merge it into a neighbor, or make it a note on one). And every core claim of the node is hit directly by at least one question. A claim that appears only in an example was never tested, and a ✅ built on it is hollow. If the questions of four layers can't cover the claims, split the node.
- **Failure-point test.** If an exercise has two independent reasoning steps that could each fail for different reasons, that is two nodes.

Err on the side of smaller. A node that turns out trivial costs five minutes; a node that is secretly three nodes produces a lesson where the learner answers correctly for the wrong reason and nobody notices.

## IDs, groups, and edges

Each node has a short ID: a group letter plus a number (A1, S12, T23); the group letter must match the directory. IDs never change once assigned, because other sessions and the learner's own notes refer to them; a retired node keeps its file with `status: "retired"` and `merged_into`, and its ID is never reused. Groups are branches of the subject (foundations, one subsystem per letter, practice techniques, …).

Edges have a type:

- **Prerequisite** (`prereqs`, gating): to understand this node, the learner must first master that one. Only these gate unlocking.
- **Target** (`targets`, non-gating, optional): for *practice* nodes — exercises, drills, techniques — says which concept node the practice trains or exposes. Practice commonly precedes understanding, so a practice node may be learned while its target is still locked. When teaching it, you still may not *explain* using the locked target's content.

If the subject has both a "how it works" side and a "what to do about it" side, keep them in separate groups. Conclusions from practice ("this drill helps") must not be written into mechanism nodes as if they were mechanisms; observations from practice may serve as evidence for or against a mechanism.
