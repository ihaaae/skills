# Building and re-goaling a graph

Read this when starting a new topic (section A) or when the learner changes their goal (section H). Building also needs the node kinds and the 25-minute tests in nodes.md.

## A. Starting fresh: build the graph

Copy this checklist and track progress:

```
Build progress:
- [ ] A.1 Pin goal, altitude and object; write goals.md and each goal's question
- [ ] A.2 Chain backward; apply the 25-minute tests; add map and synthesis nodes
- [ ] A.3 Create topic.yaml, rules.md, nodes via graph.py add
- [ ] A.4 Stop two or three layers ahead of the frontier
- [ ] A.5 Diagnose (diagnosis.md) and set initial statuses
- [ ] A.6 graph.py sync; show the frontier; recommend a first node
```

1. **Pin the goal.** What concept or ability does the learner want, and why? The "why" decides priorities later. Ask about background only as far as it helps you choose where to start diagnosing — self-reports don't set statuses. Write `goals.md`, including explicit non-goals.

   **Pin the altitude too, before chaining backward.** "Understand X" can mean implement it, review someone else's work on it, or oversee it (follow progress, judge risks, set plans) — and the three produce graphs of very different depth. Topic names and scope checklists don't reveal which one the learner means. Take one or two real sentences from the learning material and ask what the learner should be able to do with them at the end: re-derive them, check them, or explain what they mean for the plan. A graph built at the wrong altitude has to be rebuilt (section H).

   **Pin the object, not only the altitude.** When the learning material is a concrete thing — a repository, a project, a product — it contains two kinds of content: knowledge that exists independently of it (standards, protocols, mechanisms, common practice in the field, the hardware's own documentation), and the material's own decisions (its plans, task breakdowns, internal layering, process). Default priorities:
   - **Durable before transient.** Teach the independent knowledge; use the material's own decisions only as one-line examples of it. A project still in flux will change its plans, and a lesson built on them expires with them.
   - **General before specific.** Within durable knowledge, concepts that apply everywhere (the bus, the OS, the field's standard architecture) come before "how this device / this vendor does it".
   - **Process is a non-goal by default.** What counts as sufficient verification, how to grade evidence, when a task is "done", how to track progress — leave these out unless the learner explicitly asks to learn them. State honestly where a fact comes from, but don't turn that into a lesson.
   - **Warning sign:** node titles that mostly cite the material's own file names, task numbers or layer names mean the graph is studying the material, not the knowledge behind it. Check with the learner before building further.

   When the material's own design is unstable and the vendor's is opaque, the field's mainstream practice (widely used open-source frameworks, standards) is usually the best anchor for "architecture" topics.

   Write each goal's `question` in `topic.yaml` (see "Big picture and meaning" in teaching.md): one concrete question the learner wants to be able to answer.
2. **Chain backward.** From the goal, ask "what must be understood before this?" repeatedly until you reach things a general adult already knows or that you'll diagnose. Apply the 25-minute tests as you go. Then check the shape: each main group needs a map node near its entry and at least one synthesis node near its end.
3. **Create the directory**: `topic.yaml` (title, `[track] main`, one `[[goal]]` per goal with `targets` — the end-point nodes whose ancestors form the goal path), `rules.md`, and nodes via `graph.py add` (first `add` in a new group needs `--group-title`). Run `graph.py check` after adding; fix and re-run until clean.
4. **Don't build the whole domain.** Build solidly two or three layers ahead of the frontier and leave distant regions as a few coarse 🔒 stubs. The graph grows as learning reveals what's needed.
5. **Diagnose** (section C) and `set` initial statuses.
6. Run `sync`, show the learner the frontier and recommend a first node.

## H. Changing the goal

Learners revise their goal, most often its altitude ("I don't need every detail after all, just enough to follow the project") or its object ("teach me the field's knowledge, not our project's plans" — see "Pin the object" in A.1). Nodes built for the old goal are usually still true, just not what the learner needs now. Keep them; don't retire them.

1. Rewrite `goals.md` for the new goal. Move what the old goal covered and the new one doesn't into the non-goals, and name the groups that hold it, so a later session knows where to resume a deep dive.
2. Build the new layer as **new groups** (`graph.py add` with `--group-title`). Don't retitle old nodes to fit: their IDs, statuses and summaries describe what was built or taught under the old goal.
3. In `topic.yaml`, set `[track] main` to the groups that serve the new goal — the new groups, plus any old groups whose content still fits — and replace the goals with the new targets. The remaining old groups drop to side groups: `next` stops recommending them but can still reach them, and any ✅ in them still counts.
4. Record in a comment in `topic.yaml` why the old groups are off the main track, then `sync`.

Retire a node only when it is wrong or duplicated, never just because it is out of the current goal's scope — a retired ID can't be used again, and a deep dive later would have to rebuild it.
