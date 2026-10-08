#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""topic-graph: 学习图谱的计算器。

图谱的"事实"只有两类：每个节点的前置关系，和每个节点的掌握状态(new/taught/mastered/retired)。
🔓/🔒、前沿、待复测、下一步推荐全部由本脚本从这两类事实算出，不手工维护。

用法（在专题目录内运行，或用 --root 指定含 topic.yaml 的目录）：
  uv run graph.py <命令>     # 依赖由脚本头的 PEP 723 声明，uv 自动准备
  graph.py check                校验图谱；有错误时退出码为 1
  graph.py next [-n 5] [--json] 计算下一步学什么
  graph.py preflight ID         开讲前自查：节点是否可讲、允许引用哪些概念
  graph.py show ID              查看节点及其直接前置的摘要
  graph.py set ID STATUS        更新状态 (new|taught|mastered) [--caveat 文本]
  graph.py add ID --title T --prereq A,B [--target X,Y]
  graph.py retire ID --into ID2 把节点标为废止
  graph.py sync                 校验并重新生成 STATE.md

依赖：pyyaml（由 uv 自动安装）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STATUSES = ("new", "taught", "mastered", "retired")
ICON = {"mastered": "✅", "taught": "📝", "unlockable": "🔓", "locked": "🔒", "retired": "🗑"}
ID_RE = re.compile(r"^([A-Z]+)(\d+)$")
FM_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
# 正文里标"这里没讲"的行：其中提到的未学节点是边界标注，不是前向引用
BOUNDARY_MARK = re.compile(r"未讲|没讲|没测|边界")


# ───────────────────────── 数据模型 ─────────────────────────

@dataclass
class Node:
    id: str
    title: str
    group: str
    prereqs: list[str]
    targets: list[str]
    status: str
    caveat: str
    merged_into: str
    updated: str
    body: str
    path: Path
    verified: str = ""   # 最近一次验证为 ✅ 的日期（复习排期用）

    @property
    def num(self) -> int:
        return int(ID_RE.match(self.id).group(2))


