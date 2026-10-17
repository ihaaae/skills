#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anki==26.9.3", "markdown-it-py", "pyyaml"]
# ///
"""spaced-repetition: 用 Anki 的 collection 格式和 FSRS 调度做间隔重复；复习在 Anki 桌面版里做。

卡片内容的来源是专题里的 srs/<节点ID>.yaml（进 git）；调度和复习记录在本地 collection 里（不进 git）。
collection 路径：$LEARN_SRS_COLLECTION（必须设置，通常指向 Anki profile 里的 collection.anki2）；backups/ 放在它旁边。
本脚本写 collection 时，Anki 桌面版不能打开它。

用法（在专题目录内运行，或用 --root 指定；在含多个专题的工作区根目录运行则覆盖全部专题）：
  srs.py check                   校验 atom 文件；有错误时退出码为 1
  srs.py sync [--apply] [--delete] 把 atom 同步进 collection；默认只显示计划
  srs.py counts                  现在到期的 new / learning / review 张数
  srs.py flag N ATOM             给 ATOM 的所有卡片设 flag 1-7，0 清除
  srs.py suspend ATOM / unsuspend ATOM
  srs.py leeches / flagged       需要维护的卡片
  srs.py card ATOM               一个 atom 的内容、调度和复习记录
  srs.py stats / backup

ATOM 写成 <节点>/<atom id>（在专题内）或 <专题>/<节点>/<atom id>。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FM_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
ATOM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)
ATOM_KEYS = {"id", "section", "front", "back", "cloze", "extra"}
BASIC_MODEL = "Learn Basic"
CLOZE_MODEL = "Learn Cloze"
MANAGED_TAG_PREFIXES = ("node::", "group::", "depth::")
RETIRED_TAG = "retired"
RATINGS = ["Again", "Hard", "Good", "Easy"]
FRONT_MAX, BACK_MAX = 200, 300
RULE = "────────"


# ───────────────────────── 专题与 atom 文件 ─────────────────────────

@dataclass
class Node:
    id: str
    title: str
    status: str
    depth: str | None
    group: str | None


@dataclass
class Atom:
    topic: str
    node: str
    id: str
    kind: str  # basic | cloze
    front: str = ""
    back: str = ""
    cloze: str = ""
    extra: str = ""
    section: str = ""

    @property
    def atom_id(self) -> str:
        return f"{self.topic}/{self.node}/{self.id}"


@dataclass
class Topic:
    name: str
    path: Path
    nodes: dict[str, Node] = field(default_factory=dict)
    atoms: list[Atom] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def deck(self) -> str:
        return f"Learn::{self.name}"


@dataclass
class Scope:
    topics: list[Topic]
    deck: str
    single: bool  # True: 一个专题；False: 工作区

    def atom_index(self) -> dict[str, Atom]:
        return {a.atom_id: a for t in self.topics for a in t.atoms}


def find_scope(explicit: str | None) -> Scope:
    if explicit:
        p = Path(explicit).expanduser().resolve()
    else:
        p = Path.cwd().resolve()
        for d in [p, *p.parents]:
            if (d / "topic.yaml").exists():
                p = d
                break
    if (p / "topic.yaml").exists():
        return Scope([load_topic(p)], f"Learn::{p.name}", True)
    subs = sorted(d for d in p.iterdir() if d.is_dir() and (d / "topic.yaml").exists()) if p.is_dir() else []
    if not subs:
        sys.exit(f"{p} 不是专题目录（没有 topic.yaml），下面也没有专题。请在专题目录内运行，或用 --root 指定。")
    return Scope([load_topic(d) for d in subs], "Learn", False)


def load_nodes(root: Path) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    base = root / "nodes"
    for f in sorted(base.glob("**/*.md")):
        if f.name.startswith("_"):
            continue
        m = FM_RE.match(f.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict) or "id" not in fm:
            continue
        rel = f.parent.relative_to(base)
        group = "::".join(rel.parts) if rel.parts else None
        nid = str(fm["id"])
        nodes[nid] = Node(nid, str(fm.get("title", nid)), str(fm.get("status", "new")),
                          str(fm["depth"]) if fm.get("depth") else None, group)
    return nodes


def load_topic(root: Path) -> Topic:
    t = Topic(root.name, root, load_nodes(root))
    node_id_re = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, sorted(t.nodes, key=len, reverse=True))) + r")(?![A-Za-z0-9_])") if t.nodes else None
    for f in sorted((root / "srs").glob("*.yaml")):
        rel = f.relative_to(root)
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            t.errors.append(f"{rel}: YAML 解析失败：{e}")
            continue
        if not isinstance(data, dict) or "node" not in data or "atoms" not in data:
            t.errors.append(f"{rel}: 顶层需要 node 和 atoms 两个键")
            continue
        nid = str(data["node"])
        if nid != f.stem:
            t.errors.append(f"{rel}: node 是 {nid}，但文件名是 {f.stem}.yaml")
            continue
        node = t.nodes.get(nid)
        if node is None:
            t.errors.append(f"{rel}: 节点 {nid} 不存在")
            continue
        if node.status == "retired":
            t.warnings.append(f"{rel}: 节点 {nid} 已 retired，sync 会 suspend 它的卡片")
        elif node.status != "mastered":
            t.warnings.append(f"{rel}: 节点 {nid} 状态是 {node.status}，还没有 mastered")
        atoms = data["atoms"]
        if not isinstance(atoms, list):
            t.errors.append(f"{rel}: atoms 必须是列表")
            continue
        seen: set[str] = set()
        for i, a in enumerate(atoms):
            where = f"{rel} 第 {i + 1} 个 atom"
            if not isinstance(a, dict):
                t.errors.append(f"{where}: 必须是映射")
                continue
            aid = str(a.get("id", ""))
            if aid:
                where = f"{rel} {aid}"
            if not ATOM_ID_RE.match(aid):
                t.errors.append(f"{where}: id 必须匹配 [a-z0-9-]+，以字母或数字开头")
                continue
            if aid in seen:
                t.errors.append(f"{where}: id 重复")
                continue
            seen.add(aid)
            unknown = set(a) - ATOM_KEYS
            if unknown:
                t.errors.append(f"{where}: 不认识的键 {', '.join(sorted(unknown))}")
                continue
            bad = [k for k in a if k != "id" and not isinstance(a[k], str)]
            if bad:
                t.errors.append(f"{where}: {', '.join(bad)} 必须是字符串")
                continue
            has_basic = "front" in a or "back" in a
            has_cloze = "cloze" in a or "extra" in a
            if has_basic == has_cloze:
                t.errors.append(f"{where}: 必须是 front+back 或 cloze(+extra) 二者之一")
                continue
            if has_basic:
                if not a.get("front", "").strip() or not a.get("back", "").strip():
                    t.errors.append(f"{where}: front 和 back 都不能为空")
                    continue
                atom = Atom(t.name, nid, aid, "basic", front=a["front"].strip(), back=a["back"].strip(),
                            section=a.get("section", "").strip())
                if len(atom.front) > FRONT_MAX:
                    t.warnings.append(f"{where}: front 有 {len(atom.front)} 个字符，超过 {FRONT_MAX}，考虑拆分")
                if len(atom.back) > BACK_MAX:
                    t.warnings.append(f"{where}: back 有 {len(atom.back)} 个字符，超过 {BACK_MAX}，考虑拆分")
                texts = [atom.front, atom.back]
            else:
                text = a.get("cloze", "").strip()
                if not CLOZE_RE.search(text):
                    t.errors.append(f"{where}: cloze 里没有 {{{{c1::…}}}}")
                    continue
                atom = Atom(t.name, nid, aid, "cloze", cloze=text, extra=a.get("extra", "").strip(),
                            section=a.get("section", "").strip())
                if len(atom.cloze) > FRONT_MAX:
                    t.warnings.append(f"{where}: cloze 有 {len(atom.cloze)} 个字符，超过 {FRONT_MAX}，考虑拆分")
                texts = [atom.cloze, atom.extra]
            if node_id_re:
                ids = sorted({m.group(1) for s in texts for m in node_id_re.finditer(s)})
                if ids:
                    t.warnings.append(f"{where}: 文字里出现节点编号 {', '.join(ids)}；提到别的节点请用名字")
            t.atoms.append(atom)
    return t


# ───────────────────────── 渲染 ─────────────────────────

_md = None


def md_html(text: str) -> str:
    global _md
    if _md is None:
        from markdown_it import MarkdownIt
        _md = MarkdownIt("commonmark")
    return _md.render(text).strip() if text else ""


def strip_html(s: str) -> str:
    s = re.sub(r"<style.*?</style>", "", s, flags=re.S)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|<hr[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def source_line(topic: Topic, atom: Atom) -> str:
    node = topic.nodes.get(atom.node)
    parts = [topic.name, node.title if node else atom.node]
    if atom.section:
        parts.append(atom.section)
    return " · ".join(parts)


def note_fields(topic: Topic, atom: Atom) -> dict[str, str]:
    src = html.escape(source_line(topic, atom), quote=False)
    if atom.kind == "basic":
        return {"Front": md_html(atom.front), "Back": md_html(atom.back), "Source": src, "AtomID": atom.atom_id}
    return {"Text": md_html(atom.cloze), "Extra": md_html(atom.extra), "Source": src, "AtomID": atom.atom_id}


def note_tags(topic: Topic, atom: Atom) -> list[str]:
    node = topic.nodes[atom.node]
    tags = [f"node::{atom.node}"]
    if node.group:
        tags.append(f"group::{node.group}")
    if node.depth:
        tags.append(f"depth::{node.depth}")
    return [t.replace(" ", "_") for t in tags]


def guid_for(atom_id: str) -> str:
    return "lrn" + hashlib.sha1(atom_id.encode()).hexdigest()[:16]


# ───────────────────────── collection ─────────────────────────

def collection_path() -> Path:
    p = os.environ.get("LEARN_SRS_COLLECTION")
    if not p:
        # 没有默认路径：默认路径会悄悄新建一个空 collection，看起来像卡全丢了
        sys.exit("srs.py: LEARN_SRS_COLLECTION 未设置（应指向 Anki profile 的 collection.anki2）")
    return Path(p).expanduser()


def open_col():
    from anki.collection import Collection
    p = collection_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    col = Collection(str(p))
    if not col.get_config("fsrs", False):
        col.set_config("fsrs", True)
    return col


def make_backup(col) -> None:
    folder = collection_path().parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    col.create_backup(backup_folder=str(folder), force=True, wait_for_completion=True)


def ensure_models(col) -> None:
    from anki.models import MODEL_CLOZE
    mm = col.models
    css = ".card { font-family: sans-serif; font-size: 20px; text-align: left; }\n.ctx { font-size: 14px; color: #888; margin-bottom: 1em; }\n"
    if not mm.by_name(BASIC_MODEL):
        m = mm.new(BASIC_MODEL)
        for f in ["Front", "Back", "Source", "AtomID"]:
            mm.add_field(m, mm.new_field(f))
        t = mm.new_template("Card 1")
        t["qfmt"] = "<div class=ctx>{{Source}}</div>{{Front}}"
        t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
        mm.add_template(m, t)
        m["css"] = css
        mm.add(m)
    if not mm.by_name(CLOZE_MODEL):
        m = mm.new(CLOZE_MODEL)
        m["type"] = MODEL_CLOZE
        for f in ["Text", "Extra", "Source", "AtomID"]:
            mm.add_field(m, mm.new_field(f))
        t = mm.new_template("Cloze")
        t["qfmt"] = "<div class=ctx>{{Source}}</div>{{cloze:Text}}"
        t["afmt"] = "<div class=ctx>{{Source}}</div>{{cloze:Text}}<hr id=answer>{{Extra}}"
        mm.add_template(m, t)
        m["css"] = css
        mm.add(m)


def search_escape(s: str) -> str:
    return re.sub(r'([\\"*_])', r"\\\1", s)


def notes_with_prefix(col, prefix: str) -> list:
    ids = col.find_notes(f'"AtomID:{search_escape(prefix)}*"')
    notes = [col.get_note(i) for i in ids]
    return [n for n in notes if n["AtomID"].startswith(prefix)]


def notes_for_atom(col, atom_id: str) -> list:
    ids = col.find_notes(f'"AtomID:{search_escape(atom_id)}"')
    return [n for n in (col.get_note(i) for i in ids) if n["AtomID"] == atom_id]


def deck_id(col, name: str):
    return col.decks.id_for_name(name)


def resolve_atom(scope: Scope, ref: str) -> str:
    parts = ref.strip("/").split("/")
    if len(parts) == 3:
        return "/".join(parts)
    if len(parts) == 2 and scope.single:
        return f"{scope.topics[0].name}/{parts[0]}/{parts[1]}"
    sys.exit(f"ATOM 要写成 <节点>/<atom id>（在专题内）或 <专题>/<节点>/<atom id>：{ref}")


def atom_cards(col, scope: Scope, ref: str) -> tuple[str, list]:
    atom_id = resolve_atom(scope, ref)
    notes = notes_for_atom(col, atom_id)
    if not notes:
        sys.exit(f"collection 里没有 {atom_id}")
    return atom_id, [c for n in notes for c in n.cards()]


# ───────────────────────── sync ─────────────────────────

def print_check(scope: Scope) -> bool:
    ok = True
    for t in scope.topics:
        for e in t.errors:
            print(f"错误 [{t.name}] {e}")
            ok = False
        for w in t.warnings:
            print(f"警告 [{t.name}] {w}")
    return ok


def cmd_check(scope: Scope, args) -> None:
    ok = print_check(scope)
    n = sum(len(t.atoms) for t in scope.topics)
    files = sum(len(list((t.path / "srs").glob("*.yaml"))) for t in scope.topics)
    print(f"{'通过' if ok else '有错误'}：{files} 个文件，{n} 个 atom。")
    if not ok:
        sys.exit(1)


def cmd_sync(scope: Scope, args) -> None:
    if not print_check(scope):
        sys.exit("atom 文件有错误，先修正（srs.py check）。")
    col = open_col()
    try:
        plan: list[tuple[str, str, object]] = []  # (动作, AtomID, 数据)
        problems: list[str] = []
        for t in scope.topics:
            existing: dict[str, list] = {}
            for n in notes_with_prefix(col, f"{t.name}/"):
                existing.setdefault(n["AtomID"], []).append(n)
            for aid, ns in existing.items():
                if len(ns) > 1:
                    problems.append(f"{aid} 在 collection 里有 {len(ns)} 条 note；用 card 查看后手工处理")
            did = deck_id(col, t.deck)
            live: set[str] = set()
            for atom in t.atoms:
                if t.nodes[atom.node].status == "retired":
                    continue
                live.add(atom.atom_id)
                model = BASIC_MODEL if atom.kind == "basic" else CLOZE_MODEL
                fields, tags = note_fields(t, atom), note_tags(t, atom)
                ns = existing.get(atom.atom_id)
                if not ns:
                    plan.append(("add", atom.atom_id, (t, atom, model, fields, tags)))
                    continue
                note = ns[0]
                if note.note_type()["name"] != model:
                    problems.append(f"{atom.atom_id} 从 {note.note_type()['name']} 变成了 {model}：换一个新的 atom id")
                    continue
                if atom.kind == "cloze":
                    have = {c.ord + 1 for c in note.cards()}
                    want = {int(m.group(1)) for m in CLOZE_RE.finditer(atom.cloze)}
                    if have - want:
                        problems.append(f"{atom.atom_id} 去掉了 c{', c'.join(map(str, sorted(have - want)))}：换一个新的 atom id")
                        continue
                changed = [k for k, v in fields.items() if note[k] != v]
                keep = [x for x in note.tags if not x.startswith(MANAGED_TAG_PREFIXES) and x != RETIRED_TAG]
                new_tags = tags + keep
                retired = RETIRED_TAG in note.tags
                wrong_deck = did is not None and any(c.did != did for c in note.cards())
                if retired:
                    plan.append(("restore", atom.atom_id, (note, fields, new_tags, t.deck)))
                elif changed or sorted(new_tags) != sorted(note.tags) or wrong_deck:
                    what = changed + (["tags"] if sorted(new_tags) != sorted(note.tags) else []) + (["deck"] if wrong_deck else [])
                    plan.append(("update", atom.atom_id, (note, fields, new_tags, t.deck, what)))
            for aid, ns in sorted(existing.items()):
                if aid in live:
                    continue
                if args.delete:
                    plan.append(("delete", aid, ns))
                elif not all(RETIRED_TAG in n.tags for n in ns):
                    plan.append(("retire", aid, ns))
        for p in problems:
            print(f"错误 {p}")
        if problems:
            sys.exit("有无法同步的变化，先处理上面的错误。")
        marks = {"add": "+ 新增", "update": "~ 更新", "restore": "↺ 恢复", "retire": "- 退役(suspend)", "delete": "× 删除"}
        for action, aid, data in plan:
            extra = f"（{', '.join(data[4])}）" if action == "update" else ""
            print(f"{marks[action]} {aid}{extra}")
        summary = "，".join(f"{marks[a].split()[1]} {sum(1 for p in plan if p[0] == a)}" for a in marks if any(p[0] == a for p in plan))
        if not plan:
            print("collection 已是最新，没有变化。")
            return
        if not args.apply:
            print(f"计划：{summary}。加 --apply 执行。")
            return
        ensure_models(col)
        if col.card_count():
            make_backup(col)
        for action, aid, data in plan:
            if action == "add":
                t, atom, model, fields, tags = data
                did = col.decks.id(t.deck)
                note = col.new_note(col.models.by_name(model))
                for k, v in fields.items():
                    note[k] = v
                note.guid = guid_for(aid)
                note.tags = tags
                col.add_note(note, did)
            elif action in ("update", "restore"):
                note, fields, tags, deck = data[:4]
                for k, v in fields.items():
                    note[k] = v
                note.tags = tags
                col.update_note(note)
                cids = [c.id for c in note.cards()]
                col.set_deck(cids, col.decks.id(deck))
                if action == "restore":
                    col.sched.unsuspend_cards(cids)
            elif action == "retire":
                for note in data:
                    if RETIRED_TAG not in note.tags:
                        note.tags.append(RETIRED_TAG)
                        col.update_note(note)
                    col.sched.suspend_cards([c.id for c in note.cards()])
            elif action == "delete":
                col.remove_notes([n.id for n in data])
        print(f"已执行：{summary}。")
    finally:
        col.close()


# ───────────────────────── 单张卡片操作 ─────────────────────────

def queue_label(card) -> str:
    if card.queue == 0:
        return "new"
    if card.type == 3:
        return "relearning"
    if card.queue in (1, 3):
        return "learning"
    return "review"


def atom_for_card(scope: Scope, card) -> tuple[Atom, str]:
    """返回 (atom, 来源行)。YAML 里找不到时，用 note 里存的字段还原。"""
    note = card.note()
    aid = note["AtomID"]
    index = scope.atom_index()
    if aid in index:
        atom = index[aid]
        topic = next(t for t in scope.topics if t.name == atom.topic)
        return atom, source_line(topic, atom)
    parts = aid.split("/")
    if "Text" in note.keys():
        atom = Atom(parts[0] if parts else "", parts[1] if len(parts) > 1 else "", parts[-1], "cloze",
                    cloze=strip_html(note["Text"]), extra=strip_html(note["Extra"]))
    else:
        atom = Atom(parts[0] if parts else "", parts[1] if len(parts) > 1 else "", parts[-1], "basic",
                    front=strip_html(note["Front"]), back=strip_html(note["Back"]))
    return atom, strip_html(note["Source"])


def with_col(fn):
    def run(scope: Scope, args) -> None:
        col = open_col()
        try:
            fn(col, scope, args)
        finally:
            col.close()
    return run


@with_col
def cmd_flag(col, scope, args) -> None:
    if not 0 <= args.n <= 7:
        sys.exit("flag 是 0（清除）到 7。")
    aid, cards = atom_cards(col, scope, args.atom)
    col.set_user_flag_for_cards(args.n, [c.id for c in cards])
    print(f"已{'清除 flag' if args.n == 0 else f'设 flag {args.n}'}：{aid}（{len(cards)} 张卡片）。")


@with_col
def cmd_suspend(col, scope, args) -> None:
    aid, cards = atom_cards(col, scope, args.atom)
    col.sched.suspend_cards([c.id for c in cards])
    print(f"已 suspend {aid}（{len(cards)} 张卡片），unsuspend 之前不再出现。")

@with_col
def cmd_unsuspend(col, scope, args) -> None:
    aid, cards = atom_cards(col, scope, args.atom)
    col.sched.unsuspend_cards([c.id for c in cards])
    print(f"已 unsuspend {aid}（{len(cards)} 张卡片）。")


def card_row(card) -> str:
    note = card.note()
    tag = f" c{card.ord + 1}" if "Text" in note.keys() else ""
    state = "suspended" if card.queue == -1 else ("buried" if card.queue in (-2, -3) else queue_label(card))
    return f"{note['AtomID']}{tag}  {state}  lapses {card.lapses}  reps {card.reps}" + (f"  flag {card.user_flag()}" if card.user_flag() else "")


@with_col
def cmd_leeches(col, scope, args) -> None:
    cids = col.find_cards(f'"deck:{search_escape(scope.deck)}" tag:leech')
    if not cids:
        print("没有 leech。")
    for cid in cids:
        print(card_row(col.get_card(cid)))


@with_col
def cmd_flagged(col, scope, args) -> None:
    cids = col.find_cards(f'"deck:{search_escape(scope.deck)}" -flag:0')
    if not cids:
        print("没有 flagged 的卡片。")
    for cid in cids:
        print(card_row(col.get_card(cid)))


def fmt_ivl(ivl: int) -> str:
    return f"{-ivl // 60}m" if ivl < 0 else f"{ivl}d"


def due_text(col, card) -> str:
    if card.queue == 0:
        return f"new #{card.due}"
    if card.queue == 1:
        return dt.datetime.fromtimestamp(card.due).strftime("%Y-%m-%d %H:%M")
    if card.queue in (2, 3):
        return (dt.date.today() + dt.timedelta(days=card.due - col.sched.today)).isoformat()
    return "-"


@with_col
def cmd_card(col, scope, args) -> None:
    aid, cards = atom_cards(col, scope, args.atom)
    atom, src = atom_for_card(scope, cards[0])
    print(aid)
    print(src)
    print(RULE)
    if atom.kind == "basic":
        print(atom.front)
        print(RULE)
        print(atom.back)
    else:
        print(atom.cloze)
        if atom.extra:
            print(RULE)
            print(atom.extra)
    print(RULE)
    print("tags: " + " ".join(cards[0].note().tags))
    for c in cards:
        print()
        print(card_row(c))
        ms = c.memory_state
        mem = f"  stability {ms.stability:.1f}d · difficulty {ms.difficulty:.1f}" if ms else ""
        print(f"  due {due_text(col, c)} · interval {c.ivl}d{mem}")
        for rid, ease, ivl, rtype in col.db.all("select id, ease, ivl, type from revlog where cid = ? order by id", c.id):
            when = dt.datetime.fromtimestamp(rid / 1000).strftime("%Y-%m-%d %H:%M")
            kind = ["learning", "review", "relearning", "filtered", "manual", "rescheduled"][rtype] if 0 <= rtype <= 5 else str(rtype)
            name = RATINGS[ease - 1] if 1 <= ease <= 4 else "-"
            print(f"  {when}  {name:<5}  {kind:<10}  → {fmt_ivl(ivl)}")


@with_col
def cmd_stats(col, scope, args) -> None:
    q = f'"deck:{search_escape(scope.deck)}"'
    cids = col.find_cards(q)
    print(f"[{scope.deck}] 卡片 {len(cids)} 张")
    for label, extra in [("new", "is:new"), ("learning", "is:learn -is:review"), ("review", "is:review -is:learn"),
                         ("relearning", "is:learn is:review"), ("suspended", "is:suspended"), ("buried", "is:buried"),
                         ("leech", "tag:leech"), ("retired", f"tag:{RETIRED_TAG}")]:
        print(f"  {label:<11}{len(col.find_cards(f'{q} {extra}'))}")
    if not cids:
        return
    since = int((time.time() - 30 * 86400) * 1000)
    marks = ",".join("?" * len(cids))
    total = col.db.scalar(f"select count() from revlog where cid in ({marks})", *cids)
    recent = col.db.all(f"select ease, type from revlog where id > ? and cid in ({marks})", since, *cids)
    reviews = [e for e, t in recent if t == 1]
    print(f"复习记录 {total} 条；最近 30 天 {len(recent)} 条")
    if reviews:
        kept = sum(1 for e in reviews if e > 1)
        print(f"最近 30 天 review 卡片的记住率 {kept / len(reviews):.0%}（{kept}/{len(reviews)}）")


@with_col
def cmd_counts(col, scope, args) -> None:
    decks = [scope.deck] if scope.single else [t.deck for t in scope.topics]
    any_deck = False
    for name in decks:
        did = deck_id(col, name)
        if not did:
            continue
        any_deck = True
        col.decks.select(did)
        new, lrn, rev = col.sched.counts()
        print(f"[{name}] new {new} · learning {lrn} · review {rev}")
    if not any_deck:
        print("collection 里还没有卡片：先写 atom，再 srs.py sync --apply。")


@with_col
def cmd_backup(col, scope, args) -> None:
    make_backup(col)
    print(f"已备份到 {collection_path().parent / 'backups'}")


# ───────────────────────── 入口 ─────────────────────────

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="间隔重复：Anki collection + FSRS；复习在 Anki 桌面版里做。")
    ap.add_argument("--root", help="专题目录（含 topic.yaml）或含多个专题的工作区目录")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("sync")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--delete", action="store_true", help="删除不在 YAML 里的 atom（默认只 suspend）")
    for name in ["counts", "leeches", "flagged", "stats", "backup"]:
        sub.add_parser(name)
    p = sub.add_parser("flag")
    p.add_argument("n", type=int)
    p.add_argument("atom")
    for name in ["suspend", "unsuspend", "card"]:
        sub.add_parser(name).add_argument("atom")
    args = ap.parse_args(argv)
    scope = find_scope(args.root)
    globals()[f"cmd_{args.cmd}"](scope, args)


if __name__ == "__main__":
    main()
