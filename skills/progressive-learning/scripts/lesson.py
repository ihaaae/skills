#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""progressive-learning: 按 topic 文档上课时的状态机。

脚本负责控制：判选择题对错、记住进度、决定这一轮发什么。
agent 负责内容：写问题解答、补充例子、补充问题，回答学习者的提问。

用法（每条命令都先给文档路径；进度存在文档旁边的 <文档>.progress.json）：
  lesson.py <文档> start                开始上课，打印第一轮
  lesson.py <文档> continue             学习者读完了这一轮的新内容
  lesson.py <文档> answer C             学习者答了选择题（开放题用 --correct yes|no）
  lesson.py <文档> supplement --key B   登记 agent 写的补充问题及其正确选项（开放题用 --open）
  lesson.py <文档> status               查看当前进度（例如 context 被压缩之后）

学习者提问、没有作答时，直接回答，不运行脚本，进度不变。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_topic import H2_RE, H3_RE, check, cn, sections

KEY_LETTER_RE = re.compile(r"^\s*\**([A-E])\**(?=[\s。.，,：:、]|$)")
STOP_READ = "停，等学习者读完。结尾用一句话收住，如\"读完有疑问就问，没问题就说继续\"。"
STOP_ANSWER = "停，等学习者回答。"
FINISH = ("课上完了。把课上写的补充例子、补充问题连同解析，补进文档末尾的 `## 课上补充`"
          "（放在答案与解析之后）。")


class LessonError(Exception):
    pass


# ---------------------------------------------------------------- 文档

def parse(text: str) -> dict:
    """把（已通过 check_topic 的）文档拆成上课要用的块。"""
    h2 = sections(text, H2_RE)
    body, key = sections(h2[0][1], H3_RE), dict(sections(h2[1][1], H3_RE))
    block = {t: f"### {t}\n{s.rstrip()}\n" for t, s in body}
    titles = [t for t, _ in body]
    layers = []
    for t in titles:
        if t.startswith("例子"):
            layers.append({"knowledge": None, "example": t, "questions": []})
        elif re.fullmatch(r"问题.+", t) and layers:
            layers[-1]["questions"].append(t)
    for t in titles:
        m = re.fullmatch(r"知识(.+?)：.+", t)
        if m:
            k = next(i for i in range(len(layers)) if cn(i + 1) == m.group(1))
            layers[k]["knowledge"] = t
    return {
        "block": block,
        "key": {t: s.strip() for t, s in key.items()},
        "reading": "阅读任务" in block,
        "layers": layers,
        "extension": next((t for t in titles if t.startswith("延伸：")), None),
    }


def load(doc: Path) -> dict:
    text = doc.read_text(encoding="utf-8")
    reading = bool(re.search(r"^###\s+阅读任务\s*$", text, re.MULTILINE))
    errors = check(text, reading=reading)
    if errors:
        raise LessonError("文档没有通过结构检查，先改好文档：\n" + "\n".join(f"✗ {e}" for e in errors))
    return parse(text)


