#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""progressive-learning: 检查 topic 文档的结构。

只查结构（标题、顺序、层数、编号、答案位置），不查内容讲得好不好。

用法：
  uv run check_topic.py <topic.md> [--reading]

--reading 表示阅读型知识点：定位之后必须有"阅读任务"。
通过时打印"通过"，退出码 0；不通过时逐条列出问题，退出码 1。

文档第一个二级标题之前的内容（如 frontmatter）不检查；
"## 课上补充"及其之后的内容（课上临时加的例子和题目）也不检查。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DIGITS = "一二三四五六七八九"
MIN_LAYERS, MAX_LAYERS = 2, 4
MAX_OPEN_QUESTIONS = 2

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
OPTION_RE = re.compile(r"^\s*(?:[-*]\s*)?\**([A-E])[.、．):：]\s*\S", re.MULTILINE)
ANSWER_LINE_RE = re.compile(r"^\s*\**(?:正确)?答案\**\s*[:：]", re.MULTILINE)
DIAGRAM_RE = re.compile(r"```mermaid|^\|.*\|\s*\n\|\s*:?-{3,}", re.MULTILINE)


def cn(n: int) -> str:
    """1 → 一，10 → 十，12 → 十二，20 → 二十。"""
    tens, ones = divmod(n, 10)
    head = "" if tens == 0 else ("十" if tens == 1 else DIGITS[tens - 1] + "十")
    return head + (DIGITS[ones - 1] if ones else "")


def sections(text: str, heading_re: re.Pattern) -> list[tuple[str, str]]:
    """按标题切分，返回 [(标题, 标题下的正文)]，第一个标题之前的内容丢弃。"""
    marks = list(heading_re.finditer(text))
    return [(m.group(1), text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)])
            for i, m in enumerate(marks)]


def check(text: str, reading: bool = False) -> list[str]:
    """返回问题列表；空列表表示通过。"""
    h2 = sections(text, H2_RE)
    h2 = h2[:next((i for i, (t, _) in enumerate(h2) if t.startswith("课上补充")), len(h2))]
    if len(h2) < 2 or not h2[-1][0].startswith("答案与解析"):
        return [("文档应该只有两个二级标题：开头的 `## <知识点标题>`，和文末的 `## 答案与解析`。"
                 f"现在的二级标题是：{[t for t, _ in h2]}")]
    if len(h2) > 2:
        return [f"正文里多了二级标题 {[t for t, _ in h2[1:-1]]}：模块一律用三级标题。"]
    body, key = sections(h2[0][1], H3_RE), sections(h2[1][1], H3_RE)
    titles = [t for t, _ in body]
    errors: list[str] = []

    # 正文的模块顺序：定位、[阅读任务]、知识，然后每层 [知识N]、例子N、两道题，最后 [延伸]、回到全景。
    expected_head = ["定位"] + (["阅读任务"] if reading else []) + ["知识"]
    if titles[:len(expected_head)] != expected_head:
        errors.append(f"文档开头的三级标题应该依次是 {expected_head}，现在是 {titles[:len(expected_head)]}。")
        return errors
    i, layers, questions = len(expected_head), 0, []
    while True:
        k = layers + 1
        if k >= 2 and i < len(titles) and re.fullmatch(rf"知识{cn(k)}：.+", titles[i]):
            i += 1
        if not (i < len(titles) and titles[i].startswith("例子")):
            break
        if not re.fullmatch(rf"例子{cn(k)}：.+", titles[i]):
            errors.append(f"「{titles[i]}」应该是「例子{cn(k)}：<标题>」：例子按层编号，冒号后写标题。")
            return errors
        for n in (2 * k - 1, 2 * k):
            if not (i + 1 < len(titles) and titles[i + 1] == f"问题{cn(n)}"):
                got = titles[i + 1] if i + 1 < len(titles) else "（文档结束）"
                errors.append(f"例子{cn(k)}这一层应该有问题{cn(2 * k - 1)}、问题{cn(2 * k)}两道题，"
                              f"第 {n - 2 * k + 2} 道的位置是「{got}」。每层正好一个例子、两道题，题号全文连续。")
                return errors
            i += 1
            questions.append((titles[i], body[i][1]))
        i += 1
        layers += 1
    if i < len(titles) and re.fullmatch(r"延伸：.+", titles[i]):
        i += 1
    if titles[i:] != ["回到全景"]:
        errors.append(f"最后一层之后应该是可选的「延伸：<标题>」，再是「回到全景」，然后进入答案与解析；"
                      f"现在是 {titles[i:] or '（什么也没有）'}。")
    if layers > MAX_LAYERS:
        errors.append(f"有 {layers} 层，超过 {MAX_LAYERS} 层：这个知识点太大，25 分钟学不完。"
                      "不要压缩层数凑数，回到第一步，告诉用户它太大在哪里、可以怎样拆。")
    elif layers < MIN_LAYERS:
        errors.append(f"只有 {layers} 层，每个知识点至少 {MIN_LAYERS} 层（每层一个例子、两道题）。")

    knowledge = body[expected_head.index("知识")][1]
    if not DIAGRAM_RE.search(knowledge):
        errors.append("「知识」里没有图或表：至少一张 mermaid 图或 Markdown 表格。")
    leaked = [t for t, s in body if ANSWER_LINE_RE.search(s) and t.startswith("问题")]
    if leaked:
        errors.append(f"{leaked} 的正文里出现了答案：答案只放在文末的答案与解析里。")
    open_qs = [t for t, s in questions if len(set(OPTION_RE.findall(s))) < 3]
    if len(open_qs) > MAX_OPEN_QUESTIONS:
        errors.append(f"{open_qs} 不是选择题（少于 3 个 A～E 选项）：开放式题目最多 {MAX_OPEN_QUESTIONS} 道。")

    want = [t for t, _ in questions]
    got = [t for t, _ in key]
    if got != want:
        errors.append(f"答案与解析的三级标题应该依次是 {want}，现在是 {got}。")
    empty = [t for t, s in key if not s.strip()]
    if empty:
        errors.append(f"答案与解析里 {empty} 是空的。")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--reading", action="store_true", help="阅读型知识点")
    args = ap.parse_args()
    errors = check(args.path.read_text(encoding="utf-8"), reading=args.reading)
    if not errors:
        print("通过")
        return 0
    for e in errors:
        print(f"✗ {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