@dataclass
class Graph:
    root: Path
    config: dict
    nodes: dict[str, Node]
    group_titles: dict[str, str]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)

    def rhythm(self, key: str, default: int) -> int:
        return int((self.config.get("rhythm") or {}).get(key, default))

    # ---- 复习：✅ 会被遗忘 ----
    def review_due(self, today: dt.date | None = None) -> list[tuple[str, int, int]]:
        """(id, 距上次验证天数, 后代数)：久未验证、又有后续节点依赖的 ✅，依赖多、隔得久的在前。"""
        today = today or dt.date.today()
        after = self.rhythm("review_after_days", 14)
        out = []
        for i, n in self.live().items():
            if n.status != "mastered" or not n.verified:
                continue
            try:
                age = (today - dt.date.fromisoformat(n.verified[:10])).days
            except ValueError:
                continue
            desc = len(self.descendants(i))
            if age >= after and desc:
                out.append((i, age, desc))
        return sorted(out, key=lambda r: (-r[2], -r[1], r[0]))

    # ---- retro：外循环（目标与学法是否还对） ----
    def last_retro(self) -> dt.date | None:
        f = self.root / "retro.md"
        if not f.exists():
            return None
        dates = re.findall(r"^##\s+(\d{4}-\d{2}-\d{2})", f.read_text(encoding="utf-8"), re.MULTILINE)
        return max(dt.date.fromisoformat(d) for d in dates) if dates else None

    def retro_reasons(self, today: dt.date | None = None) -> list[str]:
        today = today or dt.date.today()
        last = self.last_retro()
        since = [e for e in self.log if last is None or dt.date.fromisoformat(e["ts"][:10]) > last]
        why = []
        if self.log:
            gap = (today - dt.date.fromisoformat(self.log[-1]["ts"][:10])).days
            if gap >= self.rhythm("retro_gap_days", 7):
                why.append(f"距上次学习已 {gap} 天")
        if len(since) >= self.rhythm("retro_every_changes", 12):
            why.append(f"{'从未做过 retro，' if last is None else '上次 retro 后'}已有 {len(since)} 次状态变化")
        demoted = [e["id"] for e in since if e.get("from") == "mastered" and e.get("to") != "mastered"]
        if len(demoted) >= 2:
            why.append(f"{'至今' if last is None else '上次 retro 后'} {len(demoted)} 个 ✅ 被降级（{', '.join(demoted)}），掌握可能不牢")
        done_ids = {e["id"] for e in since if e.get("to") == "mastered"}
        for grp in sorted({n.group for n in self.live().values()}):
            members = [i for i, n in self.live().items() if n.group == grp]
            if all(self.nodes[i].status == "mastered" for i in members) and done_ids & set(members):
                why.append(f"{grp} 组刚全部学完")
        return why

    # ---- 派生量 ----
    def live(self) -> dict[str, Node]:
        return {i: n for i, n in self.nodes.items() if n.status != "retired"}

    def derived(self, nid: str) -> str:
        n = self.nodes[nid]
        if n.status in ("mastered", "retired"):
            return n.status
        ok = all(self.nodes[p].status == "mastered" for p in n.prereqs if p in self.nodes)
        if n.status == "taught":
            return "taught"  # 已讲未验证；是否可复测见 retest_due
        return "unlockable" if ok else "locked"

    def prereqs_ok(self, nid: str) -> bool:
        return all(p in self.nodes and self.nodes[p].status == "mastered" for p in self.nodes[nid].prereqs)

    def children(self) -> dict[str, list[str]]:
        ch: dict[str, list[str]] = defaultdict(list)
        for i, n in self.live().items():
            for p in n.prereqs:
                ch[p].append(i)
        return ch

    def ancestors(self, nid: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.nodes[nid].prereqs)
        while stack:
            p = stack.pop()
            if p in seen or p not in self.nodes:
                continue
            seen.add(p)
            stack.extend(self.nodes[p].prereqs)
        return seen

    def descendants(self, nid: str) -> set[str]:
        ch = self.children()
        seen: set[str] = set()
        stack = list(ch.get(nid, []))
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(ch.get(c, []))
        return seen

    def frontier(self) -> list[str]:
        return [i for i in self.live() if self.derived(i) == "unlockable"]

    def retest_due(self) -> list[str]:
        return [i for i, n in self.live().items() if n.status == "taught" and self.prereqs_ok(i)]

    def goal_path(self) -> set[str]:
        s: set[str] = set()
        for g in self.config.get("goal", []):
            for t in g.get("targets", []):
                if t in self.nodes:
                    s.add(t)
                    s |= self.ancestors(t)
        return s

    def goal_routes(self, nid: str) -> list[tuple[dict, list[str]]]:
        """每个用到 nid 的目标，给出一条 nid → … → 终点 的最短依赖链（回答"学它有什么用"）。"""
        ch = self.children()
        out = []
        for g in self.config.get("goal", []):
            best: list[str] | None = None
            for t in g.get("targets", []):
                if t not in self.nodes or (t != nid and nid not in self.ancestors(t)):
                    continue
                allowed = self.ancestors(t) | {t}
                prev: dict[str, str | None] = {nid: None}
                queue = [nid]
                while queue and t not in prev:
                    u = queue.pop(0)
                    for c in sorted(ch.get(u, [])):
                        if c in allowed and c not in prev:
                            prev[c] = u
                            queue.append(c)
                if t in prev:
                    chain, cur = [], t
                    while cur is not None:
                        chain.append(cur)
                        cur = prev[cur]
                    chain.reverse()
                    if best is None or len(chain) < len(best):
                        best = chain
            if best:
                out.append((g, best))
        return out


# ───────────────────────── 读写 ─────────────────────────

