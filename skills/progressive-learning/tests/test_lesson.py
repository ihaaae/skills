import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_check_topic import doc

SCRIPT = Path(__file__).parent.parent / "scripts" / "lesson.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("lesson", SCRIPT)
lesson = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lesson)


@pytest.fixture
def topic(tmp_path):
    def make(text=None):
        p = tmp_path / "T1.md"
        p.write_text(text if text is not None else doc())
        return p
    return make


def step(path, command, *args, **kw):
    return lesson.run(path, command, *args, **kw)


def now(out):
    """这一轮要发的部分，不含预先给出的后续几轮。"""
    return out.split("—— 预先给出")[0]


def state(path):
    return json.loads(lesson.state_path(path).read_text())


def test_happy_path(topic):
    p = topic()   # 两层，第二层有知识二，有延伸；所有题的正确答案都是 C
    assert "### 定位" in step(p, "start") and "### 知识\n" in step(p, "start")
    assert "### 例子一" in step(p, "continue")
    assert "### 问题一" in step(p, "continue")
    out = step(p, "answer", "c")
    assert "答对" in out and "### 问题解答一" in out and "### 问题二" in out
    out = step(p, "answer", "C")
    assert "### 问题解答二" in out and "### 知识二" in out and "### 例子二" not in now(out)
    assert "### 例子二" in step(p, "continue")
    assert "### 问题三" in step(p, "continue")
    step(p, "answer", "C")
    assert "### 延伸" in step(p, "answer", "C")
    out = step(p, "continue")
    assert "### 回到全景" in out and "课上补充" in out
    assert state(p)["stage"] == "done"
    with pytest.raises(lesson.LessonError):
        step(p, "continue")


def test_second_wrong_reexplains_then_supplements(topic):
    p = topic()
    for c in ("start", "continue", "continue"):
        step(p, c)
    step(p, "answer", "C")
    out = step(p, "answer", "A")
    assert "答错" in out and "正确答案 C" in out
    assert "补充例子一" in out and "### 知识二" not in out
    assert "补充问题一" in step(p, "continue")
    with pytest.raises(lesson.LessonError):
        step(p, "answer", "B")   # 还没登记补充问题
    step(p, "supplement", key="b")
    out = step(p, "answer", "B")   # ✓ ✗ ✓：最近两道不是都对
    assert "补充问题二" in out and "### 知识二" not in out
    step(p, "supplement", key="A")
    assert "### 知识二" in step(p, "answer", "A")


def test_first_wrong_second_right_needs_one_more(topic):
    p = topic()
    for c in ("start", "continue", "continue"):
        step(p, c)
    assert "### 问题二" in step(p, "answer", "A")
    out = step(p, "answer", "C")
    assert "补充问题一" in out and "补充例子" not in out


def test_reading(topic):
    p = topic(doc(reading=True))
    out = step(p, "start")
    assert "### 阅读任务" in out and "### 知识\n" not in out
    out = step(p, "continue")
    assert "疑问" in out and "### 知识\n" in out


def test_open_question(topic):
    p = topic(doc().replace("### 问题一\n\n**C**。", "### 问题一\n\n要点：", 1))
    for c in ("start", "continue", "continue"):
        step(p, c)
    with pytest.raises(lesson.LessonError, match="--correct"):
        step(p, "answer", "C")
    assert "答对" in step(p, "answer", correct="yes")


def test_waiting_for_answer(topic):
    p = topic()
    for c in ("start", "continue", "continue"):
        step(p, c)
    with pytest.raises(lesson.LessonError, match="直接回答"):
        step(p, "continue")
    assert "等回答的题：问题一" in step(p, "status")


def test_refuses_broken_doc(topic):
    with pytest.raises(lesson.LessonError, match="结构检查"):
        step(topic(doc(1)), "start")


def test_needs_start(topic):
    with pytest.raises(lesson.LessonError, match="start"):
        step(topic(), "continue")


def test_lookahead_covers_continues_until_next_question(topic):
    p = topic()
    out = step(p, "start")
    head, ahead = out.split("—— 预先给出")
    assert "### 知识\n" in head and "### 例子一" not in head
    assert ahead.index("### 例子一") < ahead.index("### 问题一")
    assert "### 问题二" not in ahead
    st = state(p)   # 进度已记到等回答问题一
    assert st["stage"] == "question" and st["current"]["label"] == "问题一"
    assert len(st["pending"]) == 2
    assert "### 问题二" in step(p, "answer", "C")   # 不运行 continue 也能直接作答


def test_lookahead_after_layer_and_extension(topic):
    p = topic()
    step(p, "start")
    step(p, "answer", "C")
    out = step(p, "answer", "C")
    assert "### 知识二" in now(out)
    assert "### 例子二" in out and "### 问题三" in out
    step(p, "answer", "C")
    out = step(p, "answer", "C")
    assert "### 延伸" in now(out) and "### 回到全景" in out
    assert state(p)["stage"] == "done"


@pytest.mark.parametrize("key, letter", [
    ("**C**。解析", "C"),
    ("**C**（`Ann Bob Ann`）。照判断方法", "C"),   # F3 问题二：字母后紧跟全角括号
    ("B (prints 5)", "B"),
    ("C", "C"),
    ("Cat 不是答案", None),
    ("开放题，看学习者的解释", None),
])
def test_correct_letter(key, letter):
    assert lesson.correct_letter(key) == letter
