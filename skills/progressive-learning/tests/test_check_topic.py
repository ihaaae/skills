import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_topic.py"
spec = importlib.util.spec_from_file_location("check_topic", SCRIPT)
check_topic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_topic)
check = check_topic.check

OPTIONS = "\n\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"
DIAGRAM = "\n\n| 情况 | 结果 |\n|---|---|\n| x | y |\n"


def layer(k: int, knowledge: bool = False) -> str:
    q1, q2 = check_topic.cn(2 * k - 1), check_topic.cn(2 * k)
    head = f"### 知识{check_topic.cn(k)}：新机制\n\n内容\n\n" if knowledge else ""
    return (f"{head}### 例子{check_topic.cn(k)}：标题\n\n解答\n\n"
            f"### 问题{q1}\n\n题干{OPTIONS}\n### 问题{q2}\n\n题干{OPTIONS}\n")


def doc(layers: int = 2, reading: bool = False, extra: str = "", key: list[int] | None = None) -> str:
    body = "".join(layer(k, knowledge=k == 2) for k in range(1, layers + 1))
    nums = key if key is not None else list(range(1, 2 * layers + 1))
    answers = "".join(f"### 问题{check_topic.cn(n)}\n\n**C**。理由\n\n" for n in nums)
    task = "### 阅读任务\n\n读第 3 节\n\n" if reading else ""
    return (f"## T1：标题\n\n### 定位\n\n目标\n\n{task}### 知识\n\n主张{DIAGRAM}\n"
            f"{body}### 延伸：后话\n\n不考\n\n### 回到全景\n\n收尾\n\n{extra}## 答案与解析\n\n{answers}")


def test_cn():
    assert [check_topic.cn(n) for n in (1, 9, 10, 11, 20)] == ["一", "九", "十", "十一", "二十"]


@pytest.mark.parametrize("layers", [2, 3, 4])
def test_valid(layers):
    assert check(doc(layers)) == []


def test_reading():
    assert check(doc(reading=True), reading=True) == []
    assert "阅读任务" in check(doc(), reading=True)[0]


def test_one_layer():
    assert any("至少 2 层" in e for e in check(doc(1)))


def test_five_layers_is_too_big():
    assert any("太大" in e and "第一步" in e for e in check(doc(5)))


def test_three_questions_in_a_layer():
    text = doc().replace("### 知识二", "### 问题三\n\n题干" + OPTIONS + "\n### 知识二", 1)
    assert any("两道题" in e for e in check(text))


def test_numbering_does_not_restart():
    text = doc().replace("### 问题三", "### 问题一").replace("### 问题四", "### 问题二")
    assert any("问题三" in e for e in check(text))


def test_answer_leak():
    text = doc().replace("### 问题二\n\n题干", "### 问题二\n\n题干\n\n答案：C", 1)
    assert any("出现了答案" in e for e in check(text))


def test_key_must_cover_every_question():
    assert any("答案与解析" in e for e in check(doc(key=[1, 2, 3])))


def test_needs_diagram():
    assert any("图或表" in e for e in check(doc().replace(DIAGRAM, "\n")))


def test_too_many_open_questions():
    assert any("开放式" in e for e in check(doc().replace(OPTIONS, "\n")))


def test_preamble_and_class_additions_ignored():
    text = "---\nid: T1\n---\n\n" + doc() + "## 课上补充\n\n### 补充例子一：更简单的\n\n### 补充问题一\n"
    assert check(text) == []


def test_cli(tmp_path):
    good, bad = tmp_path / "good.md", tmp_path / "bad.md"
    good.write_text(doc())
    bad.write_text(doc(1))
    run = [sys.executable, str(SCRIPT)]
    assert subprocess.run(run + [str(good)], capture_output=True, text=True, check=False).stdout.strip() == "通过"
    assert subprocess.run(run + [str(bad)], capture_output=True, check=False).returncode == 1
