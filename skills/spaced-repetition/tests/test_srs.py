import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "srs.py"
spec = importlib.util.spec_from_file_location("srs", SCRIPT)
srs = importlib.util.module_from_spec(spec)
sys.modules["srs"] = srs
spec.loader.exec_module(srs)

C3_ATOMS = textwrap.dedent("""\
    node: C3
    atoms:
      - id: index-is-byte
        section: string 是一串 byte
        front: |
          `s := "Go!"`，`fmt.Println(s[0])` 打印什么？
        back: |
          `71`。
      - id: len-counts-bytes
        cloze: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。"
      - id: rune-is-type
        cloze: "rune 是表示一个 {{c1::code point}} 的 type，是 {{c2::int32::一个整数 type}} 的 alias。"
        extra: "rune 是 type，UTF-32 是 encoding。"
    """)


def node(root, nid, title, status="mastered", depth="write"):
    d = root / "nodes" / nid[0]
    d.mkdir(parents=True, exist_ok=True)
    (d / "_group.md").write_text(f'---\ntitle: "{nid[0]} 组"\n---\n')
    (d / f"{nid}.md").write_text(
        f'---\nid: "{nid}"\ntitle: "{title}"\nprereqs: []\ndepth: "{depth}"\nstatus: "{status}"\n---\nx\n'
    )


@pytest.fixture
def topic(tmp_path, monkeypatch):
    root = tmp_path / "Golang"
    root.mkdir()
    (root / "topic.yaml").write_text("title: t\n")
    node(root, "C2", "slicing slices")
    node(root, "C3", "string, rune, byte, UTF-8")
    node(root, "C4", "maps", status="taught")
    (root / "srs").mkdir()
    (root / "srs" / "C3.yaml").write_text(C3_ATOMS, encoding="utf-8")
    monkeypatch.setenv("LEARN_SRS_COLLECTION", str(tmp_path / "data" / "collection.anki2"))
    return root


