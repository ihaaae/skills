#!/usr/bin/env python3
"""book-graph: 检查"书 → 节点"映射表（book-map.md）。

只用标准库。书是 epub-to-markdown 转出的单个 Markdown 文件，行号指该文件。

映射表里的一行是 Markdown 表格行，前两列是：
  | <节点 ID> <标题> | <行号范围，如 1758–2184, 2516–2655> | …其余列随意…
  | — <说明>        | <行号范围或"小节名 771–849"> | …
第一列以节点 ID（大写字母 + 数字）开头的是节点行；以 "—" 开头的是非节点行（non-goal 等），
同样计入覆盖。范围用 "–" 或 "-" 连接。

用法：
  bookmap.py check BOOK MAP [--from N] [--to N] [--ignore REGEX]
      覆盖检查：[from, to] 内每个 2–4 级标题恰好被一行覆盖。--ignore 匹配的标题（如每章的
      Exercises、Wrapping Up）跳过。有问题时退出码为 1。
  bookmap.py stats BOOK MAP [--big 170] [--small 60]
      每个节点行的正文行数（不含代码块、标题、空行）和代码行数；正文 ≥ big 标 <<（检查是否该拆），
      ≤ small 标 >>（检查是否该并）。
  bookmap.py refs BOOK MAP
      每个节点行里指向书内其他位置的链接 [](#anchor)：指向前文的是前置候选，指向后文的是前向引用。
"""
from __future__ import annotations

import argparse
import re
import sys

HEAD_RE = re.compile(r"^(#{1,6}) (.*)")
ROW_RE = re.compile(r"^\|\s*(\S+)[^|]*\|([^|]*)\|")
ID_RE = re.compile(r"^[A-Z]+\d+$")
RANGE_RE = re.compile(r"(\d+)\s*[–-]\s*(\d+)")
LINK_RE = re.compile(r"\]\(#([^)]+)\)")


def read_book(path):
    """返回 (lines, in_code)；in_code[i] 为 True 表示第 i 行（1 起）在代码块里或是围栏行。"""
    lines = open(path, encoding="utf-8").read().split("\n")
    in_code = [False] * (len(lines) + 1)
    fence = False
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code[i] = True
            fence = not fence
        else:
            in_code[i] = fence
    # 跳过 YAML front matter
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            in_code[i] = True
            if lines[i] == "---":
                in_code[i + 1] = True
                break
    return lines, in_code


def headings(lines, in_code, lo=2, hi=4):
    out = []
    for i, line in enumerate(lines, 1):
        m = HEAD_RE.match(line)
        if m and not in_code[i] and lo <= len(m.group(1)) <= hi:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def read_map(path):
    """返回 [(key, is_node, [(a, b), ...])]。"""
    rows = []
    for line in open(path, encoding="utf-8"):
        m = ROW_RE.match(line)
        if not m:
            continue
        key, cell = m.group(1), m.group(2)
        is_node = bool(ID_RE.match(key))
        if not is_node and key != "—":
            continue
        ranges = [(int(a), int(b)) for a, b in RANGE_RE.findall(cell)]
        rows.append((key if is_node else "—", is_node, ranges))
    return rows


def slug(title):
    t = re.sub(r"[`*]", "", title.lower().strip())
    t = re.sub(r"\s+", "-", t)
    return re.sub(r"[^\w\-’—]", "", t)


def cmd_check(a):
    lines, in_code = read_book(a.book)
    rows = read_map(a.map)
    problems = []
    cover = {}
    for key, _, ranges in rows:
        if not ranges:
            problems.append(f"行 {key} 没有行号范围")
        for lo, hi in ranges:
            if lo > hi or hi > len(lines):
                problems.append(f"行 {key} 的范围 {lo}–{hi} 无效（书共 {len(lines)} 行）")
            for i in range(lo, hi + 1):
                cover.setdefault(i, []).append(key)
    ign = re.compile(a.ignore) if a.ignore else None
    lo, hi = a.from_ or 1, a.to or len(lines)
    for i, _, title in headings(lines, in_code):
        if not lo <= i <= hi or (ign and ign.search(title)):
            continue
        owners = cover.get(i, [])
        if not owners:
            problems.append(f"未覆盖：{i}: {title}")
        elif len(owners) > 1:
            problems.append(f"重复覆盖：{i}: {title} ← {', '.join(owners)}")
    ids = [k for k, n, _ in rows if n]
    dup = sorted({k for k in ids if ids.count(k) > 1})
    if dup:
        problems.append(f"重复的节点 ID：{', '.join(dup)}")
    for p in problems:
        print(p)
    print(f"{len(ids)} 个节点行，{len(rows) - len(ids)} 个非节点行；"
          + ("覆盖完整" if not problems else f"{len(problems)} 个问题"))
    return 1 if problems else 0


def cmd_stats(a):
    lines, in_code = read_book(a.book)
    for key, is_node, ranges in read_map(a.map):
        if not is_node:
            continue
        idx = [i for lo, hi in ranges for i in range(lo, hi + 1) if i <= len(lines)]
        code = sum(1 for i in idx if in_code[i])
        prose = sum(1 for i in idx if not in_code[i] and lines[i - 1].strip()
                    and not HEAD_RE.match(lines[i - 1]))
        flag = " <<" if prose >= a.big else (" >>" if prose <= a.small else "")
        print(f"{key:5} prose={prose:4} code={code:4}{flag}")
    return 0


def cmd_refs(a):
    lines, in_code = read_book(a.book)
    anchors = {}
    for i, _, title in headings(lines, in_code, 1, 6):
        anchors.setdefault(slug(title), i)
    rows = [(k, r) for k, n, r in read_map(a.map) if n]

    def owner(line):
        for k, ranges in rows:
            if any(lo <= line <= hi for lo, hi in ranges):
                return k
        return None

    for key, ranges in rows:
        back, fwd, unknown = set(), set(), set()
        for lo, hi in ranges:
            for i in range(lo, hi + 1):
                for anc in LINK_RE.findall(lines[i - 1]):
                    target = anchors.get(anc)
                    if target is None:
                        unknown.add(anc)
                        continue
                    o = owner(target)
                    if o and o != key:
                        (back if target < lo else fwd).add(o)
        out = f"{key:5} 前置候选={sorted(back)} 前向引用={sorted(fwd)}"
        if unknown:
            out += f" 未解析={sorted(unknown)[:3]}"
        print(out)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "stats", "refs"):
        s = sub.add_parser(name)
        s.add_argument("book")
        s.add_argument("map")
        if name == "check":
            s.add_argument("--from", dest="from_", type=int)
            s.add_argument("--to", type=int)
            s.add_argument("--ignore")
        if name == "stats":
            s.add_argument("--big", type=int, default=170)
            s.add_argument("--small", type=int, default=60)
    a = p.parse_args(argv)
    return {"check": cmd_check, "stats": cmd_stats, "refs": cmd_refs}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