def find_root(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not (p / "topic.yaml").exists():
            sys.exit(f"{p} 下没有 topic.yaml")
        return p
    p = Path.cwd().resolve()
    for d in [p, *p.parents]:
        if (d / "topic.yaml").exists():
            return d
    sys.exit("找不到 topic.yaml：请在专题目录内运行，或用 --root 指定。")


def parse_file(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        raise ValueError(f"{path}: 缺少 --- YAML 头")
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()


def load(root: Path) -> Graph:
    config = yaml.safe_load((root / "topic.yaml").read_text(encoding="utf-8"))
    g = Graph(root=root, config=config, nodes={}, group_titles={})
    nodes_dir = root / "nodes"
    # A brand-new topic has no nodes/ yet; `add` creates it.
    gdirs = sorted(p for p in nodes_dir.iterdir() if p.is_dir()) if nodes_dir.is_dir() else []
    for gdir in gdirs:
        gf = gdir / "_group.md"
        if gf.exists():
            meta, _ = parse_file(gf)
            g.group_titles[gdir.name] = meta.get("title", gdir.name)
        for f in sorted(gdir.glob("*.md")):
            if f.name == "_group.md":
                continue
            try:
                meta, body = parse_file(f)
            except Exception as e:  # noqa: BLE001
                g.errors.append(str(e))
                continue
            nid = meta.get("id", "")
            if nid in g.nodes:
                g.errors.append(f"重复的节点 ID：{nid}（{f} 与 {g.nodes[nid].path}）")
                continue
            g.nodes[nid] = Node(
                id=nid,
                title=meta.get("title", ""),
                group=gdir.name,
                prereqs=list(meta.get("prereqs", [])),
                targets=list(meta.get("targets", [])),
                status=meta.get("status", "new"),
                caveat=meta.get("caveat", ""),
                merged_into=meta.get("merged_into", ""),
                updated=str(meta.get("updated", "")),
                body=body,
                path=f,
                verified=str(meta.get("verified", "")),
            )
    logf = root / "log.jsonl"
    if logf.exists():
        g.log = [json.loads(line) for line in logf.read_text(encoding="utf-8").splitlines() if line.strip()]
    # 没写 verified 的旧节点：取日志里最后一次变为 mastered 的日期，再退回 updated
    last_ok = {e["id"]: e["ts"][:10] for e in g.log if e.get("to") == "mastered"}
    for n in g.nodes.values():
        if not n.verified and n.status == "mastered":
            n.verified = last_ok.get(n.id, n.updated)
    return g


def set_fm_field(path: Path, key: str, value: str | None) -> None:
    """就地修改（或新增/删除）头部的一个字符串字段；不动正文。"""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    head, body = m.group(1), m.group(2)
    lines = head.split("\n")
    pat = re.compile(rf"^{re.escape(key)}\s*:")
    idx = next((i for i, l in enumerate(lines) if pat.match(l)), None)
    if value is None:
        if idx is not None:
            del lines[idx]
    else:
        new = f"{key}: {value}"
        if idx is None:
            lines.append(new)
        else:
            lines[idx] = new
    sep = "\n" if not body.startswith("\n") else ""
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + sep + body, encoding="utf-8")


def q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


# ───────────────────────── 校验 ─────────────────────────

def validate(g: Graph) -> None:
    ids = set(g.nodes)
    for i, n in g.nodes.items():
        m = ID_RE.match(i)
        if not m:
            g.errors.append(f"{i}: ID 格式应为 大写字母+数字")
            continue
        if m.group(1) != n.group:
            g.errors.append(f"{i}: 位于目录 {n.group}/，但 ID 的组字母是 {m.group(1)}")
        if n.path.stem != i:
            g.errors.append(f"{i}: 文件名 {n.path.name} 与 ID 不一致")
        if n.status not in STATUSES:
            g.errors.append(f"{i}: 未知状态 {n.status!r}（应为 {'/'.join(STATUSES)}）")
        if not n.title:
            g.errors.append(f"{i}: 缺少 title")
        if n.status == "retired" and not n.merged_into:
            g.warnings.append(f"{i}: 已废止但没写 merged_into")
        if n.status == "retired":
            continue
        for p in n.prereqs:
            if p not in ids:
                g.errors.append(f"{i}: 前置 {p} 不存在")
            elif g.nodes[p].status == "retired":
                g.errors.append(f"{i}: 前置 {p} 已废止，请改指向 {g.nodes[p].merged_into or '替代节点'}")
        for t in n.targets:
            if t not in ids:
                g.errors.append(f"{i}: target {t} 不存在")
        if n.status == "mastered" and not g.prereqs_ok(i):
            bad = [p for p in n.prereqs if p in ids and g.nodes[p].status != "mastered"]
            g.errors.append(f"{i}: 标了 mastered，但前置 {', '.join(bad)} 不是 mastered（状态不可能成立）")
        if n.status in ("mastered", "taught") and not n.body.strip():
            g.warnings.append(f"{i}: {n.status} 节点没有正文摘要（下个会话无法据此一致地教学）")
    # 环检测
    color: dict[str, int] = {}

    def dfs(u: str, stack: list[str]) -> None:
        color[u] = 1
        for p in g.nodes[u].prereqs:
            if p not in ids:
                continue
            if color.get(p) == 1:
                cyc = stack[stack.index(p):] + [p] if p in stack else [u, p]
                g.errors.append("依赖环：" + " → ".join(cyc))
            elif p not in color:
                dfs(p, stack + [p])
        color[u] = 2

    for i in ids:
        if i not in color:
            dfs(i, [i])
    # goal 目标
    for goal in g.config.get("goal", []):
        for t in goal.get("targets", []):
            if t not in ids:
                g.errors.append(f"goal {goal.get('id')}: target {t} 不存在")
    for grp in g.config.get("track", {}).get("main", []):
        if grp not in g.group_titles and not any(n.group == grp for n in g.nodes.values()):
            g.warnings.append(f"topic.yaml 的 track.main 含未知组 {grp}")
    # 原文里提到的、尚不是 mastered 的节点：只对 mastered 节点的正文检查前向引用。
    # 已交代的不报：只出现在边界标注行里，或 debts.md 有一行同时提到这两个节点。
    debts = g.root / "debts.md"
    debt_lines = debts.read_text(encoding="utf-8").splitlines() if debts.exists() else []

    def mentions(line: str, nid: str) -> bool:
        return re.search(rf"\b{nid}\b(?!-\d)", line) is not None

    def accounted(i: str, ref: str, body: str) -> bool:
        if all(BOUNDARY_MARK.search(ln) for ln in body.splitlines() if mentions(ln, ref)):
            return True
        return any(mentions(ln, i) and mentions(ln, ref) for ln in debt_lines)

    for i, n in g.live().items():
        if n.status != "mastered" or n.caveat:  # 带限定的节点，缺口已在限定里交代
            continue
        # 反引号里的是材料里的名字（如 layer 名 `L3`），后接 -数字 的是编号（如验收项 P1-3），都不算节点
        text = re.sub(r"`[^`\n]*`", "", n.body)
        for ref in set(re.findall(r"\b([A-Z]\d{1,2})\b(?!-\d)", text)):
            if ref in g.nodes and ref != i and g.nodes[ref].status != "mastered" and ref not in n.prereqs \
                    and not accounted(i, ref, text):
                g.warnings.append(
                    f"{i}: 摘要提到 {ref}（{g.nodes[ref].status}）——若是前向引用，请确认已记为债务"
                )


# ───────────────────────── 推荐 ─────────────────────────

def rank(g: Graph) -> list[dict]:
    main = g.config.get("track", {}).get("main", [])
    gp = g.goal_path()
    order = {grp: k for k, grp in enumerate(main)}
    ch = g.children()
    rows = []
    for nid in g.retest_due() + g.frontier():
        n = g.nodes[nid]
        retest = n.status == "taught"
        desc = {d for d in g.descendants(nid) if g.nodes[d].status != "mastered"}
        direct = [c for c in ch.get(nid, []) if g.nodes[c].status == "new"
                  and all(g.nodes[p].status == "mastered" or p == nid for p in g.nodes[c].prereqs)]
        in_main = n.group in main
        on_goal = nid in gp
        reasons = []
        if retest:
            reasons.append("已讲未验证，前置齐全，可直接复测")
        if in_main:
            reasons.append("主线")
        if on_goal:
            reasons.append("在目标路径上")
        else:
            reasons.append("不在目标路径上（换口味）" if not retest else "")
        reasons.append(f"其后共 {len(desc)} 个节点依赖它；学完立刻解锁 {len(direct)} 个"
                       + (f"（{', '.join(sorted(direct, key=lambda x: (g.nodes[x].group, g.nodes[x].num)))}）" if direct else ""))
        rows.append({
            "id": nid, "title": n.title, "kind": "retest" if retest else "learn",
            "main": in_main, "on_goal": on_goal, "descendants": len(desc),
            "unlocks_now": sorted(direct), "why": "；".join(r for r in reasons if r),
            "_key": (0 if retest else 1, 0 if in_main else 1, 0 if on_goal else 1,
                     -len(desc), order.get(n.group, 99), n.group, n.num),
        })
    rows.sort(key=lambda r: r["_key"])
    for r in rows:
        del r["_key"]
    return rows


# ───────────────────────── 命令 ─────────────────────────

def cmd_check(g: Graph, _a) -> int:
    validate(g)
    live = g.live()
    cnt = defaultdict(int)
    for i in live:
        cnt[g.derived(i)] += 1
    print(f"节点 {len(live)}（废止 {len(g.nodes) - len(live)}）："
          + "  ".join(f"{ICON[k]} {cnt[k]}" for k in ("mastered", "taught", "unlockable", "locked")))
    for e in g.errors:
        print("ERROR  ", e)
    for w in g.warnings:
        print("WARN   ", w)
    if not g.errors:
        print("OK  图谱一致。" + ("" if not g.warnings else f"（{len(g.warnings)} 条警告）"))
    return 1 if g.errors else 0


def cmd_next(g: Graph, a) -> int:
    validate(g)
    if g.errors:
        print("图谱有错误，先修复（graph.py check）。", file=sys.stderr)
        for e in g.errors:
            print("ERROR", e, file=sys.stderr)
        return 1
    rows = rank(g)
    if a.json:
        print(json.dumps(rows[: a.n], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("没有可学节点：全部完成，或图谱需要扩展。")
        return 0
    for r in g.retro_reasons():
        print(f"建议先做 retro（topic-graph 第 I 节）：{r}")
    top = rows[0]
    print(f"推荐：{top['id']}  {top['title']}   [{'复测' if top['kind']=='retest' else '新学'}]")
    print(f"  理由：{top['why']}")
    print_routes(g, top["id"], indent="  ")
    rest = rows[1 : a.n]
    if rest:
        print("其余候选：")
        for r in rest:
            tag = ("复测·" if r["kind"] == "retest" else "") + ("主线" if r["main"] else "支线")
            print(f"  {r['id']:<4} [{tag}{'·目标路径' if r['on_goal'] else ''}] {r['title']}  (后代 {r['descendants']})")
    side = next((r for r in rows if not r["main"] and r["kind"] == "learn"), None)
    if side and side is not top:
        print(f"换口味：{side['id']}  {side['title']}")
    rev = g.review_due()
    if rev:
        i, age, desc = rev[0]
        print(f"复习：{i}  {g.nodes[i].title}（{age} 天前验证，{desc} 个后续节点依赖它）——课前一道题；对了 set mastered 刷新日期，错了降为 taught")
    return 0


def print_routes(g: Graph, nid: str, indent: str = "") -> None:
    routes = g.goal_routes(nid)
    if not routes:
        print(f"{indent}通往目标：无（不在任何目标路径上）\n")
        return
    print(f"{indent}通往目标（学它有什么用）：")
    for goal, chain in routes:
        print(f"{indent}  {goal.get('id')}「{goal.get('title', '')}」：" + " → ".join(chain))
        if goal.get("question"):
            print(f"{indent}    终点要能回答：{goal['question']}")
    print()


def cmd_preflight(g: Graph, a) -> int:
    validate(g)
    if a.id not in g.nodes:
        sys.exit(f"没有节点 {a.id}")
    n = g.nodes[a.id]
    d = g.derived(a.id)
    if n.status == "retired":
        sys.exit(f"{a.id} 已废止，并入 {n.merged_into}")
    if n.status == "mastered":
        print(f"{a.id} 已是 ✅，无需再教（除非要复习）。")
    elif not g.prereqs_ok(a.id):
        miss = [p for p in n.prereqs if g.nodes[p].status != "mastered"]
        print(f"✗ 不能讲 {a.id}：前置未满足 → " + ", ".join(f"{p}({ICON[g.derived(p)]})" for p in miss))
        print("  应先学上述节点，或用 graph.py add 把缺口拆成新节点。")
        return 1
    print(f"✓ {a.id} 可以讲  [{ICON[d]}]  {n.title}\n")
    print_routes(g, a.id)
    anc = sorted(g.ancestors(a.id), key=lambda x: (g.nodes[x].group, g.nodes[x].num))
    print("允许引用的概念 = 本节点 + 全部 ✅ 节点；其余一律不可用于讲解、例子、题目答案路径。")
    print("其中本节点的祖先（讲解最可能依赖）：")
    for p in anc:
        pn = g.nodes[p]
        flag = f" ⚠️ {pn.caveat}" if pn.caveat else ""
        print(f"  {p:<4} {pn.title}{flag}")
    others = sorted((i for i, x in g.live().items() if x.status == "mastered" and i not in anc and i != a.id),
                    key=lambda x: (g.nodes[x].group, g.nodes[x].num))
    if others:
        print("其他 ✅（无依赖关系，也可引用）：" + ", ".join(others))
    weak = [i for i, x in g.live().items() if x.status == "mastered" and x.caveat]
    if weak:
        print("带限定的 ✅（引用时须守住限定）：" + ", ".join(weak))
    print("\n—— 直接前置摘要（教学须与之一致）——")
    for p in n.prereqs:
        pn = g.nodes[p]
        print(f"\n### {p}  {pn.title}" + (f"   ⚠️ {pn.caveat}" if pn.caveat else ""))
        print(pn.body or "(无摘要)")
    print("\n—— 本节点已有内容 ——")
    print(n.body or "(尚无)")
    gf = g.root / "nodes" / n.group / "_group.md"
    if gf.exists():
        _, gb = parse_file(gf)
        if gb:
            print(f"\n—— 所属组 {n.group} 的说明 ——\n{gb}")
    return 0


def cmd_show(g: Graph, a) -> int:
    if a.id not in g.nodes:
        sys.exit(f"没有节点 {a.id}")
    n = g.nodes[a.id]
    print(f"{a.id}  {ICON[g.derived(a.id)]}  {n.title}")
    print("前置：" + (", ".join(f"{p}{ICON[g.derived(p)]}" for p in n.prereqs) or "—"))
    kids = sorted(g.children().get(a.id, []))
    print("被依赖：" + (", ".join(kids) or "—"))
    if n.caveat:
        print("限定：" + n.caveat)
    print("\n" + (n.body or "(无正文)"))
    return 0


def cmd_set(g: Graph, a) -> int:
    validate(g)
    if a.id not in g.nodes:
        sys.exit(f"没有节点 {a.id}")
    if a.status not in ("new", "taught", "mastered"):
        sys.exit("STATUS 应为 new|taught|mastered（废止请用 retire）")
    n = g.nodes[a.id]
    if a.status == "mastered" and not g.prereqs_ok(a.id):
        miss = [p for p in n.prereqs if g.nodes[p].status != "mastered"]
        sys.exit(f"拒绝：{a.id} 的前置 {', '.join(miss)} 不是 mastered；先修好前置或改标 taught。")
    old = n.status
    set_fm_field(n.path, "status", q(a.status))
    set_fm_field(n.path, "updated", dt.date.today().isoformat())
    set_fm_field(n.path, "verified", dt.date.today().isoformat() if a.status == "mastered" else None)
    if a.caveat is not None:
        set_fm_field(n.path, "caveat", q(a.caveat) if a.caveat else None)
    elif a.status != "mastered":
        set_fm_field(n.path, "caveat", None)
    with (g.root / "log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), "id": a.id,
                            "from": old, "to": a.status, "caveat": a.caveat or ""}, ensure_ascii=False) + "\n")
    print(f"{a.id}: {old} → {a.status}")
    if a.status in ("mastered", "taught") and not n.body.strip():
        print(f"提醒：{a.id} 还没有摘要，请把本节点教过的内容写进 {n.path.relative_to(g.root)}。")
    if old == "mastered" and a.status != "mastered":
        lost = sorted(d for d in g.descendants(a.id) if g.nodes[d].status == "mastered")
        if lost:
            print(f"警告：以下 ✅ 节点依赖 {a.id}，现在状态不再成立：{', '.join(lost)}（需复核）")
    return 0


def cmd_add(g: Graph, a) -> int:
    validate(g)
    m = ID_RE.match(a.id)
    if not m:
        sys.exit("ID 格式应为 大写字母+数字，如 T8")
    if a.id in g.nodes:
        sys.exit(f"{a.id} 已存在（ID 永不复用）")
    prereqs = [p for p in (a.prereq or "").split(",") if p]
    targets = [p for p in (a.target or "").split(",") if p]
    for p in prereqs + targets:
        if p not in g.nodes:
            sys.exit(f"节点 {p} 不存在")
        if g.nodes[p].status == "retired":
            sys.exit(f"节点 {p} 已废止")
    grp = m.group(1)
    gdir = g.root / "nodes" / grp
    if not gdir.exists():
        if not a.group_title:
            sys.exit(f"新组 {grp}：请用 --group-title 给出组名")
        gdir.mkdir(parents=True)
        (gdir / "_group.md").write_text(f"---\ntitle: {q(a.group_title)}\n---\n", encoding="utf-8")
    text = (f"---\nid: {q(a.id)}\ntitle: {q(a.title)}\n"
            f"prereqs: {json.dumps(prereqs)}\n"
            + (f"targets: {json.dumps(targets)}\n" if targets else "")
            + f"status: \"new\"\nupdated: {dt.date.today().isoformat()}\n---\n")
    (gdir / f"{a.id}.md").write_text(text, encoding="utf-8")
    g2 = load(g.root)
    validate(g2)
    if g2.errors:
        (gdir / f"{a.id}.md").unlink()
        sys.exit("新增后图谱出错，已回滚：\n" + "\n".join(g2.errors))
    print(f"已创建 {gdir / (a.id + '.md')}  状态 {ICON[g2.derived(a.id)]}")
    return 0


def cmd_retire(g: Graph, a) -> int:
    validate(g)
    if a.id not in g.nodes or a.into not in g.nodes:
        sys.exit("节点不存在")
    n = g.nodes[a.id]
    users = sorted(i for i, x in g.live().items() if a.id in x.prereqs)
    if users:
        sys.exit(f"仍有节点以 {a.id} 为前置：{', '.join(users)}；先把它们改指向 {a.into}。")
    set_fm_field(n.path, "status", q("retired"))
    set_fm_field(n.path, "merged_into", q(a.into))
    set_fm_field(n.path, "updated", dt.date.today().isoformat())
    print(f"{a.id} 已废止，并入 {a.into}（ID 永不复用）")
    return 0


def render_state(g: Graph) -> str:
    live = g.live()
    groups = sorted({n.group for n in live.values()},
                    key=lambda x: (g.config.get("track", {}).get("main", []).index(x)
                                   if x in g.config.get("track", {}).get("main", []) else 99, x))
    out = [f"# {g.config.get('title', '学习进度')} — 当前状态", "",
           "> **自动生成**（`graph.py sync`），不要手改。事实来源是 `nodes/` 下各节点文件。", ""]
    cnt = defaultdict(int)
    for i in live:
        cnt[g.derived(i)] += 1
    out.append(f"**{len(live)} 个节点**：" + "　".join(f"{ICON[k]} {cnt[k]}" for k in ("mastered", "taught", "unlockable", "locked")))
    out.append("")
    for goal in g.config.get("goal", []):
        tg = goal.get("targets", [])
        need = set()
        for t in tg:
            need |= {t} | g.ancestors(t)
        done = sum(1 for x in need if g.nodes[x].status == "mastered")
        out.append(f"- 目标 {goal.get('id')}「{goal.get('title','')}」：路径上 {done}/{len(need)} 个节点已 ✅（终点 {', '.join(tg)}）")
    out += ["", "## 下一步", ""]
    for r in g.retro_reasons():
        out.append(f"- **建议先做 retro**：{r}")
    rev = g.review_due()
    if rev:
        out.append("- 待复习的 ✅（久未验证、被依赖）：" + "、".join(f"{i}（{age} 天）" for i, age, _ in rev[:5]))
    rows = rank(g)
    if rows:
        top = rows[0]
        out.append(f"**推荐 {top['id']}** {top['title']}（{'复测' if top['kind']=='retest' else '新学'}）——{top['why']}")
        out += ["", "| 候选 | 类型 | 后代数 | 立即解锁 | 标题 |", "|---|---|---|---|---|"]
        for r in rows[:8]:
            tag = ("复测·" if r["kind"] == "retest" else "") + ("主线" if r["main"] else "支线") + ("·目标路径" if r["on_goal"] else "")
            out.append(f"| {r['id']} | {tag} | {r['descendants']} | {', '.join(r['unlocks_now']) or '—'} | {r['title']} |")
    else:
        out.append("无可学节点。")
    out += ["", "## 组间依赖", "", "```mermaid", "graph LR"]
    edges = set()
    for n in live.values():
        for p in n.prereqs:
            if p in g.nodes and g.nodes[p].group != n.group:
                edges.add((g.nodes[p].group, n.group))
    for grp in groups:
        members = [n for n in live.values() if n.group == grp]
        done = sum(1 for n in members if n.status == "mastered")
        out.append(f'  {grp}["{grp} {g.group_titles.get(grp, "")} · {done}/{len(members)}"]')
    for a_, b_ in sorted(edges):
        out.append(f"  {a_} --> {b_}")
    out += ["```", "", "## 全部节点", ""]
    for grp in groups:
        out += [f"### {grp} — {g.group_titles.get(grp, '')}", "", "| ID | 状态 | 节点 | 前置 |", "|---|---|---|---|"]
        for n in sorted((x for x in live.values() if x.group == grp), key=lambda x: x.num):
            st = ICON[g.derived(n.id)] + (" ⚠️" if n.caveat else "")
            out.append(f"| {n.id} | {st} | {n.title} | {', '.join(n.prereqs) or '—'} |")
        out.append("")
    return "\n".join(out)


def cmd_sync(g: Graph, a) -> int:
    rc = cmd_check(g, a)
    if rc:
        return rc
    (g.root / "STATE.md").write_text(render_state(g), encoding="utf-8")
    print("已更新 STATE.md")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="含 topic.yaml 的专题目录（默认从当前目录向上找）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("next"); p.add_argument("-n", type=int, default=5); p.add_argument("--json", action="store_true")
    p = sub.add_parser("preflight"); p.add_argument("id")
    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("status"); p.add_argument("--caveat")
    p = sub.add_parser("add"); p.add_argument("id"); p.add_argument("--title", required=True)
    p.add_argument("--prereq", default=""); p.add_argument("--target", default=""); p.add_argument("--group-title")
    p = sub.add_parser("retire"); p.add_argument("id"); p.add_argument("--into", required=True)
    sub.add_parser("sync")
    a = ap.parse_args()
    g = load(find_root(a.root))
    return {"check": cmd_check, "next": cmd_next, "preflight": cmd_preflight, "show": cmd_show,
            "set": cmd_set, "add": cmd_add, "retire": cmd_retire, "sync": cmd_sync}[a.cmd](g, a)


if __name__ == "__main__":
    sys.exit(main())