def run(root, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                       capture_output=True, text=True, env=os.environ.copy(), check=False)
    if ok and r.returncode != 0:
        raise AssertionError(f"srs.py {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def edit_atoms(root, text):
    (root / "srs" / "C3.yaml").write_text(textwrap.dedent(text), encoding="utf-8")


class Col:
    """在测试进程里打开 collection；离开 with 时关闭，免得锁住子进程。"""

    def __enter__(self):
        self.col = srs.open_col()
        return self.col

    def __exit__(self, *exc):
        self.col.close()


def cards_of(col, atom_id):
    return [c for n in srs.notes_for_atom(col, atom_id) for c in n.cards()]


def revlog(col, cid):
    return col.db.list("select ease from revlog where cid = ? order by id", cid)


def make_due(atom_id, deck="Learn::Golang"):
    """把一个 atom 之外的卡片都 suspend，并让它现在到期，复习队列里只有它。"""
    with Col() as col:
        mine = sorted(cards_of(col, atom_id), key=lambda c: c.ord)  # c1、c2 的顺序；card id 不保证有序
        keep = {c.id for c in mine}
        others = [cid for cid in col.find_cards(f'"deck:{deck}"') if cid not in keep]
        col.sched.suspend_cards(others)
        return [c.id for c in mine]


# ───────────── check ─────────────

def test_check_passes(topic):
    r = run(topic, "check")
    assert "通过：1 个文件，3 个 atom。" in r.stdout


@pytest.mark.parametrize("body, msg", [
    ("node: C3\natoms: [\n", "YAML 解析失败"),
    ("atoms: []\n", "顶层需要 node 和 atoms"),
    ("node: C2\natoms: []\n", "node 是 C2，但文件名是 C3.yaml"),
    ("node: C3\natoms: {}\n", "atoms 必须是列表"),
    ("node: C3\natoms:\n  - id: Bad_ID\n    front: a\n    back: b\n", "id 必须匹配"),
    ("node: C3\natoms:\n  - {id: a, front: x, back: y}\n  - {id: a, front: x, back: y}\n", "id 重复"),
    ("node: C3\natoms:\n  - {id: a, front: x, back: y, hint: z}\n", "不认识的键 hint"),
    ("node: C3\natoms:\n  - {id: a, front: x, back: 3}\n", "back 必须是字符串"),
    ("node: C3\natoms:\n  - {id: a, front: x, cloze: \"{{c1::y}}\"}\n", "二者之一"),
    ("node: C3\natoms:\n  - {id: a, front: x, back: \" \"}\n", "都不能为空"),
    ("node: C3\natoms:\n  - {id: a, cloze: no marker}\n", "cloze 里没有"),
])
def test_check_errors(topic, body, msg):
    (topic / "srs" / "C3.yaml").write_text(body, encoding="utf-8")
    r = run(topic, "check", ok=False)
    assert r.returncode == 1
    assert msg in r.stdout


def test_check_unknown_node(topic):
    (topic / "srs" / "Z9.yaml").write_text("node: Z9\natoms: []\n")
    r = run(topic, "check", ok=False)
    assert "节点 Z9 不存在" in r.stdout


def test_check_warnings(topic):
    (topic / "srs" / "C4.yaml").write_text(
        "node: C4\natoms:\n  - id: a\n    front: 和 C2 讲的一样吗？C22 不算。\n    back: " + "很长" * 200 + "\n",
        encoding="utf-8")
    r = run(topic, "check")
    assert "状态是 taught，还没有 mastered" in r.stdout
    assert "文字里出现节点编号 C2；" in r.stdout
    assert "back 有 400 个字符，超过 300" in r.stdout
    assert r.stdout.strip().endswith("通过：2 个文件，4 个 atom。")


# ───────────── rendering ─────────────

def test_cloze_side():
    text = "rune 是 {{c1::code point}} 的 type，是 {{c2::int32::整数}} 的 alias。"
    assert srs.cloze_side(text, 1, False) == "rune 是 [...] 的 type，是 int32 的 alias。"
    assert srs.cloze_side(text, 1, True) == "rune 是 [code point] 的 type，是 int32 的 alias。"
    assert srs.cloze_side(text, 2, False) == "rune 是 code point 的 type，是 [整数] 的 alias。"
    assert srs.cloze_side(text, 2, True) == "rune 是 code point 的 type，是 [int32] 的 alias。"


def test_search_escape():
    assert srs.search_escape('a_b*c"d\\') == 'a\\_b\\*c\\"d\\\\'


# ───────────── sync ─────────────

def test_sync_plan_apply_idempotent(topic):
    r = run(topic, "sync")
    assert "+ 新增 Golang/C3/index-is-byte" in r.stdout
    assert "计划：新增 3。加 --apply 执行。" in r.stdout
    with Col() as col:
        assert col.card_count() == 0
    r = run(topic, "sync", "--apply")
    assert "已执行：新增 3。" in r.stdout
    with Col() as col:
        assert col.card_count() == 4  # rune-is-type 有两个 cloze
        did = col.decks.id_for_name("Learn::Golang")
        assert did
        (note,) = srs.notes_for_atom(col, "Golang/C3/rune-is-type")
        assert note.guid == srs.guid_for("Golang/C3/rune-is-type")
        assert sorted(note.tags) == ["depth::write", "group::C", "node::C3"]
        assert note["Source"] == "Golang · string, rune, byte, UTF-8"
        assert all(c.did == did for c in note.cards())
        assert col.get_config("fsrs")
    assert "collection 已是最新，没有变化。" in run(topic, "sync").stdout


def test_sync_edit_keeps_schedule(topic):
    run(topic, "sync", "--apply")
    (cid,) = make_due("Golang/C3/index-is-byte")
    run(topic, "next")
    run(topic, "reveal")
    run(topic, "answer", "3")
    run(topic, "done")
    with Col() as col:
        before = col.get_card(cid)
        due, ivl = before.due, before.ivl
    edit_atoms(topic, C3_ATOMS.replace("`71`。", "`71`，一个 `uint8` 数字。"))
    r = run(topic, "sync")
    assert "~ 更新 Golang/C3/index-is-byte（Back）" in r.stdout
    run(topic, "sync", "--apply")
    with Col() as col:
        (card,) = cards_of(col, "Golang/C3/index-is-byte")
        assert card.id == cid and card.due == due and card.ivl == ivl
        assert revlog(col, cid) == [3]
        assert "uint8" in card.note()["Back"]


def test_sync_keeps_learner_tags(topic):
    run(topic, "sync", "--apply")
    with Col() as col:
        (note,) = srs.notes_for_atom(col, "Golang/C3/index-is-byte")
        note.tags.append("mine")
        col.update_note(note)
    assert "collection 已是最新" in run(topic, "sync").stdout
    node(topic, "C3", "string, rune, byte, UTF-8", depth="read")
    r = run(topic, "sync", "--apply")
    assert "~ 更新 Golang/C3/index-is-byte（tags）" in r.stdout
    with Col() as col:
        (note,) = srs.notes_for_atom(col, "Golang/C3/index-is-byte")
        assert sorted(note.tags) == ["depth::read", "group::C", "mine", "node::C3"]


def test_sync_retire_restore_delete(topic):
    run(topic, "sync", "--apply")
    edit_atoms(topic, C3_ATOMS.split("  - id: len-counts-bytes")[0])
    r = run(topic, "sync", "--apply")
    assert "- 退役(suspend) Golang/C3/len-counts-bytes" in r.stdout
    assert "- 退役(suspend) Golang/C3/rune-is-type" in r.stdout
    with Col() as col:
        cards = cards_of(col, "Golang/C3/rune-is-type")
        assert len(cards) == 2 and all(c.queue == -1 for c in cards)
        assert "retired" in cards[0].note().tags
    assert "collection 已是最新" in run(topic, "sync").stdout

    edit_atoms(topic, C3_ATOMS)
    r = run(topic, "sync", "--apply")
    assert "↺ 恢复 Golang/C3/rune-is-type" in r.stdout
    with Col() as col:
        cards = cards_of(col, "Golang/C3/rune-is-type")
        assert all(c.queue == 0 for c in cards)
        assert "retired" not in cards[0].note().tags

    edit_atoms(topic, C3_ATOMS.split("  - id: len-counts-bytes")[0])
    r = run(topic, "sync", "--apply", "--delete")
    assert "× 删除 Golang/C3/len-counts-bytes" in r.stdout
    with Col() as col:
        assert col.card_count() == 1
    assert list((topic.parent / "data" / "backups").iterdir())


def test_sync_retired_node(topic):
    run(topic, "sync", "--apply")
    node(topic, "C3", "string, rune, byte, UTF-8", status="retired")
    assert "已 retired" in run(topic, "check").stdout
    r = run(topic, "sync", "--apply")
    assert "退役(suspend) 3" in r.stdout


def test_sync_rejects_kind_change_and_removed_cloze(topic):
    run(topic, "sync", "--apply")
    edit_atoms(topic, C3_ATOMS.replace(
        'cloze: "`len(s)` 返回 s 里 {{c1::byte}} 的个数。"', "front: len 数什么？\n    back: byte"))
    r = run(topic, "sync", ok=False)
    assert "从 Learn Cloze 变成了 Learn Basic" in r.stdout
    assert r.returncode != 0
    edit_atoms(topic, C3_ATOMS.replace("{{c2::int32::一个整数 type}}", "int32"))
    r = run(topic, "sync", ok=False)
    assert "去掉了 c2" in r.stdout


def test_sync_refuses_on_lint_error(topic):
    (topic / "srs" / "C3.yaml").write_text("node: C3\natoms: {}\n")
    r = run(topic, "sync", ok=False)
    assert r.returncode != 0
    assert "先修正" in r.stderr


# ───────────── review ─────────────

def test_review_requires_deck(topic):
    r = run(topic, "next", ok=False)
    assert "还没有 Learn::Golang" in r.stderr


def test_review_flow_records_rating(topic):
    run(topic, "sync", "--apply")
    assert "[Learn::Golang] new 4 · learning 0 · review 0" in run(topic, "counts").stdout
    (cid,) = make_due("Golang/C3/index-is-byte")
    r = run(topic, "next")
    assert "Golang/C3/index-is-byte · new" in r.stdout
    assert "Golang · string, rune, byte, UTF-8 · string 是一串 byte" in r.stdout
    assert '`s := "Go!"`' in r.stdout
    assert "71" not in r.stdout
    assert run(topic, "next").stdout == r.stdout  # 没评分时还是同一张
    assert "还没有 reveal" in run(topic, "answer", "3", ok=False).stderr
    r = run(topic, "reveal")
    assert "`71`。" in r.stdout
    assert "1 Again · " in r.stdout and "4 Easy · " in r.stdout
    assert "⁨" not in r.stdout
    r = run(topic, "answer", "2")
    assert "已记下 Hard。" in r.stdout
    with Col() as col:
        assert revlog(col, cid) == [2]  # 评分立即写入
    # 没有别的卡片时，learn-ahead 让刚评 Hard 的卡片马上回来，和 Anki 一样
    assert "Golang/C3/index-is-byte · learning" in r.stdout
    r = run(topic, "done")
    assert "本次复习 1 张：Again 0 · Hard 1 · Good 0 · Easy 0" in r.stdout
    with Col() as col:
        assert revlog(col, cid) == [2]
    assert not (topic.parent / "data" / "session.json").exists()


def test_cloze_review_shows_one_deletion(topic):
    run(topic, "sync", "--apply")
    cids = make_due("Golang/C3/rune-is-type")
    r = run(topic, "next")
    assert "Golang/C3/rune-is-type c1 · new" in r.stdout
    assert "rune 是表示一个 [...] 的 type，是 int32 的 alias。" in r.stdout
    r = run(topic, "reveal")
    assert "[code point]" in r.stdout and "UTF-32 是 encoding" in r.stdout
    r = run(topic, "answer", "4")
    assert "Golang/C3/rune-is-type c2" in r.stdout
    assert "[一个整数 type]" in r.stdout
    run(topic, "reveal")
    run(topic, "answer", "1")
    run(topic, "done")
    with Col() as col:
        assert [revlog(col, c) for c in cids] == [[4], [1]]


def test_undo_across_processes(topic):
    run(topic, "sync", "--apply")
    (cid,) = make_due("Golang/C3/index-is-byte")
    run(topic, "next")
    run(topic, "reveal")
    run(topic, "answer", "1")
    r = run(topic, "undo")
    assert "已撤销 Again，重新显示这张卡片。" in r.stdout
    assert "Golang/C3/index-is-byte · new" in r.stdout
    with Col() as col:
        assert revlog(col, cid) == []
        card = col.get_card(cid)
        assert (card.queue, card.reps, card.memory_state is None) == (0, 0, True)
    assert "没有可以撤销的评分" in run(topic, "undo", ok=False).stderr
    assert "还没有 reveal" in run(topic, "answer", "3", ok=False).stderr
    run(topic, "reveal")
    run(topic, "answer", "4")
    r = run(topic, "done")
    assert "本次复习 1 张：Again 0 · Hard 0 · Good 0 · Easy 1" in r.stdout
    with Col() as col:
        assert revlog(col, cid) == [4]


def test_undo_keeps_flag_and_stops_after_suspend(topic):
    run(topic, "sync", "--apply")
    (cid,) = make_due("Golang/C3/index-is-byte")
    run(topic, "next")
    run(topic, "reveal")
    run(topic, "answer", "3")
    run(topic, "flag", "2", "C3/index-is-byte")
    run(topic, "undo")
    with Col() as col:
        assert col.get_card(cid).user_flag() == 2
    run(topic, "reveal")
    run(topic, "answer", "3")
    run(topic, "suspend", "C3/index-is-byte")
    assert "没有可以撤销的评分" in run(topic, "undo", ok=False).stderr
    run(topic, "done")
    with Col() as col:
        assert revlog(col, cid) == [3]
        assert col.get_card(cid).queue == -1


def test_flag_bury_unsuspend(topic):
    run(topic, "sync", "--apply")
    make_due("Golang/C3/index-is-byte")
    run(topic, "next")
    assert "已设 flag 1：1 张卡片。" in run(topic, "flag", "1").stdout
    assert "Golang/C3/index-is-byte" in run(topic, "flagged").stdout
    r = run(topic, "bury")
    assert "已 bury 1 张卡片" in r.stdout
    assert "现在没有到期的卡片" in r.stdout
    r = run(topic, "done")
    assert "flagged 1 张" in r.stdout
    run(topic, "flag", "0", "C3/index-is-byte")
    assert "没有 flagged" in run(topic, "flagged").stdout
    run(topic, "unsuspend", "C3/rune-is-type")
    with Col() as col:
        assert all(c.queue == 0 for c in cards_of(col, "Golang/C3/rune-is-type"))


def test_leech_after_eight_lapses(topic):
    from anki.scheduler.v3 import CardAnswer
    run(topic, "sync", "--apply")
    (cid,) = make_due("Golang/C3/index-is-byte")

    def rate(col, rating):
        card = col.get_card(cid)
        card.start_timer()
        states = col._backend.get_scheduling_states(cid)
        col.sched.answer_card(col.sched.build_answer(card=card, states=states, rating=rating))

    with Col() as col:
        rate(col, CardAnswer.EASY)  # new → review
        for _ in range(7):
            col.sched.set_due_date([cid], "0")
            rate(col, CardAnswer.AGAIN)
        col.sched.set_due_date([cid], "0")
        assert col.get_card(cid).lapses == 7
    run(topic, "next")
    run(topic, "reveal")
    assert "成为 leech" in run(topic, "answer", "1").stdout
    run(topic, "undo")  # 撤销会去掉 leech tag
    with Col() as col:
        card = col.get_card(cid)
        assert card.lapses == 7 and "leech" not in card.note().tags
    run(topic, "reveal")
    assert "成为 leech" in run(topic, "answer", "1").stdout
    r = run(topic, "done")
    assert "需要维护：leech 1 张" in r.stdout
    assert "Golang/C3/index-is-byte  " in run(topic, "leeches").stdout
    r = run(topic, "card", "C3/index-is-byte")
    assert "lapses 8" in r.stdout and "leech" in r.stdout
    assert r.stdout.count("Again") == 8


def test_workspace_scope(topic):
    run(topic, "sync", "--apply")
    r = run(topic.parent, "counts")
    assert "[Learn::Golang] new 4" in r.stdout
    assert "卡片 4 张" in run(topic.parent, "stats").stdout
    assert "Golang/C3/len-counts-bytes" in run(topic.parent, "card", "Golang/C3/len-counts-bytes").stdout