def correct_letter(key_text: str) -> str | None:
    m = KEY_LETTER_RE.match(key_text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 状态

def state_path(doc: Path) -> Path:
    return doc.with_name(doc.name + ".progress.json")


def save(doc: Path, st: dict) -> None:
    state_path(doc).write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_state(doc: Path) -> dict:
    p = state_path(doc)
    if not p.exists():
        raise LessonError(f"还没开始上课（没有 {p.name}），先运行 start。")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 输出

def verbatim(d: dict, title: str) -> str:
    return f"照抄文档里的这一块：\n\n{d['block'][title]}"


def turn(*items: str, then: str) -> str:
    lines = ["这一轮发："]
    lines += [f"{i}. {item}" for i, item in enumerate(items, 1)]
    lines.append(f"然后：{then}")
    return "\n\n".join(lines)


def ask_question(d: dict, st: dict) -> str:
    """出这一层的下一道题：文档里还有就出文档的，出完了就让 agent 写补充问题。"""
    layer = d["layers"][st["layer"]]
    if st["next_q"] < len(layer["questions"]):
        title = layer["questions"][st["next_q"]]
        st["next_q"] += 1
        st["stage"] = "question"
        st["current"] = {"label": title, "key": correct_letter(d["key"][title]), "doc": True}
        return verbatim(d, title)
    st["supplements"] += 1
    st["stage"] = "await_supplement"
    n = cn(st["supplements"])
    return (f"你来写 `### 补充问题{n}`：和{layer['example'].split('：')[0]}同构，考同一个原理，不加新变量。"
            f"发出之前运行 `lesson.py <文档> supplement --key <正确选项>`（开放题用 --open）登记它。")


def advance(d: dict, st: dict) -> tuple[str, str]:
    """这一层已掌握：给下一层的第一块新内容，最后一层之后给延伸或回到全景。返回 (要发的内容, 然后)。"""
    st["layer"] += 1
    st["next_q"], st["recent"] = 0, []
    if st["layer"] < len(d["layers"]):
        layer = d["layers"][st["layer"]]
        if layer["knowledge"]:
            st["stage"] = "knowledge"
            return verbatim(d, layer["knowledge"]), STOP_READ
        st["stage"] = "example"
        return verbatim(d, layer["example"]), STOP_READ
    if d["extension"]:
        st["stage"] = "extension"
        return verbatim(d, d["extension"]), STOP_READ
    st["stage"] = "done"
    return verbatim(d, "回到全景"), FINISH


# ---------------------------------------------------------------- 命令

def cmd_start(d: dict) -> tuple[dict, str]:
    # 补充问题、补充例子在整份文档里各自连续编号，不随层重置
    st = {"layer": 0, "next_q": 0, "recent": [], "supplements": 0, "supplement_examples": 0,
          "current": None, "log": []}
    if d["reading"]:
        st["stage"] = "reading_task"
        return st, turn(verbatim(d, "定位"), verbatim(d, "阅读任务"), then="停，等学习者读完材料。")
    st["stage"] = "knowledge"
    return st, turn(verbatim(d, "定位"), verbatim(d, "知识"), then=STOP_READ)


def cmd_continue(d: dict, st: dict) -> str:
    stage = st["stage"]
    if stage == "reading_task":
        st["stage"] = "knowledge"
        return turn("回答学习者读材料时的疑问，只用知识基础和指定章节的内容（没有疑问就省略）。",
                    verbatim(d, "知识"), then=STOP_READ)
    if stage == "knowledge":
        st["stage"] = "example"
        return turn(verbatim(d, d["layers"][st["layer"]]["example"]), then=STOP_READ)
    if stage == "example":
        item = ask_question(d, st)
        return turn(item, then=STOP_ANSWER if st["stage"] == "question" else "登记后发出这道题，" + STOP_ANSWER)
    if stage == "extension":
        st["stage"] = "done"
        return turn(verbatim(d, "回到全景"), then=FINISH)
    if stage == "done":
        raise LessonError(FINISH)
    raise LessonError(f"现在不该用 continue（当前在等：{WAITING[stage]}）。学习者提问的话，直接回答，不用运行脚本。")


def cmd_answer(d: dict, st: dict, letter: str | None, correct: str | None) -> str:
    if st["stage"] != "question":
        raise LessonError(f"现在没有在等回答（当前在等：{WAITING[st['stage']]}）。")
    cur = st["current"]
    if cur["key"] is None:
        if correct is None:
            raise LessonError(f"{cur['label']} 不是选择题，由你判断对错，用 --correct yes|no 告诉脚本。")
        right = correct == "yes"
        verdict = "答对" if right else "答错"
    else:
        if letter is None:
            raise LessonError(f"{cur['label']} 是选择题，给出学习者选的字母，如 `answer C`。")
        right = letter.upper() == cur["key"]
        verdict = f"{'答对' if right else '答错'}（学习者选 {letter.upper()}，正确答案 {cur['key']}）"
    st["recent"].append(right)
    st["log"].append({"layer": st["layer"] + 1, "question": cur["label"], "right": right})

    label = cur["label"]
    feedback = (f"`### {label.replace('问题', '问题解答', 1)}`：你来写。先判断对错，"
                + ("简短点明学习者用对了哪条规律。" if right else
                   "按例子示范的思路逐步对照，点出所选选项错在哪一步，再回到最接近的例子。"))
    source = f"判定：{verdict}"
    if cur["doc"]:
        source += f"\n\n写问题解答的素材（答案与解析 · {label}）：\n\n{d['key'][label]}"

    layer = d["layers"][st["layer"]]
    if st["recent"][-2:] == [True, True]:
        item, then = advance(d, st)
        return source + "\n\n" + turn(feedback, item, then=then)
    if st["next_q"] < len(layer["questions"]):
        return source + "\n\n" + turn(feedback, ask_question(d, st), then=STOP_ANSWER)
    if not right:
        st["stage"] = "example"
        st["supplement_examples"] += 1
        n = cn(st["supplement_examples"])
        item = (f"你来写 `### 补充例子{n}：<标题>`：比{layer['example'].split('：')[0]}更简单或更接近它，"
                "针对这道题暴露出的误区重讲，同样写成题目 + 解答，末尾给判断方法。这一轮不出题。")
        return source + "\n\n" + turn(feedback, item, then=STOP_READ)
    item = ask_question(d, st)
    return source + "\n\n" + turn(feedback, item, then="登记后发出这道题，" + STOP_ANSWER)


def cmd_supplement(st: dict, key: str | None, open_q: bool) -> str:
    if st["stage"] != "await_supplement":
        raise LessonError(f"现在不需要补充问题（当前在等：{WAITING[st['stage']]}）。")
    if (key is None) == (not open_q):
        raise LessonError("给出补充问题的正确选项 `--key B`，或者用 `--open` 表示开放题。")
    label = f"补充问题{cn(st['supplements'])}"
    st["stage"] = "question"
    st["current"] = {"label": label, "key": key.upper() if key else None, "doc": False}
    return f"已登记 {label}。把它发给学习者，然后：{STOP_ANSWER}"


WAITING = {
    "reading_task": "学习者读完材料（continue）",
    "knowledge": "学习者读完知识（continue）",
    "example": "学习者读完例子（continue）",
    "question": "学习者回答（answer）",
    "await_supplement": "你写好补充问题并登记（supplement）",
    "extension": "学习者读完延伸（continue）",
    "done": "无，课已上完",
}


def cmd_status(d: dict, st: dict) -> str:
    lines = [f"第 {st['layer'] + 1} 层（共 {len(d['layers'])} 层）" if st["layer"] < len(d["layers"])
             else "所有层都已掌握",
             f"当前在等：{WAITING[st['stage']]}"]
    if st["stage"] == "question":
        lines.append(f"等回答的题：{st['current']['label']}")
    if st["recent"]:
        lines.append("这一层的作答：" + " ".join("✓" if r else "✗" for r in st["recent"]))
    return "\n".join(lines)


def run(doc: Path, command: str, letter: str | None = None, correct: str | None = None,
        key: str | None = None, open_q: bool = False) -> str:
    d = load(doc)
    if command == "start":
        st, out = cmd_start(d)
    else:
        st = read_state(doc)
        if command == "continue":
            out = cmd_continue(d, st)
        elif command == "answer":
            out = cmd_answer(d, st, letter, correct)
        elif command == "supplement":
            out = cmd_supplement(st, key, open_q)
        elif command == "status":
            return cmd_status(d, st)
        else:
            raise LessonError(f"未知命令 {command}")
    save(doc, st)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc", type=Path)
    ap.add_argument("command", choices=["start", "continue", "answer", "supplement", "status"])
    ap.add_argument("letter", nargs="?", help="answer：学习者选的字母")
    ap.add_argument("--correct", choices=["yes", "no"], help="answer：开放题由 agent 判断的对错")
    ap.add_argument("--key", help="supplement：补充问题的正确选项")
    ap.add_argument("--open", action="store_true", help="supplement：补充问题是开放题")
    args = ap.parse_args()
    try:
        print(run(args.doc, args.command, args.letter, args.correct, args.key, args.open))
    except LessonError as e:
        print(f"✗ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
